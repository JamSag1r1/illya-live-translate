# Illya's live-translate tools

> **本软件由 千禧年科技の纱雾（B站同名）与其 Hermes 助手 Illya 完成，完全开源。**
> 仅供学习交流，请勿商用，一切后果自负。

## 下载就能用（预编译包）

**[➜ 点这里去 Releases 下载](../../releases/latest)** —— 约 **2.0 GB**，内含离线翻译模型，解压即用。

1. 下载 `Illya-live-translate-tools-vX.X.zip`
2. 解压到任意目录（例如 `D:\IllyaTranslate`）——**保持 `live-translate-gui\` 和 `models\` 两个文件夹同级**
3. 双击 `live-translate-gui\live-translate-gui.exe` → 选好参数 → 点「▶ 开始翻译」

- **默认离线可用**：本地翻译模型已经随包自带，断网也能出中文字幕
- 第一次选某个识别模型时，程序会弹窗告诉你多大、要不要下载（`small` 约 460 MB，从魔搭 ModelScope 下，下过一次就不再下）
- 想要更好的翻译质量：在「翻译模型」里选「云端 API」，填自己的 DeepSeek API Key
- 系统要求：Windows 10/11 64 位；有 NVIDIA 显卡会自动用 GPU 加速（没有也能跑，识别模型选 `small` 即可）

> 中国大陆从 GitHub 下载大文件可能很慢；如果 Releases 打不开，用网盘备用链接：**<待补>**

## macOS 上怎么装（Mac 用户看这里）

上面那个预编译 zip 是 **Windows 专用**（里面的 `.exe` 在 Mac 上跑不了）。Mac 安装步骤为：

```bash
# 1) 依赖（Homebrew 没装的话先看 https://brew.sh）
brew install python@3.12 python-tk@3.12 ffmpeg

# 2) 拉代码 + 建环境（一键脚本，会自动装依赖并检查 tkinter / ffmpeg）
git clone https://github.com/JamSag1r1/illya-live-translate.git
cd illya-live-translate
bash setup_mac.sh

# 3) 跑起来（抓直播间，不需要虚拟声卡）
./.venv/bin/python live_translate.py --url https://live.bilibili.com/<房间号> \
    --src ja --device cpu --model-size small
# 大字幕：浏览器打开 http://127.0.0.1:8777
# 图形界面：./.venv/bin/python live_gui.py
```

- **识别模型**：第一次运行会问你要不要下载（`small` 约 460 MB，从魔搭 ModelScope 下，国内可直连）
- **想离线翻译**：把 Windows 机器上的 `models/nllb-200-distilled-600M-ct2`（约 620 MB）拷进 `models/` 即可
- **想抓"系统声音"**（不只是直播间）：装 BlackHole 虚拟声卡，再用 `--input-device ":<序号>"`
  （序号用 `./.venv/bin/python live_translate.py --list-input-devices` 看）——完整步骤见
  **[docs/MACOS.md](docs/MACOS.md)**
- Mac 上没有 NVIDIA 卡（CTranslate2 也没有 Metal 后端），识别模型建议 `small` / `medium`；
  `large-v3` 在 CPU 上跟不上直播

### macOS 常见问题

**① `brew` 报 `unknown or unsupported macOS version: "26.x"`**
（Homebrew 太旧、不认识你的系统版本 → **所有** brew 命令都这样，连 `brew update` 都跑不起来）

- **方案一（先试，一行）**：重新拉一遍 Homebrew 自己的代码
  ```bash
  brew update-reset
  ```
  还报错就手动更新：
  ```bash
  cd /opt/homebrew && git fetch origin && git reset --hard origin/master && cd -
  brew --version        # 能打印版本号就成了
  ```
- **方案二（绕开 Homebrew，用 conda）**：
  ```bash
  conda create -y -n livetrans python=3.12 && conda activate livetrans
  conda install -y -c conda-forge ffmpeg
  pip install -r requirements.txt
  ```

**② `git clone` / `git fetch` 报 `Error in the HTTP2 framing layer`（或连不上 github.com）**
国内网络问题，不是代码问题。要么给 Mac 也挂代理并让 git 走代理：
```bash
git config --global http.proxy http://127.0.0.1:7890     # 端口按你 Mac 上代理软件的改
```
要么干脆绕开 git：从别人那儿拷一份源码，覆盖掉需要更新的文件（最常变的就是 `live_gui.py`）。

**③ 界面里没有「抓系统声音」**
正常——那是 Windows 专属的 WASAPI 环回，macOS 上不显示。用「抓直播间网址」或「抓音频输入设备」。

**④ 浮窗拖右下角 `◢` 不能改大小**
用浮窗顶部那排按钮：`宽 −` `宽 ＋` `高 −` `高 ＋`（字号同理用 `字号 −` `字号 ＋`）。

**⑤ 以前 clone 过，`git pull` 提示 diverged / non-fast-forward**
仓库历史被重写过一次（去掉过一条提交里的私人邮箱）。对齐一次即可，以后 `pull` 正常：
```bash
git fetch origin && git reset --hard origin/main
```

## 更新记录

- **2026-10-09**　macOS 支持完成：
  - 新增 `--input-device`（走 ffmpeg，macOS `avfoundation` / Windows `dshow` / Linux `pulse`）与 `--list-input-devices`
  - 新增 [docs/MACOS.md](docs/MACOS.md) 与 `setup_mac.sh`（Homebrew 不可用时自动改用 conda）
  - `requirements.txt` 里 `pyaudiowpatch` 加平台标记 → macOS 上 `pip install -r requirements.txt` 不再失败
  - GUI：macOS 上隐藏「抓系统声音」并默认选「抓直播间网址」；界面字体按平台选（macOS 苹方 / Windows 雅黑）；
    字幕浮窗新增 `宽 − 宽 ＋ 高 − 高 ＋` 按钮；「打开字幕页」「打开记录文件夹」改为跨平台实现
- **2026-10-09**　v1.0.0：首个可下载版本（Windows 便携包，见 Releases）

## 开发 / 自己跑源码

给没有字幕的直播/视频做实时中文字幕：日语、英语、韩语 → 中文，延迟约 2 秒。

> Real-time Chinese subtitles for any live stream or video without captions.
> Local ASR (faster-whisper) + your choice of translation backend (cloud API / local NLLB / local Ollama).

- **音频不出本机**：识别全程本地推理（CUDA 或 CPU），只有转写出来的文字会发给你选的翻译后端
- **三选一翻译**：云端 DeepSeek（质量最好）/ 本地 NLLB-200（离线免费、只够听懂大意）/ 本机 Ollama 大模型
- **三种字幕呈现**：控制台、浏览器字幕页（自动滚动 / 可调字号 / 可扔副屏）、无边框置顶半透明浮窗
- **带图形界面**：tkinter 的 exe，不用碰命令行；能打包成便携包拷到别的电脑
- **有记录**：每场翻译落盘成 jsonl（原文 / 译文 / 耗时），方便复盘

实测（RTX 5070，large-v3）：识别 ~270 ms/句，云端翻译 ~0.6 s/句，本地 NLLB 翻译 50–90 ms/句。

## 怎么跑起来

```bash
# 1) 环境（Python 3.10+，实测 3.11）
uv venv --python 3.11 .venv
.venv/Scripts/activate          # Windows
uv pip install -r requirements.txt
uv pip install -r requirements-cuda.txt   # 可选：有 N 卡时装，走 GPU

# 2) 命令行最简用法（抓系统声音，日→中）
python live_translate.py --src ja

# 3) 图形界面
python live_gui.py
```

声音来源有两种：

- **抓系统声音**（默认）：扬声器里放什么就翻什么。浏览器放直播即可，别静音。
- **抓直播间网址**：`--url https://live.bilibili.com/<房间号>`，只抓这一路——你可以同时听别的音乐，甚至把网页静音。断流会自动重连。

翻译后端用 `--translator api|local|ollama` 切换；云端需要在界面里填一次 API Key（或设环境变量 `DEEPSEEK_API_KEY`、或放一个 `api_key.txt`）。

## 模型

仓库里**不含任何模型权重**（识别模型好几个 GB）。

- **识别模型**：首次使用时自动从魔搭 ModelScope 下载到 `models/`（huggingface 在国内不通，所以走镜像）。`small` 约 460 MB，`medium` 1.5 GB，`large-v3` 3.1 GB。
- **本地翻译模型**：需要把 NLLB-200 转成 CTranslate2 格式再用，转换脚本在 `tools/convert_mt_model.py`，步骤见 [docs/DEV-NOTES.md](docs/DEV-NOTES.md)。只想用云端 API 的话不需要它。
- **术语提示**：`--prompt "整句话，含专业词"` 能显著提高 Whisper 认专业名词的准确率（比词表有效）。

## 参数速查

```
--src ja|en|ko|zh|auto     待翻译语种（auto 会慢一倍）
--model-size small|medium|large-v3|...
--device auto|cuda|cpu     auto = 有 N 卡就用卡
--translator api|local|ollama
--url <直播间链接或房间号> 抓单路直播流，而不是系统声音
--merge-below 1.6          短于这个秒数的碎句先攒着合并（上下文更足）
--silence 0.45             静音多久算一句结束
--port 8777                字幕页端口
--no-web / --no-translate / --save-audio / --for 30
```

## 目录结构

```
live_translate.py     主流程：抓音 → VAD 切句 → Whisper 识别 → 翻译 → 输出
live_gui.py           图形界面（exe 入口），含浮窗、API Key 弹窗、模型下载确认
stream_source.py      B 站直播间取流（解析 + ffmpeg 拉流 + 断线重连）
tools/                fetch_model.py 下模型 / convert_mt_model.py 转本地翻译模型 /
                      make_portable_zip.py 打便携包 / test_*.py 各项自测
docs/DEV-NOTES.md     开发笔记：踩过的所有坑、实测数据、打包细节（信息量最大的文件）
```

## 已知限制

- 本地 NLLB-600M 翻译**质量明显不行**（口语、人名、梗全翻错，只够听懂大意）；要离线的同时还要质量，请用 Ollama 路线，或者换更大的 NLLB（1.3B/3.3B，转换流程一样）
- **Windows 上功能最全**（WASAPI 环回 = 抓系统声音）。**macOS 也能跑**：抓直播间 / 装 BlackHole 后抓系统声音，
  见 [docs/MACOS.md](docs/MACOS.md)；Linux 同理（ffmpeg pulse 抓音）
- 直播没有字幕流也没关系（本来就是纯音频识别），但主播语速极快、多人抢话时效果会掉

## 授权与声明

- 本仓库代码：**MIT**
- 第三方组件：faster-whisper / CTranslate2 / Whisper 权重 = MIT；**NLLB-200 = CC-BY-NC-4.0（非商用）**；便携包内那份 ffmpeg 是 GPL 静态构建——如果要分发二进制包，注意这些授权差异
- 仓库里不含任何 API Key、模型权重或个人记录
- 仅供个人学习与观看使用，直播内容版权归主播所有

---

开发笔记、打包流程、以及一路上踩过的坑（CUDA DLL 注入、Whisper 复读幻觉、CTranslate2 转 NLLB 的两个陷阱、便携包的两个坑……）都在 [docs/DEV-NOTES.md](docs/DEV-NOTES.md)。
