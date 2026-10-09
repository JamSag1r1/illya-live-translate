#!/usr/bin/env python3
"""
live_translate.py — 实时语音翻译（系统声音 → 中文）

原理: WASAPI loopback 抓「扬声器正在播放的声音」→ 能量分段 → faster-whisper 本地转写
      → DeepSeek 翻译 → 控制台 + 本地网页实时显示。

用法:
    .venv\\Scripts\\python.exe live_translate.py                 # 默认英→中, small 模型
    .venv\\Scripts\\python.exe live_translate.py --src ja        # 日→中
    .venv\\Scripts\\python.exe live_translate.py --model-size medium
    .venv\\Scripts\\python.exe live_translate.py --list-devices  # 看能抓哪些设备
    .venv\\Scripts\\python.exe live_translate.py --no-translate  # 只出原文
    .venv\\Scripts\\python.exe live_translate.py --no-web        # 不开网页
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")   # 国内直连 huggingface 不通

import numpy as np

HERE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
    else Path(__file__).resolve().parent          # 打包成 exe 后按 exe 所在目录找 models/logs


def _find_dir(name: str) -> Path:
    """打包后 exe 可能在 dist 子目录里，models/ 往往在上一层——往上找几级"""
    for base in (HERE, *list(HERE.parents)[:3]):
        p = base / name
        if p.is_dir():
            return p
    return HERE / name


MODELS_DIR = _find_dir("models")
LOGS_DIR = _find_dir("logs")
SR = 16000                    # whisper 采样率
VAD_CHUNK = 1024              # loopback 每次读取的帧数

# 预设的术语提示：用「一整句包含术语的话」比只列单词准得多（尤其日语同音词）
PRESETS = {
    "chem-ja": ("化学の配信です。ラジカル配位子が二つのランタノイドイオンを架橋する話と、"
                "ジスプロシウム中心の異方性、単分子磁石についてです。"),
    "chem-en": ("A chemistry livestream about radical ligands bridging two lanthanide ions, "
                "the anisotropy of the dysprosium center, and single-molecule magnets."),
}


# ────────────────────────────── 音频工具 ──────────────────────────────
def lowpass_fir(cutoff_hz: float, fs: int, taps: int = 33) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff_hz / fs * n) * np.hamming(taps)
    return (h / h.sum()).astype(np.float32)


def to_16k_mono(int16_stereo: np.ndarray, src_rate: int) -> np.ndarray:
    """int16 (n, ch) → float32 mono 16k"""
    a = int16_stereo.astype(np.float32) / 32768.0
    if a.ndim > 1:
        a = a.mean(axis=1)
    if src_rate != SR:                                   # 抗混叠 + 线性重采样
        h = lowpass_fir(min(7000.0, SR * 0.45), src_rate)
        a = np.convolve(a, h, mode="same")
        n_out = int(len(a) * SR / src_rate)
        a = np.interp(np.arange(n_out) / SR, np.arange(len(a)) / src_rate, a)
    return a.astype(np.float32)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def enable_cuda_dlls() -> int:
    """把 pip 装的 nvidia-*-cu12 里的 bin 目录加进 DLL 搜索路径。
    ctranslate2 用 CUDA 时找不到 cublas64_12.dll / cudnn_ops64_9.dll 就是这个原因。

    Windows 专属（os.add_dll_directory）；macOS/Linux 上直接返回 0 不做事。
    """
    if os.name != "nt":
        return 0
    import glob
    import sysconfig
    roots = []
    for r in (getattr(sys, "_MEIPASS", None), HERE, Path(sysconfig.get_paths()["purelib"])):
        if r:
            roots.append(str(r))
    n = 0
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)          # py3.8+ 需要显式加
            except OSError:
                continue
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            n += 1
    return n


def looks_like_hallucination(text: str, seg_seconds: float) -> tuple[bool, str]:
    """Whisper 在噪声/片段边界上会循环吐同一句，或凭空造出一大段。返回 (是否丢掉, 原因)。
    实测的真样本（必须拦住）：'今天 我們會討論如何 彩繩子能夠 成功的 敵人的 人類的 人類的 …'×40
    """
    if not text:
        return True, "空"
    parts = text.split()
    if len(parts) > 8 and len(set(parts)) <= max(3, len(parts) // 6):
        return True, f"词表重复过高（{len(set(parts))}/{len(parts)}）"
    rep = max((parts.count(p) for p in set(parts)), default=0)
    if rep > 8:
        return True, f"单个词重复 {rep} 次"
    limit = 14 * max(seg_seconds, 0.5) + 40        # 中文语速约 5 字/秒，留足余量
    if len(text) > limit:
        return True, f"字数 {len(text)} 远超音频时长 {seg_seconds:.1f}s 的上限 {limit:.0f}"
    return False, ""


# ────────────────────────────── 抓声音 ──────────────────────────────
class LoopbackCapture:
    """抓系统正在播放的音频（WASAPI loopback）。device=None → 当前默认输出设备"""

    def __init__(self, device_index: int | None = None, verbose: bool = True):
        import pyaudiowpatch as pyaudio
        self._pa = pyaudio
        self.p = pyaudio.PyAudio()
        wasapi = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = self.p.get_device_info_by_index(wasapi["defaultOutputDevice"])

        target = None
        if device_index is not None:
            target = self.p.get_device_info_by_index(device_index)
        else:
            if default_out.get("isLoopbackDevice"):
                target = default_out
            else:
                for lb in self.p.get_loopback_device_info_generator():
                    if default_out["name"] in lb["name"]:
                        target = lb
                        break
        if target is None:
            raise RuntimeError("找不到当前默认输出设备的 loopback（换个 --loopback 试试）")

        self.info = target
        self.rate = int(target["defaultSampleRate"])
        self.channels = min(2, int(target["maxInputChannels"]))
        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._stream = None
        self._paused = False
        if verbose:
            print(f"[capture] {target['name']}  {self.rate} Hz / {self.channels} ch")

    def _cb(self, in_data, frame_count, time_info, status):
        if not self._paused:
            arr = np.frombuffer(in_data, dtype=np.int16).reshape(-1, self.channels)
            try:
                self.q.put_nowait(arr)
            except queue.Full:
                pass
        return (None, self._pa.paContinue)

    def start(self):
        self._stream = self.p.open(
            format=self._pa.paInt16, channels=self.channels, rate=self.rate,
            input=True, input_device_index=self.info["index"],
            frames_per_buffer=VAD_CHUNK, stream_callback=self._cb)
        self._stream.start_stream()

    def set_paused(self, flag: bool):
        self._paused = flag

    def stop(self):
        try:
            if self._stream:
                self._stream.stop_stream(); self._stream.close()
        finally:
            self.p.terminate()


def list_devices():
    import pyaudiowpatch as pyaudio
    p = pyaudio.PyAudio()
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    dflt = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    print(f"默认输出: {dflt['name']}")
    print("可抓的 loopback 设备:")
    for lb in p.get_loopback_device_info_generator():
        mark = "  <- 默认" if dflt["name"] in lb["name"] else ""
        print(f"  [{lb['index']:>3}] {lb['name']}  {int(lb['defaultSampleRate'])} Hz{mark}")
    p.terminate()


# ────────────────────────────── 翻译 ──────────────────────────────
class Translator:
    """DeepSeek 翻译（关掉思考模式，约 1s/段）。key 从 Hermes 的 .env 取"""

    SYS = ("你是同声传译。把用户给的直播口语翻成自然的中文（口语，不要书面腔、不要加戏）。"
           "只输出译文，不要解释、不要引号。上文的原文/译文只用来保持术语和人称一致。")

    def __init__(self, enabled=True, model="deepseek-flash", timeout=20):
        self.enabled = enabled
        self.model = model
        self.timeout = timeout
        self.key = self._read_key()
        self.history: deque = deque(maxlen=3)
        if enabled and not self.key:
            print("[translate] 没找到 DEEPSEEK_API_KEY，退化为只显示原文")
            self.enabled = False

    @staticmethod
    def _read_key():
        """Key 的来源，按优先级：环境变量 → 程序目录的 api_key.txt → Hermes 的 .env
        （打包带到别的电脑上，就在界面里填，或者放个 api_key.txt）"""
        env = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        if env:
            return env
        for path in (HERE / "api_key.txt",
                     Path(os.environ.get("HERMES_HOME", "")) / ".env",
                     Path.home() / "AppData/Local/hermes/.env",
                     HERE / ".env"):
            try:
                if not path.is_file():
                    continue
                txt = path.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'DEEPSEEK_API_KEY\s*=\s*(.+)', txt)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
                if path.name == "api_key.txt":
                    k = txt.strip()
                    if k:
                        return k
            except OSError:
                pass
        return None

    def translate(self, text: str) -> tuple[str, float]:
        if not self.enabled:
            return "", 0.0
        import requests
        msgs = [{"role": "system", "content": self.SYS}]
        for src, tgt in self.history:
            msgs.append({"role": "user", "content": src})
            msgs.append({"role": "assistant", "content": tgt})
        msgs.append({"role": "user", "content": text})
        body = {"model": self.model, "messages": msgs, "temperature": 0.2,
                "max_tokens": 512, "thinking": {"type": "disabled"}}
        t0 = time.time()
        for attempt in (1, 2):
            try:
                r = requests.post("https://api.deepseek.com/chat/completions", json=body,
                                  headers={"Authorization": f"Bearer {self.key}"},
                                  timeout=self.timeout)
                r.raise_for_status()
                out = (r.json()["choices"][0]["message"]["content"] or "").strip()
                self.history.append((text, out))
                return out, time.time() - t0
            except Exception as e:
                if attempt == 2:
                    return f"[翻译失败: {type(e).__name__}]", time.time() - t0
                time.sleep(0.5)
        return "", 0.0


class LocalTranslator:
    """本地翻译：CTranslate2 跑的 NLLB（随包自带的那份）。
    离线、不花钱、不外发；质量明显不如云端 LLM（口语/术语尤其）。"""

    def __init__(self, model_dir, device: str = "auto", compute_type: str | None = None,
                 threads: int = 8):
        import ctranslate2
        import sentencepiece as spm
        md = Path(model_dir)
        if not md.is_dir():
            raise RuntimeError(f"本地翻译模型不存在：{md}")
        self.sp = spm.SentencePieceProcessor(model_file=str(md / "sentencepiece.bpe.model"))
        if device == "auto":
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        if device == "cuda":
            enable_cuda_dlls()
        ct = compute_type or ("int8_float16" if device == "cuda" else "int8")
        self.tr = ctranslate2.Translator(str(md), device=device, compute_type=ct,
                                         inter_threads=1, intra_threads=threads)
        print(f"[mt] 本地翻译就绪：{md.name} ({device}/{ct})")

    @staticmethod
    def _src_lang(text: str) -> str:
        if re.search(r"[\u3040-\u30ff]", text):
            return "jpn_Jpan"
        if re.search(r"[\uac00-\ud7af]", text):
            return "kor_Hang"
        if re.search(r"[A-Za-z]", text):
            return "eng_Latn"
        return "zho_Hans"

    def translate(self, text: str) -> tuple[str, float]:
        t0 = time.time()
        if not text.strip():
            return "", 0.0
        # 语种 token 要整块贴在句首；句尾必须补 </s>（CT2 这份配置 add_source_eos=False，
        # 少了它模型只会吐语种 token 或复读“▁”——实测踩过）
        toks = [self._src_lang(text)] + self.sp.encode(text, out_type=str) + ["</s>"]
        res = self.tr.translate_batch([toks], target_prefix=[["zho_Hans"]], beam_size=1,
                                      max_batch_size=1)
        out = list(res[0].hypotheses[0])
        if out and out[0] == "zho_Hans":
            out = out[1:]
        return self.sp.decode(out), time.time() - t0


class OllamaTranslator:
    """本地大模型翻译（走本机 Ollama 的 HTTP 接口）：质量远好于 NLLB，但需要先装 Ollama 并拉好模型。"""

    SYS = "你是同声传译。把用户给的直播口语翻成自然的中文口语，只输出译文，不要解释。"

    def __init__(self, model: str = "qwen3:4b", host: str = "http://127.0.0.1:11434",
                 timeout: float = 60.0):
        import requests
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout
        r = requests.get(self.host + "/api/tags", timeout=5)
        r.raise_for_status()
        names = [m.get("name", "") for m in (r.json().get("models") or [])]
        if not any(n == model or n.startswith(model.split(":")[0]) for n in names):
            raise RuntimeError(f"Ollama 里还没有模型 {model}（先 `ollama pull {model}`）")
        print(f"[mt] 本地大模型就绪：{model} @ {self.host}")

    def translate(self, text: str) -> tuple[str, float]:
        import requests
        t0 = time.time()
        if not text.strip():
            return "", 0.0
        body = {"model": self.model, "stream": False, "options": {"temperature": 0.2},
                "messages": [{"role": "system", "content": self.SYS},
                             {"role": "user", "content": text}]}
        try:
            r = requests.post(self.host + "/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
            return (r.json().get("message", {}).get("content") or "").strip(), time.time() - t0
        except Exception as e:
            return f"[本地翻译失败: {type(e).__name__}]", time.time() - t0


# ────────────────────────────── 输出 ──────────────────────────────
class Sink:
    """控制台 + jsonl + 网页"""

    def __init__(self, jsonl: Path | None, web: bool = True, web_port: int = 8777):
        self.lines: list[dict] = []
        self.lock = threading.Lock()
        self.jsonl = jsonl
        if jsonl:
            jsonl.parent.mkdir(parents=True, exist_ok=True)
        if web:
            try:
                self._start_web(web_port)
            except OSError as e:
                print(f"[web] 起不来（端口占用?）: {e}")

    def add(self, src: str, tgt: str, t_start: float, asr_ms: int, tr_ms: int):
        rec = {"t": round(t_start, 1), "time": datetime.now().strftime("%H:%M:%S"),
               "src": src, "tgt": tgt, "asr_ms": asr_ms, "tr_ms": tr_ms}
        with self.lock:
            self.lines.append(rec)
        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{stamp}] {src}")
        if tgt:
            print(f"          → {tgt}")
        print(f"          ({asr_ms}ms asr / {tr_ms}ms translate)", flush=True)
        if self.jsonl:
            with open(self.jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _start_web(self, port):
        import socket
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        sink = self
        probe = socket.socket()
        busy = probe.connect_ex(("127.0.0.1", port)) == 0   # Windows 上 SO_REUSEADDR 允许重复绑定，
        probe.close()                                      # 不先探一下的话字幕页会连到旧实例
        if busy:
            print(f"[web] 警告：{port} 端口已被占用（多半有旧实例没退干净），字幕页会连到旧进程！"
                  f" 先杀旧 python，或换 --port {port + 1}")

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/api/lines"):
                    m = re.search(r"since=(\d+)", self.path)
                    since = int(m.group(1)) if m else 0
                    with sink.lock:
                        data = sink.lines[since:]
                        total = len(sink.lines)
                    body = json.dumps({"total": total, "lines": data}, ensure_ascii=False).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers(); self.wfile.write(body)
                else:
                    body = PAGE.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers(); self.wfile.write(body)

        srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"[web] 字幕页: http://127.0.0.1:{port}")


PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>实时翻译</title><style>
:root{color-scheme:dark}
body{margin:0;background:#0f1115;color:#e8e8ea;font:16px/1.6 "Microsoft YaHei",system-ui,sans-serif}
#h{position:sticky;top:0;background:#0f1115ee;padding:10px 20px;border-bottom:1px solid #262a33;
   font-size:13px;color:#8b93a5;display:flex;gap:18px;align-items:center}
#h b{color:#6ee7b7}
.wrap{padding:16px 20px 60vh}
.p{margin:0 0 22px;padding-left:14px;border-left:3px solid #2b3140}
.src{font-size:14px;color:#8b93a5;margin-bottom:4px}
.tgt{font-size:var(--fs,22px);line-height:1.5;color:#f2f4f8}
.err{color:#fca5a5}
</style></head><body>
<div id="h"><span>实时翻译（系统声音 → 中文）</span><span>已译 <b id="n">0</b> 段</span>
<span id="s">连接中…</span>
<span style="margin-left:auto;color:#8b93a5">
  <a href="#" id="fsDown" style="color:#8b93a5;text-decoration:none;padding:0 6px">A−</a>
  <a href="#" id="fsUp" style="color:#8b93a5;text-decoration:none;padding:0 6px">A＋</a>
  <label><input type="checkbox" id="showSrc" checked> 显示原文</label></span></div>
<div class="wrap" id="w"></div>
<script>
let since=0,atBottom=true;
addEventListener('scroll',()=>{atBottom=innerHeight+scrollY>=document.body.scrollHeight-80});
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function tick(){
 try{
  const r=await fetch('/api/lines?since='+since);const d=await r.json();
  if(d.lines.length){
   for(const l of d.lines){
    const el=document.createElement('div');el.className='p';
    el.innerHTML='<div class="src">'+esc(l.src)+'</div><div class="tgt'+(l.tgt&&l.tgt.startsWith('[')?' err':'')+'">'+(esc(l.tgt)||'…')+'</div>';
    w.appendChild(el);
   }
   since=d.total;document.getElementById('n').textContent=d.total;
   if(atBottom)scrollTo(0,document.body.scrollHeight);
  }
  document.getElementById('s').textContent='已连接';
 }catch(e){document.getElementById('s').textContent='等待中…';}
}
document.getElementById('showSrc').onchange=e=>{
 document.querySelectorAll('.src').forEach(x=>x.style.display=e.target.checked?'':'none');};
// 字号：A− / A＋，存 localStorage
let fs=parseInt(localStorage.getItem('fs')||'22');
function applyFs(){fs=Math.max(12,Math.min(64,fs));document.documentElement.style.setProperty('--fs',fs+'px');
 localStorage.setItem('fs',fs);}
applyFs();
document.getElementById('fsUp').onclick=e=>{e.preventDefault();fs+=3;applyFs();};
document.getElementById('fsDown').onclick=e=>{e.preventDefault();fs-=3;applyFs();};
setInterval(tick,1000);tick();
</script></body></html>"""


# ────────────────────────────── 主流程 ──────────────────────────────
def resolve_model(size_or_path: str) -> str:
    p = Path(size_or_path)
    if p.is_dir():
        return str(p)
    local = MODELS_DIR / f"faster-whisper-{size_or_path}"
    if local.is_dir() and (local / "model.bin").is_file():
        return str(local)
    # huggingface 在这台机器上不可达，走魔搭（见 tools/fetch_model.py）
    try:
        import fetch_model                     # 打包成 exe 时按普通模块找（pyinstaller --paths tools）
    except ImportError:
        sys.path.insert(0, str(HERE / "tools"))
        import fetch_model
    return str(fetch_model.fetch(size_or_path, dest=MODELS_DIR))


def main():
    ap = argparse.ArgumentParser(description="系统声音实时翻译")
    ap.add_argument("--model-size", default="small", help="small / medium / large-v3 或本地目录")
    ap.add_argument("--src", default="en", help="源语言 en/ja/ko/…，auto=自动")
    ap.add_argument("--loopback", type=int, default=None,
                    help="loopback 设备号（默认跟随系统默认输出；--list-devices 看编号）")
    ap.add_argument("--url", default=None,
                    help="改为直接抓这个网址的音频（B站直播间链接/房间号，或 ffmpeg 能开的媒体地址）："
                         "不经过扬声器，你放别的音乐也不会被抓进去")
    ap.add_argument("--source", default="loopback", choices=["loopback", "url"],
                    help="声音从哪来：loopback=系统正在播放的声音（默认）/ url=按网址直抓")
    ap.add_argument("--max-seg", type=float, default=6.0, help="一段最长秒数（到点强切）")
    ap.add_argument("--min-seg", type=float, default=0.8, help="太短丢弃")
    ap.add_argument("--merge-below", type=float, default=1.6, metavar="SEC",
                    help="短于这个秒数的句子先攒着，跟下一句合并再转写（上下文更足、更准；0=关）")
    ap.add_argument("--silence", type=float, default=0.45, help="静音多久算一句结束")
    ap.add_argument("--vad", type=float, default=0.006, help="音量阈值（噪声自适应，这是下限）")
    ap.add_argument("--translator", default="api", choices=["api", "local", "ollama"],
                    help="api=云端 API / local=本地 NLLB（CT2）/ ollama=本机 Ollama 大模型")
    ap.add_argument("--local-mt", default=None, metavar="DIR",
                    help="本地翻译模型目录（含 model.bin 和 sentencepiece.bpe.model）")
    ap.add_argument("--ollama-model", default="qwen3:4b", help="Ollama 模型名（配合 --translator ollama）")
    ap.add_argument("--no-translate", action="store_true", help="只转写不翻译")
    ap.add_argument("--prompt", default=None,
                    help="术语提示，帮 whisper 认专业词，例如 --prompt \"lanthanide, anisotropy, dysprosium, radical ligand\"")
    ap.add_argument("--preset", default=None, choices=sorted(PRESETS),
                    help="现成的术语提示：" + " / ".join(sorted(PRESETS)))
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--save-audio", default=None, metavar="DIR",
                    help="把每段音频存成 wav（排查漏句/幻觉用）")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--threads", type=int, default=8, help="whisper CPU 线程数")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"],
                    help="auto=有 N 卡就用 GPU（float16，快 10 倍以上）")
    ap.add_argument("--compute-type", default=None, help="覆盖精度，如 int8_float16 / float16")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--input-device", default=None, metavar="SPEC",
                    help="从音频输入设备抓音（跨平台）。macOS: \":<序号>\"（BlackHole）; "
                         "Windows: \"audio=<设备名>\"; Linux: \"default\"")
    ap.add_argument("--input-format", default=None, metavar="FMT",
                    help="ffmpeg 输入格式：默认 macOS=avfoundation / Windows=dshow / Linux=pulse")
    ap.add_argument("--list-input-devices", action="store_true",
                    help="列出能抓的音频输入设备（和该填的参数）")
    ap.add_argument("--level", action="store_true", help="只看音量（调阈值用）")
    ap.add_argument("--stop-file", default=None, metavar="PATH",
                    help="这个文件一出现就优雅退出（GUI 的「停止」用的就是它，比 CTRL_BREAK 干净）")
    ap.add_argument("--for", dest="run_for", type=float, default=0,
                    help="跑够这么多秒自动停（测试用，默认一直跑）")
    args = ap.parse_args()

    if args.list_input_devices:
        from stream_source import list_input_devices
        print(list_input_devices(args.input_format))
        return
    if args.list_devices:
        list_devices(); return
    if args.level:
        cap = LoopbackCapture(args.loopback)
        cap.start()
        print("显示 5 秒音量，Ctrl+C 结束。--vad 调到 0.5~1 倍于安静时的读数")
        t0 = time.time()
        while time.time() - t0 < 5:
            try:
                x = to_16k_mono(cap.q.get(timeout=1), cap.rate)
            except queue.Empty:
                continue
            bars = int(min(60, rms(x) * 400))
            print("  " + "#" * bars, f"rms={rms(x):.4f}")
        cap.stop(); return

    from faster_whisper import WhisperModel

    model_path = resolve_model(args.model_size)
    device = args.device
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    if device == "cuda":
        print(f"[cuda] 注入 {enable_cuda_dlls()} 个 nvidia DLL 目录")
    compute = args.compute_type or ("float16" if device == "cuda" else "int8")
    t0 = time.time()
    print(f"[model] 加载 {Path(model_path).name} ({device}/{compute}) …")
    model = WhisperModel(model_path, device=device, compute_type=compute,
                         cpu_threads=args.threads, num_workers=1)
    print(f"[model] 就绪 ({time.time()-t0:.1f}s)")

    logs = LOGS_DIR / f"live_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    sink = Sink(logs, web=not args.no_web, web_port=args.port)
    if args.no_translate:
        translator = Translator(enabled=False)
    elif args.translator == "local":
        translator = LocalTranslator(args.local_mt or (MODELS_DIR / "nllb-200-distilled-600M-ct2"),
                                     device=device, threads=args.threads)
    elif args.translator == "ollama":
        translator = OllamaTranslator(args.ollama_model)
    else:
        translator = Translator(enabled=True)

    cap = None
    if args.input_device:
        from stream_source import DeviceCapture   # 从音频输入设备抓（macOS: BlackHole / Windows: dshow）
        try:
            cap = DeviceCapture(args.input_device, args.input_format)
        except Exception as e:
            print(f"[x] 打开音频设备失败：{e}")
            return
    elif not (args.url or args.source == "url"):
        if os.name != "nt":
            print("[x] 这台系统没有 WASAPI 环回可抓：请用 --url 抓直播间，"
                  "或用 --input-device 指定录音设备（macOS 先装 BlackHole，"
                  "再用 --list-input-devices 看序号）")
            return
        cap = LoopbackCapture(args.loopback)
    if cap is None:
        if not args.url:
            print("[x] --source url 要同时给 --url，例如 --url https://live.bilibili.com/22105860")
            return
        from stream_source import StreamCapture     # 按网址直抓，不碰扬声器
        try:
            cap = StreamCapture(args.url)
        except Exception as e:                      # 网络/DNS、房间没开播…都别甩 traceback
            print(f"[x] 抓流失败：{e}")
            return
    cap.start()

    asr_q: queue.Queue = queue.Queue()
    tr_q: queue.Queue = queue.Queue()
    stats = {"asr": [], "tr": [], "audio": 0.0, "segs": 0}
    ctx = deque(maxlen=3)          # 给 whisper 的 initial_prompt
    stop_flag = threading.Event()

    counts = {"n": 0}

    def asr_worker():
        while not stop_flag.is_set():
            try:
                seg, t_start = asr_q.get(timeout=0.3)
            except queue.Empty:
                continue
            ta = time.time()
            if args.save_audio:
                import wave as _wave
                d = Path(args.save_audio)
                d.mkdir(parents=True, exist_ok=True)
                counts["n"] += 1
                fn = d / f"seg{counts['n']:04d}_{t_start:07.1f}s.wav"
                with _wave.open(str(fn), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                    w.writeframes((np.clip(seg, -1, 1) * 32767).astype(np.int16).tobytes())
            prompt = " ".join(x for x in [args.prompt or PRESETS.get(args.preset, ""), " ".join(ctx)] if x)[-400:] or None
            segments, info = model.transcribe(
                seg, language=None if args.src == "auto" else args.src,
                beam_size=1, temperature=0.0, vad_filter=False,
                condition_on_previous_text=False, initial_prompt=prompt)
            # 丢掉静音段上的幻觉（whisper 会在噪声上凭空造句，no_speech_prob 高）
            keep = []
            for s in segments:
                if s.no_speech_prob > 0.5 and s.avg_logprob < -0.7:
                    continue
                keep.append(s.text.strip())
            text = " ".join(t for t in keep if t).strip()
            bad, why = looks_like_hallucination(text, len(seg) / SR)
            if bad:
                if text:
                    print(f"[asr] 丢掉可疑段（{why}）: {text[:60]}…", flush=True)
                text = ""
            asr_ms = int((time.time() - ta) * 1000)
            stats["asr"].append(asr_ms); stats["audio"] += len(seg) / SR; stats["segs"] += 1
            if not text or len(re.sub(r"\W", "", text)) < 2:
                continue
            ctx.append(text)
            tr_q.put((text, t_start, asr_ms))

    def tr_worker():
        while not stop_flag.is_set():
            try:
                text, t_start, asr_ms = tr_q.get(timeout=0.3)
            except queue.Empty:
                continue
            tgt, dt = translator.translate(text)
            sink.add(text, tgt, t_start, asr_ms, int(dt * 1000))

    threading.Thread(target=asr_worker, daemon=True).start()
    threading.Thread(target=tr_worker, daemon=True).start()

    # ── 分段状态机 ──
    print("[run] 开始听（Ctrl+C 结束）\n")
    noise = args.vad
    buf: list[np.ndarray] = []
    pending: list[np.ndarray] = []         # 攒着没形成完整句子的短段，跟下一段合并
    pre: deque = deque()                   # 预滚 ~0.25s（按样本数截，兼容 url 模式的大块）
    in_speech = False
    silent_for = 0.0
    seg_len = 0.0
    seg_t0 = 0.0
    started = time.time()

    def flush(reason):
        nonlocal buf, in_speech, silent_for, seg_len, seg_t0
        if buf:
            audio = np.concatenate(buf)
            dur = len(audio) / SR
            if dur >= args.merge_below:
                if pending:            # 和攒下的短段拼起来再转写：上下文更足，识别和翻译都更准
                    audio = np.concatenate(pending + [audio])
                    pending.clear()
                if len(audio) / SR >= args.min_seg:
                    asr_q.put((audio, seg_t0 - started))
            else:
                pending.append(audio)  # 太短就先攒着（勿让 ASR 处理没有上下文的碎片）
                if sum(len(p) for p in pending) / SR >= 6.0:
                    asr_q.put((np.concatenate(pending), seg_t0 - started))
                    pending.clear()
            buf = []
        in_speech = False
        silent_for = 0.0
        seg_len = 0.0

    try:
        while True:
            if args.run_for and time.time() - started >= args.run_for:
                break
            if args.stop_file and Path(args.stop_file).exists():
                print("\n[run] 收到停止信号，收尾退出")
                try:
                    Path(args.stop_file).unlink()
                except OSError:
                    pass
                break
            if getattr(cap, "dead", False):
                print("\n[capture] 拉流已断开（直播结束或地址失效），收尾退出")
                break
            try:
                raw = cap.q.get(timeout=1.0)
            except queue.Empty:
                continue
            x = to_16k_mono(raw, cap.rate)
            if not len(x):
                continue
            dt = len(x) / SR
            r = rms(x)
            if not in_speech:
                noise = 0.98 * noise + 0.02 * r
            thresh = max(args.vad, noise * 3.0)

            if r > thresh:
                if not in_speech:
                    in_speech = True
                    if pending:                       # 接上攒下的短段，时间戳往前推
                        seg_t0 = time.time() - sum(len(p) for p in pending) / SR
                    else:
                        seg_t0 = time.time()
                    buf = list(pending) + list(pre)   # 攒下的短段 + 预滚，一起喂给 whisper
                    pending.clear()
                    silent_for = 0.0
                buf.append(x)
                silent_for = 0.0
            elif in_speech:
                buf.append(x)
                silent_for += dt

            if in_speech:
                seg_len += dt
                if silent_for >= args.silence:
                    flush("silence")
                elif seg_len >= args.max_seg:
                    # 到上限：优先在最后 1.2s 里找真正安静的点切开；若整段都在说话，
                    # 再宽限 3s 等一个自然停顿，避免把词切两半（切一半会让下一段重念）
                    cut = None
                    quiet = False
                    if len(buf) > 4 and dt > 0:
                        tail = buf[-int(1.2 / dt):]
                        win = max(1, len(tail) // 4)
                        rmses = [rms(np.concatenate(tail[i:i + win])) for i in range(0, len(tail), win)]
                        if rmses:
                            best = min(range(len(rmses)), key=lambda i: rmses[i])
                            quiet = rmses[best] < max(args.vad, noise * 2.5)
                            cut = int((len(buf) - len(tail)) + best * win)
                    if quiet and cut and cut > len(buf) // 3:
                        audio = np.concatenate(buf[:cut])
                        if len(audio) / SR >= args.min_seg:
                            asr_q.put((audio, seg_t0 - started))
                        rest = buf[cut:]
                        seg_t0 = time.time()
                        buf = list(rest)
                        seg_len = len(np.concatenate(buf)) / SR
                    elif seg_len >= args.max_seg + 3.0:
                        # 宽限期里一直没人停嘴，硬切
                        flush("hard-max")
            else:
                pre.append(x)
                while sum(len(p) for p in pre) > int(0.25 * SR):
                    pre.popleft()
    except KeyboardInterrupt:
        pass
    finally:
        stop_flag.set()
        flush("end")
        if pending:                      # 收尾：把最后攒着的碎片也送出去
            asr_q.put((np.concatenate(pending), 0.0))
            pending.clear()
        # 排空队列：不能用 asr_q.join()——worker 没调 task_done()，会永远挂住（进程退不出去、
        # 旧实例继续抓声音继续调 API，实测踩过）
        deadline = time.time() + 25
        while (asr_q.qsize() or tr_q.qsize()) and time.time() < deadline:
            time.sleep(0.2)
        time.sleep(0.6)
        cap.stop()
        a = stats["asr"]; t = [x for x in stats["tr"] if x]
        print("\n──────── 统计 ────────")
        print(f"音频 {stats['audio']:.0f}s / {stats['segs']} 段")
        if a:
            print(f"转写 平均 {sum(a)/len(a):.0f}ms  最大 {max(a)}ms  → 实时倍率 {sum(a)/1000/max(stats['audio'],1e-9):.2f}x")
        if t:
            print(f"翻译 平均 {sum(t)/len(t):.0f}ms  最大 {max(t)}ms")
        if sink.jsonl:
            print(f"记录 {sink.jsonl}")


if __name__ == "__main__":
    main()
