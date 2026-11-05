# -*- coding: utf-8 -*-
"""numpy 样本级混音（**禁止**用 ffmpeg amix 大滤镜图：>20 路输入会静默丢 adelay，语音全堆在开头）。
用法: python scripts/mix_numpy.py [gain]
产出: _voice/voice.wav、<outdir>/<prefix>_配音版_<tag>.mp4

做法：逐句解码为 48k 单声道 -> 按 10ms 帧阈值裁掉 TTS 片头静音垫（否则整体晚约 0.19s）
      -> 精确放到该句字幕起点 -> 全轨求和 -> 增益/限幅 -> 写 wav -> 与成片混流。
"""
import os, sys, json, shutil, subprocess, wave
import numpy as np

ROOT = os.getcwd()
CFG = json.load(open(os.path.join(ROOT, 'demo.json'), encoding='utf-8'))
VO = os.path.join(ROOT, '_voice')
TMP = os.path.join(ROOT, '_segs')
OUTDIR = os.path.join(ROOT, CFG.get('outdir', '输出'))
os.makedirs(OUTDIR, exist_ok=True)
TOTAL = float(CFG.get('total', 300.0))
GAIN = float(sys.argv[1]) if len(sys.argv) > 1 else float((CFG.get('voice') or {}).get('gain', 0.88))
SR = 48000


def find_bin():
    cands = [os.environ.get('WB_FFMPEG_BIN'),
             os.path.join(ROOT, 'tools', 'ffmpeg-9.0.2-essentials_build', 'bin'),
             os.path.join(ROOT, '..', 'tools', 'ffmpeg-9.0.2-essentials_build', 'bin')]
    for c in cands:
        if c:
            for exe in ('ffmpeg.exe', 'ffmpeg'):
                if os.path.exists(os.path.join(c, exe)):
                    return os.path.join(c, exe)
    if shutil.which('ffmpeg'):
        return shutil.which('ffmpeg')
    sys.exit('未找到 ffmpeg/ffprobe')


FF = find_bin()
plan = json.load(open(os.path.join(VO, 'plan.json'), encoding='utf-8'))


def decode(path, atempo):
    af = f'atempo={atempo}' if atempo and atempo != 1.0 else 'anull'
    r = subprocess.run([FF, '-v', 'error', '-i', path, '-af', af,
                        '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True)
    assert r.returncode == 0, (path, r.stderr[-300:])
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def trim_lead(x, th=0.004, frame=480):
    """裁掉片头静音垫：10ms 帧 RMS 首个超阈帧，回退 1 帧留气口。"""
    n = len(x) // frame
    if n == 0:
        return x
    rms = np.sqrt(np.array([np.mean(x[i * frame:(i + 1) * frame] ** 2) for i in range(n)]))
    nz = np.where(rms > th)[0]
    if len(nz) == 0:
        return x
    return x[max(0, int(nz[0]) - 1) * frame:]


buf = np.zeros(int(TOTAL * SR), dtype=np.float64)
for it in plan:
    clip = trim_lead(decode(it['path'], it.get('atempo', 1.0)))
    i0 = int(round(it['st'] * SR))
    i1 = min(i0 + len(clip), len(buf))
    if i1 > i0:
        buf[i0:i1] += clip[:i1 - i0]
    fill = (len(clip) / SR) / max(1e-6, it['en'] - it['st'])
    print('#%02d %6.2fs 起 长%.2fs 填充%3.0f%%  %s'
          % (it['i'], it['st'], len(clip) / SR, fill * 100, it['text'][:16]))

mix = buf * GAIN
peak = np.abs(mix).max()
if peak > 0.98:
    print('峰值超限，增益自动缩至 %.3f' % (0.98 / peak * GAIN))
    mix *= 0.98 / peak
peak = np.abs(mix).max()
print('电平: mean %.1f dB  peak %.1f dB'
      % (20 * np.log10(np.sqrt(np.mean(mix ** 2)) + 1e-12), 20 * np.log10(peak + 1e-12)))

stereo = np.repeat((np.clip(mix, -1, 1) * 32767).astype(np.int16)[:, None], 2, axis=1)
wav = os.path.join(VO, 'voice.wav')
with wave.open(wav, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(stereo.tobytes())
print('voice.wav 已写入 (%.2fs)' % (len(stereo) / SR))

tag = CFG.get('tag', '5min')
voiced = os.path.join(OUTDIR, '%s_配音版_%s.mp4' % (CFG.get('prefix', '演示视频'), tag))
r = subprocess.run([FF, '-y', '-i', os.path.join(TMP, 'subbed.mp4'), '-i', wav,
                    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '128k', '-shortest', '-t', str(TOTAL), voiced],
                   capture_output=True, text=True, encoding='utf-8', errors='ignore')
assert r.returncode == 0, r.stderr[-800:]
print('配音版:', voiced)
