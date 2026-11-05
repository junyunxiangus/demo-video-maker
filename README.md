# demo-video-maker

把一段产品操作录屏，加工成一条可直接对外播放的**产品功能演示视频**：固定总时长、科技感片头片尾、逐帧对齐的单行硬字幕、原厂名打码遮盖、TTS 中文女声旁白，一次交付**配音前 / 配音后**两版 mp4。

A reusable WorkBuddy/CodeBuddy skill that turns a raw screen recording into a polished, narrated product demo video with frame-accurate hard subtitles — fully automated with ffmpeg + Python.

---

## 它解决什么问题

手工剪一条 5 分钟演示视频的痛点在于**字幕和画面对不上**：改一处慢放，全片字幕就整体错位。这个 skill 把时间轴收敛成一份 `demo.json`（唯一事实源），所有阶段都从它派生，因此任何改动都能一次性同步到画面、字幕、配音三条轨道。

自带多轮实战打磨出来的防错机制：

- 字幕恒为单行（FREEZE 定格只延伸段末那条字幕，避免事件重叠被渲染成两行）
- numpy 样本级混音，绕开 ffmpeg `amix` 大滤镜图静默丢 `adelay` 的坑
- 自动裁掉 TTS 片头约 0.19s 静音垫，保证起讲点 = 字幕起点
- 对齐体检用 10ms **包络**相关而非波形相关（避免 atempo 相位差造成的假性零相关）
- 切段后自动校验每段实长，防止段落错位丢内容

## 安装

### 1. 取回仓库

```bash
git clone https://github.com/junyunxiangus/demo-video-maker.git
cd demo-video-maker
```

（没有 git 就点仓库右上 Code → Download ZIP 解压）

### 2. 一条命令装到 skill 目录

```bash
# macOS / Linux / Git Bash
bash install.sh

# Windows PowerShell
.\install.ps1
# 若提示脚本被禁止运行：Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

安装脚本做的事：把目录内容拷到 `~/.workbuddy/skills/demo-video-maker/`（Windows 为 `%USERPROFILE%\.workbuddy\skills\demo-video-maker\`），自动跳过 `.git` 与 `__pycache__`。已有同名目录会被覆盖。

自定义位置：`bash install.sh /path/to/skills/demo-video-maker` 或 `.\install.ps1 -Target "D:\skills\demo-video-maker"`。

不想用脚本，手动拷也行：`cp -r demo-video-maker ~/.workbuddy/skills/`。

### 3. 装依赖

```bash
pip install -r requirements.txt
# 即：pillow numpy edge-tts
# OCR 定位画面节点时额外需要（可选）：pip install rapidocr-onnxruntime
```

### 4. 准备 ffmpeg

三选一（脚本会自动按这个顺序找）：

1. 设环境变量 `WB_FFMPEG_BIN` 指向 ffmpeg 的 `bin` 目录
2. 把静态包放在**工作目录**的 `tools/ffmpeg-9.0.2-essentials_build/bin/`
3. 安装到系统 `PATH`（`ffmpeg` / `ffprobe` 可直接调用）

配音走 edge-tts，**需要联网**。

装完后在对话里说关键词 **「演示视频流水线」**，或直接描述需求（"帮我做个产品演示视频"），它会先把材料清单发给你。

## 需要准备的材料

| # | 材料 | 说明 |
|---|---|---|
| 1 | 源录屏 mp4 | 整段录制即可，不用预剪 |
| 2 | 功能介绍文档 | docx/pdf/md，决定讲什么、字幕从哪来 |
| 3 | 对外产品名 + 要遮掉的字样 | 不知道坐标会先抽帧确认 |
| 4 | 目标总时长 | 默认锁死 5:00.00 |
| 5 | 可选 | 参考样片、片头片尾文案、音色偏好 |

## 工作流

```
demo.json（时间轴唯一事实源）
   │
   ├─ 阶段0  analyze_recording.py   抽帧 / 场景跳变 / OCR → 定位真实画面节点
   ├─ 阶段1  写 demo.json            切段 + 逐句字幕 + 语速预算（≤4.2 字/秒）
   ├─ 阶段2  make_pages.py           封面页 + 汇聚特效页（按目标时长重新渲染）+ 片尾两页
   │        cut_segments.py         打码 + 慢放 + 末帧定格（自动校验实长）
   │        assemble.py             拼接 + ASS 单行硬字幕 → 配音前版
   ├─ 阶段3  synth_voice.py         edge-tts 逐句合成，语速自适应档位（92% 填充，钳 ±20%）
   │        mix_numpy.py            样本级混音 → 配音版
   └─ 阶段4  check_sync.py          起讲偏差 / 收尾余量 / 包络相关 三项体检
```

所有脚本都在含 `demo.json` 的工作目录下执行：

```bash
python <skill>/scripts/analyze_recording.py
python <skill>/scripts/make_pages.py
python <skill>/scripts/cut_segments.py
python <skill>/scripts/assemble.py
python <skill>/scripts/synth_voice.py
python <skill>/scripts/mix_numpy.py
python <skill>/scripts/check_sync.py
```

### 自检

改过脚本后先跑端到端自检（用合成录屏，约 2 分钟）：

```bash
python <skill>/scripts/selftest.py            # 加 --no-voice 跳过 TTS
# 输出 SELFTEST PASS 才算可用
```

## 验收标准

| 项 | 标准 |
|---|---|
| 成片时长 | = 目标值 ±0.1s（两版都查） |
| 起讲偏差 | 均值 ≤0.03s，超 0.15s 的 0 条 |
| 内容相关（包络） | 均值 ≥0.95，最低 ≥0.5 |
| 电平 | 峰值 ≤ -1.5dB，无削波 |
| 字幕 | 全片单行、无空档、无重叠 |

## 目录结构

```
SKILL.md                      技能主文档（关键词、材料清单、五阶段、硬性规则）
README.md                     本文件
requirements.txt              Python 依赖
install.sh / install.ps1      一键安装脚本（macOS/Linux、Windows）
references/workflow.md        详细流程、字幕时间轴公式、11 条踩坑对照表
references/demo_example.json  完整配置示例（把 src 换成你的录屏即可开跑）
scripts/*.py                  8 个可执行脚本（含 selftest）
```

## 已知边界

- 字幕文案需要人工确认（自动从文档摘要生成的字幕，节奏通常不行）
- 画面节点必须逐帧核对，OCR 对图表类型切换（折线↔柱状）不敏感
- Windows 字体依赖 `Microsoft YaHei`；其他平台改 `demo.json` 的 `sub_style.font`
- 语速预算 4.2 字/秒是"能读完"下限；≤6 字的短句档位不要低于 2.2s，否则会触发时间拉伸

## License

MIT
