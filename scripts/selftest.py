# -*- coding: utf-8 -*-
"""自检：用合成录屏把七个阶段全跑一遍，验证脚本链路完好。
用法: python scripts/selftest.py [--no-voice]
在任意可写目录执行，产物落在 ./_selftest（可随时删除）。
"""
import os, sys, json, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(os.getcwd(), '_selftest')
NO_VOICE = '--no-voice' in sys.argv


def find_ff():
    cands = [os.environ.get('WB_FFMPEG_BIN'),
             os.path.join(os.getcwd(), 'tools', 'ffmpeg-9.0.2-essentials_build', 'bin'),
             os.path.join(os.getcwd(), '..', 'tools', 'ffmpeg-9.0.2-essentials_build', 'bin')]
    for c in cands:
        if c:
            for exe in ('ffmpeg.exe', 'ffmpeg'):
                if os.path.exists(os.path.join(c, exe)):
                    return os.path.join(c, exe)
    if shutil.which('ffmpeg'):
        return shutil.which('ffmpeg')
    sys.exit('未找到 ffmpeg')


FF = find_ff()
if os.path.isdir(WORK):
    shutil.rmtree(WORK)
os.makedirs(WORK)

print('[0] 生成 40s 合成录屏 ...')
r = subprocess.run([FF, '-y', '-v', 'error', '-f', 'lavfi',
                    '-i', 'testsrc2=size=1920x1080:rate=30:duration=40',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                    '-pix_fmt', 'yuv420p', os.path.join(WORK, 'src.mp4')])
assert r.returncode == 0, '合成录屏失败'

CFG = {
    "src": "src.mp4", "w": 1920, "h": 1080, "fps": 30, "total": 23.93,
    "prefix": "自检", "tag": "selftest", "outdir": "输出",
    "mask": {"enable": True, "x": 200, "y": 100, "w": 400, "h": 80},
    "title": {"text": "示例产品", "sub": "智能问数平台", "dur": 2.0},
    "overview": {"dur": 6.0, "top_label": "功能演示概览",
                 "chips": ["数据接入与管理", "创建 AI 数据助手", "自然语言智能问数", "业务知识沉淀"],
                 "bottom": "从数据到答案"},
    "tail": {"a_dur": 3.93, "b_dur": 2.0, "a_text": "感谢观看", "b_title": "示例产品",
             "b_sub": "让数据自己说话", "b_note": "自检页"},
    "sub_style": {"font": "Microsoft YaHei", "size": 50, "outline": 2, "margin_v": 60},
    "voice": {"enabled": True, "voice": "zh-CN-XiaoxiaoNeural", "gain": 0.88, "fill": 0.92,
              "rate_min": -18, "rate_max": 20, "natural_idx": [0],
              "intro": [[0.30, 2.70, "测试片头旁白"]]},
    "segs": [
        [2.0, 5.0, False, "段一", [[0.2, 2.4, "第一段说明"], [2.5, 4.8, "第二个要点"]]],
        [10.0, 5.0, True, "段二", [[0.2, 2.4, "遮掉品牌字样"], [2.5, 4.8, "画面干净了"]]],
    ],
    "freeze": {}, "slow": {},
}
json.dump(CFG, open(os.path.join(WORK, 'demo.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)

STEPS = [('素材分析', 'analyze_recording.py'),
         ('片头片尾', 'make_pages.py'),
         ('切段', 'cut_segments.py'),
         ('拼接字幕', 'assemble.py')]
if not NO_VOICE:
    STEPS += [('TTS 合成', 'synth_voice.py'), ('混音', 'mix_numpy.py'), ('对齐体检', 'check_sync.py')]

for name, script in STEPS:
    print('[%s] %s ...' % (name, script))
    r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=WORK,
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')
    tail = (r.stdout or '').strip().splitlines()[-4:]
    for line in tail:
        print('   ', line)
    if r.returncode != 0:
        print((r.stderr or '')[-1500:])
        sys.exit('FAIL 于 %s' % script)

fp = os.path.join(os.path.dirname(FF), os.path.basename(FF).replace('ffmpeg', 'ffprobe'))
for f in sorted(os.listdir(os.path.join(WORK, '输出'))):
    if f.endswith('.mp4'):
        d = subprocess.run([fp, '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'default=nw=1:nk=1', os.path.join(WORK, '输出', f)],
                           capture_output=True, text=True).stdout.strip()
        print('   %s  %ss' % (f, d))
print('\nSELFTEST PASS  产物在 %s' % WORK)
