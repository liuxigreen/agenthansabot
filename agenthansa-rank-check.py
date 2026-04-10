#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

CONFIG = '/root/.config/agenthansa/config.json'
BASE = 'https://www.agenthansa.com/api'
UA = 'OpenClaw-Xiami/1.0'
SAFE_LEAD_TARGET = int(os.getenv('AGENTHANSA_SAFE_LEAD_TARGET', '100'))


def load_cfg():
    with open(CONFIG) as f:
        return json.load(f)


def req(path, key):
    url = path if path.startswith('http') else BASE + path
    request = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Authorization': f'Bearer {key}',
    })
    with urllib.request.urlopen(request, timeout=30) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw else {}


def fetch_status(key):
    me = req('/agents/me', key)
    alliance_name = me.get('alliance')
    agent_name = me.get('name') or 'Xiami'

    alliance_daily = req('/agents/alliance-daily-leaderboard', key)
    global_daily = req('/agents/daily-points-leaderboard', key)

    alliance_info = (alliance_daily.get('alliances') or {}).get(alliance_name) or {}
    alliance_lb = alliance_info.get('leaderboard') or []
    global_lb = global_daily.get('leaderboard') or []

    alliance_row = next((row for row in alliance_lb if row.get('name') == agent_name), None)
    global_row = next((row for row in global_lb if row.get('name') == agent_name), None)

    alliance_leader = alliance_lb[0] if alliance_lb else None
    second_row = alliance_lb[1] if len(alliance_lb) > 1 else None

    status = {
        'agent_name': agent_name,
        'alliance': alliance_name,
        'alliance_display_name': alliance_info.get('name') or alliance_name,
        'alliance_rank': alliance_row.get('rank') if alliance_row else None,
        'alliance_points': alliance_row.get('today_points') if alliance_row else None,
        'global_rank': global_row.get('rank') if global_row else None,
        'global_points': global_row.get('today_points') if global_row else None,
        'leader_name': alliance_leader.get('name') if alliance_leader else None,
        'leader_points': alliance_leader.get('today_points') if alliance_leader else None,
        'second_name': second_row.get('name') if second_row else None,
        'second_points': second_row.get('today_points') if second_row else None,
    }

    if status['alliance_points'] is not None and status['leader_points'] is not None:
        status['gap_to_first'] = status['leader_points'] - status['alliance_points']
    else:
        status['gap_to_first'] = None

    if status['alliance_rank'] == 1 and status['alliance_points'] is not None and status['second_points'] is not None:
        status['lead_over_second'] = status['alliance_points'] - status['second_points']
    else:
        status['lead_over_second'] = None

    return status


def format_number(value):
    if value is None:
        return '?'
    num = float(value)
    if num.is_integer():
        return str(int(num))
    return f'{num:.2f}'.rstrip('0').rstrip('.')


def needs_chase(status):
    rank = status.get('alliance_rank')
    if rank is None:
        return True
    if rank != 1:
        return True
    lead = status.get('lead_over_second')
    if lead is None:
        return True
    return lead < SAFE_LEAD_TARGET


def main():
    try:
        cfg = load_cfg()
        key = cfg['api_key']

        status = fetch_status(key)
        if not needs_chase(status):
            print('NO_REPLY')
            return

        rank = status.get('alliance_rank')
        alliance_name = status.get('alliance_display_name') or 'Terra'
        if rank == 1:
            print(f"{alliance_name}#1，领先{format_number(status.get('lead_over_second'))}分，低于安全线")
        elif rank is None:
            print(f'{alliance_name}未上榜，需追分')
        else:
            print(f"{alliance_name}#{rank}，落后{format_number(status.get('gap_to_first'))}分，需追分")

    except Exception as e:
        print(f'巡检失败：{e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
