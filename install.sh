#!/usr/bin/env bash
# demo-video-maker 一键安装（macOS / Linux / Git Bash）
# 用法：bash install.sh [目标目录]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="${1:-$HOME/.workbuddy/skills/demo-video-maker}"

mkdir -p "$(dirname "$DST")"
rm -rf "$DST"
mkdir -p "$DST"

tar -C "$SRC" \
  --exclude=.git --exclude=__pycache__ --exclude='*.pyc' \
  --exclude=_segs --exclude=_frames --exclude=_voice --exclude=_selftest --exclude=_chk \
  --exclude='output*' --exclude='*.mp4' --exclude='*.wav' --exclude='*.mp3' \
  --exclude=tools --exclude=.venv --exclude=venv \
  -cf - . | tar -C "$DST" -xf -

echo "✔ skill 已安装到: $DST"
echo
echo "下一步："
echo "  1) 装依赖:  pip install -r \"$DST/requirements.txt\""
echo "  2) 准备 ffmpeg（三选一）:"
echo "     - 设环境变量 WB_FFMPEG_BIN 指向 ffmpeg 的 bin 目录"
echo "     - 放到工作目录 tools/ffmpeg-9.0.2-essentials_build/bin/"
echo "     - 安装到系统 PATH"
echo "  3) 在对话里说关键词「演示视频流水线」即可触发"
