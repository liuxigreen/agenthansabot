#!/usr/bin/env python3
import json
import os
from pathlib import Path

from agenthansa_runtime_profile import leaderboard_snapshot

STATE = Path(os.getenv('AGENTHANSA_STATE', '/root/.openclaw/workspace/memory/agenthansa-state.json'))


def main():
    data = json.loads(STATE.read_text()) if STATE.exists() else {}
    rank = (data.get('last_rank_status') or {}).get('alliance_rank')
    my_points = (data.get('last_rank_status') or {}).get('alliance_points')
    second_points = (data.get('last_rank_status') or {}).get('second_points')
    print(json.dumps(leaderboard_snapshot(my_points, second_points, rank), ensure_ascii=False))


if __name__ == '__main__':
    main()
