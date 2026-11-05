# -*- coding: utf-8 -*-
"""片头片尾页生成：封面页 + 参数化汇聚特效页 + 片尾A/B页。
用法: python scripts/make_pages.py     （读 demo.json）
产出: _segs/seg_title.mp4 / ov.mp4 / seg_end_a.mp4 / seg_end_b.mp4
配置字段:
  title:   {text, sub, dur}
  overview:{dur, top_label, chips:[4个能力名], bottom}
  tail:    {a_dur, b_dur, a_text="感谢观看", b_title, b_sub, b_note}
特效页时间线按 14s 参考节奏等比缩放到 overview.dur（重渲染，非拉长，保证 30fps 平滑）。
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
BRAND = (CFG.get('title') or {}).get('text') or CFG.get('brand') or CFG.get('prefix', '演示视频')
TMP = os.path.join(ROOT, '_segs')
os.makedirs(TMP, exist_ok=True)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    sys.exit('需要 Pillow: pip install pillow')

F_BIG = r'C:\Windows\Fonts\msyhbd.ttc'
F_NOR = r'C:\Windows\Fonts\msyh.ttc'


def font(path, size):
    return ImageFont.truetype(path, size) if os.path.exists(path) else ImageFont.load_default()


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    if r.returncode != 0:
        print('FAIL:', ' '.join(cmd)[:240]); print(r.stderr[-1200:]); raise SystemExit(1)
    return r


def gradient():
    im = Image.new('RGB', (W, H), (13, 32, 58)); d = ImageDraw.Draw(im)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)], fill=(int(13 + 18 * t), int(32 + 30 * t), int(58 + 45 * t)))
    return im


def dur_of(p):
    return float(run([FP, '-v', 'error', '-show_entries', 'format=duration',
                      '-of', 'default=nw=1:nk=1', p]).stdout.strip())


def encode_png(png, out, dur, fade_in=0.7, fade_out=None):
    vf = f'scale={W}:{H},fps={FPS},fade=t=in:st=0:d={fade_in}'
    if fade_out:
        vf += f',fade=t=out:st={dur - fade_out}:d={fade_out}'
    run([FF, '-y', '-loop', '1', '-i', png, '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
         '-t', str(dur), '-vf', vf, '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', out])
    print('%s  %.2fs' % (out, dur_of(out)))


# ---------- 1. 封面页 ----------
t = CFG.get('title') or {'text': CFG.get('prefix', '演示视频'), 'sub': '', 'dur': 3.0}
im = gradient(); d = ImageDraw.Draw(im)
f1 = font(F_BIG, 104); f2 = font(F_NOR, 44)
d.text((W // 2, H // 2 - 40), t.get('text', CFG.get('prefix', '演示视频')), font=f1, fill=(255, 255, 255), anchor='mm')
if t.get('sub'):
    d.line([(W // 2 - 240, H // 2 + 50), (W // 2 + 240, H // 2 + 50)], fill=(88, 132, 190), width=3)
    d.text((W // 2, H // 2 + 110), t['sub'], font=f2, fill=(176, 200, 232), anchor='mm')
png = os.path.join(TMP, 'title.png')
im.save(png)
encode_png(png, os.path.join(TMP, 'seg_title.mp4'), t.get('dur', 3.0), fade_in=0.5, fade_out=0.5)

# ---------- 2. 汇聚特效页（参数化，按 14s 参考节奏缩放） ----------
ov = CFG.get('overview') or {'dur': 14.0, 'chips': []}
DUR = float(ov.get('dur', 14.0))
SC = DUR / 14.0
N = int(FPS * DUR)
import math, random
random.seed(42)
CX, CY = W // 2, int(H * 0.463)
FRD = os.path.join(TMP, 'ovf')
os.makedirs(FRD, exist_ok=True)

base = gradient()
grid = Image.new('RGBA', (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(grid)
for x in range(0, W, 120):
    gd.line([(x, 0), (x, H)], fill=(80, 150, 230, 14))
for y in range(0, H, 120):
    gd.line([(0, y), (W, y)], fill=(80, 150, 230, 14))
base = Image.alpha_composite(base.convert('RGBA'), grid)
blob = Image.new('RGBA', (W, H), (0, 0, 0, 0)); bd = ImageDraw.Draw(blob)
bd.ellipse([CX - 500, CY - 360, CX + 500, CY + 360], fill=(40, 110, 200, 36))
blob = blob.filter(ImageFilter.GaussianBlur(120))
base = Image.alpha_composite(base, blob)


def glow_sprite(radius, color):
    s = radius * 6
    im2 = Image.new('RGBA', (s, s), (0, 0, 0, 0)); dd = ImageDraw.Draw(im2)
    for k in range(12, 0, -1):
        a = int(255 * (1 - k / 12) ** 2.2)
        dd.ellipse([s / 2 - radius * k / 3, s / 2 - radius * k / 3,
                    s / 2 + radius * k / 3, s / 2 + radius * k / 3], fill=color + (a,))
    return im2.filter(ImageFilter.GaussianBlur(radius * 0.5))


SP = [glow_sprite(8, (110, 215, 255)), glow_sprite(8, (130, 165, 255)), glow_sprite(7, (235, 245, 255))]
SP_CORE = glow_sprite(56, (110, 205, 255))
f_brand = font(F_BIG, 104); f_bs = font(F_NOR, 46)
f_top = font(F_NOR, 40); f_chip = font(F_BIG, 42); f_sub = font(F_NOR, 44)


def edge_point():
    side = random.choice('tblr')
    if side == 't': return random.randint(-100, W + 100), random.randint(-160, -60)
    if side == 'b': return random.randint(-100, W + 100), random.randint(H + 60, H + 160)
    if side == 'l': return random.randint(-200, -60), random.randint(-60, H + 60)
    return random.randint(W + 60, W + 200), random.randint(-60, H + 60)


particles = []
for i in range(96):
    ang = random.uniform(0, 2 * math.pi)
    R = random.uniform(150, 235)
    tgt = (CX + R * math.cos(ang), CY + R * math.sin(ang))
    p0 = edge_point()
    mx, my = (p0[0] + tgt[0]) / 2, (p0[1] + tgt[1]) / 2
    off = random.uniform(-260, 260)
    hyp = max(1e-6, math.hypot(tgt[0] - p0[0], tgt[1] - p0[1]))
    ctrl = (mx - (tgt[1] - p0[1]) / hyp * off, my + (tgt[0] - p0[0]) / hyp * off)
    particles.append(dict(p0=p0, ctrl=ctrl, tgt=tgt,
                          t0=random.uniform(0.0, 2.0) * SC, dur=random.uniform(2.0, 3.4) * SC,
                          sp=random.choice(SP), phase=random.uniform(0, 6.28), trail=[]))

chips = ov.get('chips', [])
targets = [(-260, int(H * 0.24)), (W + 260, int(H * 0.24)),
           (-260, int(H * 0.78)), (W + 260, int(H * 0.78))]
anchors = [(int(W * 0.36), int(H * 0.30)), (int(W * 0.68), int(H * 0.30)),
           (int(W * 0.36), int(H * 0.64)), (int(W * 0.68), int(H * 0.64))]
chips = [(label, targets[i % 4], anchors[i % 4]) for i, label in enumerate(chips[:4])]


def smooth(x):
    x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)


def bez(p0, c, p1, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
            u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1])


def ramp(t, a, b):
    return smooth((t - a) / max(1e-6, (b - a)))


def paste_glow(canvas, sprite, x, y, alpha=255):
    if alpha <= 0:
        return
    sp = sprite
    if alpha < 255:
        sp = sprite.copy()
        a = sp.getchannel('A').point(lambda v: v * alpha // 255)
        sp.putalpha(a)
    canvas.alpha_composite(sp, (int(x - sp.width / 2), int(y - sp.height / 2)))


for n in range(N):
    t = n / FPS
    frame = base.copy().convert('RGBA')
    ovl = Image.new('RGBA', (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ovl)

    a_top = int(255 * ramp(t, 0.30 * SC, 1.30 * SC))
    if a_top > 0:
        label = ov.get('top_label', '功 能 演 示 概 览')
        od.text((W / 2 + 1, 121), label, font=f_top, fill=(120, 200, 255, a_top // 2), anchor='mm')
        od.text((W / 2, 120), label, font=f_top, fill=(210, 230, 250, a_top), anchor='mm')
        od.line([(W / 2 - 130, 165), (W / 2 + 130, 165)], fill=(90, 160, 240, a_top // 2), width=2)

    for p in particles:
        pr = (t - p['t0']) / p['dur']
        if pr <= 0:
            continue
        if pr >= 1.0:
            a = int(150 + 100 * math.sin(t * 3 + p['phase']))
            tx, ty = p['tgt']
            paste_glow(ovl, p['sp'], tx, ty, max(40, a))
            od.line([(tx, ty), (CX + (tx - CX) * 0.25, CY + (ty - CY) * 0.25)],
                    fill=(100, 190, 255, 34), width=1)
            continue
        e = smooth(pr)
        x, y = bez(p['p0'], p['ctrl'], p['tgt'], e)
        p['trail'].append((x, y))
        if len(p['trail']) > 12:
            p['trail'].pop(0)
        for k in range(1, len(p['trail'])):
            fade = k / len(p['trail'])
            od.line([p['trail'][k - 1], p['trail'][k]],
                    fill=(120, 205, 255, int(200 * fade)), width=max(1, int(3 * fade)))
        paste_glow(ovl, p['sp'], x, y, 255)
        if pr > 0.75:
            la = int(130 * (pr - 0.75) / 0.25)
            od.line([(x, y), (x + (CX - x) * 0.45, y + (CY - y) * 0.45)],
                    fill=(130, 215, 255, la), width=2)

    a_core = int(255 * ramp(t, 1.40 * SC, 3.00 * SC))
    if a_core > 0:
        paste_glow(ovl, SP_CORE, CX, CY, a_core)
        for k in range(3):
            rr = 150 + k * 42 + 14 * math.sin(t * 2.2 + k)
            a = int((110 - k * 30) * a_core / 255)
            od.ellipse([CX - rr, CY - rr, CX + rr, CY + rr],
                       outline=(120, 205, 255, max(0, a)), width=3)
        rr = 218; rot = t * 0.9
        for si in range(22):
            a0 = rot + si * (2 * math.pi / 22)
            od.arc([CX - rr, CY - rr, CX + rr, CY + rr], math.degrees(a0), math.degrees(a0 + 0.10),
                   fill=(150, 220, 255, int(120 * a_core / 255)), width=2)

    a_brand = int(255 * ramp(t, 2.00 * SC, 3.20 * SC))
    if a_brand > 0:
        od.text((CX + 2, CY + 3), BRAND, font=f_brand, fill=(110, 205, 255, a_brand // 3), anchor='mm')
        od.text((CX, CY), BRAND, font=f_brand, fill=(255, 255, 255, a_brand), anchor='mm')
    a_bs = int(255 * ramp(t, 2.70 * SC, 3.90 * SC))
    if a_bs > 0:
        od.text((CX, CY + 88), ov.get('brand_sub', CFG.get('subtitle_brand', '')),
                font=f_bs, fill=(178, 208, 240, a_bs), anchor='mm')

    for i, (label, p0, tgt) in enumerate(chips):
        t0 = (4.60 + i * 0.28) * SC
        pr = (t - t0) / (1.70 * SC)
        if pr <= 0:
            continue
        e = smooth(pr)
        x = p0[0] + (tgt[0] - p0[0]) * e
        y = p0[1] + (tgt[1] - p0[1]) * e
        a = int(255 * ramp(t, t0, t0 + 0.7 * SC))
        if pr > 0.55:
            la = int(190 * ramp(t, t0 + 0.9 * SC, t0 + 1.9 * SC))
            od.line([(x, y), (x + (CX - x) * 0.62, y + (CY - y) * 0.62)],
                    fill=(120, 200, 255, la), width=2)
        tw = od.textlength(label, font=f_chip)
        bw, bh = tw + 76, 86
        od.rounded_rectangle([x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2], radius=14,
                             fill=(18, 42, 74, int(0.88 * a)), outline=(96, 182, 255, a), width=2)
        od.text((x, y), label, font=f_chip, fill=(232, 242, 252, a), anchor='mm')
        paste_glow(ovl, SP[0], x, y - bh / 2 - 10, a // 2)

    a_sub = int(255 * ramp(t, 7.20 * SC, 8.40 * SC))
    if a_sub > 0:
        od.line([(W / 2 - 240, H - 145), (W / 2 + 240, H - 145)], fill=(90, 160, 240, a_sub // 2), width=2)
        od.text((W / 2, H - 95), ov.get('bottom', ''), font=f_sub,
                fill=(196, 220, 245, a_sub), anchor='mm')

    Image.alpha_composite(frame, ovl).convert('RGB').save(os.path.join(FRD, 'f_%04d.png' % n))

print('特效页渲染 %d 帧' % N)
run([FF, '-y', '-framerate', str(FPS), '-i', os.path.join(FRD, 'f_%04d.png'),
     '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(DUR),
     '-vf', f'fps={FPS},fade=t=in:st=0:d=0.5,fade=t=out:st={DUR - 0.7}:d=0.7',
     '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
     '-c:a', 'aac', '-shortest', os.path.join(TMP, 'ov.mp4')])
print('ov.mp4  %.2fs' % dur_of(os.path.join(TMP, 'ov.mp4')))

# ---------- 3. 片尾两页 ----------
tl = CFG.get('tail') or {}
a_dur = float(tl.get('a_dur', 3.93)); b_dur = float(tl.get('b_dur', 2.0))
im = gradient(); d = ImageDraw.Draw(im)
d.text((W // 2, H // 2 - 70), tl.get('a_text', '感谢观看'), font=f_brand, fill=(255, 255, 255), anchor='mm')
d.line([(W // 2 - 230, H // 2 + 12), (W // 2 + 230, H // 2 + 12)], fill=(88, 132, 190), width=3)
d.text((W // 2, H // 2 + 80), tl.get('b_sub', CFG.get('subtitle_brand', '')),
       font=f_bs, fill=(176, 200, 232), anchor='mm')
png = os.path.join(TMP, 'end_a.png'); im.save(png)
encode_png(png, os.path.join(TMP, 'seg_end_a.mp4'), a_dur, 0.7, 0.6)

im = gradient(); d = ImageDraw.Draw(im)
d.text((W // 2, H // 2 - 120), tl.get('b_title', BRAND), font=f_brand, fill=(255, 255, 255), anchor='mm')
d.text((W // 2, H // 2 - 10), tl.get('b_sub', ''), font=f_bs, fill=(176, 200, 232), anchor='mm')
d.line([(W // 2 - 260, H // 2 + 60), (W // 2 + 260, H // 2 + 60)], fill=(88, 132, 190), width=3)
d.text((W // 2, H // 2 + 120), tl.get('b_note', ''), font=font(F_NOR, 26),
       fill=(140, 172, 210), anchor='mm')
png = os.path.join(TMP, 'end_b.png'); im.save(png)
encode_png(png, os.path.join(TMP, 'seg_end_b.mp4'), b_dur, 0.5, 0.5)
print('DONE')
