#!/usr/bin/env python3
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

RUNTIME_PROFILE = os.getenv('AGENTHANSA_RUNTIME_PROFILE', 'mac_openclaw').strip() or 'mac_openclaw'
HIGH_VALUE_REWARD_THRESHOLD = float(os.getenv('AGENTHANSA_HIGH_VALUE_REWARD_THRESHOLD', '20'))
LOW_REWARD_SKIP_THRESHOLD = float(os.getenv('AGENTHANSA_LOW_REWARD_SKIP_THRESHOLD', '0.5'))
LOW_REWARD_SIGNAL_THRESHOLD = float(os.getenv('AGENTHANSA_LOW_REWARD_SIGNAL_THRESHOLD', '2'))
BROWSER_PROOF_KEYWORDS = [
    'proof', 'proof_url', 'screenshot', 'screen recording', 'record video', 'upload photo',
    'twitter', 'x.com', 'reddit', 'linkedin', 'youtube', 'telegram', 'discord', 'external platform',
    'manual verification', 'verify manually', 'browser', 'open website', 'post link'
]
SPAMMY_KEYWORDS = ['great post', 'nice post', 'thanks for sharing', 'quick feedback', 'short answer']
DAILY_API_KEYWORDS = [
    'daily quest', 'checkin', 'check-in', 'curate', 'referral', 'distribute',
    'read forum', 'read digest', 'digest', 'simple create content', 'daily'
]
DAILY_API_BLOCKERS = [
    'proof_url', 'proof url', 'screenshot', 'screen recording', 'record video', 'external site',
    'external platform', 'browser', 'manual', 'post on', 'post to', 'twitter', 'x.com',
    'reddit', 'linkedin', 'youtube', 'telegram', 'discord'
]
ALLIANCE_HIGH_VALUE_KEYWORDS = ['alliance', 'competitive', 'merchant', 'campaign', 'strategy', 'proposal']
LONG_FORM_KEYWORDS = ['long-form', '1500', '1000', '800+', 'in-depth', 'detailed']
HIGH_VALUE_KEYWORDS = ['article', 'guide', 'seo', 'review', 'thread', 'campaign', 'strategy', 'proposal', 'writeup']
QUALITY_KEYWORDS = ['quality', 'creative', 'creativity', 'conversion', 'high quality', 'engaging']
HUMAN_JUDGING_KEYWORDS = ['human evaluation', 'subjective judging', 'judge', 'review panel', 'manual review']
SIMPLE_REPLY_KEYWORDS = ['templated reply', 'copy template', 'simple reply', 'one-line']
SIMPLE_DAILY_KEYWORDS = ['daily', 'checkin', 'check-in', 'routine']
SIMPLE_COMMENT_KEYWORDS = ['simple comment', 'forum reply', 'comment on forum', 'comment']
AMBIGUOUS_KEYWORDS = ['tbd', 'to be decided', 'something about', 'any topic', 'anything', 'vague']
SKIP_RISKY_KEYWORDS = ['wallet', 'fund', 'deposit', 'private key', 'seed phrase', 'pay upfront', 'airdrop dm']


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


def _reward_value(task_like):
    if not isinstance(task_like, dict):
        return 0.0
    candidates = []
    for key in ['reward', 'reward_amount', 'payout', 'rewards', 'bonus', 'prize', 'value']:
        value = task_like.get(key)
        if value is not None:
            candidates.append(value)
    for value in candidates:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            m = re.search(r'(\d+(?:\.\d+)?)', value)
            if m:
                return float(m.group(1))
        if isinstance(value, dict):
            for nested_key in ['amount', 'value', 'reward']:
                nested = value.get(nested_key)
                if isinstance(nested, (int, float)):
                    return float(nested)
                if isinstance(nested, str):
                    m = re.search(r'(\d+(?:\.\d+)?)', nested)
                    if m:
                        return float(m.group(1))
    return 0.0


def _contains_any(text, keywords):
    return any(k in text for k in keywords)


def _is_redpacket(task_like, text, kind):
    if kind == 'redpacket':
        return True
    if not isinstance(task_like, dict):
        return False
    if any(task_like.get(k) for k in ['challenge_description', 'next_packet_at']):
        return True
    if _contains_any(text, ['red packet', 'red-packet', 'join packet', 'join red']):
        return True
    return False


def _is_daily_api(text):
    if not _contains_any(text, DAILY_API_KEYWORDS):
        return False
    return not _contains_any(text, DAILY_API_BLOCKERS)


def _score_text_value(text, reward_value):
    score = 0
    reasons = []
    if reward_value >= HIGH_VALUE_REWARD_THRESHOLD:
        score += 3
        reasons.append(f'reward {reward_value:g} >= {HIGH_VALUE_REWARD_THRESHOLD:g} (+3)')
    if _contains_any(text, ALLIANCE_HIGH_VALUE_KEYWORDS):
        score += 3
        reasons.append('alliance/competitive/merchant context (+3)')
    if _contains_any(text, LONG_FORM_KEYWORDS):
        score += 2
        reasons.append('long-form writing required (+2)')
    if _contains_any(text, HIGH_VALUE_KEYWORDS):
        score += 2
        reasons.append('high-value writing keywords matched (+2)')
    if _contains_any(text, QUALITY_KEYWORDS):
        score += 2
        reasons.append('quality/creativity/conversion language (+2)')
    if _contains_any(text, HUMAN_JUDGING_KEYWORDS):
        score += 3
        reasons.append('human evaluation/subjective judging (+3)')

    if _contains_any(text, SIMPLE_REPLY_KEYWORDS):
        score -= 2
        reasons.append('simple templated reply signal (-2)')
    if _contains_any(text, SIMPLE_DAILY_KEYWORDS):
        score -= 3
        reasons.append('obvious daily/simple signal (-3)')
    if _contains_any(text, SIMPLE_COMMENT_KEYWORDS):
        score -= 3
        reasons.append('simple comment/forum interaction (-3)')
    if reward_value and reward_value <= LOW_REWARD_SIGNAL_THRESHOLD:
        score -= 2
        reasons.append(f'low reward {reward_value:g} <= {LOW_REWARD_SIGNAL_THRESHOLD:g} (-2)')
    if len(text.split()) < 8 or _contains_any(text, AMBIGUOUS_KEYWORDS):
        score -= 2
        reasons.append('vague/short/low-signal description (-2)')
    return score, reasons


def classify_task_detail(task_like):
    text = _text(task_like)
    kind = str((task_like or {}).get('type') or (task_like or {}).get('kind') or '').lower() if isinstance(task_like, dict) else ''
    reward_value = _reward_value(task_like)

    # Hard override: redpacket
    if _is_redpacket(task_like, text, kind):
        return {'task_class': 'redpacket', 'reason': 'hard override: deterministic red-packet semantics (challenge/join/next_packet)'}

    # Hard override: skip for high-risk/spam-prone/poor-fit tasks
    if _contains_any(text, SKIP_RISKY_KEYWORDS) or _contains_any(text, SPAMMY_KEYWORDS):
        return {'task_class': 'skip', 'reason': 'hard override: spam-risky or poor-fit automation task'}
    if reward_value and reward_value <= LOW_REWARD_SKIP_THRESHOLD and _contains_any(text, ['manual', 'external', 'proof', 'social', 'browser']):
        return {'task_class': 'skip', 'reason': f'hard override: low reward ({reward_value:g}) with high execution risk'}

    # Hard override: browser proof required
    if _contains_any(text, BROWSER_PROOF_KEYWORDS):
        return {'task_class': 'browser_proof_required', 'reason': 'hard override: proof/browser/external/manual verification required'}

    if _is_daily_api(text):
        return {'task_class': 'daily_api', 'reason': 'deterministic daily-quest family and API-completable without proof/browser steps'}

    score, reasons = _score_text_value(text, reward_value)
    reason = '; '.join(reasons) if reasons else 'no strong signals'
    if score >= 5:
        return {'task_class': 'text_high_value', 'reason': f'score={score} (>=5): {reason}'}
    if score >= 2:
        return {'task_class': 'text_simple', 'reason': f'score={score} (2-4): {reason}'}
    return {'task_class': 'skip', 'reason': f'final fallback: low-confidence/poor-fit task (score={score}): {reason}'}


def classify_task(task_like):
    return classify_task_detail(task_like)['task_class']


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
