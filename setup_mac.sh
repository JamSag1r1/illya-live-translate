#!/usr/bin/env bash
# macOS 一键准备：装依赖 → 建环境 → 检查模型 → 告诉你下一步怎么跑
#
#   bash setup_mac.sh
#
# 两种装法：
#   1) Homebrew 能用  → brew install python@3.12 python-tk@3.12 ffmpeg + .venv
#   2) Homebrew 不可用 → 用已有的 conda（conda-forge 的 ffmpeg + python）
#      （常见于新版 macOS：Homebrew 太旧会报 unknown or unsupported macOS version）
set -u
cd "$(dirname "$0")"
say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }
die() { printf '\n\033[1;31m[x] %s\033[0m\n' "$1"; exit 1; }

BREW_OK=0
USE_CONDA=0
PY=""
RUNPY=""

say "1/5 检查 Homebrew"
if command -v brew >/dev/null 2>&1; then
  if brew --version >/dev/null 2>&1; then
    BREW_OK=1
    echo "ok: $(brew --version | head -1)"
  else
    echo "[!] brew 跑不起来。若报 'unknown or unsupported macOS version'，是 Homebrew 太旧不认识你的系统版本。"
    echo "    修法：brew update-reset"
    echo "    还不行：cd /opt/homebrew && git fetch origin && git reset --hard origin/master && cd -"
  fi
else
  echo "[!] 没装 Homebrew"
fi

if [ "$BREW_OK" = "1" ]; then
  say "2/5 安装 python + tkinter + ffmpeg（已装会自动跳过）"
  brew install python@3.12 python-tk@3.12 ffmpeg || die "brew install 失败，把上面的输出贴回来"
  PY="$(brew --prefix)/bin/python3.12"
  [ -x "$PY" ] || PY="$(command -v python3.12)"
  [ -n "$PY" ] || die "找不到 python3.12"
elif command -v conda >/dev/null 2>&1; then
  say "2/5 Homebrew 不可用 → 改用 conda（conda-forge）"
  USE_CONDA=1
  conda create -y -n livetrans python=3.12 || die "conda create 失败，把输出贴回来"
  CONDA_BASE="$(conda info --base)"
  PY="$CONDA_BASE/envs/livetrans/bin/python"
  [ -x "$PY" ] || die "conda 环境建好了但找不到 python：$PY"
  conda install -y -n livetrans -c conda-forge ffmpeg || echo "[!] ffmpeg 没装上：抓直播间模式会用到它（可以后补）"
else
  die "Homebrew 跑不起来，也没找到 conda。二选一：
  A) 修 Homebrew： brew update-reset   （还不行就 cd /opt/homebrew && git fetch origin && git reset --hard origin/master）
  B) 装 Miniforge/Anaconda 后重跑本脚本"
fi

say "3/5 安装 Python 依赖"
if [ "$USE_CONDA" = "1" ]; then
  "$PY" -m pip install -q -U pip
  "$PY" -m pip install -q -r requirements.txt || die "pip 装依赖失败（贴输出）"
  RUNPY="$PY"
else
  [ -d .venv ] || "$PY" -m venv .venv
  ./.venv/bin/python -m pip install -q -U pip
  ./.venv/bin/pip install -q -r requirements.txt || die "pip 装依赖失败（贴输出）"
  RUNPY="./.venv/bin/python"
fi
echo "ok: $("$RUNPY" -V)"

say "4/5 检查 tkinter 与 ffmpeg"
"$RUNPY" - <<'PY' || echo "[!] tkinter 不可用：conda 用户 conda install -c conda-forge tk；brew 用户 brew install python-tk@3.12 后用 Homebrew 的 python 重建 .venv"
import shutil
try:
    import tkinter  # noqa: F401
    print("tkinter ok")
except Exception as e:
    print("tkinter 缺失:", e)
    raise SystemExit(1)
print("ffmpeg:", shutil.which("ffmpeg") or "（PATH 里没有；抓直播间模式需要它）")
PY

say "5/5 检查模型目录"
if [ -d models ] && [ -n "$(ls -A models 2>/dev/null)" ]; then
  echo "已有模型："; ls -1 models | sed 's/^/  /'
else
  mkdir -p models
  cat <<'EOT'
models/ 还是空的。可以：
  · 识别模型：直接跑就行，第一次会问你要不要从魔搭 ModelScope 下载（small 约 460 MB）
  · 本地翻译模型（想离线翻译才需要）：把 Windows 机器上的
      models/nllb-200-distilled-600M-ct2
    整个文件夹拷过来（约 620 MB）；只想用云端 API 就不用它
EOT
fi

cat <<EOT

== 准备完成，接下来 ==

抓直播间（最省事，不需要虚拟声卡）：
  $RUNPY live_translate.py --url https://live.bilibili.com/<房间号> --src ja --device cpu --model-size small
  大字幕：浏览器打开 http://127.0.0.1:8777

图形界面：
  $RUNPY live_gui.py            # 声音来源选「抓直播间网址」

抓系统声音（需要 BlackHole，步骤见 docs/MACOS.md）：
  $RUNPY live_translate.py --list-input-devices            # 看音频设备序号
  $RUNPY live_translate.py --input-device ":1" --src ja --device cpu --model-size small
EOT
