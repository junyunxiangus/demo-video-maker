# Demo Video Maker — 详细工作流与踩坑手册

本文件是 SKILL.md 的执行细则。**动手前先读完对应阶段**，尤其「时间轴公式」与「踩坑清单」两节。

---

## 0. 环境准备

- **ffmpeg/ffprobe**：优先用静态包 `tools/ffmpeg-9.0.2-essentials_build/bin/`（脚本按此路径探测），或设环境变量 `WB_FFMPEG_BIN` 指向 bin 目录，或系统 PATH 里有 ffmpeg。
- **Python 依赖**：`pip install pillow numpy edge-tts`；需要 OCR 时再装 `rapidocr-onnxruntime`。
- 所有脚本都在**含 demo.json 的工作目录**下执行（`python <skill>/scripts/xxx.py`），产物落在 `_frames/ _segs/ _voice/ 输出/`。

---

## 1. 阶段 0：素材分析与画面节点定位

```bash
python <skill>/scripts/analyze_recording.py          # 抽 1fps 帧 + 场景跳变 + 拼图
python <skill>/scripts/analyze_recording.py --ocr    # 再加 OCR 主体文字
```

产物：
- `_frames/f_00001.jpg...`（1fps 帧）
- `_frames/sheet_*.jpg`（20 帧/张拼图，每格左上角标 src 秒数）
- `_frames/report.txt`（时长、分辨率、Top40 场景跳变）

**必须做的事**：用 `ViewImage` 看拼图，把"画面真正切换的 src 秒数"逐条记下来，形成内容节点表。字幕偏移只能基于这张表写，**禁止凭文档推测**（历次 3 分 00 秒、25-40 秒段返工全部源于节点误判）。

判断技巧：
- 场景跳变 diff 大 = 页面切换；diff 小但 OCR 文字变了 = 同页内容更新（例如从输入框变成结果图表）
- 导航条、鼠标、加载动画会造成大量噪音，OCR 只看主体区域
- 图表类型切换（折线↔柱状↔环形）diff 很小，必须靠 OCR 读坐标轴/图例确认

---

## 2. 阶段 1：写 demo.json（时间轴是唯一事实源）

复制 `references/demo_example.json` 逐字段改写。字段说明：

| 字段 | 说明 |
|---|---|
| `src` | 源录屏绝对路径 |
| `total` | 目标总时长（秒），锁死值 |
| `prefix` / `tag` / `outdir` | 成片命名：`<prefix>_配音版_<tag>.mp4` |
| `mask` | drawbox 遮盖参数（x/y/w/h 为像素） |
| `title` / `overview` / `tail` | 片头封面页、汇聚特效页、片尾两页 |
| `sub_style` | ASS 字幕样式 |
| `voice` | 音色、填充率、语速钳制区间、片头旁白 |
| `segs` | 内容段数组，见下 |
| `freeze` / `slow` | 段索引 → 末帧定格秒数 / 慢放倍率 |

**段结构**：`[src_start, src_dur, mask_bool, note, [[偏移a, 偏移b, 字幕], ...]]`
- `src_start/src_dur`：从源录屏哪个时间点切多长
- `mask_bool`：本段是否打码（含品牌字样的段才 true）
- 字幕偏移是**相对本段输出起点**的秒数（已含慢放后的时间），段内必须首尾覆盖、句间不留空档

**时长预算**（务必先算）：
```
总长 = title.dur + overview.dur + Σ(seg.dur/slow + freeze) + tail.a_dur + tail.b_dur
```
调 `tail.a_dur`（感谢观看页）是最方便的配平手段：内容超了就从这里减，内容短了就加。

---

## 3. 阶段 2：画面生成

```bash
python <skill>/scripts/make_pages.py     # seg_title / ov / seg_end_a / seg_end_b
python <skill>/scripts/cut_segments.py   # seg_00..NN（打码+慢放+定格）
python <skill>/scripts/assemble.py       # 拼接 + 硬字幕 + 配音前版
```

- `make_pages.py` 的特效页按 14s 参考节奏**等比重新渲染**（不是 setpts 拉长），因此任意 dur 都平滑；品牌字、卡片飞入、停留分段比例固定。
- `cut_segments.py` 会**自动校验每段实长**与 `dur/rate+freeze` 是否一致，不一致会报错——这是防"段文件错位"的关键（曾因段错位丢 13 秒内容）。
- `assemble.py` 输出的 `输出/字幕时间轴.txt` 是验收依据之一。

### 字幕时间轴公式（唯一正确写法）

```python
cursor = title.dur + overview.dur
for idx, (ss, dur, mask, note, subs) in enumerate(SEGS):
    fz, rate = FREEZE.get(idx, 0), SLOW.get(idx, 1.0)
    for a, b, text in subs:
        st = cursor + min(a, dur + fz) / rate
        en = cursor + min(b, dur + fz) / rate
    cursor += dur / rate + fz
```

- `min(b, dur+fz)` 让**段末那条**字幕延伸覆盖定格期；若把 `fz` 加到段内每条字幕上，相邻字幕就会重叠 → ASS 渲染成两行（用户明确要求单行）。
- 慢放段（rate<1）里字幕偏移要按输出时间写，公式除以 rate 就是干这个。
- 任何 SLOW/FREEZE/片头片尾时长改动，**必须重跑 assemble 与 synth_voice**，禁止只改视频。

### 语速预算（写字幕时就要算）

```
eff(text) = 中文字符数 × 1.0 + 其他字符数 × 0.55
eff / (字幕时长) ≤ 4.2 字/秒
```
超了只有两条路（用户既定原则）：**慢放该段** 或 **减字**。绝不允许靠抢时间/叠字幕解决。

**实测校准（自检中量到的）**：TTS 短句有固定头尾气口，6 字以内的句子原速也要约 **2.0s**。
所以 ≤6 字的字幕档位不要低于 **2.2s**，否则即使 +20% 语速也吃不进档位，会触发 atempo 兜底（听感发硬）。
4.2 字/秒只是"能读完"的下限，配音要好看还得留这个气口余量。

---

## 4. 阶段 3：配音与混音

```bash
python <skill>/scripts/synth_voice.py    # 生成 _voice/v_XX.mp3 + plan.json
python <skill>/scripts/mix_numpy.py      # numpy 混音 → 配音版
python <skill>/scripts/check_sync.py     # 三项对齐体检
```

`synth_voice.py` 策略：
1. 先 rate=0 合成量原速时长
2. `target = 档位 × fill(0.92)`，`rate = (d0/target-1)×100`，钳到 [-18%, +20%]
3. 仍超档位 0.12s 才用 `atempo` 兜底（打印告警，说明该段该慢放或减字）
4. `voice.natural_idx` 里的条目强制 rate=0（片头旁白要自然语速）

`mix_numpy.py` 关键点：
- **绝对不要用 ffmpeg amix 大滤镜图**：>20 路输入时会静默丢弃 adelay，所有语音堆在 0 秒，且渲染耗时数分钟，极难排查
- TTS mp3 开头有 0.19s 静音垫，必须按 10ms 帧 RMS 阈值 0.004 裁掉，否则整体晚 0.19s
- 峰值 >0.98 自动缩增益，正常峰值应在 -2.4dB 左右

---

## 5. 阶段 4：验收清单（全绿才交付）

```bash
python <skill>/scripts/check_sync.py && echo SYNC_OK
```

| 项 | 标准 | 检查方式 |
|---|---|---|
| 成片时长 | = total ±0.1s（两版都要） | `ffprobe -show_entries format=duration` |
| 起讲偏差 | 均值 ≤0.03s，超 0.15s 的 0 条 | check_sync |
| 内容相关 | 均值 ≥0.95，最低 ≥0.5 | check_sync（包络相关） |
| 电平 | 峰值 ≤ -1.5dB，无削波 | mix_numpy 输出 |
| 字幕 | 全片单行、无空档、无重叠 | 抽帧 + 时间轴 txt |
| 画面 | 片头/衔接点/片尾逐帧核对 | 抽 8 帧拼图 ViewImage |

抽帧拼图命令模板：

```bash
FF=tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe
for t in 6.5 9.0 13.0 16.7 17.3 296.0 298.4 299.6; do
  "$FF" -y -v error -ss $t -i "输出/xxx_配音版_5min.mp4" -frames:v 1 "_chk/g_$t.jpg"
done
# 再用 PIL 拼成 4×2 网格，ViewImage 逐格核对
```

---

## 6. 踩坑清单（真实事故，逐条防）

| 症状 | 真因 | 处置 |
|---|---|---|
| 字幕出现两行 | FREEZE 时长被加到段内每条字幕，事件时间重叠 | 用 `min(b, dur+fz)`，只延伸段末那条 |
| 字幕整体比画面早/晚数秒 | 画面节点判断错（同页内容变化没识别出来） | 重抽该区段帧逐张看，别信推测 |
| 某段时间完全没字幕 | 改了 SLOW/FREEZE 后没重排后续字幕 | assemble 后对照 `字幕时间轴.txt` 找 >3s 空档 |
| 语音全堆在开头 | ffmpeg amix 大图丢 adelay | 改 mix_numpy.py 样本级混音 |
| 语音整体晚 0.19s | TTS mp3 片头静音垫 | trim_lead 裁垫 |
| 改了 SHIFT 但混音没变 | 同上 amix bug，参数根本没生效 | 别调 SHIFT，起讲点=字幕起点即可 |
| 片头有字无声 | 片头文字是画面内嵌，不在 ASS 字幕轨 | 在 `voice.intro` 单独列旁白 |
| 某段内容整体丢 13 秒 | 段文件与 segs 索引错位 | cut_segments 的实长校验必须通过 |
| 对齐全绿但内容对不上 | 用波形相关检验，atempo 相位差导致假性零相关 | 一律用 10ms 包络相关 |
| 概览页拉长后卡顿跳帧 | 用 setpts 拉伸已渲染视频 | 按新时长重新渲染帧序列 |
| 配音语速像赶火车 | 靠 atempo 硬压 | 放宽档位（慢放/减字），让 TTS 原生变速 |

---

## 7. 迭代与局部重建

用户改一两句字幕或片头旁白时，**不要全量重跑**：
- 只改字幕 → 重跑 `assemble.py` + `mix_numpy.py`（配音时间轴变了就要重跑 synth_voice）
- 只改片头时长 → 重跑 `make_pages.py`（只有 ov 变）+ `assemble.py` + 全量配音（时间轴整体平移）
- 只改某段切点 → 删掉对应 `_segs/seg_NN.mp4` 后重跑 `cut_segments.py`（脚本会重切全部，成本可接受）

**时间轴整体平移**时，配音必须全部重配（不要试图只平移 plan.json 的 st/en：填充率变了，语速就不匹配了）。
