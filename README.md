# Illya's live-translate tools

> **本软件由 千禧年科技の纱雾（B站同名）与其 Hermes 助手 Illya 完成，完全开源。**
> 仅供学习交流，请勿商用，一切后果自负。该软件完全免费，如果你发现你是从任何渠道购买到该软件，请立刻向作者举报

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

# 3) 运行程序
有两种（推荐第一种）
a.
cd ~/illya-live-translate
conda activate livetrans && python live_gui.py
b.如果你会一定计算机的话可以用这种
./.venv/bin/python live_translate.py --url 直播间网址 \
    --src ja --device cpu --model-size small
# 大字幕：浏览器打开 http://127.0.0.1:8777
# 图形界面：./.venv/bin/python live_gui.py
```

- **识别模型**：第一次运行会问你要不要下载（`small` 约 460 MB，从魔搭 ModelScope 下，国内可直连）
- **想离线翻译**：把 Windows 机器上的 `models/nllb-200-distilled-600M-ct2`（约 620 MB）拷进 `models/` 即可
- **想抓"系统声音"**（正在放的直播/视频/音乐，不只是直播间链接，一般用不上）：
  1. **装 BlackHole 2ch**：`brew install blackhole-2ch`；Homebrew 用不了就去官网下 `.pkg` 安装包
     <https://existential.audio/blackhole/>（双击安装，会问系统密码）
  2. 打开「**音频 MIDI 设置**」→ 左下角「**+**」→ **创建多输出设备** → 勾上你的「扬声器」**和**「BlackHole 2ch」；
     再把系统输出切到这个多输出设备（这样你自己还听得见声音）
  3. 看音频设备序号：
     ```bash
     ./.venv/bin/python live_translate.py --list-input-devices
     ```
     ⚠️ **只看 `AVFoundation audio devices` 那一段**（视频段跳过），序号按你自己机器上打出来的填，别照抄例子
  4. 跑起来（`:<音频序号>`）：
     ```bash
     ./.venv/bin/python live_translate.py --input-device ":1" \
         --src ja --device cpu --model-size small
     ```
     图形界面里则是：声音来源选「**抓音频输入设备**」，「输入设备」那一格填 `:1`
  5. 会弹「是否允许访问麦克风」→ **点允许**

  > **想先确认这条链通不通**：第 1–2 步可以先跳过，直接填你**内置麦克风**的序号（例如 `:2`），
  > 对着电脑说句话——有字幕出来就说明抓音链路没问题，再去折腾 BlackHole。
  > 更详细（含排查）见 **[docs/MACOS.md](docs/MACOS.md)**
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
- **YouTube 直播**：把 `https://www.youtube.com/live/...`（或 `youtu.be` 短链）填进同一个格子 / `--url` 就行。
  ⚠️ **国内必须先开代理**：程序会**自己找到你的系统代理**（Windows 上直接读系统设置，双击 exe 也能用 ✓），
  用全局/TUN 模式的话更不用管。代理开着时建议用「规则模式」——YouTube 走代理、B 站直连，这样两个平台能同时用。
  YouTube 常改规则，哪天报错先升级：`pip install -U yt-dlp`。

翻译后端用 `--translator api|local|ollama` 切换；云端需要在界面里填一次 API Key（或设环境变量 `DEEPSEEK_API_KEY`、或放一个 `api_key.txt`）。

### 翻译后端怎么选（Ollama 用户必读）

| 你想要 | 选哪个 | 要额外装什么 |
|---|---|---|
| 质量最好、便宜 | **云端 API**（DeepSeek，填自己的 key · 需联网） | 无 |
| 离线免费、不折腾 | **本地模型（NLLB-200）** —— 离线翻译模型已随预编译包提供 | 无 |
| 离线 **+** 质量好（有独显更佳） | **Ollama**（本机大模型） | 见下 ↓ |

**Ollama 是一个要单独安装的软件**——本工具只能帮你 `ollama pull` 拉**模型**，装不了 Ollama 本身。
所以在界面里点了"下载"却报「下载失败：没能启动 ollama pull」，就是这一步没做：

1. **装 Ollama**
   - Windows：打开 <https://ollama.com/download> → 下 `OllamaSetup.exe`（约 700 MB）→ 双击装 → 装完它会常驻后台（托盘里能看到小图标）
   - macOS：<https://ollama.com/download/mac> → 下 `.dmg` 拖进应用程序
   - 国内下载慢就挂个代理
2. **装好后不用碰命令行**，回到本工具：界面里选「Ollama」→ 点「开始翻译」→
   它会提示"还缺 `qwen2.5:3b`（约 2 GB），现在下载吗"→ 点「是」→ 会弹一个窗口显示下载进度 → **下完再点一次「开始翻译」**
   （想手动也行：终端里敲 `ollama pull qwen2.5:3b`；已经装了别的模型也行，界面下拉里会把你装好的都列出来）
3. **配置参考**：`qwen2.5:3b` 约需 3 GB 显存；没有独显用 CPU 也能跑，只是慢一些。
4. **⚠️ 选哪个模型对速度影响极大**：优先选**不带"思考 / 推理"**的模型，也就是
   `qwen2.5` 系列（3B / 7B）这类；名字里带 `qwen3`、`deepseek-r1`、`qwq` 的都会**翻译前先自己想一大段**，
   每句要 5–10 秒，直播字幕会明显慢半拍。
   实测同一台电脑：`qwen2.5:3b` 约 **0.1 秒/句**，`qwen3:4b` 约 **8.8 秒/句**（差近百倍，译文质量基本相当）。

> 大多数人不一定需要 Ollama：只想离线免费就选「本地模型」；想要最好质量就选「云端 API」（自己的 key，很便宜）。
> 只有"既要离线又要质量"才值得装 Ollama。

## 用户反馈的常见问题（报错对照表）

> 这一节汇总用户实际遇到过的报错和解决办法。出问题先在这儿扫一眼，多半就有答案。
> 下面这些**都是环境或用法问题**，不是程序坏了 —— 照"怎么办"那列做就行。

| 现象 / 报错 | 原因 | 怎么办 |
|---|---|---|
| 选了 Ollama 的模型，一点「开始翻译」就弹 **"缺少本地翻译模型：没找到 models\Ollama · qwen3:4b"** | **旧版本的程序 bug**：它把下拉里的标签当成了本地模型文件夹名去找 | **升级到最新版**即可（新版已修）。临时办法：改用「云端 API」或「本地模型」 |
| Ollama 明明装好了、模型也 `pull` 了，界面却显示"还没有模型"/"读不出来" | ① 设置里的模型名和实际装的不完全一样（写 `qwen3`、实际是 `qwen3:4b`）② 开着代理/加速器时，旧版本连**本机** Ollama 的请求被代理接管（返回 502） | 升级到最新版（两处都修了）；或自己把模型名写全：`ollama list` 看真实名字，照抄进设置 |
| Ollama 翻译**很慢**（每句好几秒，字幕慢半拍） | 选到了**带"思考/推理"**的模型（`qwen3`、`deepseek-r1` 这类），它翻译前先自己想一大段 | 换 **`qwen2.5:3b`**（不带思考，实测快近百倍，质量相当）：`ollama pull qwen2.5:3b`，再在界面下拉里选它 |
| `OSError: 【Errno -9996】 Invalid device`（pyaudiowpatch）| 选了「抓系统声音」，但这台机器**没有能抓的输出设备** | **最省事**：把「声音来源」改成「**抓直播间网址**」。想抓系统声音就先插好耳机/音箱、把默认输出设成一个**真实存在**的设备（别选"未插入"的显示器），也别只连着蓝牙耳机 |
| `ValueError: Requested float16 compute type, but the target device or backend do not support efficient float16 computation` | 显卡太老（**GTX 10 系及更早**）或驱动太旧；也可能是没有 N 卡却把「运行设备」选成了 cuda | 「运行设备」改成 **cpu**、「识别模型」改成 **small**（CPU 上 large-v3 跟不上直播）；确实有 N 卡的话，先更新显卡驱动 |
| 云端 API 报 `SSLError` | 代理软件或杀毒软件在**解密 HTTPS**：浏览器认它们的证书，本程序自带的是一套公共证书、不认 | 让 `api.deepseek.com` **不走代理**：代理软件里给它加"直连（DIRECT）"规则，或直接退出代理再跑；还不行就关掉杀毒软件的「HTTPS 扫描 / 网页防护」 |
| 云端 API 报 `InvalidHeader: Invalid leading whitespace…` | **API key 里混进了换行**（复制时带上的；网页上长 key 常常折成两行）| 界面里把 key 清空重填：**先粘到记事本**看一眼，确认是连续一整行，再从记事本复制过去 |
| 报 `NOT_FOUND … No such file or directory`（堆栈里有 `sentencepiece`）| **程序放在含中文的路径下**（"桌面""下载"这些实际路径都是中文），C++ 库把路径读成了乱码 | 把整个文件夹挪到**纯英文路径**，例如 `D:\LT\Illya-live-translate-tools`；挪了还报，就是解压不完整，用 7-Zip 重新解压一次 |
| 字幕里出现**英文**、或者一串罗马字（`Yo, kya, nandesho` 这种）| 「待翻译语种」填错了：主播说的是英语却填了 `ja`（或反过来）。Whisper 被强行按错误的语言解码时，会干脆吐出英文原文、或者把语音音译成一串罗马字垃圾 | 把「待翻译语种」改成实际语言（日语直播选 `ja`、英语选 `en`）；不确定就选 **auto**（自己判断，每段多花约一倍时间）。注意：这时候下面的中文译文通常还是对的，看着别扭的其实是被带歪的**原文**那行 |
| 云端 API 报 `HTTPError` | **三种来源**：① key 无效、没填、或**余额为 0**（401/402）② **代理在中间挡了**：Clash、Watt Toolkit（瓦特工具箱）、各种加速器会接管你的请求并返回自己的错误状态（最典型 **407 需要代理认证**，或 403/502）③ 换了接口但地址/模型名没填对 | 先**彻底退出所有加速/代理软件**（Watt Toolkit 要退出程序 —— 它改的是 hosts，光关加速开关不够）再跑；还不行检查 key 与余额；再不行核对「云端接口」那栏的地址和模型名 |
| Mac：`brew: unknown or unsupported macOS version` | Homebrew 版本太旧 | `brew update-reset`；或用 conda 那条路（见 [docs/MACOS.md](docs/MACOS.md)）|
| Mac：`git … Error in the HTTP2 framing layer` | 连不上 github.com（国内网络）| 给 git 挂代理，或直接把改过的文件拷过去覆盖 |
| Mac：`URLError: [Errno 8] nodename nor servname provided` | 代理开成了**全局模式**，导致 B 站这类国内域名解析不了 | 代理改「**规则模式**」（国内直连），或者先关掉代理再跑 |
| 界面里点了 Ollama 的"下载"却报「没能启动 ollama pull」/ 一直提示缺模型 | **Ollama 是要单独安装的软件**，本程序只能帮你拉它里面的模型 | 见上一节「翻译后端怎么选（Ollama 用户必读）」 |
| 字幕页/浮窗一直没字，但 `logs/*.jsonl` 里明明有内容 | 界面读自己本地接口时被代理拦了（**旧版**问题，v1.0.2 起已修）| 升级到最新版；临时办法：让本地地址 `127.0.0.1` 绕过代理 |

**还是解决不了？** 把这几样发出来，一般一眼就能定位：

1. **报错原文**（截图或复制文字都行；字幕里那种 `[翻译失败: Xxx]` 请把 `Xxx` 带上）
2. `live-translate-gui\logs\gui_run.log` 的最后二三十行
3. 你机器的大致情况：系统版本、有没有独显（什么型号）、用的哪种声音来源

## 模型

仓库里**不含任何模型权重**

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
                      build_windows_package.py 一条命令打 Windows 便携包（改完源码要发新版就用它）
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
