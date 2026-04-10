#!/bin/bash
set -euo pipefail
export PATH="/Users/liuxi/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
WORKDIR="/Users/liuxi/.openclaw/workspace/apps/agenthansa-local"
LOG_FILE="/Users/liuxi/.openclaw/workspace/logs/agenthansa-top1-stable.out"
STATE_FILE="/Users/liuxi/.openclaw/workspace/memory/agenthansa-top1-stable.json"
mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$STATE_FILE")"
cd "$WORKDIR"
set -a
source ./.env
set +a

BASE_INTERVAL=300
PROBLEM_INTERVAL=180
RANK_CHECK_INTERVAL=1800
PROBLEM_GAP=150
START_HOUR=15
START_EPOCH="$(date +%s)"
LAST_RANK_CHECK=0
TODAY="$(date +%F)"

cat > "$STATE_FILE" <<JSON
{"started_at":"$(date '+%F %T')","start_epoch":$START_EPOCH,"mode":"stable","base_interval":$BASE_INTERVAL,"problem_interval":$PROBLEM_INTERVAL,"rank_check_interval":$RANK_CHECK_INTERVAL,"problem_gap":$PROBLEM_GAP}
JSON

log(){
  echo "[$(date '+%F %T')] $*" | tee -a "$LOG_FILE"
}

fetch_rank_json(){
  /usr/bin/env python3 /Users/liuxi/.openclaw/workspace/apps/agenthansa-local/agenthansa-top1.py status 2>/dev/null || true
}

current_interval(){
  local now elapsed rank_json interval
  now="$(date +%s)"
  elapsed=$((now - START_EPOCH))
  interval=$BASE_INTERVAL
  if [ "$elapsed" -ge 43200 ]; then
    rank_json="$(fetch_rank_json)"
    interval="$(python3 - <<'PY' "$rank_json" "$PROBLEM_GAP" "$BASE_INTERVAL" "$PROBLEM_INTERVAL"
import json, sys
text=sys.argv[1].strip() or '{}'
problem_gap=int(sys.argv[2]); base=int(sys.argv[3]); problem=int(sys.argv[4])
try:
    data=json.loads(text)
except Exception:
    print(problem)
    raise SystemExit
rank=(data.get('rank') or {})
alliance_rank=rank.get('alliance_rank')
gap=rank.get('gap_to_first')
far = alliance_rank is None or (alliance_rank != 1 and (gap is None or float(gap) >= problem_gap))
print(problem if far else base)
PY
)"
  fi
  echo "$interval"
}

while true; do
  if [ "$(date +%F)" != "$TODAY" ]; then
    log "stop: date changed"
    break
  fi

  if [ "$(date +%H)" -lt "$START_HOUR" ]; then
    log "waiting until ${START_HOUR}:00"
    sleep 30
    continue
  fi

  now="$(date +%s)"
  if [ $((now - LAST_RANK_CHECK)) -ge "$RANK_CHECK_INTERVAL" ]; then
    rank_json="$(fetch_rank_json)"
    echo "$rank_json" > "$STATE_FILE.rank.json"
    python3 - <<'PY' "$rank_json" | tee -a "$LOG_FILE"
import json, sys
text=sys.argv[1].strip() or '{}'
try:
    data=json.loads(text)
except Exception:
    print('[rank] unavailable')
    raise SystemExit
rank=(data.get('rank') or {})
print(f"[rank] alliance={rank.get('alliance')} rank={rank.get('alliance_rank')} points={rank.get('alliance_points')} leader={rank.get('leader_name')} leader_points={rank.get('leader_points')} gap={rank.get('gap_to_first')} lead={rank.get('lead_over_second')}")
PY
    LAST_RANK_CHECK=$now
  fi

  interval="$(current_interval)"
  log "run-once interval=${interval}s"
  export AGENTHANSA_TASK_PUSH_START_HOUR=$START_HOUR
  export AGENTHANSA_TASK_PUSH_EVERY_SECONDS=$interval
  export AGENTHANSA_MAX_AUTO_QUESTS=1
  export AGENTHANSA_AGGRESSIVE_AUTO_QUESTS=1
  export AGENTHANSA_MAX_AUTO_COMMUNITY_TASKS=1
  export AGENTHANSA_AGGRESSIVE_AUTO_COMMUNITY_TASKS=1
  /usr/bin/env python3 /Users/liuxi/.openclaw/workspace/apps/agenthansa-local/agenthansa-top1.py run-once || true
  log "sleep ${interval}s"
  sleep "$interval"
done
