# live-translate — 系统声音实时翻译（纯音频，无字幕也能用）

抓「扬声器正在播放的声音」→ 本地 Whisper 转写 → DeepSeek 翻成中文 → 控制台 + 本地网页实时显示。
不需要直播带字幕，也不要虚拟声卡；用的是 Windows 自带的 **WASAPI loopback**。

## 用法

```bat
run_live.bat                     :: 双击就行，默认 日→中 / small 模型（带化学术语 prompt）
```
或者命令行：

```powershell
cd <项目目录>
.\.venv\Scripts\python.exe live_translate.py --src ja --prompt "化学の配信です。ラジカル配位子が二つのランタノイドイオンを架橋する話です。"   # 日→中
.\.venv\Scripts\python.exe live_translate.py --src en             # 英→中
.\.venv\Scripts\python.exe live_translate.py --model-size medium  # 更准，CPU 也扛得住
.\.venv\Scripts\python.exe live_translate.py --no-translate       # 只出原文（练听力）
.\.venv\Scripts\python.exe live_translate.py --list-devices       # 看能抓到哪些输出设备
.\.venv\Scripts\python.exe live_translate.py --level              # 看音量条，调 --vad 用
```

字幕页（跑起来后自动开）：<http://127.0.0.1:8777> —— 扔到副屏，原文小灰字、译文大字，自动滚。
每场结束在 `logs/live_YYYYmmdd_HHMMSS.jsonl` 留一份带时间戳的记录。

## 常用参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--src` | `en` | 源语言，`ja`/`ko`/`auto` 都行；明确指定比 auto 准 |
| `--preset` | 无 | 现成术语提示：`chem-ja` / `chem-en`（等价于下面那条整句 prompt） |
| `--model-size` | `small` | `tiny/base/small/medium/large-v3/large-v3-turbo`，缺哪个自动去魔搭下 |
| `--device` | `auto` | `auto/cpu/cuda`；auto = 有 N 卡就用 GPU（float16） |
| `--compute-type` | 自动 | 覆盖精度：`float16`(GPU) / `int8`(CPU) / `int8_float16` |
| `--loopback` | 跟随默认输出 | 指定 loopback 设备号（`--list-devices` 看编号） |
| `--merge-below` | `1.6` | 短于这个秒数的句子先攒着、跟下一句合并再转写（上下文更足更准；0=关） |
| `--silence` | `0.45` | 静音这么久算一句说完（觉得切得太碎就调大） |
| `--max-seg` | `6.0` | 一段最长几秒，超了在低音量处强切 |
| `--vad` | `0.006` | 起声阈值下限；环境噪声大就调大，说话声音小就调小 |
| `--threads` | `8` | Whisper 的 CPU 线程数（机器 20 线程，还有余量） |
| `--no-web` / `--port` | 开 / 8777 | 关掉或改字幕页端口 |
| `--save-audio DIR` | 关 | 把每段音频存成 wav，排查漏句/幻觉/语言用 |
| `--for N` | 0 | 跑 N 秒自动停（默认一直跑到 Ctrl+C） |

**`--src` 一定要对**：默认 `en`。源语言填错的后果不是「翻得差」，是**整段变成罗马字垃圾**
（日语音频按英语解码 → “Yo, kya, nandesho” 这种）。拿不准就用 `--src auto`（实测能正确判出 ja），
但 auto 每段要多花约一倍转写时间，确定了语言就直接写死。

## 实测延迟（这台机器，20 线程 CPU）

| 环节 | 实测 |
|---|---|
| 转写 small int8（16 线程） | RTF 0.13–0.22 → 6 s 一段约 1 s 出字 |
| 转写 medium int8（20 线程） | RTF 0.49–0.60 → 6 s 一段约 3 s，跟得上但更吃 CPU |
| 转写 small 日语（16 线程，`--src ja`） | RTF 0.18–0.37（`--src auto` 要 ×2） |
| 翻译（deepseek-flash，关思考） | 0.5–1.2 s / 段（ja→zh 实测 0.5–1.0 s） |
| **合计滞后** | 静音判定 0.45 s + 转写 ~1 s + 翻译 ~0.8 s ≈ **落后直播 2–4 s** |

想要更准就 `--model-size medium`（medium 已经下好，不用再等）；默认 small 在术语上会翻车，
加 `--prompt "术语表"` 能明显救回来（实测 lanthanide/anisotropy 从错变对）。

## 日语（实测全链路）

`--src ja` 已整套跑通：日本语音频 → 日文转写 → 中文。实测每段 0.9–1.1 s 转写 + 0.6–1.2 s 翻译。

- 转写速度：small 离线 RTF 0.07–0.08、medium 0.22–0.24（比英语还快）。
- **`--prompt` 对日语是刚需**，而且要给**一整句话**，不要只列单词：
  - 只列单词 `"ランタノイド、ラジカル配位子、架橋、異方性"` → 术语基本对了，但 `架橋`→“家境”。
  - 整句 `"化学の配信です。ラジカル配位子が二つのランタノイドイオンを架橋する話と、ジスプロシウム中心の異方性についてです。"` → **逐字全对**（small 和 medium 都是）。
  - 不加 prompt 的基线：`ラジカル配位子`→“ラジカル配信”、`ランタノイドイオン`→“ランタのイドイオン”、`異方性`→“異放性”，然后翻译会忠实地把这些错字也翻错（“Radical Harry”、“Lantana的Idion”）。
- 日语同音词多，光靠 prompt 兜不住所有情况；正式讲化学的直播建议直接 `--model-size medium`。

## GPU（这台机器：RTX 5070 12 GB，强烈建议开）

CPU 上 large-v3 根本跑不动；GPU 上它比 CPU 跑 small 还快。装一次就永久生效：

```powershell
uv pip install --python .venv/Scripts/python.exe nvidia-cublas-cu12 "nvidia-cudnn-cu12>=9,<10"
```
（实测装成功的版本：`nvidia-cublas-cu12==12.9.2.10`、`nvidia-cudnn-cu12==9.27.0.42`、顺带 `nvidia-cuda-nvrtc-cu12==12.9.86`；
下载约 1.3 GB、13 分钟。ctranslate2 只带 CUDA 支持，不带 cuBLAS/cuDNN 的 DLL；`live_translate.py` 里的 `enable_cuda_dlls()`
会自动把 `site-packages/nvidia/*/bin` 加进 DLL 搜索路径，否则报 `cublas64_12.dll is not found`。）

**同一段 20.7 s 你的直播真实音频，实测：**

| 配置 | 转写耗时 | 实时倍率 |
|---|---|---|
| small / CPU int8 / 16 线程 | 2.0 s | 0.095 |
| medium / GPU float16 | 1.1 s | 0.054 |
| **large-v3 / GPU float16** | **1.2 s** | **0.057** |

直播里逐段实测（large-v3 + GPU）：**ASR 194–440 ms**（CPU small 是 900–1100 ms），
VRAM 占用 5.6 GB / 12 GB。现在瓶颈已经不是识别，而是"等一句话说完" + 翻译那 0.5–1 s。

所以推荐组合：`--device cuda --model-size large-v3 --merge-below 1.6`
——又准又快，模型大反而让端到端更快（因为延迟全在等待和翻译上）。

## 按网址直抓（想同时听别的音乐就用这个）

```powershell
.\.venv\Scripts\python.exe live_translate.py --url https://live.bilibili.com/22105860 --src ja --device cuda --model-size large-v3
.\.venv\Scripts\python.exe live_translate.py --url 22105860          # 直接填房间号也行
```

它走 B 站官方 `getRoomPlayInfo` 拿到 FLV/HLS 地址，再让 **ffmpeg 把音频流直接拉进来**（16k 单声道 PCM 管道），
**完全不经过扬声器**——所以：

- 你可以**静音**、可以把音量拉到 0、可以**同时听别的音乐**，互不干扰（这是它最大的好处）；
- 识别输入是原始流，不受音量、均衡器、音效影响；
- 代价：比扬声器那条路多 1–2 秒缓冲；且**要求房间正在播**、能公开拉流。

支持的输入：B 站直播间链接或纯房间号；别的平台只要是 **ffmpeg 能直接打开的媒体地址**（m3u8 / flv / http 直链）也能填。

自动重连：B 站的流地址会过期/断流，脚本会**每隔 1.5 秒重新解析地址并重启 ffmpeg**，最多 10 次；连续失败才报
`[capture] 拉流已断开` 并收尾退出。房间没开播时会直接说「房间 xxx 现在没有开播」。

## 怎么实现的

1. **抓声音**：`pyaudiowpatch` 打开默认输出设备的 WASAPI loopback（设备名带 `[Loopback]`）。只抓**当前默认输出**——中途换耳机要重启脚本。
2. **分段**：按 RMS 能量自适应阈值（噪声底 ×3，下限 `--vad`）判语音/静音，前滚 0.25 s 避免吃掉开头，静音 0.45 s 收一句，超 `--max-seg` 在最低能量点强切。
3. **转写**：faster-whisper small int8，`beam_size=1`、不跨段带上下文，只把前几句文本作为 `initial_prompt` 保持术语连贯。
4. **翻译**：DeepSeek `/chat/completions`，`thinking={"type":"disabled"}`（开着思考会拖到 4 s+，且 content 会是空的）。带前 3 句双语对照做上下文。
   需要 `DEEPSEEK_API_KEY` —— 脚本从 `~/AppData/Local/hermes/.env` 自己读，不写进代码。没有 key 时自动降级成只显示原文。
5. **输出**：控制台 + jsonl + 内建 HTTP 服务（`Sink._start_web`）供字幕页轮询。

## 坑（都踩过了）

- **huggingface.co 和它的 xet 存储在这台机器上不通**（`cas-bridge.xethub.hf.co` 连不上），faster-whisper 默认走 HF 会卡死。所以模型一律从**魔搭**下：`tools/fetch_model.py`（`pengzhendong/faster-whisper-*`，约 6 MB/s）。
- `sounddevice` 的 `WasapiSettings(loopback=True)` 在 0.5.5 上不存在；用 `pyaudiowpatch` 的 loopback 设备。
- 别用 MSYS 的 curl 下魔搭的文件（返回 200 但 0 字节），要用 `requests` 流式下载。
- 抓的是 loopback，所以**别静音扬声器**（静音后 loopback 也没有声音）；音量太小会漏句。
- **虚拟声卡（VB-Cable / 你机器上已装的 Intelligo VAC）不会更快也不会更准**：loopback 已经在数字层
  复制了同一份 PCM，虚拟声卡只是把同一份数据换个设备、还多一道路由（要改播放器输出、自己还得另接一路监听）。
  唯一的差别场景是 DRM/独占模式播放器，loopback 抓不到时虚拟线有时能绕——本机没遇到这种情况。
- **ctranslate2 装了也不等于 GPU 能用**：wheel 只带 CUDA 支持，`cublas64_12.dll` / `cudnn_ops64_9.dll`
  要另装 `nvidia-cublas-cu12` / `nvidia-cudnn-cu12`，并把 `site-packages/nvidia/*/bin` 加进 DLL 路径
  （`enable_cuda_dlls()` 干的就是这个）。
- **large-v3 的词表文件叫 `vocabulary.json`，不是 `vocabulary.txt`**（魔搭仓库里如此）；少了它会报
  `Cannot load the vocabulary from the model directory`。fetch_model.py 现在两个都试、404 就跳过。
- 两个参数别重名：`--device` 曾经既是 loopback 设备号又是 GPU 设备，argparse 直接崩（`conflicting option string`），
  现在 loopback 那个叫 `--loopback`。
- **别在 `.bat` 里写非 ASCII 参数**：cmd.exe 用 OEM 代码页（这里 GBK）读 .bat，UTF-8 的日文参数会被拆坏，报
  “不是内部或外部命令”。所以 `run_live.bat` 保持纯 ASCII，术语提示改成 `--preset chem-ja` 由 Python 提供；
  同时 bat 里 `chcp 65001` + `set PYTHONUTF8=1`（否则 cmd 里 Python 的 stdout 按 cp936 编码，日文直接 UnicodeEncodeError）。
- 抓的是「播放了什么」，不是「麦克风」——想翻自己说话，采集端要换成麦克风设备（不在 loopback 列表里）。

## 字幕浮窗（歌词式）

点主窗口的 **「弹出字幕浮窗」**：

- **无边框 + 永远置顶 + 半透明**（`-alpha 0.82`，面板外的底色用 `-transparentcolor` 抠掉，只剩一条浮动字幕）；
- 歌词式排版：最新一句大字加粗纯白，往上两句自动变暗变小；
- **拖动面板任意处移动**，右下角 **◢ 把手自由缩放**（最小 200×64），位置和尺寸都会记住；
- 浮窗上的 **`字号 −` / `字号 +`** 按钮调字号，**`原文`** 开关决定译文上方要不要再显示一行原文，**`✕`** 关闭；
- **滚轮不绑任何功能**——滚轮在别人眼里是"滚动/翻页"，拿来调字号会让人莫名其妙（用户明确否掉了这个设计）。

字号三处联动：主窗口的「字幕字号」拉条、浮窗按钮、网页字幕页右上角的 A−/A＋，改哪一处都会同步并写进设置。

## 翻译模型：本地 or 云端

界面上「翻译模型」那一行两个选项：

- **本地模型** —— CTranslate2 跑的 **NLLB-200 distilled 600M**（`models/nllb-200-distilled-600M-ct2`，int8 约 600 MB，**随包自带**）。
  离线、零成本、看的内容一个字不外发；每段约 30–150 ms（GPU）。**质量明显不如云端 LLM**——口语、专有名词、语气都会糙一些。
- **云端 API** —— DeepSeek（默认关思考，每段约 80 token ≈ 一小时直播 7–10 万 token）。
  质量好得多，但要联网 + 要 key。

key 平时在界面上只显示 `********`，点那一格或「修改」才弹输入框（`show="*"`），保存后写进 `gui_settings.json`。

**开始翻译前的下载确认**：如果选的识别模型还没下载，会先弹窗告诉你「需要下载 faster-whisper-X（约 N MB/GB）」并让你确认；
本地翻译模型缺失时也会明确报错（它需要随包提供，不联网下载）。

**记忆**：所有设置（含 API Key、浮窗位置与尺寸、字号、音量阈值、端口）随手改随手写进 `gui_settings.json`，
关窗口时也落盘一次；下次打开原样恢复。

### 本地翻译模型是怎么来的（换模型时照做）

huggingface 不通，所以走魔搭镜像下载 HF 格式权重：

```bat
.venv\Scripts\python.exe tools\fetch_hf_model.py facebook/nllb-200-distilled-600M --dest models\nllb-600M-hf
.venv\Scripts\python.exe tools\convert_mt_model.py models\nllb-600M-hf models\nllb-200-distilled-600M-ct2 --quantization int8
```
转换会连 tokenizer 文件一起拷过去，并在最后自检两句日语翻译。**运行端只需要 ctranslate2 + sentencepiece**（都随 exe 打包），不需要 torch / transformers —— torch 只在开发机转换时用一次（CPU wheel，`--index-url https://download.pytorch.org/whl/cpu`）。

坑：NLLB 的语种标签（`jpn_Jpan` / `zho_Hans`）是 tokenizer 的 added token，**用 sentencepiece 单独 encode 会被拆成子词**；
必须把它们当**整块 token** 贴在句首（源语言）和 `target_prefix`（目标语言）里，否则翻译出来是乱码。

### 本地翻译的实测质量（重要，别抱太高期待）

同一批真实直播音频（large-v3 转写 → 三种翻译）：

| 日文原文 | 本地 NLLB-600M | 云端 API |
|---|---|---|
| おやすみなさい | 晚上好好. | 晚安。 |
| 明日もお楽しみに。 | 我希望你能看到我. | 明天也敬请期待。 |
| 終わりです。今日はとても楽しい一日でした。 | 现在,我们结束了. | 结束了。今天真是很开心的一天。 |
| ワンリンターン 世界一のヤンパパ | ⁇ ,我知道你是个 ⁇ . | （术语本来就难，但至少通顺） |

速度上本地极快（**50–90 ms/段**，GPU），但**口语、人名、梗全都翻不对**，只适合"听懂大意"的场景。
想要**好质量的离线翻译**，别指望 NLLB 600M：换更大的 NLLB（1.3B/3.3B，改 `--local-mt` 即可，转换流程一样），
或者用列表里的 **Ollama 本地大模型**（Qwen3-4B 之类，质量接近云端，但需要先装 Ollama）。

## 便携版（拷到别的电脑直接用）

产出：`Illya-live-translate-tools-portable.zip`（**2.42 GB**，解压后 3.5 GB）。打包脚本：`tools/make_portable_zip.py`。

**一键打包（推荐）**：`python tools/build_windows_package.py` —— 它会连着做完 PyInstaller 打包 → 拷 ffmpeg.exe → 清包内 `gui_settings.json` 的 api_key → 压 zip → 打印 gh 上传命令。想先看它会做什么加 `--dry-run`；要把离线翻译模型也塞进包加 `--with-model`（zip 会大 ~600 MB）。运行前确认在装了依赖的那个环境里（`sys.executable` 指向的 python 需要 pyinstaller）。**包里自带模型，解压就能用，不需要联网下载**：

```
Illya-live-translate-tools\
├── live-translate-gui\      exe + _internal\ + ffmpeg.exe + gui_settings.json + README-portable.txt
└── models\
    ├── nllb-200-distilled-600M-ct2\   本地翻译模型（620 MB）→ 离线翻译
    └── faster-whisper-small\          识别模型（460 MB，默认用它）
```

两个文件夹**必须放一起**：exe 会从自己所在目录往上 3 层找 `models\`（`_models_dir()`），所以解压到哪都能用，但别只拷 `live-translate-gui\`。

换电脑要解决的三件事（都已处理）：

1. **ffmpeg**：`stream_source.py` 的 `ffmpeg_path()` 会先找程序目录（及往上 3 级）里的 `ffmpeg.exe`，找不到才用 PATH 里的。包里带了一份（212 MB 的 gyan 静态构建）。
2. **API Key**：`Translator._read_key()` 优先级 = **环境变量 `DEEPSEEK_API_KEY` → 程序目录 `api_key.txt` → Hermes 的 `.env`**。GUI 里填的 key 由父进程放进子进程环境变量（不写进命令行），存在 `gui_settings.json`。**打包时会把这个文件里的 key 清空**（实测过 `grep -rI "sk-…"` 全包零命中），免得压缩包外传时泄露。
3. **模型**：本地翻译模型和 small 识别模型**都打进包**；只有换更大的识别模型（medium / large-v3）才会联网下载到 `models\`，且开跑前会弹窗告知大小让你确认。

便携包默认设置：**翻译模式=本地模型**、`model=small`、抓系统声音、网址留空、无 key、不显示日志 → 解压即可离线跑起来。

打包本身有两个坑（都实测过）：
- **别用 `tar -a -cf x.zip`**：这里的 GNU tar 不支持 zip，`-a` 只是把**普通 tar 套上 .zip 后缀**（3.5 GB 2.9 秒"压"完 = 没压），而且 MSYS 的 GNU tar 也读不了真 zip。用 `tools/make_portable_zip.py`（标准库 `zipfile` + deflate，3.5 GB → 2.42 GB，约 130 秒）。
- **验证方式**：把 zip 解压到项目树**外面**的目录再跑 exe —— 只有这样才能证明「往上找 models」真的走通了（在项目目录里测会误命中项目自己的 `models\`）。看 `logs\gui_run.log` 里有没有 `[mt] 本地翻译就绪：nllb-…`，跑的时候**不要**传 `--local-mt`。


## 图形界面 / exe（不想碰命令行就用这个）

**双击 `live-translate-gui\live-translate-gui.exe`** —— 窗口里挑参数，点「开始翻译」，原文+译文直接显示在窗口下半部分。

界面上能调的东西：

| 界面上的名字 | 对应命令行参数 | 白话解释 |
|---|---|---|
| 声音来源 | `--source` / `--url` | 「抓系统声音」=扬声器里放什么翻什么；「抓直播间网址」=只抓那一路流，你可以静音、可以听别的音乐 |
| 直播间网址/房间号 | `--url` | 如 `https://live.bilibili.com/22105860` 或直接 `22105860` |
| 主播说什么语言 | `--src` | 填错会变成罗马字垃圾，务必对上 |
| 识别模型 | `--model-size` | large-v3 最准（有 N 卡就选它） |
| 运行设备 | `--device` | auto = 有 N 卡自动用 GPU |
| **说完多久算一句** | `--silence` | **小而快 / 大而准**：越小越快，但句子被切得更碎 |
| **短句合并阈值** | `--merge-below` | 短于此秒数的碎句先攒着跟下句一起翻，更准 |
| **一句话最长** | `--max-seg` | 说得太急时到点强切 |
| 术语提示 | `--prompt` / `--preset` | 专有名词多就选「化学·日语」；闲聊留空 |
| 开字幕网页 + 端口 | `--no-web` / `--port` | 勾上就有 `http://127.0.0.1:8777` 网页版 |

「打开记录文件夹」直接跳到 `logs/`（每次运行都有带时间戳的 jsonl）。设置会存进 `gui_settings.json`，下次打开还是这套。

打包（改完源码要重打）：

```bat
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name live-translate-gui ^
  --distpath . --workpath build_tmp --specpath build_tmp --paths tools ^
  --collect-all ctranslate2 --collect-all faster_whisper --collect-all onnxruntime ^
  --collect-all tokenizers --collect-all av --collect-all pyaudiowpatch ^
  --add-data ".venv/Lib/site-packages/nvidia;nvidia" live_gui.py
```

打包相关的事实：
- 产物 `live-translate-gui\` 约 **2.3 GB**（含 1.3 GB 的 CUDA 运行库）；**模型不打包**（5 GB），exe 会从自己所在目录往上找 `models/`，所以 exe 文件夹别单独搬走。
- exe 目录里有自己的 `gui_settings.json`（界面设置）和 `logs/`；预置了「抓直播间网址 + 你那个房间」，想改用抓系统声音点左边那个单选按钮就行。
- 已打包的能力：GPU / large-v3 / 按网址直抓（`stream_source.py`，动态 import 在 if 分支里——PyInstaller 的 AST 分析能找到，保险起见构建时也加了 `--paths .`）/ 信号文件优雅停止。
- 无声自检（不弹窗）：`live-translate-gui.exe --run-cli --for 10 --no-web --no-translate`，看 `live-translate-gui\logs\gui_run.log`；
  GUI 逻辑自检 `live-translate-gui.exe --smoke 20 --hidden`（窗口隐藏），结果写 `logs/smoke_result.txt`。
- `--add-data` 必须用**绝对路径**：加了 `--specpath` 之后相对路径会以 spec 目录为基准（踩过）。
- `--windowed` 下 `sys.stdout is None`，子进程里 `print()` 会直接报错，所以 `--run-cli` 分支先把 stdout/stderr 接到 `logs/gui_run.log`。
- 已知差异：**当前这个 exe 的 `--smoke` 结束时会停在 mainloop 不自动退出**（源码已改成写 `logs/smoke_result.txt`，重打一次就一致）——平时用不到，正常开 GUI 不受影响。

## 文件

```
live_translate.py        主程序（抓声音→分段→转写→翻译→输出）
run_live.bat             双击启动（默认 日→中）
tools/fetch_model.py     从魔搭下模型到 models/
tools/test_loopback.py   只测 loopback 能不能抓到声音
tools/test_asr.py        只测转写速度和准确度（支持 --lang / --prompt）
tools/test_translate.py  只测 DeepSeek 翻译延迟/参数
tools/sample_en.mp3      英文测试样本（TTS）
tools/sample_ja.mp3      日语测试样本（TTS, ja-JP-NanamiNeural）
models/faster-whisper-small/   已下好（464 MB）
models/faster-whisper-medium/  已下好（1.5 GB）
logs/                    每场的 jsonl 记录
viewer_preview.html      字幕页的静态预览
```
