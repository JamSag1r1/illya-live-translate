# 在 macOS 上运行

代码本身是跨平台的，只有"抓系统正在播放的声音"那部分原来用的是 Windows 专属的 WASAPI 环回。
macOS 上换成 **ffmpeg 的 avfoundation + BlackHole 虚拟声卡**，接口和原来一样。

> ⚠️ 诚实声明：macOS 这条路径是照 ffmpeg 官方用法写的（`-f avfoundation -i ":<音频序号>"`），
> 但**开发机是 Windows，没有在真机上跑过**。哪一步报错，把终端输出贴回来就能修。

## 三种声音来源，在 macOS 上分别是什么情况

| 界面选项 | macOS | 说明 |
|---|---|---|
| 抓系统声音 | ❌ | WASAPI 环回是 Windows 专属，macOS 不启用这一项 |
| **抓直播间网址** | ✅ | 用 ffmpeg 直接拉 B 站直播流，不需要任何录音设备（**推荐先试这个**） |
| **抓音频输入设备** | ✅ | 装 BlackHole 后，用 `--input-device ":<序号>"` 抓系统声音 |

识别、翻译、字幕页、浮窗这些在 macOS 上都正常；CTranslate2 在 macOS 上没有 Metal 后端，走 CPU。

## 一次性准备

```bash
# 1) 依赖（Homebrew 没装的话先装 https://brew.sh）
brew install python@3.12 python-tk@3.12 ffmpeg

# 2) 进入项目目录（从 Windows 那边拷过来的，或者 git clone 的）
cd /path/to/illya-live-translate

# 3) 虚拟环境 + 依赖
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 4) 模型（见下一节）
```

## 模型从哪来

- **识别模型**（必须）：第一次运行时会自动从魔搭 ModelScope 下载到 `models/`
  （`small` 约 460 MB，国内可直连）。也可以直接从 Windows 那台机器把 `models/faster-whisper-small`
  整个文件夹拷过来，省一次下载。
- **本地翻译模型**（想离线翻译才需要）：`models/nllb-200-distilled-600M-ct2`（约 620 MB）。
  两个来源：
  1. 从 Windows 机器拷 `models/nllb-200-distilled-600M-ct2` 过来（最快）；
  2. 或者下载 GitHub Release 里那个安装包（2 GB），从里面把 `Illya-live-translate-tools/models/`
     解压出来用（exe 部分在 Mac 上没用）。
  不想用本地翻译也可以：界面里选「云端 API」填自己的 DeepSeek Key，或者用本机 Ollama。

## 跑起来

### A. 抓直播间（最简单，不需要 BlackHole）

```bash
./.venv/bin/python live_translate.py --url https://live.bilibili.com/<房间号> \
    --src ja --device cpu --model-size small --port 8777
```

大字幕在浏览器里看 `http://127.0.0.1:8777`（原文小灰字、译文大字、自动滚动）。
图形界面：`./.venv/bin/python live_gui.py`，声音来源选「抓直播间网址」。

### B. 抓系统声音（BlackHole）

1. 装 BlackHole：`brew install blackhole-2ch`（或官网下载安装）
2. 打开「音频 MIDI 设置」→ 左下角「+」→ **创建多输出设备** → 勾上你的扬声器 **和** BlackHole 2ch
   （这样你还能听见声音，同时程序也能收到）
3. 系统输出切到这个多输出设备
4. 看 ffmpeg 认到的音频设备序号：

   ```bash
   ./.venv/bin/python live_translate.py --list-input-devices
   ```

   输出里音频设备长这样（序号就是中括号里的数字）：
   ```
   [1] BlackHole 2ch
   ```
5. 跑（avfoundation 的写法是 `<视频>:<音频>`，不抓视频就留空）：

   ```bash
   ./.venv/bin/python live_translate.py --input-device ":1" \
       --src ja --device cpu --model-size small
   ```

   图形界面里选「抓音频输入设备」，设备那一格填 `:1`。

> macOS 会问"要不要允许终端/程序访问麦克风"——**要点允许**（BlackHole 是通过录音通道进来的）。

## 性能预期（CPU）

| 识别模型 | macOS 上的表现 |
|---|---|
| `small` | 够用，跟得上直播 ✓ |
| `medium` | 更准，CPU 上大概还跟得上 |
| `large-v3` | 太慢，不要用于直播（Windows 上有 N 卡才建议） |

本地翻译模型（NLLB CT2）在 CPU 上每句几十毫秒到一两百毫秒，够用。

## 打包成 .app（可选）

PyInstaller **不能跨平台编译**——.app 必须在 Mac 上打：

```bash
./.venv/bin/pip install pyinstaller
./.venv/bin/pyinstaller --noconfirm --windowed --name live-translate-gui \
    --collect-all ctranslate2 --collect-all faster_whisper --collect-all onnxruntime \
    --collect-all tokenizers --collect-all av --collect-all sentencepiece \
    live_gui.py
```

（Windows 上那套多带了 `--add-data nvidia` 和 `--collect-all pyaudiowpatch`，Mac 上不需要。）
日常用其实**直接跑源码就够**（`./.venv/bin/python live_gui.py`），省得每次重打。

## 常见问题

- **`brew` 报 `unknown or unsupported macOS version: "26.x"`**（Homebrew 太旧，不认识你的系统版本 → 所有
  brew 命令都跑不起来，包括 `brew update`）：两种方案
  1. **更新 Homebrew 自己**（推荐先试）：`brew update-reset`；
     不行就手动 `cd /opt/homebrew && git fetch origin && git reset --hard origin/master && cd -`，
     然后 `brew --version` 验证
  2. **绕开 Homebrew，用 conda**：
     ```bash
     conda create -y -n livetrans python=3.12 && conda activate livetrans
     conda install -y -c conda-forge ffmpeg
     pip install -r requirements.txt
     ```
- **`git clone` / `git fetch` 报 `Error in the HTTP2 framing layer`**（或连不上 github.com）：国内网络问题。
  给 Mac 挂上代理后让 git 也走代理 `git config --global http.proxy http://127.0.0.1:7890`（端口按实际改）；
  或者直接手动拷贝源码文件覆盖（最常改的是 `live_gui.py`）
- **以前 clone 过，`git pull` 报 diverged / non-fast-forward**：仓库历史被重写过一次（去掉了某条提交里的
  私人邮箱）。执行 `git fetch origin && git reset --hard origin/main` 对齐一次，以后 `pull` 就正常了
- **界面里没有「抓系统声音」**：正常，Windows 专属；macOS 用「抓直播间网址」或「抓音频输入设备」
- **浮窗拖右下角 `◢` 不好使**：用浮窗顶部的 `宽 −` `宽 ＋` `高 −` `高 ＋` 按钮
- **`没找到 ffmpeg`** → `brew install ffmpeg`；或者 `export LIVE_TRANSLATE_FFMPEG=$(which ffmpeg)`
- **`ModuleNotFoundError: No module named 'tkinter'`** → `brew install python-tk@3.12`，然后用 Homebrew 的
  python 建 venv（`/opt/homebrew/bin/python3.12 -m venv .venv`）
- **设备抓不到声音** → `--list-input-devices` 看序号对不对；确认系统输出切到了「多输出设备」；
  确认给了麦克风权限（系统设置 → 隐私与安全性 → 麦克风）
- **`[x] 这台系统没有 WASAPI 环回可抓`** → 选「抓直播间网址」，或用 `--input-device`
- **直播拉不到流** → 房间没开播 / 需要登录；代码会自动重连 10 次
