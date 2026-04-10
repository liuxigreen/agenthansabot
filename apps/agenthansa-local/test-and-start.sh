#!/bin/bash
set -euo pipefail
cd /Users/liuxi/.openclaw/workspace/apps/agenthansa-local
chmod +x run-agenthansa-top1.sh install-launchd.sh
set -a
source ./.env
set +a
printf '\n=== test-keys ===\n'
python3 agenthansa-top1.py test-keys
printf '\n=== run-once ===\n'
python3 agenthansa-top1.py run-once || true
printf '\n=== install-launchd ===\n'
bash install-launchd.sh
printf '\n=== launchd status ===\n'
launchctl print gui/$(id -u)/com.liuxi.agenthansa-top1 | sed -n '1,120p' || true
