#!/bin/bash
set -euo pipefail
cd /Users/liuxi/.openclaw/workspace/apps/agenthansa-local
chmod +x run-agenthansa-top1.sh
SRC="/Users/liuxi/.openclaw/workspace/apps/agenthansa-local/com.liuxi.agenthansa-top1.plist"
DST="$HOME/Library/LaunchAgents/com.liuxi.agenthansa-top1.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cp "$SRC" "$DST"
launchctl unload "$DST" >/dev/null 2>&1 || true
launchctl load "$DST"
launchctl kickstart -k gui/$(id -u)/com.liuxi.agenthansa-top1 || true
echo "installed: $DST"
