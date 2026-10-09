#!/usr/bin/env python3
"""一键打 Windows 便携包（以后发新版就靠它）。

    python tools/build_windows_package.py --dry-run        # 只打印会做什么，不真跑
    python tools/build_windows_package.py                  # 真打：exe + 便携 zip
    python tools/build_windows_package.py --with-model     # 顺便把本地翻译模型也塞进包（zip 会大 ~600 MB）

做四件事：
  1) PyInstaller 打 exe（那些 --collect-all / --exclude 参数就是 DEV-NOTES 里那套）
  2) 把 ffmpeg.exe 拷进去
  3) 清掉包内 gui_settings.json 里的 api_key（绝不能把 key 发出去）
  4) 用 make_portable_zip.py 压成 zip，并打印 gh 上传命令

注意：模型默认**不**塞进包（识别模型让用户首次运行时自己下）；--with-model 才带上本地翻译模型。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # 项目根目录
PY = sys.executable                                    # 用当前解释器（须先装 pyinstaller）
DIST = "live-translate-gui"
PKG_ROOT = "Illya-live-translate-tools"

PYINSTALLER_ARGS = [
    "--noconfirm", "--clean", "--windowed", "--name", DIST,
    "--collect-all", "ctranslate2", "--collect-all", "faster_whisper",
    "--collect-all", "onnxruntime", "--collect-all", "tokenizers",
    "--collect-all", "av", "--collect-all", "pyaudiowpatch",
    "--collect-all", "sentencepiece",
    # 这两个是 ctranslate2 转换模型时才用的，运行端不需要，带上会白胖 600 MB
    "--exclude-module", "torch", "--exclude-module", "transformers",
    "--exclude-module", "tensorflow", "--exclude-module", "sympy",
    "--exclude-module", "matplotlib",
]


def run(cmd: list[str], dry: bool, **kw):
    print("  $ " + " ".join(str(c) for c in cmd))
    if dry:
        return 0
    return subprocess.call(cmd, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印步骤")
    ap.add_argument("--with-model", action="store_true",
                    help="把 models/nllb-200-distilled-600M-ct2 也塞进包（离线翻译用）")
    ap.add_argument("--out", default=str(HERE / "Illya-live-translate-tools-portable.zip"))
    a = ap.parse_args()
    dry = a.dry_run

    print("== 0/4 环境检查 ==")
    try:
        import PyInstaller  # noqa: F401
        print("  pyinstaller ok")
    except ImportError:
        print("  [!] 没装 pyinstaller：先跑  pip install pyinstaller")
        if not dry:
            return 1
    for f in ("ffmpeg.exe", "live_gui.py", "stream_source.py", "live_translate.py"):
        p = HERE / f
        print(f"  {'ok ' if p.exists() else '[!]'} {f}")
    if not (HERE / "ffmpeg.exe").exists() and not dry:
        print("  [!] 缺 ffmpeg.exe：便携包要用它抓直播流，放一个到项目根目录再跑")
        return 1

    print("== 1/4 PyInstaller 打 exe（约 3-5 分钟）==")
    # nvidia 的 DLL 从"当前解释器的 site-packages"里找（别写死 .venv 路径，换个目录跑就对不上）
    import sysconfig
    nvidia = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    args = [PY, "-m", "PyInstaller", *PYINSTALLER_ARGS]
    if nvidia.is_dir():
        args += ["--add-data", f"{nvidia};nvidia"]
    else:
        print(f"  [i] 没找到 {nvidia}（没装 nvidia-cublas/cudnn 就是纯 CPU 版，正常）")
    args += ["--distpath", str(HERE), "--workpath", str(HERE / "build_tmp"),
             "--specpath", str(HERE / "build_tmp"), "--paths", str(HERE / "tools"),
             "--paths", str(HERE), "live_gui.py"]
    if run(args, dry, cwd=str(HERE)) not in (0, None) and not dry:
        print("[x] PyInstaller 失败，把上面的输出发出来")
        return 1

    print("== 2/4 组装目录（exe + ffmpeg.exe + 模型）==")
    stage = HERE / "_pkg" / PKG_ROOT
    if not dry:
        shutil.rmtree(HERE / "_pkg", ignore_errors=True)
        (stage / "models").mkdir(parents=True, exist_ok=True)
        shutil.copytree(HERE / DIST, stage / DIST)
        shutil.rmtree(stage / DIST / "logs", ignore_errors=True)
        shutil.copy2(HERE / "ffmpeg.exe", stage / DIST / "ffmpeg.exe")
        for extra in ("README-portable.txt",):
            if (HERE / extra).exists():
                shutil.copy2(HERE / extra, stage / DIST / extra)
        if a.with_model:
            src = HERE / "models" / "nllb-200-distilled-600M-ct2"
            if src.is_dir():
                shutil.copytree(src, stage / "models" / src.name)
                print(f"  + 模型 {src.name}")
            else:
                print(f"  [!] 没找到 {src}，跳过模型")
        else:
            print("  （没带本地翻译模型：--with-model 才会带）")

    print("== 3/4 清掉包内 key ==")
    settings = stage / DIST / "gui_settings.json"
    if dry:
        print(f"  $ 把 {settings.name} 里的 api_key 置空")
    else:
        try:
            d = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
            d.update({"api_key": "", "trans_mode": "本地模型", "model": "small",
                      "source": "抓系统声音（扬声器里放什么就翻什么）", "url": "", "console": False})
            settings.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ok: api_key = {settings and d['api_key']!r}")
        except Exception as e:
            print(f"  [!] 写设置失败：{e}")

    print("== 4/4 压成 zip ==")
    run([PY, str(HERE / "tools" / "make_portable_zip.py"),
         "--src", str(HERE / "_pkg"), "--out", a.out], dry, cwd=str(HERE))

    if not dry:
        z = Path(a.out)
        if z.is_file():
            size_gib = z.stat().st_size / 2 ** 30
            flag = "✓ 在 GitHub 单附件上限（2 GiB）之内" if size_gib < 2 else "✗ 超过 2 GiB，得再瘦身"
            print(f"\n[ok] {z}  {size_gib:.2f} GiB  {flag}")
            print("\n下一步（发新版）：")
            print(f'  gh release create vX.Y.Z --repo <owner>/<repo> --title "..." --notes-file <说明.md> \\')
            print(f'      --target main --latest "{z}"')
            print("  大文件上传用 tools/../release-assets 里那套 python 脚本更稳（gh 直传容易 EOF），见 docs/DEV-NOTES.md")
        else:
            print("[x] 没生成 zip，看上面的输出")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
