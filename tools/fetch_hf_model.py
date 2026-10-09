#!/usr/bin/env python3
"""从魔搭镜像下载 HuggingFace 格式的模型仓库（huggingface.co 在这台机器上不通）。

    python tools/fetch_hf_model.py facebook/nllb-200-distilled-600M --dest models/nllb-600M-hf
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

API = "https://modelscope.cn/api/v1/models/{repo}/repo?Revision=master&FilePath={fn}"
LIST = "https://modelscope.cn/api/v1/models/{repo}/repo/files?Revision=master"
WANT_HINT = (".bin", ".safetensors", ".json", ".model", ".txt", ".spm")


def human(n):
    return f"{n/1e9:.2f} GB" if n > 1e9 else f"{n/1e6:.1f} MB"


def list_files(repo: str):
    r = requests.get(LIST.format(repo=repo), timeout=30)
    r.raise_for_status()
    files = (r.json().get("Data") or {}).get("Files") or []
    return [(f["Path"], f.get("Size") or 0) for f in files]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="魔搭上的仓库，如 facebook/nllb-200-distilled-600M")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--include", default=None, help="只下含这些子串的文件，逗号分隔")
    a = ap.parse_args()
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)

    files = list_files(a.repo)
    if a.include:
        keys = [k.strip() for k in a.include.split(",")]
        files = [f for f in files if any(k in f[0] for k in keys)]
    files = [f for f in files if f[0].endswith(WANT_HINT)]
    print(f"[hf] {a.repo}: 需要 {len(files)} 个文件，共 {human(sum(s for _, s in files))}")

    for fn, size in files:
        out = dest / fn
        if out.is_file() and out.stat().st_size == size:
            print(f"  = {fn} 已完整")
            continue
        tmp = out.with_suffix(out.suffix + ".part")
        have = tmp.stat().st_size if tmp.exists() else 0
        if have > size:
            have = 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        t0 = time.time()
        with requests.get(API.format(repo=a.repo, fn=fn), stream=True, timeout=60,
                          headers=headers) as r:
            if r.status_code not in (200, 206):
                print(f"  [x] {fn} HTTP {r.status_code}")
                continue
            mode = "ab" if (have and r.status_code == 206) else "wb"
            if mode == "wb":
                have = 0
            done = have
            dec = -1
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, mode) as f:
                for chunk in r.iter_content(1 << 18):
                    f.write(chunk)
                    done += len(chunk)
                    if size > 5e7:
                        pct = done / size * 100 if size else 0
                        if int(pct // 10) != dec:
                            dec = int(pct // 10)
                            sp = (done - have) / 1e6 / max(time.time() - t0, .01)
                            print(f"  ↓ {fn} {pct:5.1f}% {human(done)}/{human(size)} "
                                  f"{sp:5.2f} MB/s")
        tmp.replace(out)
        if size <= 5e7:
            print(f"  + {fn} ({human(size)})")
    print(f"[hf] 完成: {dest}")


if __name__ == "__main__":
    main()
