#!/usr/bin/env python3
"""从 ModelScope（国内可达）下载 faster-whisper 模型到本地 models/ 目录。

huggingface.co 与其 xet 存储在这台机器上不可达，所以走魔搭镜像：
    pengzhendong/faster-whisper-{tiny,base,small,medium,large-v3,large-v3-turbo}
"""
from __future__ import annotations      # 让 Path | None 这类写法在 Python 3.9 上也能跑

import argparse
import sys
import time
from pathlib import Path

import requests

API = "https://modelscope.cn/api/v1/models/{repo}/repo?Revision=master&FilePath={fn}"
FILES = ["model.bin", "config.json", "tokenizer.json",
         "vocabulary.txt", "vocabulary.json", "preprocessor_config.json"]
HERE = Path(__file__).resolve().parent.parent
DEST = HERE / "models"


def get(url, **kw):
    return requests.get(url, timeout=30, **kw)


def human(n):
    return f"{n/1e9:.2f} GB" if n > 1e9 else f"{n/1e6:.1f} MB"


def fetch(size: str, repo_ns: str = "pengzhendong", dest: Path | None = None) -> Path:
    repo = f"{repo_ns}/faster-whisper-{size}"
    out = (dest or DEST) / f"faster-whisper-{size}"
    out.mkdir(parents=True, exist_ok=True)

    r = get(API.format(repo=repo, fn="model.bin"), stream=True)
    if r.status_code != 200 or "octet-stream" not in r.headers.get("Content-Type", ""):
        print(f"[x] 魔搭上没有 {repo}（试试 --size small / medium / large-v3）")
        sys.exit(1)
    total = int(r.headers.get("Content-Length", 0))
    r.close()
    print(f"[model] {repo}  model.bin = {human(total)}")

    for fn in FILES:
        path = out / fn
        if fn != "model.bin" and path.is_file() and path.stat().st_size > 100:
            print(f"  = {fn} 已存在")
            continue
        tmp = path.with_suffix(path.suffix + ".part")
        have = tmp.stat().st_size if tmp.exists() else 0
        if fn == "model.bin" and path.is_file() and path.stat().st_size == total:
            print(f"  = {fn} 已完整")
            continue
        headers = {"Range": f"bytes={have}-"} if have else {}
        t0 = time.time()
        prev_decile = -1
        with get(API.format(repo=repo, fn=fn), stream=True, headers=headers) as r:
            if r.status_code != 200 and r.status_code != 206:
                # 404 通常只是这个仓库没有这个文件（large-v3 用 vocabulary.json 而不是 vocabulary.txt）
                print(f"  - {fn} 不在该仓库（HTTP {r.status_code}），跳过")
                continue
            mode = "ab" if (have and r.status_code == 206) else "wb"
            if mode == "wb":
                have = 0
            done = have
            with open(tmp, mode) as f:
                for chunk in r.iter_content(1 << 18):
                    f.write(chunk)
                    done += len(chunk)
                    if fn == "model.bin":
                        el = time.time() - t0
                        pct = done / total * 100 if total else 0
                        if int(pct // 10) != prev_decile or pct >= 100:
                            prev_decile = int(pct // 10)
                            sp = (done - have) / 1e6 / max(el, .01)
                            print(f"  ↓ model.bin {pct:5.1f}%  {human(done)} / {human(total)}"
                                  f"  {sp:5.2f} MB/s  ETA {(total-done)/max(sp*1e6,.01):5.0f}s")
        tmp.replace(path)
        if fn != "model.bin":
            print(f"  + {fn}")
    print(f"[model] 就绪: {out}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="small",
                    help="tiny/base/small/medium/large-v3/large-v3-turbo")
    ap.add_argument("--namespace", default="pengzhendong")
    fetch(ap.parse_args().size, ap.parse_args().namespace)
