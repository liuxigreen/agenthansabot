#!/bin/bash
set -euo pipefail
export PATH="/Users/liuxi/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
cd /Users/liuxi/.openclaw/workspace/apps/agenthansa-local
set -a
source ./.env
set +a
export AGENTHANSA_TASK_PUSH_EVERY_SECONDS=120
export AGENTHANSA_MAX_AUTO_QUESTS=1
export AGENTHANSA_AGGRESSIVE_AUTO_QUESTS=1
export AGENTHANSA_MAX_AUTO_COMMUNITY_TASKS=1
export AGENTHANSA_AGGRESSIVE_AUTO_COMMUNITY_TASKS=1
export AGENTHANSA_RUN_EVERY_SECONDS=120
export AGENTHANSA_PRE_WATCH_SECONDS=30
export AGENTHANSA_WATCH_MAX_SECONDS=90
while true; do
  hour=$(date +%H)
  if [ "$hour" -ge 15 ]; then
    echo "[$(date '+%F %T')] stop: reached 15:00+"
    break
  fi
  echo "[$(date '+%F %T')] run-once"
  /usr/bin/env python3 /Users/liuxi/.openclaw/workspace/apps/agenthansa-local/agenthansa-top1.py run-once || true
  echo "[$(date '+%F %T')] sleep 120s"
  sleep 120
done
