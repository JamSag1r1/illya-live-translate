#!/usr/bin/env python3
"""测转写速度：给一个音频文件，报出 RTF（转写耗时 / 音频时长）。"""
import argparse, subprocess, sys, time, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent.parent


def load_wav16k(path: Path) -> np.ndarray:
    tmp = path.with_suffix(".16k.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
                    "-ac", "1", "-ar", "16000", str(tmp)], check=True)
    with wave.open(str(tmp), "rb") as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return a


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--model", default=str(HERE / "models/faster-whisper-small"))
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--prompt", default=None, help="术语提示（initial_prompt）")
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    t0 = time.time()
    m = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=a.threads, num_workers=1)
    print(f"load {time.time()-t0:.1f}s")

    audio = load_wav16k(Path(a.audio))
    dur = len(audio) / 16000
    print(f"audio {dur:.2f}s  model={Path(a.model).name} threads={a.threads}")
    worst = 0
    for i in range(a.repeat):
        t0 = time.time()
        segs, info = m.transcribe(audio, language=a.lang, beam_size=1, temperature=0.0,
                                  vad_filter=False, condition_on_previous_text=False,
                                  initial_prompt=a.prompt)
        text = " ".join(s.text.strip() for s in segs)
        dt = time.time() - t0
        worst = max(worst, dt)
        print(f"  run{i+1}: {dt:.2f}s  RTF={dt/dur:.3f}  lang={info.language}")
        print(f"  → {text}")
    print(f"最慢 {worst:.2f}s → 实时倍率 {worst/dur:.3f}（<1 才跟得上直播）")
