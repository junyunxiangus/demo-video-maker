# -*- coding: utf-8 -*-
"""配音合成：按字幕档位逐句 edge-tts 合成，语速自适应到「从容铺满」。
用法: python scripts/synth_voice.py
产出: _voice/v_XX.mp3、_voice/plan.json（供 mix_numpy.py 混音）

策略:
  1. 先以 rate=0 合成，量出原速时长 d0
  2. 目标 target = 档位 * fill（默认 0.92，留 8% 气口）
  3. rate = round((d0/target - 1)*100)，钳制到 [rate_min, rate_max]（默认 -18%/+20%），
     只靠 TTS 原生变速，音质自然
  4. 若仍超档位 0.12s 以上，才用 atempo 兜底（小幅时间拉伸）
  5. 片头旁白（画面自带文字、不在字幕轨）单独列在 voice.intro，需要自然语速就把 rate 设为 0
"""
import os, sys, json, shutil, asyncio, subprocess

ROOT = os.getcwd()
CFG = json.load(open(os.path.join(ROOT, 'demo.json'), encoding='utf-8'))
VO = os.path.join(ROOT, '_voice')
os.makedirs(VO, exist_ok=True)

SEGS, FREEZE, SLOW = CFG['segs'], CFG.get('freeze') or {}, CFG.get('slow') or {}
V = CFG.get('voice') or {}
VOICE = V.get('voice', 'zh-CN-XiaoxiaoNeural')
FILL = float(V.get('fill', 0.92))
RMIN, RMAX = int(V.get('rate_min', -18)), int(V.get('rate_max', 20))
NATURAL = set(V.get('natural_idx', []))      # 需要自然语速的条目序号（如片头三句）


def find_bin():
    cands = [os.environ.get('WB_FFMPEG_BIN'),
             os.path.join(ROOT, 'tools', 'ffmpeg-9.0.2-essentials_build', 'bin'),
             os.path.join(ROOT, '..', 'tools', 'ffmpeg-9.0.2-essentials_build', 'bin')]
    for c in cands:
        if c:
            for exe in ('ffmpeg.exe', 'ffmpeg'):
                if os.path.exists(os.path.join(c, exe)):
                    return os.path.join(c, exe), os.path.join(c, exe.replace('ffmpeg', 'ffprobe'))
    if shutil.which('ffmpeg') and shutil.which('ffprobe'):
        return shutil.which('ffmpeg'), shutil.which('ffprobe')
    sys.exit('未找到 ffmpeg/ffprobe')


FF, FP = find_bin()

try:
    import edge_tts
except ImportError:
    sys.exit('需要 edge-tts: pip install edge-tts')


def dur_of(p):
    r = subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=nw=1:nk=1', p], capture_output=True, text=True)
    return float(r.stdout.strip())


# ---------- 1. 事件表（与 assemble.py 完全一致） ----------
events = []
for st, en, text in V.get('intro') or []:
    events.append([float(st), float(en), text])
cursor = float(CFG['title'].get('dur', 3.0)) + float(CFG['overview'].get('dur', 14.0))
for idx, (ss, dur, mask, note, subs) in enumerate(SEGS):
    fz = float(FREEZE.get(idx, 0.0)); rate = float(SLOW.get(idx, 1.0))
    for a, b, text in subs:
        events.append([cursor + min(a, dur + fz) / rate, cursor + min(b, dur + fz) / rate, text])
    cursor += dur / rate + fz
TAIL = CFG.get('tail') or {}
a_dur = float(TAIL.get('a_dur', 3.93))
events.append([cursor + 0.4, cursor + a_dur - 0.7, TAIL.get('a_text', '感谢观看')])
events.sort(key=lambda e: e[0])

# ---------- 2. 逐句合成 ----------
async def synth(text, rate_pct, path):
    await edge_tts.Communicate(text, VOICE, rate=f'{rate_pct:+d}%').save(path)


plan = []
for i, (st, en, text) in enumerate(events):
    slot = en - st
    p = os.path.join(VO, f'v_{i:02d}.mp3')
    asyncio.run(synth(text, 0, p))
    d0 = dur_of(p)
    if i in NATURAL:
        rate, target = 0, slot
        if d0 > slot - 0.12:
            print('   !! 自然语速条目 #%d 超档位 %.2fs（原速 %.2fs）：请加长片头页或减字，'
                  '否则会用 atempo 拉伸破坏自然语速' % (i, slot, d0))
    else:
        target = slot * FILL
        rate = int(round((d0 / target - 1) * 100))
        rate = max(RMIN, min(RMAX, rate))
    d1 = d0
    if abs(rate) >= 3:
        asyncio.run(synth(text, rate, p))
        d1 = dur_of(p)
    atempo = 1.0
    if d1 > slot - 0.12:
        atempo = round(d1 / (slot - 0.12), 3)
    plan.append(dict(i=i, st=round(st, 3), en=round(en, 3), text=text, dur=round(d1, 3),
                     rate=rate, atempo=atempo, path=p))
    print('%2d %d:%05.2f 档%4.1fs 语%4.2fs 语速%+3d%% 填充%3.0f%%%s  %s'
          % (i, st // 60, st % 60, slot, d1, rate, d1 / slot * 100,
             ' (atempo %.2f)' % atempo if atempo != 1.0 else '', text[:18]))

json.dump(plan, open(os.path.join(VO, 'plan.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('\nplan.json 共 %d 句，已写入' % len(plan))
over = [p for p in plan if p['atempo'] != 1.0]
if over:
    print('注意：%d 句使用了时间拉伸兜底（%s），建议慢放或减字'
          % (len(over), ', '.join('#%d' % p['i'] for p in over)))
