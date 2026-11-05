---
name: demo-video-maker
description: 将一段产品原始录屏（screen recording mp4）加工为带硬字幕、片头片尾特效页、品牌名遮盖、TTS 旁白配音且音画逐帧对齐的产品功能演示视频（如 5 分钟精简版）。This skill should be used when the user wants to produce a polished narrated product demo video from a raw screen recording — trigger words include 产品演示视频、功能演示视频、录屏剪辑、演示视频配音、demo 视频、演示视频加字幕、录屏加配音.
agent_created: true
---

# Demo Video Maker — 录屏转产品演示视频

## 用途

把用户提供的**一整段产品操作录屏**加工为可直接对外播放的成品演示视频：精确总时长、科技感片头（封面 + 能力汇聚特效页）、逐帧对齐的单行硬字幕、对外产品名遮盖（drawbox 打码）、TTS 中文女声旁白、片尾"感谢观看"与品牌收尾页，交付**配音前 / 配音后**两版 mp4。

典型请求：「给你录屏和功能介绍文档，帮我剪一个 5 分钟演示视频加字幕和配音」「录屏里的旧品牌字样要遮掉，对外叫新产品名」。

## 调用关键词：**演示视频流水线**

用户只发这一句（或近似说法）时，**不要反问需求细节**，直接把下面这份材料清单发给他，并说明「给齐 1-4 即可开工，5 可后补」：

> 好的，走演示视频流水线。请给我：
> 1. 源录屏 mp4 的路径（整段录制即可，不用预剪）
> 2. 功能介绍文档（docx/pdf/md 均可，用来定字幕文案）
> 3. 对外产品名 + 录屏里要遮掉的字样（如原厂名；不知道坐标我会抽帧确认）
> 4. 目标总时长（不给就默认 5:00.00 整）
> 5. 可选：参考样片、片头片尾文案、音色偏好

收到材料后按下方五阶段直接执行到成片，中途只在「画面节点核对结果需要你确认」或「哪个问题区段要改」时找你。

## 开工前必须向用户确认的材料（checklist）

1. **源录屏 mp4 路径**（整段录制即可，不要求用户预剪）
2. **功能介绍文档**（docx/pdf/md，决定讲什么、字幕文案从哪来）
3. **对外产品名 + 录屏里需遮盖的字样/区域**（不知道区域就先抽帧确认坐标）
4. **目标总时长**（默认 5:00.00，锁死）
5. 参考样片（可选，用于学习字幕风格/节奏）

## 全流程（五阶段，scripts/ 均读工作目录下的 demo.json 配置）

各阶段**详细步骤、字幕时间轴公式、踩坑清单**见 `references/workflow.md`，配置字段定义与完整示例见 `references/demo_example.json`。**执行任何阶段前先读 workflow.md 对应章节。**

### 阶段 0：素材与画面节点分析
- 跑 `scripts/analyze_recording.py`：抽 1fps 帧、场景跳变检测、OCR 主体文字、产出带 src 时间戳标注的拼图。
- **必须逐帧核对画面真实节点**（看拼图上的秒数），禁止凭推测写时间轴——历次返工大多来自节点误判。

### 阶段 1：写 demo.json（时间轴=唯一事实源）
- 按功能文档切 SEGS 段；字幕逐句对应画面、句间不留空档。
- **每条字幕必须能从容读完**：`eff(中文字符=1.0, 其他=0.55) / 时长 ≤ 4.2 字/秒`；放不下就 SLOW 慢放该段或减字（用户既定原则），禁止字幕挤行。
- FREEZE（末帧定格）只用于段尾补时长；SLOW（如 0.6）用于操作密集段。

### 阶段 2：画面生成
1. `scripts/make_pages.py` → seg_title.mp4 / ov.mp4（参数化汇聚特效页）/ seg_end_a.mp4 / seg_end_b.mp4
2. `scripts/cut_segments.py` → seg_NN.mp4（drawbox 遮盖 + SLOW 慢放 + FREEZE 定格 + 统一 fps），**自动校验每段实长与配置一致**
3. `scripts/assemble.py` → concat 滤镜拼接 + ASS 硬字幕压制 → 配音前版 + 字幕时间轴.txt

### 阶段 3：配音与混音
1. `scripts/synth_voice.py` → edge-tts 逐句合成，档位填充 92%、rate 钳 [-18%, +20%]、超限才 atempo 兜底
2. `scripts/mix_numpy.py` → **numpy 样本级混音**（裁 TTS 片头静音垫，起讲点=字幕起点）→ 配音版
3. `scripts/check_sync.py` → 起讲偏差 + 包络相关 + 时移三项体检

### 阶段 4：交付验收（全部通过才可交付）
- 两版成片时长 = 目标值 ±0.1s；抽帧拼图核对片头/衔接/片尾画面
- check_sync：起讲偏差均值 ≤0.03s、超 0.15s 为 0 条、包络相关 ≥0.95
- 峰值 ≤ -1.5dB 无削波；字幕全片单行、无空档

## 硬性规则（多轮返工换来的教训）

- **字幕与画面逐帧对齐**是用户核心诉求，任何修改后必须重新抽帧核对问题区段
- **字幕恒为单行**：相邻事件重叠会被渲染成多行 → 时间轴公式见 workflow.md
- **改 SLOW/FREEZE/片头片尾时长 → 全片字幕和配音必须同步平移**，禁止只改视频不改时间轴
- **禁止 ffmpeg amix 大图混音**（>20 输入会静默丢 adelay）→ 一律用 mix_numpy.py
- 画质/音质参数、TTS 细节、验证方法见 workflow.md

## Resources

### scripts/
`selftest.py`（自检：合成录屏跑通全链路，改脚本后先跑它）· `analyze_recording.py`（素材分析）· `make_pages.py`（片头片尾）· `cut_segments.py`（切段）· `assemble.py`（拼接+字幕）· `synth_voice.py`（TTS）· `mix_numpy.py`（混音）· `check_sync.py`（对齐体检）。全部以 `python scripts/xxx.py` 在工作目录下运行，读取该目录的 `demo.json`。
**改动任何脚本后先跑 `python scripts/selftest.py`**（约 2 分钟，合成录屏端到端验证，输出 `SELFTEST PASS` 方可使用）。

### references/
- `workflow.md` — 五阶段详细流程、时间轴公式、踩坑清单、验收标准
- `demo_example.json` — 完整配置示例（来自真实项目）
