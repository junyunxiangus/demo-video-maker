# -*- coding: utf-8 -*-
"""切段：按 demo.json 的 segs/freeze/slow/mask 从源录屏切出各内容段。
用法: python scripts/cut_segments.py
产出: _segs/seg_00.mp4 ... （drawbox 遮盖 + SLOW 慢放 + FREEZE 末帧定格 + 统一 fps）
段定义: [src_start, src_dur, mask_bool, note, [[偏移a, 偏移b, 字幕], ...]]
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
SRC = CFG['src']
W, H, FPS = CFG.get('w', 1920), CFG.get('h', 1080), CFG.get('fps', 30)
MASK = CFG.get('mask') or {}
MASK.setdefault('color', '0x0F2C4A')
TMP = os.path.join(ROOT, '_segs')
os.makedirs(TMP, exist_ok=True)
SEGS, FREEZE, SLOW = CFG['segs'], CFG.get('freeze') or {}, CFG.get('slow') or {}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    if r.returncode != 0:
        print('FAIL:', ' '.join(cmd)[:240]); print(r.stderr[-1200:]); raise SystemExit(1)
    return r


def dur_of(p):
    return float(run([FP, '-v', 'error', '-show_entries', 'format=duration',
                      '-of', 'default=nw=1:nk=1', p]).stdout.strip())


for idx, (ss, dur, mask, note, subs) in enumerate(SEGS):
    out = os.path.join(TMP, 'seg_%02d.mp4' % idx)
    fz = float(FREEZE.get(idx, 0.0))
    rate = float(SLOW.get(idx, 1.0))
    vf = []
    if mask and MASK:
        vf.append('drawbox=x={x}:y={y}:w={w}:h={h}:color={color}@1:t=fill'.format(**MASK))
    vf.append(f'scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:0:black')
    if rate != 1.0:
        vf.append(f'setpts=PTS/{rate}')          # 慢放：拉长时间戳
    vf.append(f'fps={FPS}')                       # 复制帧补齐，保持平滑
    if fz > 0:
        vf.append(f'tpad=stop_mode=clone:stop_duration={fz}')
    run([FF, '-y', '-ss', str(ss), '-t', str(dur), '-i', SRC, '-vf', ','.join(vf),
         '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', '-an', out])
    expect = dur / rate + fz
    real = dur_of(out)
    assert abs(real - expect) < 0.3, 'seg%02d 期望 %.2fs 实际 %.2fs（%s）' % (idx, expect, real, note)
    print('seg%02d %-16s src=%6.1f +%4.1fs%s%s -> %.2fs'
          % (idx, note, ss, dur, ' 慢放x%.2f' % rate if rate != 1 else '',
             ' 定格%.1fs' % fz if fz else '', real))
print('DONE %d 段' % len(SEGS))
