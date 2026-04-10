#!/usr/bin/env python3
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from datetime import datetime

CONFIG = Path('/root/.config/agenthansa/config.json')
BASE = 'https://www.agenthansa.com/api'
UA = 'OpenClaw-Xiami/1.0'
AUTO_SCRIPT = '/root/.openclaw/workspace/scripts/agenthansa-auto.py'
SAFE_LEAD_TARGET = 100


def load_cfg():
    return json.loads(CONFIG.read_text())


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
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'agent_name': agent_name,
        'alliance': alliance_name,
        'alliance_display_name': alliance_info.get('name') or alliance_name,
        'alliance_members': alliance_info.get('members'),
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


def format_rank(status):
    rank = status.get('alliance_rank')
    if rank is None:
        return 'Terra未上榜'
    if rank == 1:
        return f"Terra#1 +{format_number(status.get('lead_over_second'))}"
    return f"Terra#{rank} -{format_number(status.get('gap_to_first'))}"


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


def decide_push_rounds(status):
    rank = status.get('alliance_rank') or 99
    gap = status.get('gap_to_first') or 999
    if rank >= 4 and gap <= 30:
        return 3
    if rank >= 3 and gap <= 30:
        return 2
    if rank != 1:
        return 1
    lead = status.get('lead_over_second')
    if lead is None or lead < SAFE_LEAD_TARGET:
        return 1
    return 0


def parse_auto_output(output):
    parsed = {'result': '', 'blocker': '', 'next_step': ''}
    for line in [line.strip() for line in output.splitlines() if line.strip()]:
        if line.startswith('结果：'):
            parsed['result'] = line.split('：', 1)[1].strip()
        elif line.startswith('blocker：'):
            parsed['blocker'] = line.split('：', 1)[1].strip()
        elif line.startswith('下一步：'):
            parsed['next_step'] = line.split('：', 1)[1].strip()
    return parsed


def run_auto_push(rounds=1):
    last_info = {'result': '', 'blocker': '', 'next_step': ''}
    last_rc = 0
    for i in range(max(1, rounds)):
        proc = subprocess.run(
            ['python3', AUTO_SCRIPT],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        last_rc = proc.returncode
        output = '\n'.join(x for x in [proc.stdout.strip(), proc.stderr.strip()] if x).strip()
        if output:
            last_info = parse_auto_output(output)
            if not any(last_info.values()):
                lines = [line.strip() for line in output.splitlines() if line.strip()]
                last_info['blocker'] = lines[-1] if lines else output
        if proc.returncode != 0:
            break
    return last_rc, last_info


def main():
    try:
        cfg = load_cfg()
        key = cfg['api_key']

        before = fetch_status(key)
        if not needs_chase(before):
            print('NO_REPLY')
            return

        rounds = decide_push_rounds(before)
        rc, _push_info = run_auto_push(rounds)
        after = fetch_status(key)

        if rc != 0:
            if after.get('alliance_rank') == 1:
                print(f"Terra#1，领先{format_number(after.get('lead_over_second'))}分，推进失败")
            elif after.get('alliance_rank') is None:
                print('Terra未上榜，推进失败')
            else:
                print(f"Terra#{after.get('alliance_rank')}，落后{format_number(after.get('gap_to_first'))}分，推进失败")
            sys.exit(1)

        rank = after.get('alliance_rank')
        if rank == 1:
            print(f"Terra#1，领先{format_number(after.get('lead_over_second'))}分，已追分{rounds}轮")
        elif rank is None:
            print(f"Terra未上榜，已追分{rounds}轮")
        else:
            print(f"Terra#{rank}，落后{format_number(after.get('gap_to_first'))}分，已追分{rounds}轮")

    except Exception as e:
        print(f'巡检失败：{e}')
        sys.exit(1)
