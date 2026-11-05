# -*- coding: utf-8 -*-
"""配音/字幕对齐终检。用法: python scripts/check_sync.py
三项指标:
  1) 起讲偏差：每条字幕起点后语音真实起点（10ms RMS 门限），应 ≤0.15s
  2) 收尾余量：语音结束相对字幕结束（>0 表示没说完就换字幕）
  3) 内容相关：在该句字幕起点 ±0.3s 搜索最佳时移后的 10ms 包络相关，应 ≥0.95（最低 ≥0.5）
     —— 必须用包络而非原始波形：atempo 会引入相位差，波形相关会假性归零；
        混音裁掉了 TTS 片头静音垫，也必然存在固定时移。
"""
import os, sys, json, shutil, subprocess
import numpy as np

ROOT = os.getcwd()
CFG = json.load(open(os.path.join(ROOT, 'demo.json'), encoding='utf-8'))
VO = os.path.join(ROOT, '_voice')
MIX = os.path.join(VO, 'voice.wav')
TOTAL = float(CFG.get('total', 300.0))
SR = 16000


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
    sys.exit('未找到 ffmpeg')


FF = find_bin()
plan = json.load(open(os.path.join(VO, 'plan.json'), encoding='utf-8'))


def pcm(path, atempo=None):
    af = f'atempo={atempo}' if atempo and atempo != 1.0 else 'anull'
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-af', af,
                          '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def trim_lead(y, th=0.004, frame=160):
    k = len(y) // frame
    if k == 0:
        return y
    r = np.sqrt(np.array([np.mean(y[i * frame:(i + 1) * frame] ** 2) for i in range(k)]))
    nz = np.where(r > th)[0]
    return y[max(0, int(nz[0]) - 1) * frame:] if len(nz) else y


def env(y, frame=160):
    k = len(y) // frame
    return np.sqrt(np.array([np.mean(y[i * frame:(i + 1) * frame] ** 2) for i in range(k)]))


x = pcm(MIX)
hop = int(0.01 * SR)
n = len(x) // hop
rms = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, 'valid'))[::hop][:n]
TH = 0.004
print('混音轨 %.2fs，门限 %.3f' % (len(x) / SR, TH))

rows = []
for i, it in enumerate(plan):
    st, en = it['st'], it['en']
    nxt = plan[i + 1]['st'] if i + 1 < len(plan) else TOTAL
    a = int(max(0, (st - 0.45) * SR) // hop)
    b = int((st + 0.9) * SR) // hop
    seg = np.where(rms[a:min(b, n)] > TH)[0]
    onset = (a + seg[0]) * hop / SR if len(seg) else None
    c = int(st * SR // hop)
    d = int(min(en + 0.35, nxt - 0.03) * SR // hop)
    seg2 = np.where(rms[c:max(d, c + 1)] > TH)[0]
    tail = ((c + seg2[-1] + 1) * hop / SR - en) if len(seg2) else None

    clip = trim_lead(pcm(it['path'], it.get('atempo')))
    ec = env(clip)
    best_cc, best_lag = -1.0, 0.0
    for lag in range(-30, 31):
        i0 = int(round(st / 0.01)) + lag
        if i0 < 0:
            continue
        seg_e = rms[i0:i0 + len(ec)]
        L = min(len(seg_e), len(ec))
        if L < 20:
            continue
        a1 = ec[:L] - ec[:L].mean(); a2 = seg_e[:L] - seg_e[:L].mean()
        den = np.sqrt((a1 ** 2).sum() * (a2 ** 2).sum())
        cc = float((a1 * a2).sum() / den) if den > 0 else 0.0
        if cc > best_cc:
            best_cc, best_lag = cc, lag * 0.01
    off = None if onset is None else onset - st
    rows.append((i, st, en, off, tail, best_cc, best_lag, it['text']))

os_ = [r[3] for r in rows if r[3] is not None]
tl_ = [r[4] for r in rows if r[4] is not None]
cc_ = [r[5] for r in rows]
lg_ = [r[6] for r in rows]
late = sum(1 for v in os_ if abs(v) > 0.15)
print()
print('起讲偏差：均值 %+.2fs，范围 %+.2fs ~ %+.2fs，超 0.15s 的 %d 条'
      % (np.mean(os_), min(os_), max(os_), late))
print('收尾余量：均值 %+.2fs，最小 %+.2fs' % (np.mean(tl_), min(tl_)))
print('内容相关：均值 %.3f，最低 %.3f' % (np.mean(cc_), min(cc_)))
print('最佳时移：均值 %+.3fs，范围 %+.3fs ~ %+.3fs' % (np.mean(lg_), min(lg_), max(lg_)))
print()
print('%-3s %-8s %-7s %-7s %-7s %-7s %s' % ('#', '字幕起', '档位', '起讲', '最佳移', '相关', '文案'))
for i, st, en, off, tail, cc, lag, text in rows:
    bad = '' if (off is not None and abs(off) <= 0.15 and cc >= 0.5) else '  <<<'
    if i < 5 or i >= len(rows) - 4 or bad:
        print('%-3d %-8.2f %6.1fs %+7.2f %+7.2f %7.3f  %s%s'
              % (i, st, en - st, off if off is not None else 9.99, lag, cc, text[:18], bad))

ok = late == 0 and np.mean(cc_) >= 0.95 and min(cc_) >= 0.5
print('\n结论:', 'PASS 全部对齐' if ok else 'FAIL 存在偏差，按上表 <<< 行修正')
sys.exit(0 if ok else 1)
