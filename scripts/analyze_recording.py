# -*- coding: utf-8 -*-
"""素材分析：对源录屏抽 1fps 帧、检测场景跳变、可选 OCR 主体文字、产出带时间戳拼图。
用法（在含 demo.json 的工作目录下）:
    python scripts/analyze_recording.py            # 抽帧+跳变+拼图
    python scripts/analyze_recording.py --ocr      # 额外做 OCR（需 rapidocr_onnxruntime）
输出：_frames/f_*.jpg、_frames/sheet_*.jpg（20帧/张拼图）、_frames/report.txt
"""
import os, sys, json, glob, shutil, subprocess, argparse

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
    sys.exit('未找到 ffmpeg/ffprobe：安装静态包到 tools/ 或设 WB_FFMPEG_BIN 环境变量')


FF, FP = find_bin()
ap = argparse.ArgumentParser()
ap.add_argument('--src', default=CFG.get('src'))
ap.add_argument('--fps', type=float, default=1.0)
ap.add_argument('--ocr', action='store_true')
A = ap.parse_args()
SRC = A.src
assert SRC and os.path.exists(SRC), 'demo.json 缺 src 或文件不存在: %r' % SRC

FR = os.path.join(ROOT, '_frames')
os.makedirs(FR, exist_ok=True)
for p in glob.glob(os.path.join(FR, 'f_*.jpg')) + glob.glob(os.path.join(FR, 'sheet_*.jpg')):
    os.remove(p)

r = subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration:stream=width,height,avg_frame_rate',
                    '-of', 'default=nw=1', SRC], capture_output=True, text=True)
print(r.stdout.strip())
dur = float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'default=nw=1:nk=1', SRC], capture_output=True, text=True).stdout)
print('源时长 %.1fs' % dur)

subprocess.run([FF, '-y', '-v', 'error', '-i', SRC,
                '-vf', 'fps=%d,scale=960:540' % A.fps, os.path.join(FR, 'f_%05d.jpg')], check=True)

from PIL import Image, ImageChops, ImageDraw, ImageFont

frames = sorted(glob.glob(os.path.join(FR, 'f_*.jpg')))
print('抽帧 %d 张' % len(frames))

# 场景跳变检测：相邻帧平均像素差
diffs = [(0, 0.0)]
prev = Image.open(frames[0]).convert('L')
for i, p in enumerate(frames[1:], 1):
    cur = Image.open(p).convert('L')
    d = ImageChops.difference(prev, cur)
    stat = sum(d.getdata()) / (d.width * d.height)
    diffs.append((i, stat))
    prev = cur
order = sorted(diffs, key=lambda x: -x[1])[:40]
report = ['源: %s  时长 %.1fs  抽帧 %d 张' % (SRC, dur, len(frames)), '',
          'Top 场景跳变（src 秒数, 差异值）:']
for i, v in sorted(order):
    report.append('  src %6.1fs  diff %5.1f' % (i / A.fps, v))

# 拼图：20 帧/张，每帧标注 src 秒数
f_small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20) \
    if os.path.exists('C:/Windows/Fonts/msyh.ttc') else ImageFont.load_default()
TW, TH = 480, 270
cols, rows = 4, 5
for s in range(0, len(frames), cols * rows):
    batch = frames[s:s + cols * rows]
    sheet = Image.new('RGB', (TW * cols, TH * rows), 'black')
    for k, p in enumerate(batch):
        im = Image.open(p).resize((TW, TH))
        t = (s + k) / A.fps
        d = ImageDraw.Draw(im)
        d.rectangle([0, TH - 26, 150, TH], fill=(0, 0, 0))
        d.text((6, TH - 24), 'src %6.1fs' % t, font=f_small, fill=(255, 255, 0))
        sheet.paste(im, ((k % cols) * TW, (k // cols) * TH))
    sheet.save(os.path.join(FR, 'sheet_%02d.jpg' % (s // (cols * rows))), quality=88)
report += ['', '拼图 %d 张（_frames/sheet_*.jpg），逐帧核对节点请看图上 src 时间戳' %
           ((len(frames) + cols * rows - 1) // (cols * rows))]

# 可选 OCR
if A.ocr:
    try:
        from rapidocr_onnxruntime import RapidOCR
        ocr = RapidOCR()
        report += ['', 'OCR 主体文字:']
        import numpy as np
        for i, p in enumerate(frames):
            res, _ = ocr(np.array(Image.open(p)))
            texts = [t for _, t, c in (res or []) if c > 0.6 and len(t) >= 2]
            if texts:
                report.append('  src %6.1fs  %s' % (i / A.fps, ' | '.join(texts[:8])))
    except ImportError:
        report += ['', '(未安装 rapidocr_onnxruntime，跳过 OCR: pip install rapidocr_onnxruntime)']

open(os.path.join(FR, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(report))
print('\n'.join(report[:8]))
print('... 完整报告: _frames/report.txt')
