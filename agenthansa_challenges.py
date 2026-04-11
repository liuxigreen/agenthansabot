#!/usr/bin/env python3
import json

SUPPORTED_ACTIONS = {
    'forum_upvote',
    'forum_downvote',
    'forum_post',
    'forum_comment',
    'referral_generate',
    'digest_read',
}


def packet_text(packet):
    if not isinstance(packet, dict):
        return ''
    return ' '.join([
        str(packet.get('challenge_type') or ''),
        str(packet.get('title') or ''),
        str(packet.get('challenge_description') or ''),
        json.dumps(packet.get('how_to_join') or [], ensure_ascii=False),
    ]).lower()


def detect_challenge_action(packet):
    text = packet_text(packet)
    if 'downvote' in text or 'vote down' in text:
        return 'forum_downvote'
    if 'upvote' in text or 'vote up' in text:
        return 'forum_upvote'
    if 'forum post' in text or 'publish a post' in text or 'write a forum post' in text:
        return 'forum_post'
    if 'comment' in text:
        return 'forum_comment'
    if 'referral' in text or 'ref link' in text or 'generate_ref' in text:
        return 'referral_generate'
    if 'digest' in text or 'read forum' in text:
        return 'digest_read'
    return None


def execute_challenge_action(packet, handlers, on_unknown=None):
    action = detect_challenge_action(packet)
    if action not in SUPPORTED_ACTIONS:
        reason = f'unknown challenge action: {packet.get("challenge_description") or packet.get("title") or "unknown"}'
        if callable(on_unknown):
            on_unknown(packet, reason)
        return None, reason
    fn = (handlers or {}).get(action)
    if not callable(fn):
        reason = f'handler missing for action={action}'
        if callable(on_unknown):
            on_unknown(packet, reason)
        return action, reason
    try:
        ok, err = fn()
    except Exception as e:
        return action, str(e)
    return action, None if ok else (err or f'{action} failed')
