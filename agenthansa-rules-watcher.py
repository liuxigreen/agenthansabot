#!/usr/bin/env python3
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(os.getenv('AGENTHANSA_RULES_WATCH_STATE', str(Path.home() / '.openclaw' / 'workspace' / 'memory' / 'agenthansa-rules-watch-state.json')))


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def rules_sources():
    configured = os.getenv('AGENTHANSA_RULES_SOURCES', '').strip()
    if configured:
        return [x.strip() for x in configured.split(',') if x.strip()]
    sources = ['https://agenthansa.com/llms.txt', 'https://agenthansa.com/llms-full.txt']
    forum_url = os.getenv('AGENTHANSA_RULES_FORUM_URL', '').strip()
    if forum_url:
        sources.append(forum_url)
    return sources


def fetch_source(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode('utf-8', 'ignore')


def infer_impact(content):
    text = (content or '').lower()
    tags = []
    if any(k in text for k in ['proof_url', 'screenshot', 'browser']):
        tags.append('browser-proof-policy')
    if any(k in text for k in ['red packet', 'red-packet']):
        tags.append('redpacket-flow')
    if any(k in text for k in ['daily quest', 'checkin', 'curate']):
        tags.append('daily-api-flow')
    if any(k in text for k in ['spam', 'quality', 'duplicate']):
        tags.append('anti-spam-policy')
    return tags or ['unknown']


def main():
    prev = load_state()
    latest = {}
    out = {'ts': datetime.utcnow().isoformat(timespec='seconds'), 'results': []}

    for src in rules_sources():
        item = {'source': src, 'change_type': 'no_change', 'impact': [], 'action': 'none'}
        try:
            content = fetch_source(src)
            digest = str(abs(hash(content)))
            latest[src] = {'hash': digest, 'updated_at': out['ts']}
            prev_hash = ((prev.get('sources') or {}).get(src) or {}).get('hash')
            if prev_hash is None:
                item['change_type'] = 'new_source'
                item['action'] = 'review_and_apply'
            elif prev_hash != digest:
                item['change_type'] = 'updated'
                item['action'] = 'review_and_apply'
            item['impact'] = infer_impact(content)
        except Exception as e:
            item['change_type'] = 'unreachable'
            item['impact'] = ['rules-source-unavailable']
            item['action'] = 'check_source_config'
            item['error'] = re.sub(r'\s+', ' ', str(e))[:240]
        out['results'].append(item)

    save_state({'ts': out['ts'], 'sources': latest})
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
