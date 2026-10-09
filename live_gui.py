#!/usr/bin/env python3
"""live_gui.py —— 实时翻译的图形启动器（tkinter，标准库，无需额外依赖）

窗口里调参数 → 点「开始」→ 原文/译文直接显示在下面，同时照旧提供网页字幕页。
打包成 exe 后也走这个文件；带 --run-cli 参数时它会退化成纯命令行版（GUI 用它拉起后台进程）。

    python live_gui.py              # 开发模式（用当前 venv 的 python 拉起 live_translate.py）
    live-translate-gui.exe          # 打包后
    python live_gui.py --smoke 20   # 自检：自动开始、20 秒后停止、打印结果
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
SETTINGS = HERE / "gui_settings.json"
STOP_FILE = HERE / "logs" / "STOP.signal"

# --run-cli：作为后台进程跑真正的主程序
if "--run-cli" in sys.argv:
    _want_console = "--console" in sys.argv
    sys.argv = [a for a in sys.argv if a not in ("--run-cli", "--console")]
    if _want_console and os.name == "nt":      # AllocConsole 是 Windows 专属
        try:                                   # 勾了「显示运行日志」：输出打到控制台
            import ctypes
            ok = bool(ctypes.windll.kernel32.AllocConsole())
            sys.stdout = sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            try:
                with open(HERE / "logs" / "console_debug.txt", "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%H:%M:%S')} AllocConsole={ok} 输出=CONOUT$\n")
            except Exception:
                pass
        except Exception as e:
            pass
    else:                                      # 默认：安静跑，输出写日志文件
        Path(HERE / "logs").mkdir(exist_ok=True, parents=True)
        _lf = open(HERE / "logs" / "gui_run.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = _lf          # 打包成 --windowed 后 sys.stdout 是 None，print 会炸
    sys.path.insert(0, str(HERE))
    import live_translate
    live_translate.main()
    sys.exit(0)

LANGS = ["ja", "en", "ko", "zh", "auto"]
MODELS = ["small", "medium", "large-v3", "large-v3-turbo", "base", "tiny"]
DEVICES = ["auto", "cuda", "cpu"]
MODEL_SIZES = {"tiny": "75 MB", "base": "142 MB", "small": "464 MB", "medium": "1.5 GB",
               "large-v3": "3.1 GB", "large-v3-turbo": "1.6 GB"}
TM_LOCAL = "本地模型"
TM_API = "云端 API"
LOCAL_MT = {                      # 界面上的名字 → models/ 下的目录名，或 "ollama:<模型名>"
    "NLLB-200 日→中": "nllb-200-distilled-600M-ct2",
    "Ollama 本地大模型": "ollama:qwen3:4b",
}
LOCAL_MT_DEFAULT = next(iter(LOCAL_MT))
OLLAMA_HOST = "http://127.0.0.1:11434"


def ollama_state() -> tuple[bool, list[str]]:
    """(服务是否在跑, 已有哪些模型)"""
    import urllib.request
    try:
        with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=1.5) as r:
            d = json.loads(r.read())
        return True, [m.get("name", "") for m in (d.get("models") or [])]
    except Exception:
        return False, []


def local_mt_ready(choice: str) -> bool:
    v = LOCAL_MT.get(choice.split("（")[0].strip(), choice)
    if v.startswith("ollama:"):
        up, names = ollama_state()
        want = v.split(":", 1)[1]
        return up and any(n == want or n.startswith(want.split(":")[0]) for n in names)
    return (models_dir() / v).is_dir()


def models_dir() -> Path:
    for base in (HERE, *list(HERE.parents)[:3]):
        p = base / "models"
        if p.is_dir():
            return p
    return HERE / "models"


def local_mt_choices() -> list[str]:
    """列本地可用的翻译模型（含 Ollama）"""
    out = []
    up, _ = ollama_state()
    for label, v in LOCAL_MT.items():
        if local_mt_ready(label):
            state = "已就绪"
        elif v.startswith("ollama:"):
            state = "缺模型" if up else "未装 Ollama"
        else:
            state = "缺模型"
        out.append(f"{label}（{state}）")
    try:
        for p in sorted(models_dir().glob("*-ct2")):
            if p.name not in LOCAL_MT.values():
                out.append(p.name)
    except Exception:
        pass
    return out or ["（本地还没有翻译模型）"]


def local_mt_dir(choice: str) -> Path:
    name = choice.split("（")[0].strip()
    return models_dir() / LOCAL_MT.get(name, name)
PROMPTS = {
    "不填（通用闲聊）": "",
    "化学 · 日语": ("化学の配信です。ラジカル配位子が二つのランタノイドイオンを架橋する話と、"
                 "ジスプロシウム中心の異方性、単分子磁石についてです。"),
    "化学 · 英语": ("A chemistry livestream about radical ligands bridging two lanthanide ions, "
                 "the anisotropy of the dysprosium center, and single-molecule magnets."),
}

DEFAULTS = {
    "src": "ja", "model": "large-v3", "device": "auto",
    "silence": 0.45, "merge_below": 1.6, "max_seg": 6.0,
    "prompt_name": next(iter(PROMPTS)), "prompt_custom": "",
    "port": 8777, "show_page": True,
    "target": "zh",
    "source": "抓系统声音（扬声器里放什么就翻什么）", "url": "",
    "api_key": "", "console": False,
    "trans_mode": TM_LOCAL, "local_mt": LOCAL_MT_DEFAULT,
    "font_size": 22,
}
SOURCE_LOOPBACK = "抓系统声音（扬声器里放什么就翻什么）"
SOURCE_URL = "抓直播间网址（只抓这一路，不影响你听别的）"
SOURCE_DEVICE = "抓音频输入设备（macOS 用 BlackHole）"
# 界面字体：Windows 用雅黑，macOS 用苹方（写死雅黑的话 Mac 上找不到字体，字号/排版会出问题）
UI_FONT = "Microsoft YaHei" if os.name == "nt" else ("PingFang SC" if sys.platform == "darwin"
                                                    else "Noto Sans CJK SC")


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


class App:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root = root
        self.proc: subprocess.Popen | None = None
        self.lines_seen = 0
        self.overlay = None
        self._recent_lines: list = []
        self.log_q: queue.Queue[str] = queue.Queue()
        self.s = load_settings()
        for k, v in (("font_size", 22), ("overlay_show_src", False)):
            self.s.setdefault(k, v)

        root.title("Illya's live-translate tools")
        root.geometry("960x680")
        root.minsize(760, 520)

        # ── 参数区 ──
        box = ttk.LabelFrame(root, text=" 参数 ")
        box.pack(fill="x", padx=10, pady=(8, 4))
        g = 0

        def row(label, widget, hint="", val=None):
            nonlocal g
            ttk.Label(box, text=label).grid(row=g, column=0, sticky="e", padx=(10, 6), pady=4)
            widget.grid(row=g, column=1, sticky="w", pady=4)
            col = 2
            if val is not None:                    # 拉条旁边实时显示当前值
                ttk.Label(box, textvariable=val, width=7, anchor="w").grid(row=g, column=2, sticky="w")
                col = 3
            if hint:
                ttk.Label(box, text=hint, foreground="#666").grid(row=g, column=col, columnspan=4 - col,
                                                                  sticky="w", padx=10)
            g += 1

        self.v_src = tk.StringVar(value=self.s["src"])
        row("待翻译语种", ttk.Combobox(box, textvariable=self.v_src, values=LANGS, width=8,
                                    state="readonly"))
        self.v_source = tk.StringVar(value=self.s.get("source", SOURCE_LOOPBACK))
        fr = ttk.Frame(box)
        if os.name == "nt":                          # WASAPI 环回只有 Windows 有，Mac/Linux 不显示
            ttk.Radiobutton(fr, text="抓系统声音", value=SOURCE_LOOPBACK,
                            variable=self.v_source).pack(side="left")
        elif self.v_source.get() == SOURCE_LOOPBACK:
            self.v_source.set(SOURCE_URL)            # 非 Windows 默认改成抓直播间
        ttk.Radiobutton(fr, text="抓直播间网址", value=SOURCE_URL,
                        variable=self.v_source).pack(side="left", padx=(10, 0))
        if os.name != "nt":
            ttk.Radiobutton(fr, text="抓音频输入设备", value=SOURCE_DEVICE,
                            variable=self.v_source).pack(side="left", padx=(10, 0))
        row("声音来源", fr,
            "选「网址」可以静音、可以同时听其他音频，不干扰翻译")
        self.v_url = tk.StringVar(value=self.s.get("url", ""))
        row("直播间网址/房间号", ttk.Entry(box, textvariable=self.v_url, width=46),
            "选抓网址需填写直播间网址，如：https://live.bilibili.com/***")
        self.v_inputdev = tk.StringVar(value=self.s.get("input_device", ""))
        row("输入设备", ttk.Entry(box, textvariable=self.v_inputdev, width=22))
        self.v_model = tk.StringVar(value=self.s["model"])
        row("识别模型", ttk.Combobox(box, textvariable=self.v_model, values=MODELS, width=14,
                                  state="readonly"), "large-v3 最准（需 N 卡）")
        self.v_device = tk.StringVar(value=self.s["device"])
        row("运行设备", ttk.Combobox(box, textvariable=self.v_device, values=DEVICES, width=8,
                                  state="readonly"))

        def mk_scale(var, lo, hi, fmt):
            """带实时数值显示的拉条"""
            disp = tk.StringVar(value=fmt(var.get()))
            sc = ttk.Scale(box, from_=lo, to=hi, variable=var, orient="horizontal", length=190,
                           command=lambda v: disp.set(fmt(float(v))))
            return sc, disp

        self.v_silence = tk.DoubleVar(value=self.s["silence"])
        sc, disp = mk_scale(self.v_silence, 0.2, 1.5, lambda v: f"{v:.2f} 秒")
        row("说完多久算一句（秒）", sc, "实况 0.35–0.6 合适", val=disp)
        self.v_merge = tk.DoubleVar(value=self.s["merge_below"])
        sc, disp = mk_scale(self.v_merge, 0.0, 4.0, lambda v: f"{v:.2f} 秒")
        row("短句合并阈值（秒）", sc, "自动合并短于此时间的碎句", val=disp)
        self.v_maxseg = tk.DoubleVar(value=self.s["max_seg"])
        sc, disp = mk_scale(self.v_maxseg, 3.0, 15.0, lambda v: f"{v:.1f} 秒")
        row("一句话最长（秒）", sc, val=disp)

        self.v_prompt = tk.StringVar(value=self.s["prompt_name"])
        row("术语提示", ttk.Combobox(box, textvariable=self.v_prompt, values=list(PROMPTS),
                                  width=20, state="readonly"), "专有名词多就选一个，闲聊可不填")
        self.v_custom = tk.StringVar(value=self.s["prompt_custom"])
        e = ttk.Entry(box, textvariable=self.v_custom, width=46)
        e.grid(row=g, column=0, columnspan=4, sticky="we", padx=10, pady=(0, 6))
        g += 1
        ttk.Label(box, text="（想在「术语提示」里写自定义的，填这一行；会覆盖上面的下拉选择）",
                  foreground="#666").grid(row=g, column=0, columnspan=4, sticky="w", padx=10)
        g += 1

        self.v_key = tk.StringVar(value=self.s.get("api_key", ""))
        self.v_key_show = tk.StringVar(value="********" if self.v_key.get() else "")
        self.v_transmode = tk.StringVar(value=self.s.get("trans_mode", TM_LOCAL))
        self.v_localmt = tk.StringVar(value=self.s.get("local_mt", LOCAL_MT_DEFAULT))
        fr2 = ttk.Frame(box)
        ttk.Radiobutton(fr2, text="本地模型", value=TM_LOCAL,
                        variable=self.v_transmode).pack(side="left")
        ttk.Combobox(fr2, textvariable=self.v_localmt, values=local_mt_choices(),
                     width=26, state="readonly").pack(side="left", padx=(4, 16))
        ttk.Radiobutton(fr2, text="云端 API", value=TM_API,
                        variable=self.v_transmode).pack(side="left")
        e_key = ttk.Entry(fr2, textvariable=self.v_key_show, width=24, state="readonly")
        e_key.pack(side="left", padx=(4, 4))
        e_key.bind("<Button-1>", lambda ev: self.edit_key())
        ttk.Button(fr2, text="修改", width=6, command=self.edit_key).pack(side="left")
        row("翻译模型", fr2)

        self.v_font = tk.DoubleVar(value=float(self.s.get("font_size", 22)))
        self.l_font = tk.StringVar(value=f"{int(self.v_font.get())} px")
        row("字幕字号", ttk.Scale(box, from_=10, to=44, variable=self.v_font, orient="horizontal",
                                  length=190, command=self._on_font_slide), val=self.l_font)

        self.v_page = tk.BooleanVar(value=self.s["show_page"])
        self.v_port = tk.IntVar(value=self.s["port"])
        self.v_console = tk.BooleanVar(value=bool(self.s.get("console", False)))
        f = ttk.Frame(box)
        f.grid(row=g, column=0, columnspan=4, sticky="w", padx=10, pady=6)
        ttk.Checkbutton(f, text="开字幕网页", variable=self.v_page).pack(side="left")
        ttk.Label(f, text="端口").pack(side="left", padx=(12, 4))
        ttk.Entry(f, textvariable=self.v_port, width=7).pack(side="left")
        ttk.Checkbutton(f, text="显示运行日志",
                        variable=self.v_console).pack(side="left", padx=(18, 0))
        g += 1

        # ── 按钮 ──
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=10, pady=6)
        self.b_start = ttk.Button(bar, text="▶  开始翻译", command=self.start)
        self.b_start.pack(side="left")
        self.b_stop = ttk.Button(bar, text="■  停止", command=self.stop, state="disabled")
        self.b_stop.pack(side="left", padx=6)
        ttk.Button(bar, text="打开字幕页", command=self.open_page).pack(side="left", padx=6)
        ttk.Button(bar, text="打开记录文件夹", command=self.open_logs).pack(side="left")
        self.b_overlay = ttk.Button(bar, text="弹出字幕浮窗", command=self.toggle_overlay)
        self.b_overlay.pack(side="left", padx=6)
        self.v_status = tk.StringVar(value="先把直播/视频挂起来，再点「开始翻译」。")
        ttk.Label(bar, textvariable=self.v_status).pack(side="left", padx=14)

        # ── 字幕区 ──
        area = ttk.Frame(root)
        area.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.txt = tk.Text(area, wrap="word", bg="#14161b", fg="#e8e8ea",
                           insertbackground="#e8e8ea", relief="flat", padx=14, pady=10)
        sb = ttk.Scrollbar(area, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        self.txt.tag_configure("src", foreground="#8b93a5")
        self.txt.tag_configure("tgt", foreground="#f2f4f8",
                               font=(UI_FONT, int(self.v_font.get())))
        self.txt.tag_configure("meta", foreground="#5a6274", spacing3=10)
        self.txt.configure(state="disabled")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        # 记忆：任何一处改动都延迟 1 秒写进 gui_settings.json，下次打开原样恢复
        self._save_job = None
        for var in (self.v_src, self.v_model, self.v_device, self.v_source, self.v_url,
                    self.v_inputdev,
                    self.v_transmode, self.v_localmt, self.v_console, self.v_page,
                    self.v_port, self.v_silence, self.v_merge, self.v_maxseg, self.v_font,
                    self.v_prompt, self.v_custom, self.v_key):
            try:
                var.trace_add("write", self._schedule_save)
            except Exception:
                pass
        self._flush_log_q()

    def _schedule_save(self, *_a):
        if self._save_job:
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.root.after(1000, self._save_now)

    def _save_now(self):
        self._save_job = None
        try:
            save_settings(self.snapshot())
        except Exception:
            pass

    # ────────── 启动 / 停止 ──────────
    def build_args(self) -> list[str]:
        a = ["--stop-file", str(STOP_FILE),
             "--src", self.v_src.get(), "--model-size", self.v_model.get(),
             "--device", self.v_device.get(),
             "--silence", f"{self.v_silence.get():.2f}",
             "--merge-below", f"{self.v_merge.get():.2f}",
             "--max-seg", f"{self.v_maxseg.get():.1f}",
             "--port", str(self.v_port.get())]
        custom = self.v_custom.get().strip()
        prompt = custom or PROMPTS.get(self.v_prompt.get(), "")
        if prompt:
            a += ["--prompt", prompt]
        if not self.v_page.get():
            a.append("--no-web")
        if self.v_console.get():
            a.append("--console")
        if self.v_transmode.get() == TM_LOCAL:
            sel = self.v_localmt.get()
            val = LOCAL_MT.get(sel.split("（")[0].strip(), sel)
            if val.startswith("ollama:"):
                a += ["--translator", "ollama", "--ollama-model", val.split(":", 1)[1]]
            else:
                a += ["--translator", "local", "--local-mt", str(local_mt_dir(sel))]
        else:
            a += ["--translator", "api"]
        if self.v_source.get() == SOURCE_URL:
            url = self.v_url.get().strip()
            if not url:
                raise ValueError("选了「抓直播间网址」，但网址那一格是空的")
            a = ["--url", url] + a
        elif self.v_source.get() == SOURCE_DEVICE:
            spec = self.v_inputdev.get().strip()
            if not spec:
                raise ValueError("选了「抓音频输入设备」，但设备那一格是空的"
                                 "（macOS: 先 `python live_translate.py --list-input-devices` 看序号）")
            a = ["--input-device", spec] + a
        return a

    def _cmd_prefix(self) -> list[str]:
        """拉起后台进程的命令前缀：打包后是 exe 自己，开发时是本文件（都进 --run-cli 分支）"""
        if FROZEN:
            return [sys.executable, "--run-cli"]
        return [sys.executable, str(HERE / "live_gui.py"), "--run-cli"]

    def start(self):
        if self.proc:
            return
        from tkinter import messagebox
        m = self.v_model.get()
        if not (models_dir() / f"faster-whisper-{m}").is_dir():
            if not messagebox.askyesno("需要下载模型",
                                       f"识别模型 faster-whisper-{m} 还没下载"
                                       f"（约 {MODEL_SIZES.get(m, '未知大小')}）。\n\n现在开始下载吗？"
                                       f"（只下一次，存在 models\\ 目录里）"):
                self.v_status.set("已取消：模型还没准备好。")
                return
        if self.v_transmode.get() == TM_LOCAL:
            sel = self.v_localmt.get()
            val = LOCAL_MT.get(sel.split("（")[0].strip(), sel)
            if val.startswith("ollama:"):
                model = val.split(":", 1)[1]
                up, names = ollama_state()
                if not up:
                    messagebox.showerror("没连上 Ollama",
                                         "本机 127.0.0.1:11434 上没有 Ollama 服务。\n\n"
                                         "先装并启动 Ollama，或者改选「云端 API」。")
                    return
                if not any(n == model or n.startswith(model.split(":")[0]) for n in names):
                    if not messagebox.askyesno("需要下载模型",
                                               f"Ollama 里还没有 {model}（约 2.5 GB）。\n\n"
                                               f"现在开始下载吗？"):
                        self.v_status.set("已取消：模型还没准备好。")
                        return
                    exe = shutil.which("ollama") or str(
                        Path.home() / "AppData/Local/Programs/Ollama/ollama.exe")
                    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
                    try:
                        subprocess.Popen([exe, "pull", model], creationflags=flags)
                        self.v_status.set(f"正在下载 {model}（看新开的窗口）；下完再点一次「开始翻译」。")
                    except Exception as e:
                        messagebox.showerror("下载失败", f"没能启动 ollama pull：{e}")
                    return
            else:
                md = local_mt_dir(sel)
                if not md.is_dir():
                    messagebox.showerror("缺少本地翻译模型",
                                         f"没找到：{md}\n\n本地翻译模型需要随程序一起提供，"
                                         f"或者手动放进 models\\ {md.name}。")
                    return
        try:
            args = self.build_args()
        except ValueError as e:
            self.v_status.set(f"❌ {e}")
            return
        (HERE / "logs").mkdir(exist_ok=True)
        STOP_FILE.unlink(missing_ok=True)          # 清掉上次遗留的停止信号
        logf = open(HERE / "logs" / "gui_run.log", "a", encoding="utf-8", buffering=1)
        logf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(args)} =====\n")
        if self.v_console.get():
            flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE
                     if os.name == "nt" else 0)          # 勾了「显示运行日志」：给一个真控制台看
        else:
            flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                     if os.name == "nt" else 0)          # 默认安静，不要黑框
        env = dict(os.environ)
        key = self.v_key.get().strip()
        if key:
            env["DEEPSEEK_API_KEY"] = key               # 走环境变量，不写进命令行
        cmdline = self._cmd_prefix() + args
        if self.v_console.get():
            # GUI 子系统程序自己调 AllocConsole 是弹不出窗口的；借 cmd.exe 当控制台宿主
            cmdline = ["cmd.exe", "/c", *cmdline] if os.name == "nt" else cmdline
        self.proc = subprocess.Popen(cmdline, cwd=str(HERE), stdout=logf,
                                     stderr=subprocess.STDOUT, creationflags=flags, env=env)
        self.logfile = logf
        self.lines_seen = 0
        self.b_start.configure(state="disabled")
        self.b_stop.configure(state="normal")
        self.v_status.set("启动中…（第一次用某个模型要等它下载）")
        save_settings(self.snapshot())
        self.root.after(1500, self.poll)

    def stop(self, quiet=False):
        p = self.proc
        self.proc = None
        if p and p.poll() is None:
            try:
                STOP_FILE.write_text("stop\n", encoding="utf-8")   # 优雅退出：让它自己收尾、打印统计
                p.wait(timeout=12)
            except Exception:
                try:
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                    p.wait(timeout=5)
                except Exception:
                    p.terminate()
        STOP_FILE.unlink(missing_ok=True)
        if not quiet:
            self.v_status.set(f"已停止。本次共翻 {self.lines_seen} 段。")
        self.b_start.configure(state="normal")
        self.b_stop.configure(state="disabled")

    def on_close(self):
        self.stop(quiet=True)
        if getattr(self, "overlay", None):
            try:
                self.overlay.close()               # 顺手记住浮窗位置
            except Exception:
                pass
        self._save_now()                           # 关窗口也把设置落盘
        self.root.destroy()

    # ────────── 轮询字幕 ──────────
    def poll(self):
        if not self.proc:
            return
        if self.proc.poll() is not None:
            self.stop()
            self.v_status.set("进程已退出——看 logs/gui_run.log；可能是模型没下完或端口冲突。")
            return
        try:
            url = f"http://127.0.0.1:{self.v_port.get()}/api/lines?since={self.lines_seen}"
            with urllib.request.urlopen(url, timeout=2) as r:
                d = json.loads(r.read())
            for l in d.get("lines", []):
                self.append(l)
            self.lines_seen = d.get("total", self.lines_seen)
            self.v_status.set(f"运行中 · 已翻 {self.lines_seen} 段")
        except Exception:
            pass                    # 模型还在加载 / 网页没开
        self.root.after(800, self.poll)

    def append(self, l: dict):
        self.txt.configure(state="normal")
        self.txt.insert("end", l.get("src", "") + "\n", "src")
        self.txt.insert("end", (l.get("tgt") or "…") + "\n", "tgt")
        self.txt.insert("end", f"{l.get('asr_ms', 0)}ms 转写 / {l.get('tr_ms', 0)}ms 翻译\n", "meta")
        at_bottom = self.txt.yview()[1] > 0.98
        self.txt.configure(state="disabled")
        if at_bottom:
            self.txt.see("end")
        if getattr(self, "overlay", None):            # 同步给浮窗
            self.overlay.add(l.get("src", ""), l.get("tgt") or "…")
        self._recent_lines.append(l)
        del self._recent_lines[:-5]

    # ────────── 浮窗 / 字号 ──────────
    def edit_key(self):
        import tkinter as tk
        d = tk.Toplevel(self.root)
        d.title("API Key")
        d.transient(self.root)
        d.resizable(False, False)
        d.geometry(f"420x130+{self.root.winfo_x() + 220}+{self.root.winfo_y() + 200}")
        tk.Label(d, text="API Key").pack(anchor="w", padx=14, pady=(14, 3))
        v = tk.StringVar(value=self.v_key.get())
        e = tk.Entry(d, textvariable=v, width=48, show="*")
        e.pack(padx=14)
        e.focus_set()

        def save():
            self.v_key.set(v.get().strip())
            self.v_key_show.set("********" if self.v_key.get() else "")
            self.s["api_key"] = self.v_key.get()
            try:
                save_settings(self.snapshot())
            except Exception:
                pass
            d.grab_release()
            d.destroy()

        def clear():
            v.set("")

        bar = tk.Frame(d)
        bar.pack(pady=12)
        tk.Button(bar, text="保存", width=8, command=save).pack(side="left", padx=5)
        tk.Button(bar, text="清除", width=8, command=clear).pack(side="left", padx=5)
        tk.Button(bar, text="取消", width=8, command=d.destroy).pack(side="left", padx=5)
        d.bind("<Return>", lambda ev: save())
        d.bind("<Escape>", lambda ev: d.destroy())
        e.select_range(0, "end")
        self.root.wait_window(d)
    def _on_font_slide(self, v):
        n = int(float(v))
        self.l_font.set(f"{n} px")
        self.s["font_size"] = n
        if hasattr(self, "txt"):
            self.txt.tag_configure("tgt", font=(UI_FONT, n))
        if getattr(self, "overlay", None):
            self.overlay.set_font_size(n)

    def on_overlay_font(self, n):
        """浮窗里改了字号 → 同步主窗口和设置"""
        self.v_font.set(float(n))
        self.l_font.set(f"{n} px")
        self.s["font_size"] = n
        if hasattr(self, "txt"):
            self.txt.tag_configure("tgt", font=(UI_FONT, n))

    def toggle_overlay(self):
        if getattr(self, "overlay", None):
            self.overlay.close()
            return
        self.overlay = SubtitleOverlay(self, font_size=int(self.v_font.get()))
        self.b_overlay.configure(text="关闭字幕浮窗")
        for l in self._recent_lines[-3:]:             # 把最近几句先填进去
            self.overlay.add(l.get("src", ""), l.get("tgt") or "…")

    # ────────── 小工具 ──────────
    def open_page(self):
        if not self.v_page.get():
            self.v_status.set("这次没开字幕网页（勾上「开字幕网页」再开始就有）。")
            return
        url = f"http://127.0.0.1:{self.v_port.get()}/"
        try:
            webbrowser.open(url)
            self.v_status.set(f"字幕页：{url}")
        except Exception as e:                      # 打不开浏览器也别崩，把地址告诉用户
            self.v_status.set(f"没能自动打开浏览器（{type(e).__name__}）：请手动访问 {url}")

    def open_logs(self):
        path = HERE / "logs"
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])       # macOS：用 Finder 打开
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            self.v_status.set(f"打开记录文件夹失败（{type(e).__name__}）：路径是 {path}")

    def snapshot(self) -> dict:
        return {"src": self.v_src.get(), "model": self.v_model.get(), "device": self.v_device.get(),
                "silence": round(self.v_silence.get(), 2), "merge_below": round(self.v_merge.get(), 2),
                "max_seg": round(self.v_maxseg.get(), 1), "prompt_name": self.v_prompt.get(),
                "prompt_custom": self.v_custom.get(), "port": self.v_port.get(),
                "show_page": bool(self.v_page.get()),
                "source": self.v_source.get(), "url": self.v_url.get().strip(),
                "font_size": int(self.v_font.get()),
                "api_key": self.v_key.get().strip(),
                "console": bool(self.v_console.get()),
                "trans_mode": self.v_transmode.get(),
                "local_mt": self.v_localmt.get(),
                "input_device": self.v_inputdev.get().strip(),
                "overlay_show_src": bool(self.s.get("overlay_show_src", False)),
                "overlay_geometry": self.s.get("overlay_geometry")}

    def _flush_log_q(self):
        """后台线程里没人用了，保留接口：方便以后把子进程输出直接显示到界面上"""
        while not self.log_q.empty():
            self.log_q.get_nowait()
        self.root.after(1000, self._flush_log_q)


def save_settings(s: dict):
    try:
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ────────────────────── 字幕浮窗（歌词式） ──────────────────────
TRANSPARENT_KEY = "#010203"      # 这个颜色会被 Windows 抠成透明（只剩面板本身）


class SubtitleOverlay:
    """无边框、置顶、半透明的字幕浮窗：最新一句大字，旧句自动变暗缩小。
    拖动面板任意处可移动；滚轮或 Ctrl+/- 调字号；位置会记住。"""

    def __init__(self, app, font_size: int = 22, alpha: float = 0.82):
        import tkinter as tk
        self.tk, self.app = tk, app
        self.font_size = font_size
        self.show_src = bool(app.s.get("overlay_show_src", False))
        self.items: deque = deque(maxlen=3)

        w = tk.Toplevel(app.root)
        self.win = w
        w.overrideredirect(True)                 # 无标题栏
        w.attributes("-topmost", True)           # 永远在最前
        w.configure(bg=TRANSPARENT_KEY)
        try:
            w.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass                                 # 非 Windows 没有抠图，退化成普通小窗
        try:
            w.attributes("-alpha", alpha)        # 半透明
        except tk.TclError:
            pass

        pad = tk.Frame(w, bg=TRANSPARENT_KEY)     # 留一圈透明边
        pad.pack(fill="both", expand=True, padx=3, pady=3)
        self.panel = tk.Frame(pad, bg="#0b0d12", highlightthickness=1,
                              highlightbackground="#2b3140")
        self.panel.pack(fill="both", expand=True)

        bar = tk.Frame(self.panel, bg="#0b0d12")
        bar.pack(fill="x", side="top", padx=8, pady=(4, 0))
        self._btn(bar, "字号 −", lambda: self.bump_font(-2)).pack(side="left")
        self._btn(bar, "字号 +", lambda: self.bump_font(2)).pack(side="left", padx=(4, 10))
        # 尺寸按钮：macOS 上拖右下角不一定灵，给一套按钮保险
        self._btn(bar, "宽 −", lambda: self.bump_size(-60, 0)).pack(side="left")
        self._btn(bar, "宽 +", lambda: self.bump_size(60, 0)).pack(side="left", padx=(4, 10))
        self._btn(bar, "高 −", lambda: self.bump_size(0, -30)).pack(side="left")
        self._btn(bar, "高 +", lambda: self.bump_size(0, 30)).pack(side="left", padx=(4, 10))
        self._btn(bar, "原文", self.toggle_src).pack(side="left")
        self._btn(bar, "✕", self.close).pack(side="right")
        tk.Label(bar, text="拖动移动 · 右下角◢缩放", bg="#0b0d12", fg="#5a6274",
                 font=(UI_FONT, 8)).pack(side="right", padx=6)

        self.txt = tk.Text(self.panel, wrap="word", bg="#0b0d12", fg="#f2f4f8",
                           relief="flat", highlightthickness=0, height=4, width=34, padx=10, pady=4)
        self.txt.pack(fill="both", expand=True)
        self.txt.configure(state="disabled")
        self._apply_fonts()

        for tgt in (self.panel, self.txt, bar):
            tgt.bind("<Button-1>", self._drag_start)
            tgt.bind("<B1-Motion>", self._drag_move)

        # 右下角缩放把手：无边框窗口没有系统边框，只能自己做一个
        self.grip = tk.Label(self.panel, text="◢", bg="#0b0d12", fg="#4b5563",
                             cursor="size_nw_se", font=(UI_FONT, 11))
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<Button-1>", self._resize_start)
        self.grip.bind("<B1-Motion>", self._resize_move)
        self.grip.bind("<MouseWheel>", lambda e: None)

        geo = app.s.get("overlay_geometry")
        w.geometry(geo or "440x150+60+60")
        w.protocol("WM_DELETE_WINDOW", self.close)

    def _btn(self, parent, text, cmd):
        b = self.tk.Label(parent, text=text, bg="#161a22", fg="#c9d1e0", cursor="hand2",
                          font=(UI_FONT, 9), padx=7, pady=2)
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _drag_move(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _resize_start(self, e):
        self._rw, self._rh = self.win.winfo_width(), self.win.winfo_height()
        self._rx, self._ry = e.x_root, e.y_root

    def _resize_move(self, e):
        w = max(200, self._rw + (e.x_root - self._rx))
        h = max(64, self._rh + (e.y_root - self._ry))
        self.win.geometry(f"{w}x{h}")

    def _apply_fonts(self):
        n = self.font_size
        self.txt.tag_configure("cur", font=(UI_FONT, n, "bold"), foreground="#ffffff",
                               spacing1=2, spacing3=4)
        self.txt.tag_configure("prev", font=(UI_FONT, max(9, n - 11)), foreground="#79839a",
                               spacing3=2)
        self.txt.tag_configure("src", font=(UI_FONT, max(9, n - 12)), foreground="#8b93a5")
        self._render()

    def bump_font(self, d):
        self.set_font_size(self.font_size + d)
        self.app.on_overlay_font(self.font_size)

    def bump_size(self, dw: int, dh: int):
        """用按钮改浮窗大小（拖右下角在 macOS 上不一定灵，这个保险）"""
        try:
            w = max(240, self.win.winfo_width() + dw)
            h = max(80, self.win.winfo_height() + dh)
            self.win.geometry(f"{w}x{h}+{self.win.winfo_x()}+{self.win.winfo_y()}")
            self.app.s["overlay_geometry"] = self.win.geometry()
        except Exception as e:
            print(f"[overlay] 改大小失败：{e}")

    def set_font_size(self, n):
        self.font_size = max(10, min(64, int(n)))
        self._apply_fonts()

    def toggle_src(self):
        self.show_src = not self.show_src
        self.app.s["overlay_show_src"] = self.show_src
        self._render()

    def add(self, src: str, tgt: str):
        self.items.append((src, tgt))
        self._render()

    def _render(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        for s, t in list(self.items)[:-1]:
            self.txt.insert("end", (t or "") + "\n", "prev")
        if self.items:
            s, t = self.items[-1]
            if self.show_src:
                self.txt.insert("end", (s or "") + "\n", "src")
            self.txt.insert("end", (t or "…") + "\n", "cur")
        self.txt.configure(state="disabled")

    def close(self):
        try:
            self.app.s["overlay_geometry"] = self.win.geometry()
        except Exception:
            pass
        self.win.destroy()
        self.app.overlay = None
        self.app.b_overlay.configure(text="弹出字幕浮窗")


def main():
    import tkinter as tk
    root = tk.Tk()
    app = App(root)
    if "--hidden" in sys.argv or "--smoke" in sys.argv:
        root.withdraw()          # 自检时不弹窗（用户可能在打游戏/忙别的）
    if "--smoke" in sys.argv:
        secs = 20.0
        i = sys.argv.index("--smoke")
        if len(sys.argv) > i + 1:
            try:
                secs = float(sys.argv[i + 1])
            except ValueError:
                pass
        app.start()
        root.after(int(secs * 1000), lambda: (app.stop(quiet=True),
                                              _smoke_report(app.lines_seen),
                                              sys.exit(0 if app.lines_seen else 2)))
    root.mainloop()


def _smoke_report(n: int):
    """自检结果写文件而不是 print：打包成 --windowed 后 sys.stdout 是 None，print 会炸"""
    try:
        p = HERE / "logs"
        p.mkdir(parents=True, exist_ok=True)
        (p / "smoke_result.txt").write_text(f"SMOKE lines={n}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
