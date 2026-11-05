# -*- coding: utf-8 -*-
"""总装：concat 拼接全部段落 + 生成 ASS 单行硬字幕 + 压制 + 导出配音前版。
用法: python scripts/assemble.py            （读 demo.json；要求已跑过 make_pages / cut_segments）
产出: _segs/subbed.mp4、<outdir>/<prefix>_配音前_<tag>.mp4、<outdir>/字幕时间轴.txt

时间轴公式（唯一正确写法，务必照抄）:
    st = cursor + min(a, dur+fz) / rate
    en = cursor + min(b, dur+fz) / rate
    cursor += dur/rate + fz
即 FREEZE 定格时长只延伸【段末那条】字幕，绝不能加到段内每一条（否则相邻字幕重叠→被渲染成多行）。
"""
import os, sys, json, shutil, subprocess

ROOT = os.getcwd()
CFG = json.load(open(os.path.join(ROOT, 'demo.json'), encoding='utf-8'))


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
    sys.exit('未找到 ffmpeg/ffprobe：安装静态包到 tools/ 或设 WB_FFMPEG_BIN')


FF, FP = find_bin()
W, H, FPS = CFG.get('w', 1920), CFG.get('h', 1080), CFG.get('fps', 30)
TMP = os.path.join(ROOT, '_segs')
OUTDIR = os.path.join(ROOT, CFG.get('outdir', '输出'))
os.makedirs(OUTDIR, exist_ok=True)
SEGS, FREEZE, SLOW = CFG['segs'], CFG.get('freeze') or {}, CFG.get('slow') or {}
TITLE = CFG.get('title') or {}
OV = CFG.get('overview') or {}
TAIL = CFG.get('tail') or {}
STY = CFG.get('sub_style') or {}


def run(cmd, tail=1200):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    if r.returncode != 0:
        print('FAIL:', ' '.join(cmd)[:240]); print(r.stderr[-tail:]); raise SystemExit(1)
    return r


def dur_of(p):
    return float(run([FP, '-v', 'error', '-show_entries', 'format=duration',
                      '-of', 'default=nw=1:nk=1', p]).stdout.strip())


# ---------- 1. 时间轴 ----------
cursor = float(TITLE.get('dur', 3.0)) + float(OV.get('dur', 14.0))
events = []
for idx, (ss, dur, mask, note, subs) in enumerate(SEGS):
    fz = float(FREEZE.get(idx, 0.0)); rate = float(SLOW.get(idx, 1.0))
    for a, b, text in subs:
        events.append([cursor + min(a, dur + fz) / rate, cursor + min(b, dur + fz) / rate, text])
    cursor += dur / rate + fz
content_end = cursor
a_dur = float(TAIL.get('a_dur', 3.93))
events.append([content_end + 0.4, content_end + a_dur - 0.7, TAIL.get('a_text', '感谢观看')])

# 防重叠（重叠会被 ASS 渲染成多行）：按起点排序后把上一条收在下一 tick 之前
events.sort(key=lambda e: e[0])
for i in range(len(events) - 1):
    if events[i][1] > events[i + 1][0] - 0.05:
        events[i][1] = max(events[i][0] + 0.6, events[i + 1][0] - 0.05)

TOTAL = float(CFG.get('total', 300.0))
real = content_end + a_dur + float(TAIL.get('b_dur', 2.0))
print('内容结束 %.2fs，预计总长 %.2fs（目标 %.2fs，差 %+.2fs）' % (content_end, real, TOTAL, real - TOTAL))
if abs(real - TOTAL) > 0.6:
    print('!! 与目标时长偏差过大：请调 tail.a_dur / tail.b_dur / overview.dur 收回差值')

# ---------- 2. 拼接 ----------
files = [os.path.join(TMP, 'seg_title.mp4'), os.path.join(TMP, 'ov.mp4')]
files += [os.path.join(TMP, 'seg_%02d.mp4' % i) for i in range(len(SEGS))]
files += [os.path.join(TMP, 'seg_end_a.mp4'), os.path.join(TMP, 'seg_end_b.mp4')]
files = [p for p in files if os.path.exists(p)]
assert len(files) >= len(SEGS) + 2, '段落文件缺失，先跑 make_pages.py 与 cut_segments.py'

silent = os.path.join(TMP, 'silent.mp4')
cmd = [FF, '-y']
for p in files:
    cmd += ['-i', p]
cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
ins = ''.join(f'[{i}:v:0]' for i in range(len(files)))
cmd += ['-filter_complex', f'{ins}concat=n={len(files)}:v=1:a=0[v]',
        '-map', '[v]', '-map', f'{len(files)}:a',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
        '-r', str(FPS), '-c:a', 'aac', '-shortest', silent]
run(cmd, 2000)
print('拼接完成 %d 段，实长 %.2fs' % (len(files), dur_of(silent)))

# ---------- 3. ASS 字幕 ----------
def ts(sec):
    h = int(sec // 3600); m = int(sec % 3600 // 60); s = sec % 60
    return f'{h}:{m:02d}:{s:05.2f}'


ass = os.path.join(TMP, 'sub.ass')
font = STY.get('font', 'Microsoft YaHei')
size = int(STY.get('size', 50))
margin_v = int(STY.get('margin_v', 60))
outline = STY.get('outline', 2)
with open(ass, 'w', encoding='utf-8') as f:
    f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n" % (W, H))
    f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,"
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY,"
            "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR,"
            "MarginV, Encoding\n")
    f.write("Style: Default,%s,%d,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,"
            "100,100,0,0,1,%s,0,2,40,40,%d,1\n" % (font, size, outline, margin_v))
    f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    for st, en, text in events:
        # WrapStyle:2 + 单行文案：换行符会变多行，这里强制压成一行
        f.write("Dialogue: 0,%s,%s,Default,,0,0,0,,%s\n"
                % (ts(st), ts(max(st + 0.8, en - 0.15)), text.replace('\n', ' ')))

subbed = os.path.join(TMP, 'subbed.mp4')
run([FF, '-y', '-i', silent, '-vf', 'subtitles=_segs/sub.ass',
     '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
     '-c:a', 'copy', subbed], 2000)
print('字幕 %d 条，已压制，实长 %.2fs' % (len(events), dur_of(subbed)))

# ---------- 4. 导出 ----------
tag = CFG.get('tag', '5min')
nv = os.path.join(OUTDIR, '%s_配音前_%s.mp4' % (CFG.get('prefix', '演示视频'), tag))
shutil.copyfile(subbed, nv)
txt = os.path.join(OUTDIR, '字幕时间轴.txt')
with open(txt, 'w', encoding='utf-8') as f:
    f.write('# 总长 %.2fs  共 %d 条\n' % (TOTAL, len(events)))
    for st, en, text in events:
        f.write('%d:%05.2f - %d:%05.2f  %s\n' % (st // 60, st % 60, en // 60, en % 60, text))
print('配音前版:', nv)
print('字幕时间轴:', txt)
