#!/usr/bin/env python3
"""把同一个目录里的 wav 段用多个模型各转一遍，并排打印 + 计时。
用来判断「换模型到底能提多少准确度」，拿用户真实音频比最靠谱。

    python tools/compare_models.py <wav目录> --models small,medium,large-v3 --lang ja [--prompt "..."]
"""
import argparse
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent


def load16k(path: Path) -> np.ndarray:
    tmp = path.with_suffix(".16k.wav")
    if not tmp.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
                        "-ac", "1", "-ar", "16000", str(tmp)], check=True)
    with wave.open(str(tmp), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wavdir")
    ap.add_argument("--models", default="small,medium")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    import sys as _sys
    _sys.path.insert(0, str(HERE))
    from live_translate import enable_cuda_dlls
    if a.device == "cuda":
        print(f"[cuda] 注入 {enable_cuda_dlls()} 个 nvidia DLL 目录")
    wavs = sorted(Path(a.wavdir).glob("*.wav"))
    wavs = [w for w in wavs if ".16k." not in w.name]
    audio = [(w.name, load16k(w)) for w in wavs]
    total = sum(len(x) / 16000 for _, x in audio)
    print(f"{len(audio)} 段 / 共 {total:.1f}s   prompt={'有' if a.prompt else '无'}\n")

    for name in a.models.split(","):
        path = str(HERE / f"models/faster-whisper-{name}") if not Path(name).is_dir() else name
        ct = "float16" if a.device == "cuda" else "int8"
        t0 = time.time()
        m = WhisperModel(path, device=a.device, compute_type=ct,
                         cpu_threads=a.threads if a.device == "cpu" else 1)
        load_s = time.time() - t0
        print(f"── {name} ({a.device}/{ct}) 加载 {load_s:.1f}s ──")
        t0 = time.time()
        for fname, x in audio:
            segs, _ = m.transcribe(x, language=a.lang, beam_size=1, temperature=0.0,
                                   vad_filter=False, condition_on_previous_text=False,
                                   initial_prompt=a.prompt)
            txt = "".join(s.text.strip() for s in segs)
            print(f"  [{fname[:14]}] {txt}")
        dt = time.time() - t0
        print(f"  → 合计 {dt:.1f}s  实时倍率 {dt/total:.3f}  平均每段 {dt/len(audio):.0f}ms\n")


if __name__ == "__main__":
    main()
