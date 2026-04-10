#!/usr/bin/env python3
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

RUNTIME_PROFILE = os.getenv('AGENTHANSA_RUNTIME_PROFILE', 'mac_openclaw').strip() or 'mac_openclaw'
BROWSER_PROOF_KEYWORDS = [
    'proof', 'proof_url', 'screenshot', 'screen recording', 'record video', 'upload photo',
    'twitter', 'x.com', 'reddit', 'linkedin', 'youtube', 'telegram', 'discord', 'external platform',
    'manual verification', 'verify manually', 'browser', 'open website', 'post link'
]
HIGH_VALUE_KEYWORDS = [
    'technical', 'documentation', 'migration', 'strategy', 'analysis', 'research', 'competitor',
    'case study', 'whitepaper', 'alliance', 'competitive'
]
SIMPLE_TEXT_KEYWORDS = ['faq', 'guide', 'compare', 'comparison', 'list', 'checklist', 'pricing']
SPAMMY_KEYWORDS = ['great post', 'nice post', 'thanks for sharing', 'quick feedback', 'short answer']


def _text(task_like):
    if isinstance(task_like, str):
        return task_like.lower()
    values = []
    if isinstance(task_like, dict):
        for k in ['title', 'description', 'goal', 'requirements', 'proof_requirements', 'instructions', 'category', 'tags']:
            v = task_like.get(k)
            if isinstance(v, list):
                values.extend(str(x) for x in v)
            elif v is not None:
                values.append(str(v))
    return ' '.join(values).lower()


def classify_task(task_like):
    text = _text(task_like)
    kind = str((task_like or {}).get('type') or (task_like or {}).get('kind') or '').lower() if isinstance(task_like, dict) else ''
    if 'red packet' in text or 'red-packet' in text or kind == 'redpacket':
        return 'redpacket'
    if any(x in text for x in ['daily quest', 'checkin', 'digest', 'distribute', 'curate', 'read forum']):
        return 'daily_api'
    if any(x in text for x in BROWSER_PROOF_KEYWORDS):
        return 'browser_proof_required'
    if any(x in text for x in SPAMMY_KEYWORDS):
        return 'skip'
    if any(x in text for x in HIGH_VALUE_KEYWORDS):
        return 'text_high_value'
    if any(x in text for x in SIMPLE_TEXT_KEYWORDS) or re.search(r'\b(write|draft|answer|explain)\b', text):
        return 'text_simple'
    if text.strip():
        return 'skip'
    return 'skip'


def browser_executor_stub(task):
    if RUNTIME_PROFILE != 'mac_openclaw':
        return {'ok': False, 'reason': 'profile_not_supported', 'profile': RUNTIME_PROFILE}
    return {
        'ok': False,
        'queued': True,
        'profile': RUNTIME_PROFILE,
        'task': task,
        'expected_proof_artifact': 'proof_url',
        'contract': {'input': 'task', 'output': {'ok': 'bool', 'proof_url': 'str?', 'error': 'str?'}},
    }


def leaderboard_snapshot(my_points, second_points, rank):
    gap = None
    boost_mode = True
    if my_points is not None and second_points is not None:
        gap = my_points - second_points
    if rank == 1 and gap is not None and gap >= 200:
        boost_mode = False
    return {'self_score': my_points, 'number2_score': second_points, 'gap': gap, 'boost_mode': boost_mode}


def fetch_rules_summary(url='https://agenthansa.com/llms.txt'):
    summary = {'ts': datetime.now(timezone.utc).isoformat(), 'url': url, 'ok': False, 'highlights': []}
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            txt = r.read().decode('utf-8', 'ignore')
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        keys = ['red packet', 'daily quest', 'competitive', 'proof_url', 'quality', 'spam']
        picks = [ln for ln in lines if any(k in ln.lower() for k in keys)][:8]
        summary.update({'ok': True, 'highlights': picks})
    except Exception as e:
        summary['error'] = str(e)
    return summary


if __name__ == '__main__':
    print(json.dumps({'profile': RUNTIME_PROFILE, 'sample_class': classify_task({'title': 'Write a technical migration guide'})}, ensure_ascii=False))
