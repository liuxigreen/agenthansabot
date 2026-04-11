#!/usr/bin/env python3
import hashlib
import os
import time
from datetime import datetime

COMMENT_COOLDOWN_SECONDS = int(os.getenv('AGENTHANSA_COMMENT_COOLDOWN_SECONDS', '1500'))
POST_COOLDOWN_SECONDS = int(os.getenv('AGENTHANSA_POST_COOLDOWN_SECONDS', '1800'))
PATTERN_COOLDOWN_SECONDS = int(os.getenv('AGENTHANSA_PATTERN_COOLDOWN_SECONDS', '1200'))
DAILY_COMMENT_CAP = int(os.getenv('AGENTHANSA_DAILY_COMMENT_CAP', '8'))
DAILY_POST_CAP = int(os.getenv('AGENTHANSA_DAILY_POST_CAP', '4'))
SPAM_PAUSE_SECONDS = int(os.getenv('AGENTHANSA_SPAM_PAUSE_SECONDS', '3600'))


def _hash_text(text):
    return hashlib.sha256((text or '').strip().lower().encode('utf-8')).hexdigest()


def _today():
    return datetime.utcnow().strftime('%Y-%m-%d')


def _guard_state(state):
    if not isinstance(state, dict):
        state = {}
    guard = state.setdefault('anti_spam_guard', {})
    if guard.get('day') != _today():
        guard.clear()
        guard.update({
            'day': _today(),
            'counts': {'comment': 0, 'post': 0},
            'last_action_epoch': {},
            'pattern_last_epoch': {},
            'content_hashes': [],
            'spam_risk_mode': False,
            'spam_pause_until': 0,
        })
    return guard


def guard_can_write(state, action, content='', pattern=''):
    now = int(time.time())
    guard = _guard_state(state)
    if guard.get('spam_risk_mode') and now < int(guard.get('spam_pause_until', 0) or 0):
        return False, 'spam-risk mode active; risky write actions paused'

    cooldown = COMMENT_COOLDOWN_SECONDS if action == 'comment' else POST_COOLDOWN_SECONDS
    last_epoch = int((guard.get('last_action_epoch') or {}).get(action, 0) or 0)
    if last_epoch and now - last_epoch < cooldown:
        return False, f'{action} cooldown active ({cooldown - (now - last_epoch)}s remaining)'

    counts = guard.get('counts') or {}
    if action == 'comment' and int(counts.get('comment', 0) or 0) >= DAILY_COMMENT_CAP:
        guard['spam_risk_mode'] = True
        guard['spam_pause_until'] = now + SPAM_PAUSE_SECONDS
        return False, 'daily comment cap reached; entering spam-risk pause'
    if action == 'post' and int(counts.get('post', 0) or 0) >= DAILY_POST_CAP:
        guard['spam_risk_mode'] = True
        guard['spam_pause_until'] = now + SPAM_PAUSE_SECONDS
        return False, 'daily post cap reached; entering spam-risk pause'

    p_key = _hash_text(pattern or content)[:16]
    pattern_last = int((guard.get('pattern_last_epoch') or {}).get(p_key, 0) or 0)
    if pattern_last and now - pattern_last < PATTERN_COOLDOWN_SECONDS:
        return False, 'repeated task-pattern cooldown active'

    content_hash = _hash_text(content)
    known = set(guard.get('content_hashes') or [])
    if content_hash in known:
        guard['spam_risk_mode'] = True
        guard['spam_pause_until'] = now + SPAM_PAUSE_SECONDS
        return False, 'duplicate content detected; entering spam-risk pause'
    return True, None


def guard_record_write(state, action, content='', pattern=''):
    now = int(time.time())
    guard = _guard_state(state)
    counts = guard.setdefault('counts', {'comment': 0, 'post': 0})
    counts[action] = int(counts.get(action, 0) or 0) + 1
    last = guard.setdefault('last_action_epoch', {})
    last[action] = now
    p_last = guard.setdefault('pattern_last_epoch', {})
    p_last[_hash_text(pattern or content)[:16]] = now
    hashes = [h for h in (guard.get('content_hashes') or []) if h]
    hashes.append(_hash_text(content))
    guard['content_hashes'] = hashes[-200:]
