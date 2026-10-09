#!/usr/bin/env bash
# macOS 一键准备：装依赖 → 建虚拟环境 → 拉模型（可选）→ 告诉你下一步怎么跑
# 用法：  bash setup_mac.sh
set -u
cd "$(dirname "$0")"
say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }
die() { printf '\n\033[1;31m[x] %s\033[0m\n' "$1"; exit 1; }

say "1/5 检查 Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  die "没装 Homebrew。先跑这一行（官网 https://brew.sh）：
  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
fi
echo "ok: $(brew --version | head -1)"

say "2/5 安装 python + tkinter + ffmpeg（已装会自动跳过）"
brew install python@3.12 python-tk@3.12 ffmpeg || die "brew install 失败，把上面的输出贴给我"
PY="$(brew --prefix)/bin/python3.12"
[ -x "$PY" ] || PY="$(command -v python3.12)"
[ -n "$PY" ] || die "找不到 python3.12"

say "3/5 建虚拟环境 .venv 并装依赖"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/python -m pip install -q -U pip
./.venv/bin/pip install -q -r requirements.txt || die "pip 装依赖失败（贴输出）"
echo "ok: $(./.venv/bin/python -V)"

say "4/5 检查 ffmpeg 与 tkinter"
./.venv/bin/python - <<'PY' || die "tkinter 不可用：brew install python-tk@3.12 后用 /opt/homebrew/bin/python3.12 重建 .venv"
import tkinter, shutil
print("tkinter ok, ffmpeg:", shutil.which("ffmpeg") or "（PATH 里没有，抓直播间会需要它）")
PY

say "5/5 检查模型目录"
if [ -d models ] && [ -n "$(ls -A models 2>/dev/null)" ]; then
  echo "已有模型："; ls -1 models | sed 's/^/  /'
else
  mkdir -p models
  cat <<'EOT'
models/ 还是空的。可以做：
  · 识别模型：直接跑起来就行，第一次会问你要不要从魔搭下载（small 约 460 MB）
  · 本地翻译模型（想离线翻译才需要）：把 Windows 机器上的
      models/nllb-200-distilled-600M-ct2
    整个文件夹拷过来（约 620 MB）
EOT
fi

cat <<'EOT'

== 准备完成，接下来 ==

抓直播间（最省事，不需要虚拟声卡）：
  ./.venv/bin/python live_translate.py --url https://live.bilibili.com/<房间号> \
      --src ja --device cpu --model-size small
  大字幕：浏览器打开 http://127.0.0.1:8777

图形界面：
  ./.venv/bin/python live_gui.py        # 声音来源选「抓直播间网址」

抓系统声音（要 BlackHole，步骤见 docs/MACOS.md）：
  ./.venv/bin/python live_translate.py --list-input-devices     # 看音频设备序号
  ./.venv/bin/python live_translate.py --input-device ":1" --src ja --device cpu --model-size small
EOT
