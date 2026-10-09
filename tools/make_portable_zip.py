#!/usr/bin/env python3
"""把 live-translate-gui\\ + models\\ 打成便携 zip。

    python tools/make_portable_zip.py                 # 打包到项目根目录
    python tools/make_portable_zip.py --out D:/x.zip  # 指定输出

包里保持这个相对结构（exe 会从自己所在目录往上找 models\\，别改动层级）：

    Illya-live-translate-tools/live-translate-gui/...   exe + _internal + ffmpeg + 设置
    Illya-live-translate-tools/models/...               本地翻译模型 + 识别模型

用标准库 zipfile + deflate：bsdtar 的 `-a` 对 .zip 是“存储”模式（实测 3.5 GB 原样塞进去，不压缩）。
"""
import argparse
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT_NAME = "Illya-live-translate-tools"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "Illya-live-translate-tools-portable.zip"))
    ap.add_argument("--src", default=str(HERE / "_pkg"), help=f"暂存目录（里面要有 {ROOT_NAME}\\）")
    ap.add_argument("--level", type=int, default=6, help="deflate 等级 0-9")
    a = ap.parse_args()

    src = Path(a.src) / ROOT_NAME
    if not src.is_dir():
        sys.exit(f"没找到暂存目录：{src}")
    files = sorted(p for p in src.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"[zip] {len(files)} 个文件 / {total / 2**30:.2f} GB → {a.out}", flush=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0, done = time.time(), 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=a.level) as z:
        for n, p in enumerate(files, 1):
            z.write(p, arcname=f"{ROOT_NAME}/{p.relative_to(src).as_posix()}")
            done += p.stat().st_size
            if n % 300 == 0 or n == len(files):
                print(f"  {n}/{len(files)}  已处理 {done / 2**30:.2f}/{total / 2**30:.2f} GB  "
                      f"{time.time() - t0:.0f}s", flush=True)
    print(f"[zip] 完成：{out}  {out.stat().st_size / 2**30:.2f} GB，用时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
