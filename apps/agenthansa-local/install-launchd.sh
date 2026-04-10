#!/bin/bash
set -euo pipefail
cd /Users/liuxi/.openclaw/workspace/apps/agenthansa-local
chmod +x run-agenthansa-top1.sh run-once-agenthansa-top1.sh
SRC="/Users/liuxi/.openclaw/workspace/apps/agenthansa-local/com.liuxi.agenthansa-top1.plist"
DST="$HOME/Library/LaunchAgents/com.liuxi.agenthansa-top1.plist"
LABEL="com.liuxi.agenthansa-top1"
GUI_DOMAIN="gui/$(id -u)"
mkdir -p "$HOME/Library/LaunchAgents"
cp "$SRC" "$DST"
launchctl bootout "$GUI_DOMAIN" "$DST" >/dev/null 2>&1 || true
launchctl bootstrap "$GUI_DOMAIN" "$DST"
launchctl enable "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "$GUI_DOMAIN/$LABEL" || true
echo "installed: $DST"
launchctl print "$GUI_DOMAIN/$LABEL" 2>/dev/null | egrep 'state =|pid =|last exit code =' || true
