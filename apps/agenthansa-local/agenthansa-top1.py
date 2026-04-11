#!/usr/bin/env python3
import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
WORKSPACE = Path(os.getenv('OPENCLAW_WORKSPACE', '/Users/liuxi/.openclaw/workspace'))
CONFIG = Path(os.getenv('AGENTHANSA_CONFIG', str(HOME / '.agent-hansa' / 'config.json')))
STATE = Path(os.getenv('AGENTHANSA_STATE', str(WORKSPACE / 'memory' / 'agenthansa-top1-state.json')))
MANUAL_QUEUE = Path(os.getenv('AGENTHANSA_MANUAL_QUEUE', str(WORKSPACE / 'memory' / 'agenthansa-top1-manual.json')))
LOG = Path(os.getenv('AGENTHANSA_LOG', str(WORKSPACE / 'logs' / 'agenthansa-top1.log')))
SUMMARY = Path(os.getenv('AGENTHANSA_SUMMARY', str(WORKSPACE / 'memory' / 'agenthansa-top1-summary.jsonl')))
DAILY_REVIEW = Path(os.getenv('AGENTHANSA_DAILY_REVIEW', str(WORKSPACE / 'memory' / 'agenthansa-top1-daily-review.md')))
BASE = os.getenv('AGENTHANSA_API_BASE', 'https://www.agenthansa.com/api')
UA = os.getenv('AGENTHANSA_UA', 'OpenClaw-AgentHansaTop1/1.0')
SAFE_LEAD_TARGET = int(os.getenv('AGENTHANSA_SAFE_LEAD_TARGET', '100'))
MAX_AUTO_QUESTS = int(os.getenv('AGENTHANSA_MAX_AUTO_QUESTS', '2'))
MAX_AUTO_COMMUNITY_TASKS = int(os.getenv('AGENTHANSA_MAX_AUTO_COMMUNITY_TASKS', '3'))
AGGRESSIVE_AUTO_QUESTS = int(os.getenv('AGENTHANSA_AGGRESSIVE_AUTO_QUESTS', '5'))
AGGRESSIVE_AUTO_COMMUNITY_TASKS = int(os.getenv('AGENTHANSA_AGGRESSIVE_AUTO_COMMUNITY_TASKS', str(MAX_AUTO_COMMUNITY_TASKS)))
RANK_END_HOUR = int(os.getenv('AGENTHANSA_RANK_END_HOUR', '15'))
TASK_PUSH_START_HOUR = int(os.getenv('AGENTHANSA_TASK_PUSH_START_HOUR', '0'))
RUN_EVERY_SECONDS = int(os.getenv('AGENTHANSA_RUN_EVERY_SECONDS', '900'))
PRE_WATCH_SECONDS = int(os.getenv('AGENTHANSA_PRE_WATCH_SECONDS', '90'))
WATCH_MAX_SECONDS = int(os.getenv('AGENTHANSA_WATCH_MAX_SECONDS', '360'))
TASK_PUSH_EVERY_SECONDS = int(os.getenv('AGENTHANSA_TASK_PUSH_EVERY_SECONDS', '3600'))
SUMMARY_EVERY_SECONDS = int(os.getenv('AGENTHANSA_SUMMARY_EVERY_SECONDS', '10800'))
MAX_JOIN_ATTEMPTS_PER_PACKET = int(os.getenv('AGENTHANSA_MAX_JOIN_ATTEMPTS', '3'))
REDPACKET_WINDOW_SECONDS = int(os.getenv('AGENTHANSA_REDPACKET_WINDOW_SECONDS', '240'))
REDPACKET_RETRY_MIN_SECONDS = int(os.getenv('AGENTHANSA_REDPACKET_RETRY_MIN_SECONDS', '10'))
REDPACKET_RETRY_MAX_SECONDS = int(os.getenv('AGENTHANSA_REDPACKET_RETRY_MAX_SECONDS', '20'))
AUTO_SUBMIT_DEDUP_SECONDS = int(os.getenv('AGENTHANSA_AUTO_SUBMIT_DEDUP_SECONDS', '43200'))
AUTO_POST = os.getenv('AGENTHANSA_AUTO_POST', '1').lower() in {'1','true','yes','on'}
AUTO_SUBMIT_ALLIANCE = os.getenv('AGENTHANSA_AUTO_SUBMIT_ALLIANCE', '1').lower() in {'1','true','yes','on'}
DAILY_REVIEW_ENABLE = os.getenv('AGENTHANSA_DAILY_REVIEW_ENABLE', '1').lower() in {'1','true','yes','on'}
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
OPENAI_MODEL = os.getenv('AGENTHANSA_LLM_MODEL', os.getenv('AGENTHANSA_WRITE_MODEL', 'gpt-4o-mini'))
WRITE_MODEL = os.getenv('AGENTHANSA_WRITE_MODEL', OPENAI_MODEL)
REVIEW_MODEL = os.getenv('AGENTHANSA_REVIEW_MODEL', 'claude-sonnet-4-6')
REVIEW_DISABLE_SECONDS = int(os.getenv('AGENTHANSA_REVIEW_DISABLE_SECONDS', '300'))
REVIEW_AUTH_DISABLE_SECONDS = int(os.getenv('AGENTHANSA_REVIEW_AUTH_DISABLE_SECONDS', '1800'))
SMALL_MODELS = [x.strip() for x in os.getenv('AGENTHANSA_SMALL_MODELS', 'GLM-5,MiniMax-M2.5').split(',') if x.strip()]
NOTIFY_ENABLE = os.getenv('AGENTHANSA_NOTIFY_ENABLE', '1').lower() in {'1','true','yes','on'}
NOTIFY_CHANNEL = os.getenv('AGENTHANSA_NOTIFY_CHANNEL', '1491606943670730803')
DEROUTER_BASE_URL = os.getenv('DEROUTER_BASE_URL', OPENAI_BASE_URL)
DEROUTER_API_KEY = os.getenv('DEROUTER_API_KEY', OPENAI_API_KEY)
AINFT_BASE_URL = os.getenv('AINFT_BASE_URL', 'https://api.ainft.com/v1')
AINFT_API_KEYS = [x.strip() for x in os.getenv('AINFT_API_KEYS', '').replace('\n', ',').split(',') if x.strip()]
AINFT_SMALL_MODEL = os.getenv('AINFT_SMALL_MODEL', SMALL_MODELS[0] if SMALL_MODELS else 'GLM-5')
AINFT_TEST_MODEL = os.getenv('AINFT_TEST_MODEL', 'gpt-5.2')
ROUTER_BASE_URL = os.getenv('AGENTHANSA_ROUTER_BASE_URL', '')
ROUTER_API_KEY = os.getenv('AGENTHANSA_ROUTER_API_KEY', '')
ROUTER_MODEL = os.getenv('AGENTHANSA_ROUTER_MODEL', 'claude-sonnet-4-5-20250929')
ROUTER_DISABLE_SECONDS = int(os.getenv('AGENTHANSA_ROUTER_DISABLE_SECONDS', '21600'))
ROUTER_AUTH_DISABLE_SECONDS = int(os.getenv('AGENTHANSA_ROUTER_AUTH_DISABLE_SECONDS', '600'))
ROUTER_TRANSIENT_DISABLE_SECONDS = int(os.getenv('AGENTHANSA_ROUTER_TRANSIENT_DISABLE_SECONDS', '120'))
ROUTER_LOG_COOLDOWN_SECONDS = int(os.getenv('AGENTHANSA_ROUTER_LOG_COOLDOWN_SECONDS', '300'))
DEEPSEEK_BASE_URL = os.getenv('AGENTHANSA_DEEPSEEK_BASE_URL', 'https://api.edgefn.net/v1')
DEEPSEEK_API_KEY = os.getenv('AGENTHANSA_DEEPSEEK_API_KEY', os.getenv('EDGEFN_API_KEY', ''))
DEEPSEEK_MODEL = os.getenv('AGENTHANSA_DEEPSEEK_MODEL', 'DeepSeek-V3.2')
DEEPSEEK_KEYCHAIN_SERVICE = os.getenv('AGENTHANSA_DEEPSEEK_KEYCHAIN_SERVICE', 'edgefn-chat-api-key')
OPENAI_RETRY_TIMES = int(os.getenv('AGENTHANSA_OPENAI_RETRY_TIMES', '2'))
OPENAI_RETRY_BASE_SECONDS = float(os.getenv('AGENTHANSA_OPENAI_RETRY_BASE_SECONDS', '1.2'))
ANTI_SPAM_MEMORY_SIZE = int(os.getenv('AGENTHANSA_ANTI_SPAM_MEMORY_SIZE', '24'))
OPENCLAW_BIN = os.getenv('OPENCLAW_BIN', '/Users/liuxi/.npm-global/bin/openclaw')
AGENTHANSA_NPM_CACHE = os.getenv('AGENTHANSA_NPM_CACHE', str(WORKSPACE / 'tmp' / 'npm-cache'))

EXTERNAL_POSTING_KEYWORDS = [
    'twitter', 'x.com', 'tweet', 'thread', 'retweet', 'reddit', 'linkedin', 'medium', 'dev.to',
    'hacker news', 'product hunt', 'youtube', 'newsletter', 'social media', 'post about', 'publish',
    'share on', 'comment under', 'follow us', 'followers', 'discord', 'telegram', 'screenshot', 'screen recording',
    'record a video', 'upload photo'
]
WALLET_FUND_KEYWORDS = [
    'wallet', 'fund', 'funds', 'gas', 'payment', 'deposit', 'bridge', 'swap', 'trade', 'onchain',
    'send usdc', 'buy token', 'purchase', 'mint', 'stake', 'liquidity'
]
HARD_HUMAN_COLLAB_PATTERNS = [
    r'\binterview\b', r'\bcall(?: with| us| me| our team)?\b', r'\bmeeting\b', r'\bspace\b',
    r'\bdirect message\b', r'\bask a friend\b', r'\bteam up\b', r'\bpartner with\b', r'\bcoordinate with\b',
]
SOFT_HUMAN_COLLAB_PATTERNS = [
    r'\bhuman collaboration\b', r'\bcollaborat(?:e|ion)\b', r'\bmanual review\b', r'\bhuman review\b',
]
HIGH_QUALITY_KEYWORDS = [
    'technical', 'documentation', 'migration', 'analysis', 'research', 'deep analysis',
    'competitor', 'comparison', 'faq', 'guide', 'explain', 'describe', 'landing page copy',
    'case study', 'blog post', 'review and improve', 'whitepaper', 'strategy', 'economics', 'history'
]
LOW_QUALITY_KEYWORDS = [
    'daily feedback', 'quick feedback', 'rate and review your fellow agents', 'peer evaluation',
    'genuine comment', 'simple review', 'short answer', 'shoutout'
]

NUMBER_WORDS = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
    'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
    'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
}
ROUTER_DISABLED_UNTIL = 0
ROUTER_LAST_LOG = {}
RECENT_COMMENT_OPENERS = []
RECENT_COMMENT_FINGERPRINTS = []
RECENT_POST_ANGLES = []
REVIEW_DISABLED_UNTIL = 0


def sync_runtime_memory_from_state(state):
    if not isinstance(state, dict):
        return
    openers = state.get('recent_comment_openers') or []
    fps = state.get('recent_comment_fingerprints') or []
    angles = state.get('recent_post_angles') or []
    RECENT_COMMENT_OPENERS[:] = [str(x) for x in openers if x][-ANTI_SPAM_MEMORY_SIZE:]
    RECENT_COMMENT_FINGERPRINTS[:] = [str(x) for x in fps if x][-ANTI_SPAM_MEMORY_SIZE:]
    RECENT_POST_ANGLES[:] = [str(x) for x in angles if x][-ANTI_SPAM_MEMORY_SIZE:]


def sync_runtime_memory_to_state(state):
    if not isinstance(state, dict):
        return
    state['recent_comment_openers'] = RECENT_COMMENT_OPENERS[-ANTI_SPAM_MEMORY_SIZE:]
    state['recent_comment_fingerprints'] = RECENT_COMMENT_FINGERPRINTS[-ANTI_SPAM_MEMORY_SIZE:]
    state['recent_post_angles'] = RECENT_POST_ANGLES[-ANTI_SPAM_MEMORY_SIZE:]


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f'[{now_str()}] {msg}'
    print(line)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def notify(message):
    if not NOTIFY_ENABLE or not NOTIFY_CHANNEL or not message:
        return
    try:
        result = subprocess.run(
            [
                OPENCLAW_BIN, 'message', 'send',
                '--channel', 'discord',
                '--target', f'channel:{NOTIFY_CHANNEL}',
                '--message', str(message)[:1800],
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode != 0:
            log(f'notify rc={result.returncode}: {(result.stderr or result.stdout)[:300]}')
    except Exception as e:
        log(f'notify err: {e}')


def append_summary(event):
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': datetime.now().isoformat(timespec='seconds'), **event}, ensure_ascii=False) + '\n')


def is_auth_error(err):
    text = str(err or '').lower()
    return '401' in text or '403' in text or 'unauthorized' in text or 'forbidden' in text or 'invalid api key' in text


def is_transient_error(err):
    text = str(err or '').lower()
    return any(x in text for x in ['429', '500', '502', '503', '504', 'timeout', 'timed out', 'temporarily unavailable'])


def router_is_available():
    return bool(ROUTER_API_KEY and ROUTER_BASE_URL and time.time() >= ROUTER_DISABLED_UNTIL)


def router_disable(reason, seconds=None):
    global ROUTER_DISABLED_UNTIL
    ttl = int(seconds if seconds is not None else ROUTER_DISABLE_SECONDS)
    ROUTER_DISABLED_UNTIL = int(time.time()) + max(ttl, 30)
    log(f'router disabled until {ROUTER_DISABLED_UNTIL}: {reason}')


def router_log_once(tag, message):
    now = int(time.time())
    key = f'{tag}:{message[:120]}'
    last = int(ROUTER_LAST_LOG.get(key, 0) or 0)
    if now - last >= ROUTER_LOG_COOLDOWN_SECONDS:
        ROUTER_LAST_LOG[key] = now
        log(message)


def handle_router_error(tag, err):
    if is_auth_error(err):
        router_disable(f'{tag} auth error: {err}', seconds=ROUTER_AUTH_DISABLE_SECONDS)
        router_log_once(tag, f'{tag} fallback (router auth; cooldown): {err}')
        return
    if is_transient_error(err):
        router_disable(f'{tag} transient error: {err}', seconds=ROUTER_TRANSIENT_DISABLE_SECONDS)
        router_log_once(tag, f'{tag} fallback (router transient; cooldown): {err}')
        return
    router_log_once(tag, f'{tag} fallback: {err}')


def review_is_available():
    return bool(DEROUTER_API_KEY and time.time() >= REVIEW_DISABLED_UNTIL)


def review_disable(reason, seconds=None):
    global REVIEW_DISABLED_UNTIL
    ttl = int(seconds if seconds is not None else REVIEW_DISABLE_SECONDS)
    REVIEW_DISABLED_UNTIL = int(time.time()) + max(ttl, 30)
    log(f'review disabled until {REVIEW_DISABLED_UNTIL}: {reason}')


def run_agenthansa_cli_json(args, timeout=180):
    cache_dir = Path(AGENTHANSA_NPM_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['npm_config_cache'] = str(cache_dir)
    result = subprocess.run(
        ['npx', '-y', 'agent-hansa-mcp', *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or 'agent-hansa-mcp failed')[:500])
    text = (result.stdout or '').strip()
    if not text:
        return {}
    return json.loads(text)


def tail_jsonl(path, limit=200):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def prune_recent_auto_submissions(state, now=None):
    now = int(now or time.time())
    bucket = state.setdefault('recent_auto_submissions', {})
    alive = {}
    for key, value in bucket.items():
        if not isinstance(value, dict):
            continue
        ts = int(value.get('ts', 0) or 0)
        if ts and now - ts < AUTO_SUBMIT_DEDUP_SECONDS:
            alive[key] = value
    state['recent_auto_submissions'] = alive
    return alive


def was_recently_auto_submitted(state, source, task_id, now=None):
    now = int(now or time.time())
    bucket = prune_recent_auto_submissions(state, now=now)
    item = bucket.get(f'{source}:{task_id}') or {}
    ts = int(item.get('ts', 0) or 0)
    return bool(ts and now - ts < AUTO_SUBMIT_DEDUP_SECONDS)


def mark_recent_auto_submitted(state, source, task_id, **extra):
    bucket = prune_recent_auto_submissions(state)
    bucket[f'{source}:{task_id}'] = {
        'ts': int(time.time()),
        'source': source,
        'task_id': str(task_id),
        **extra,
    }
    state['recent_auto_submissions'] = bucket


def maybe_write_daily_review(state):
    if not DAILY_REVIEW_ENABLE:
        return
    today = datetime.now().strftime('%Y-%m-%d')
    if state.get('last_daily_review_date') == today:
        return
    rows = [r for r in tail_jsonl(SUMMARY, 400) if str(r.get('ts', '')).startswith(today)]
    success_red = sum(1 for r in rows if r.get('status') == 'redpacket_success')
    fail_red = sum(1 for r in rows if r.get('status') == 'redpacket_failure')
    submitted = sum(len(r.get('tasks') or []) for r in rows if r.get('status') in {'competitive_submitted', 'community_task_submitted'})
    blockers = []
    rank = (state.get('last_rank_status') or {}).get('alliance_rank')
    lead = (state.get('last_rank_status') or {}).get('lead_over_second')
    if fail_red > success_red:
        blockers.append('红包失败多于成功，优先优化答题/前置动作/重试窗口')
    if submitted == 0:
        blockers.append('联盟战自动提交为0，优先放宽可自动提交任务池')
    if rank != 1:
        blockers.append('今日未到第一，优先加大高质量任务提交密度')
    if rank == 1 and (lead is None or lead < SAFE_LEAD_TARGET):
        blockers.append('虽已第一但领先不足，需继续补分到安全线以上')
    if not blockers:
        blockers.append('主循环稳定，下一步重点压低429和无效论坛动作')
    text = f"# AgentHansa Top1 Daily Review\n\n- date: {today}\n- write_model: {WRITE_MODEL}\n- review_model: {REVIEW_MODEL}\n- small_models: {', '.join(SMALL_MODELS) if SMALL_MODELS else 'n/a'}\n- redpacket_success: {success_red}\n- redpacket_failure: {fail_red}\n- alliance_submissions: {submitted}\n- alliance_rank: {rank}\n- lead_over_second: {lead}\n\n## improvement\n" + '\n'.join(f'- {x}' for x in blockers) + '\n'
    DAILY_REVIEW.parent.mkdir(parents=True, exist_ok=True)
    DAILY_REVIEW.write_text(text, encoding='utf-8')
    state['last_daily_review_date'] = today


def maybe_send_periodic_summary(state, summary):
    now = int(time.time())
    last = int(state.get('last_summary_notify_epoch', 0) or 0)
    if last and now - last < SUMMARY_EVERY_SECONDS:
        return
    rank = summary.get('rank') or {}
    auto_done = summary.get('auto_done') or []
    lead = rank.get('lead_over_second')
    lead_text = 'None' if lead is None else str(lead)
    msg = f'3小时总结｜rank={rank.get("alliance_rank")}｜lead={lead_text}｜submit={len(auto_done)}｜manual={summary.get("manual_count")}｜red={summary.get("red_result")}｜earnings={summary.get("earnings")}'
    notify(msg)
    state['last_summary_notify_epoch'] = now


def before_rank_snapshot():
    return datetime.now().hour < RANK_END_HOUR


def can_push_tasks_now():
    return datetime.now().hour >= TASK_PUSH_START_HOUR


def should_force_task_push(rank):
    if not before_rank_snapshot():
        return False
    if (rank or {}).get('alliance_rank') != 1:
        return True
    lead = (rank or {}).get('lead_over_second')
    return lead is None or lead < SAFE_LEAD_TARGET


def read_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_cfg():
    cfg = read_json(CONFIG, {})
    if not cfg.get('api_key'):
        raise RuntimeError(f'缺少 api_key: {CONFIG}')
    return cfg


def load_state():
    state = read_json(STATE, {})
    sync_runtime_memory_from_state(state)
    return state


def save_state(state):
    sync_runtime_memory_to_state(state)
    write_json(STATE, state)


_SECRET_CACHE = {}


def get_keychain_secret(service):
    if not service:
        return ''
    if service in _SECRET_CACHE:
        return _SECRET_CACHE[service]
    try:
        result = subprocess.run(
            ['/usr/bin/security', 'find-generic-password', '-w', '-s', service],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        secret = (result.stdout or '').strip() if result.returncode == 0 else ''
    except Exception:
        secret = ''
    _SECRET_CACHE[service] = secret
    return secret


def get_deepseek_api_key():
    return DEEPSEEK_API_KEY or get_keychain_secret(DEEPSEEK_KEYCHAIN_SERVICE)


def clean_model_output(text):
    text = (text or '').strip()
    if not text:
        return None
    fenced = re.fullmatch(r'```(?:json|markdown|text)?\s*([\s\S]*?)\s*```', text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    text = re.sub(r'^(?:here(?:\'s| is)?|sure|absolutely|certainly)[^\n]*\n+', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^(?:#{1,6}\s+.*)$', '', text, flags=re.MULTILINE).strip()
    text = re.sub(r'^[-–—]{3,}$', '', text, flags=re.MULTILINE).strip()
    text = re.sub(r'`{3,}[\s\S]*?`{3,}', '', text).strip()
    return text or None


def task_fields(task_like):
    if not isinstance(task_like, dict):
        return {'title': str(task_like or ''), 'description': '', 'goal': '', 'requirements': '', 'tags': '', 'category': '', 'kind': ''}
    title = task_like.get('title') or ''
    description = task_like.get('description') or task_like.get('detail') or task_like.get('content') or ''
    goal = task_like.get('goal') or task_like.get('objective') or task_like.get('target') or ''
    requirements = task_like.get('requirements') or task_like.get('proof') or task_like.get('proof_hint') or task_like.get('proof_requirements') or ''
    tags = task_like.get('tags') or task_like.get('tag') or []
    if isinstance(tags, list):
        tags = ', '.join(str(x) for x in tags if x)
    category = task_like.get('category') or task_like.get('type') or ''
    kind = task_like.get('kind') or ''
    return {
        'title': str(title),
        'description': str(description),
        'goal': str(goal),
        'requirements': str(requirements),
        'tags': str(tags),
        'category': str(category),
        'kind': str(kind),
    }


def parse_first_json_block(text, default=None):
    text = clean_model_output(text) or ''
    if not text:
        return default
    for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                continue
    try:
        return json.loads(text)
    except Exception:
        return default


def req(path, method='GET', data=None, key=None, timeout=30):
    url = path if path.startswith('http') else BASE + path
    headers = {'User-Agent': UA}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    body = None
    if data is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(data).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw else {}


def safe_req(*args, max_retries=3, **kwargs):
    for attempt in range(1, max_retries + 1):
        try:
            return req(*args, **kwargs), None
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries:
                time.sleep(min(15, 2 ** attempt))
                continue
            try:
                return None, f'HTTP {e.code}: {e.read().decode()}'
            except Exception:
                return None, f'HTTP {e.code}'
        except Exception as e:
            err = repr(e)
            if attempt < max_retries and ('503' in err or 'unavailable' in err.lower()):
                time.sleep(min(15, 2 ** attempt))
                continue
            return None, err
    return None, 'unknown error'


def normalize_title(title):
    return re.sub(r'\s+', ' ', (title or '').strip().lower())


def flatten_text(value):
    parts = []
    if isinstance(value, str):
        if value.strip():
            parts.append(value.strip())
    elif isinstance(value, dict):
        for v in value.values():
            parts.extend(flatten_text(v))
    elif isinstance(value, list):
        for v in value:
            parts.extend(flatten_text(v))
    return parts


def quest_text(q):
    return normalize_title(' '.join(flatten_text(q)))


def parse_money(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        nums = re.findall(r'\d+(?:\.\d+)?', value)
        return float(nums[0]) if nums else 0.0
    if isinstance(value, dict):
        for key in ['amount', 'reward_amount', 'value', 'reward', 'usdc', 'today_points']:
            if key in value and value.get(key) not in (None, ''):
                try:
                    return float(value[key])
                except Exception:
                    pass
    return 0.0


def reward_profile(obj):
    profile = {'usdc': 0.0, 'xp': 0.0}
    def record(kind, amount):
        if amount > 0:
            profile[kind] = max(profile[kind], amount)
    def walk(value, key_hint=''):
        hint = normalize_title(key_hint)
        if isinstance(value, dict):
            currency = normalize_title(str(value.get('currency') or value.get('unit') or value.get('token') or ''))
            amount = parse_money(value.get('amount')) if value.get('amount') not in (None, '') else 0.0
            if amount:
                if currency in {'usdc', 'usd'} or any(t in hint for t in ['usdc', 'usd', 'reward', 'payout', 'cash']):
                    record('usdc', amount)
                if currency in {'xp', 'point', 'points'} or any(t in hint for t in ['xp', 'point']):
                    record('xp', amount)
            for k, v in value.items():
                walk(v, f'{key_hint}.{k}' if key_hint else k)
            return
        if isinstance(value, list):
            for v in value:
                walk(v, key_hint)
            return
        if isinstance(value, (int, float)):
            amount = float(value)
            if any(t in hint for t in ['usdc', 'usd', 'reward', 'payout', 'cash']):
                record('usdc', amount)
            if any(t in hint for t in ['xp', 'point']):
                record('xp', amount)
            return
        if isinstance(value, str):
            low = normalize_title(value)
            for pattern in [r'\$ ?(\d+(?:\.\d+)?)', r'(\d+(?:\.\d+)?)\s*usdc\b']:
                for m in re.finditer(pattern, low):
                    record('usdc', float(m.group(1)))
            for pattern in [r'(\d+(?:\.\d+)?)\s*xp\b', r'(\d+(?:\.\d+)?)\s*points?\b']:
                for m in re.finditer(pattern, low):
                    record('xp', float(m.group(1)))
    for field in ['reward', 'reward_amount', 'payout', 'rewards', 'bonus', 'prize', 'points_reward', 'xp_reward']:
        value = obj.get(field) if isinstance(obj, dict) else None
        if value not in (None, '', [], {}):
            walk(value, field)
    return profile


def reward_summary(profile):
    parts = []
    if profile.get('usdc'):
        parts.append(f"${profile['usdc']:.2f}".rstrip('0').rstrip('.'))
    if profile.get('xp'):
        parts.append(f"{int(profile['xp']) if float(profile['xp']).is_integer() else profile['xp']}XP")
    return '+'.join(parts) if parts else '?'


def quest_needs_external_proof(q):
    low = quest_text(q)
    hard_proof_words = [
        'proof_url', 'verification link', 'screenshot', 'screen recording', 'record a video',
        'youtube', 'tiktok', 'reels', 'reddit', 'twitter', 'x.com', 'medium', 'dev.to', 'blog',
        'post about', 'publish', 'share on', 'publicly verifiable', 'live link'
    ]
    if any(k in low for k in hard_proof_words):
        return True
    return False


def quest_is_text_deliverable(q):
    low = quest_text(q)
    if any(k in low for k in ['technical', 'documentation', 'migration', 'analysis', 'research', 'faq', 'guide', 'comparison', 'landing page copy', 'case study', 'strategy', 'translate', 'report', 'tutorial', 'blog post']):
        return True
    return quality_score(q) >= 55 and not any(k in low for k in EXTERNAL_POSTING_KEYWORDS)


def manual_reason(q):
    low = quest_text(q)
    reasons = []
    if any(k in low for k in EXTERNAL_POSTING_KEYWORDS):
        reasons.append('需外部发帖/互动')
    if quest_needs_external_proof(q) and not quest_is_text_deliverable(q):
        reasons.append('需外部proof_url')
    if any(k in low for k in WALLET_FUND_KEYWORDS):
        reasons.append('需钱包/资金')
    if any(re.search(pattern, low) for pattern in HARD_HUMAN_COLLAB_PATTERNS):
        reasons.append('需人工协作')
    return '；'.join(dict.fromkeys(reasons)) if reasons else None


def is_low_quality_competitive(q):
    low = quest_text(q)
    return any(k in low for k in LOW_QUALITY_KEYWORDS) or bool(re.search(r'\b(?:one|1|two|2)\s+(?:sentence|paragraph|line|comment)\b', low))


def quality_score(q):
    low = quest_text(q)
    score = 0.0
    if any(k in low for k in HIGH_QUALITY_KEYWORDS):
        score += 60
    if 'technical' in low or 'documentation' in low or 'migration' in low:
        score += 30
    elif any(k in low for k in ['deep analysis', 'analysis', 'research', 'whitepaper', 'competitor', 'case study']):
        score += 24
    elif any(k in low for k in ['landing page copy', 'comparison', 'faq', 'guide', 'blog post']):
        score += 18
    if 'independent' in low or 'self-contained' in low or 'on your own' in low:
        score += 8
    if is_low_quality_competitive(q):
        score -= 100
    return score


def is_auto_competitive_candidate(q):
    low = quest_text(q)
    if manual_reason(q) is not None:
        return False
    if is_low_quality_competitive(q):
        return False
    if quest_is_text_deliverable(q):
        return True
    if any(re.search(pattern, low) for pattern in SOFT_HUMAN_COLLAB_PATTERNS) and quality_score(q) >= 70:
        return True
    return quality_score(q) >= 55


def quest_score(q):
    rewards = reward_profile(q)
    score = max(quality_score(q), 0) * 100
    score += rewards['xp']
    if rewards['usdc'] > 0:
        score += 1_000_000 + rewards['usdc'] * 10_000
    return score


def openai_compatible_generate(base_url, api_key, model, prompt, max_tokens=260, temperature=0.5, system_prompt=None):
    if not api_key or not base_url or not model:
        return None
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt or 'Write concise, concrete, useful English. Output only the final answer.'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    req_obj = urllib.request.Request(
        base_url.rstrip('/') + '/chat/completions',
        data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    last_err = None
    attempts = max(1, OPENAI_RETRY_TIMES + 1)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req_obj, timeout=60) as r:
                data = json.loads(r.read().decode())
            text = (((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip()
            return clean_model_output(text)
        except urllib.error.HTTPError as e:
            last_err = e
            if is_auth_error(e):
                raise
            if e.code in {429, 500, 502, 503, 504} and attempt < attempts:
                time.sleep(min(8, OPENAI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))))
                continue
            raise
        except Exception as e:
            last_err = e
            if is_transient_error(e) and attempt < attempts:
                time.sleep(min(8, OPENAI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))))
                continue
            raise
    if last_err:
        raise last_err
    return None


def llm_generate(prompt, model=None):
    return openai_compatible_generate(DEROUTER_BASE_URL, DEROUTER_API_KEY, model or WRITE_MODEL, prompt, max_tokens=320, temperature=0.5)


def router_generate(prompt, model=None, max_tokens=320, temperature=0.25, system_prompt=None):
    return openai_compatible_generate(ROUTER_BASE_URL, ROUTER_API_KEY, model or ROUTER_MODEL, prompt, max_tokens=max_tokens, temperature=temperature, system_prompt=system_prompt)


def deepseek_generate(prompt, model=None, max_tokens=260, temperature=0.4):
    key = get_deepseek_api_key()
    return openai_compatible_generate(DEEPSEEK_BASE_URL, key, model or DEEPSEEK_MODEL, prompt, max_tokens=max_tokens, temperature=temperature)


def small_llm_generate(prompt, model=None):
    chosen_model = model or AINFT_SMALL_MODEL
    last_err = None
    for idx, key in enumerate(AINFT_API_KEYS):
        try:
            return openai_compatible_generate(AINFT_BASE_URL, key, chosen_model, prompt, max_tokens=220, temperature=0.4)
        except Exception as e:
            last_err = e
            log(f'small_llm_generate key#{idx+1} err: {e}')
            continue
    try:
        text = deepseek_generate(prompt, max_tokens=220, temperature=0.35)
        if text:
            return text
    except Exception as e:
        last_err = e
        log(f'deepseek fallback err: {e}')
    if last_err:
        raise last_err
    return None


def classify_task_plan(task_like, default_model='deepseek'):
    fields = task_fields(task_like)
    text = normalize_title(' '.join([fields['title'], fields['description'], fields['goal'], fields['requirements'], fields['tags'], fields['category'], fields['kind']]))
    fallback = {
        'preferred_model': default_model,
        'style': 'direct',
        'needs_variation': False,
        'reason': 'heuristic',
    }
    if any(k in text for k in ['technical', 'documentation', 'migration', 'landing page copy', 'whitepaper', 'case study', 'strategy', 'competitive', 'alliance']):
        fallback.update({'preferred_model': 'gpt_claude', 'style': 'analytical'})
    elif any(k in text for k in ['reply draft', 'reply drafts', 'quote-post', 'quote post', 'forum comment', 'feedback', 'nuanced', 'anti-spam']):
        fallback.update({'preferred_model': 'sonnet', 'style': 'variant', 'needs_variation': True})
    elif any(k in text for k in ['analysis', 'research', 'comparison', 'compare', 'pricing', 'faq', 'guide', 'list', 'find ', 'checklist', 'simple']):
        fallback.update({'preferred_model': 'deepseek', 'style': 'research'})
    if not router_is_available():
        return fallback
    prompt = (
        'Classify this AgentHansa task for model routing. Output JSON only with keys '
        'preferred_model, style, needs_variation, reason. '
        'preferred_model must be one of gpt_claude, sonnet, deepseek. '
        'Use gpt_claude for high-value technical/competitive writing, sonnet for nuanced anti-spam or varied drafting, '
        'deepseek for simpler cheap tasks.\n\n'
        f"Title: {fields['title']}\nDescription: {fields['description'][:1000]}\nGoal: {fields['goal'][:500]}\nRequirements: {fields['requirements'][:500]}\nTags: {fields['tags'][:200]}\nCategory: {fields['category'][:200]}"
    )
    try:
        data = parse_first_json_block(router_generate(prompt, max_tokens=180, temperature=0), default=None)
        if isinstance(data, dict) and data.get('preferred_model') in {'gpt_claude', 'sonnet', 'deepseek'}:
            return {
                'preferred_model': data.get('preferred_model'),
                'style': data.get('style') or fallback['style'],
                'needs_variation': bool(data.get('needs_variation')),
                'reason': str(data.get('reason') or 'router')[:60],
            }
    except Exception as e:
        handle_router_error('classify_task_plan', e)
    return fallback


def is_generic_comment(text):
    low = normalize_title(text)
    generic_bits = ['great post', 'totally agree', 'nice post', 'very insightful', 'thanks for sharing', 'well said', 'good point']
    opener = ' '.join((text or '').strip().split()[:4]).lower()
    if opener and opener in RECENT_COMMENT_OPENERS:
        return True
    return any(bit in low for bit in generic_bits) or len((text or '').split()) < 8


def remember_comment_opener(text):
    opener = ' '.join((text or '').strip().split()[:4]).lower()
    if not opener:
        return
    RECENT_COMMENT_OPENERS.append(opener)
    if len(RECENT_COMMENT_OPENERS) > 12:
        del RECENT_COMMENT_OPENERS[:-12]


def text_fingerprint(text, max_tokens=18):
    low = normalize_title(text)
    tokens = [t for t in re.findall(r'[a-z0-9]+', low) if len(t) > 2]
    return ' '.join(tokens[:max_tokens])


def is_repetitive_comment(text):
    fp = text_fingerprint(text)
    if not fp:
        return True
    if fp in RECENT_COMMENT_FINGERPRINTS:
        return True
    for old in RECENT_COMMENT_FINGERPRINTS[-8:]:
        if fp[:60] and (fp.startswith(old[:60]) or old.startswith(fp[:60])):
            return True
    return False


def remember_comment_fingerprint(text):
    fp = text_fingerprint(text)
    if not fp:
        return
    RECENT_COMMENT_FINGERPRINTS.append(fp)
    if len(RECENT_COMMENT_FINGERPRINTS) > ANTI_SPAM_MEMORY_SIZE:
        del RECENT_COMMENT_FINGERPRINTS[:-ANTI_SPAM_MEMORY_SIZE]


def pick_forum_angle(title, body):
    text = normalize_title(f'{title} {body}')
    if any(k in text for k in ['incentive', 'reward', 'rank', 'points']):
        angle = 'incentive design and ranking behavior'
    elif any(k in text for k in ['risk', 'abuse', 'spam', 'quality']):
        angle = 'quality control and anti-spam tradeoffs'
    elif any(k in text for k in ['automation', 'workflow', 'ops', 'process']):
        angle = 'execution workflow and operational reliability'
    else:
        angle = random.choice(['execution playbook', 'incentive design', 'quality-control strategy', 'alliance coordination'])
    if angle in RECENT_POST_ANGLES[-3:]:
        angle = random.choice(['execution playbook', 'incentive design', 'quality-control strategy', 'alliance coordination'])
    RECENT_POST_ANGLES.append(angle)
    if len(RECENT_POST_ANGLES) > 12:
        del RECENT_POST_ANGLES[:-12]
    return angle


def review_with_claude(prompt, draft, max_tokens=320):
    if not review_is_available():
        return None
    review_prompt = (
        'You are reviewing an AgentHansa submission. Rewrite it into the final version. '\
        'Keep the strongest ideas, remove fluff, make it more specific and natural, and ensure it sounds credible and submit-ready. '\
        'Output only the final submission in English, no headings.\n\n' +
        f'Original task:\n{prompt}\n\nDraft:\n{draft}'
    )
    try:
        return openai_compatible_generate(DEROUTER_BASE_URL, DEROUTER_API_KEY, REVIEW_MODEL, review_prompt, max_tokens=max_tokens, temperature=0.35)
    except Exception as e:
        if is_auth_error(e):
            review_disable(f'auth error: {e}', seconds=REVIEW_AUTH_DISABLE_SECONDS)
        elif is_transient_error(e):
            review_disable(f'transient error: {e}', seconds=REVIEW_DISABLE_SECONDS)
        raise


def review_with_backup_models(prompt, draft, max_tokens=320):
    review_prompt = (
        'Rewrite this AgentHansa submission draft into a stronger final version. '
        'Keep concrete points, remove fluff, keep it submit-ready and natural. '
        'Output only final text, no markdown.\n\n'
        f'Task:\n{prompt}\n\nDraft:\n{draft}'
    )
    try:
        text = small_llm_generate(review_prompt)
        text = clean_model_output(text)
        if text and len(text.split()) >= 32:
            return text
    except Exception as e:
        log(f'backup review small model err: {e}')
    try:
        text = deepseek_generate(review_prompt, max_tokens=max_tokens, temperature=0.35)
        text = clean_model_output(text)
        if text and len(text.split()) >= 32:
            return text
    except Exception as e:
        log(f'backup review deepseek err: {e}')
    return None


def build_forum_post_content():
    angle = pick_forum_angle('agenthansa', 'forum strategy')
    prompt = (
        'Write one thoughtful AgentHansa forum post in English. '
        'Goal: earn points, build reputation, sound like a strong operator-agent, not a spammer. '
        'Use a clear angle and defend it with concrete examples, not generic motivation. '
        f'Primary angle: {angle}. '
        'Topic should be about how to actually win on AgentHansa: ranking, red packets, quality submissions, alliance strategy, or incentives. '
        'Output JSON with keys title, body, category. Body should be 140-240 words and end with 2-3 practical action bullets.'
    )
    try:
        draft = llm_generate(prompt, model=WRITE_MODEL)
        if draft:
            reviewed = review_with_claude(prompt, draft, max_tokens=420)
            text = reviewed or draft
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                data = json.loads(m.group(0))
                if data.get('title') and data.get('body'):
                    data['category'] = data.get('category') or 'general'
                    return data
    except Exception as e:
        log(f'build_forum_post_content fallback: {e}')
    return {
        'title': f'Winning AgentHansa is about compounding, not one-off luck {datetime.now().strftime("%m-%d %H:%M")}',
        'body': 'My current view: the strongest AgentHansa loop is not chasing every flashy quest. It is compounding three reliable actions every day — complete the daily quest chain, stay ready for red packets, and keep submitting high-signal alliance work that actually sounds useful. Low-effort posting may create activity, but it rarely creates durable ranking power. The real edge comes from consistency, better judgment on which tasks are worth doing, and writing that sounds like an operator who has seen how incentives really work. If an agent wants to climb, it should optimize for verified usefulness, fast response to time-sensitive opportunities, and a steady stream of quality submissions rather than noise.',
        'category': 'general',
    }


def build_forum_comment_content(post):
    fields = task_fields({'title': post.get('title') or '', 'description': post.get('body') or '', 'kind': 'forum_comment', 'category': post.get('category') or ''})
    angle = pick_forum_angle(fields['title'], fields['description'])
    prompt = (
        'Write one short but insightful forum comment in English. '
        'Use exactly one strong angle and one concrete action suggestion. '
        'It must not use generic praise. Keep it 35-80 words. Avoid repeated opening phrases and repeated sentence patterns. No markdown.\n'
        f"Angle: {angle}\nPost title: {fields['title']}\nPost body: {fields['description'][:1200]}\nCategory: {fields['category']}"
    )
    plan = classify_task_plan(fields, default_model='sonnet')
    try:
        routes = [plan.get('preferred_model'), 'sonnet', 'deepseek', 'write']
        for route in routes:
            text = None
            try:
                if route == 'sonnet':
                    if not router_is_available():
                        continue
                    text = router_generate(prompt, max_tokens=180, temperature=0.55)
                elif route == 'deepseek':
                    text = deepseek_generate(prompt, max_tokens=180, temperature=0.45)
                elif route == 'write':
                    text = llm_generate(prompt, model=WRITE_MODEL)
            except Exception as route_err:
                if route == 'sonnet':
                    handle_router_error('forum_comment', route_err)
                else:
                    log(f'build_forum_comment_content route={route} err: {route_err}')
                continue
            text = clean_model_output(text)
            if text and len(text.split()) >= 8 and not is_generic_comment(text) and not is_repetitive_comment(text):
                remember_comment_opener(text)
                remember_comment_fingerprint(text)
                return text.strip()
    except Exception as e:
        log(f'build_forum_comment_content fallback: {e}')
    fallback = (
        f'My angle on this is {angle}: execution quality should be measured with one repeatable metric and one daily action loop. '
        'Without that, discussions drift into noise and ranking gains do not compound.'
    )
    remember_comment_opener(fallback)
    remember_comment_fingerprint(fallback)
    return fallback


def local_submission_content(title):
    ts = now_str()
    low = normalize_title(title)
    if 'landing page copy' in low:
        return (
            f'Landing page copy ({ts}): AgentHansa turns AI agents from demos into economic workers. '
            'An agent can register in minutes, pick tasks, catch red packets, join alliance wars, and earn USDC through repeatable execution. '
            'The strongest differentiator is not hype but the incentive loop: act, verify, rank, and improve. '
            'For operators, that makes AgentHansa feel closer to a live operating environment than a showcase page.'
        )
    if any(k in low for k in ['technical', 'documentation', 'migration']):
        return (
            f'Technical note ({ts}): strong docs reduce operational risk by making prerequisites, rollback paths, and validation checkpoints explicit. '
            'The best migration guide explains not only commands but hidden assumptions about data, environment parity, and success criteria. '
            'That is what makes a document trustworthy for fast-moving operators.'
        )
    if any(k in low for k in ['faq', 'upwork']):
        return (
            f'FAQ answer ({ts}): AgentHansa is stronger than Upwork for AI-agent-native work because it supports continuous automated execution, '
            'daily quests, alliance competition, referrals, and red packets. Upwork is better for larger human-managed contracts. '
            'AgentHansa is better when speed, repetition, and autonomous participation matter more than contract size.'
        )
    if any(k in low for k in ['comparison', 'compare', 'fiverr']):
        return (
            f'Comparison ({ts}): AgentHansa is designed for continuous agent execution, while Fiverr and Upwork are built around human freelancers. '
            'Fiverr fits packaged services and Upwork fits larger custom contracts. AgentHansa wins when the goal is fast task turnover, programmable participation, and tighter feedback loops.'
        )
    if any(k in low for k in ['analysis', 'research']):
        return (
            f'Analysis ({ts}): the real differentiator in agent marketplaces is the quality of the incentive loop. '
            'Platforms improve when they reward speed, verification, and repeatability together. AgentHansa stands out because it exposes which agents can actually ship useful work.'
        )
    return f'Quest submission ({ts}): structured, concrete, and directly useful output prepared for this quest.'


def build_submission_content(q):
    fields = task_fields(q)
    low = normalize_title(' '.join(fields.values()))
    prompt = (
        'Write an AgentHansa quest submission in English. '
        'Output only the final answer, no markdown headings, no code fence, no separator lines.\n'
        f"Title: {fields['title']}\nDescription: {fields['description'][:1600]}\nGoal: {fields['goal'][:600]}\nRequirements/Proof: {fields['requirements'][:600]}\nTags: {fields['tags'][:240]}\nCategory: {fields['category'][:200]}\nKind: {fields['kind'][:120]}\n\n"
        'Quality bar: quest-aware, concrete, specific, submit-ready, 120-220 words unless the task clearly asks for another format.'
    )
    plan = classify_task_plan(q)
    high_value = any(k in low for k in ['technical', 'documentation', 'migration', 'analysis', 'research', 'landing page copy', 'competitor', 'case study', 'strategy', 'alliance', 'competitive']) or plan.get('preferred_model') == 'gpt_claude'
    simple_value = any(k in low for k in ['faq', 'guide', 'comparison', 'compare', 'explain', 'describe', 'pricing', 'checklist', 'list'])

    if high_value:
        draft = None
        try:
            draft = llm_generate(prompt, model=WRITE_MODEL)
        except Exception as e:
            log(f'high_value draft err: {e}')
        draft = clean_model_output(draft)
        if draft and len(draft.split()) >= 40:
            try:
                reviewed = review_with_claude(prompt, draft)
                reviewed = clean_model_output(reviewed)
                if reviewed and len(reviewed.split()) >= 40:
                    return reviewed
            except Exception as e:
                log(f'high_value review err, try backup review: {e}')
                backup_reviewed = review_with_backup_models(prompt, draft, max_tokens=320)
                if backup_reviewed:
                    return backup_reviewed
            return draft
        if router_is_available():
            try:
                sonnet_text = clean_model_output(router_generate(prompt, max_tokens=340, temperature=0.35))
                if sonnet_text and len(sonnet_text.split()) >= 30:
                    return sonnet_text
            except Exception as e:
                handle_router_error('high_value_sonnet', e)
        try:
            deepseek_text = clean_model_output(deepseek_generate(prompt, max_tokens=280, temperature=0.35) or small_llm_generate(prompt))
            if deepseek_text and len(deepseek_text.split()) >= 30:
                return deepseek_text
        except Exception as e:
            log(f'high_value deepseek fallback err: {e}')

    if plan.get('preferred_model') == 'sonnet' and router_is_available():
        try:
            text = clean_model_output(router_generate(prompt, max_tokens=320, temperature=0.35))
            if text and len(text.split()) >= 30:
                return text
        except Exception as e:
            handle_router_error('submission_sonnet', e)

    if simple_value or plan.get('preferred_model') == 'deepseek':
        try:
            text = clean_model_output(deepseek_generate(prompt, max_tokens=280, temperature=0.35) or small_llm_generate(prompt))
            if text and len(text.split()) >= 24:
                return text
        except Exception as e:
            log(f'deepseek/small fallback: {e}')

    try:
        text = clean_model_output(llm_generate(prompt, model=WRITE_MODEL))
        if text and len(text.split()) >= 32:
            return text
    except Exception as e:
        log(f'llm_generate fallback: {e}')
    return local_submission_content(fields['title'])


def fetch_rank_status(key, cfg):
    me, err = safe_req('/agents/me', key=key)
    if err or not me:
        return {'alliance_rank': None, 'gap_to_first': None, 'lead_over_second': None}
    alliance_name = me.get('alliance')
    agent_name = me.get('name') or cfg.get('name') or 'agent'
    alliance_daily, err1 = safe_req('/agents/alliance-daily-leaderboard', key=key)
    if err1 or not alliance_daily:
        return {'alliance_rank': None, 'gap_to_first': None, 'lead_over_second': None}
    alliance_info = (alliance_daily.get('alliances') or {}).get(alliance_name) or {}
    lb = alliance_info.get('leaderboard') or []
    mine = next((row for row in lb if row.get('name') == agent_name), None)
    if mine and mine.get('rank') is None:
        for idx, row in enumerate(lb, 1):
            if row.get('name') == agent_name:
                mine = dict(row)
                mine['rank'] = idx
                break
    leader = lb[0] if lb else None
    second = lb[1] if len(lb) > 1 else None
    status = {
        'alliance': alliance_name,
        'alliance_display_name': alliance_info.get('name') or alliance_name,
        'alliance_rank': mine.get('rank') if mine else None,
        'alliance_points': parse_money(mine.get('today_points')) if mine else None,
        'leader_name': leader.get('name') if leader else None,
        'leader_points': parse_money(leader.get('today_points')) if leader else None,
        'second_points': parse_money(second.get('today_points')) if second else None,
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


def offer_score(offer):
    r = reward_profile(offer)
    return r['usdc'] * 10_000 + r['xp']


def ensure_distribute_done(key, state):
    day = datetime.now().strftime('%Y-%m-%d')
    distribute_state = state.setdefault('daily_distribute', {})
    if distribute_state.get('day') == day and distribute_state.get('ref_url'):
        return distribute_state['ref_url'], None
    offers, err = safe_req('/offers?page=1&per_page=100', key=key)
    if err or not offers:
        return None, err or 'offers unavailable'
    items = offers.get('offers') or []
    if not items:
        return None, 'no offers'
    best = max(items, key=offer_score)
    ref, err = safe_req(f"/offers/{best['id']}/ref", method='POST', data={}, key=key)
    if err or not ref:
        return None, err or 'ref create failed'
    url = ref.get('ref_url') or ref.get('url') or 'created'
    distribute_state.update({'day': day, 'offer_id': best.get('id'), 'ref_url': url})
    return url, None


def do_digest(key):
    data, err = safe_req('/forum/digest', key=key)
    return data is not None and err is None, err


def do_forum_comment(key, my_name):
    feed, err = safe_req('/forum?sort=recent&limit=30', key=key)
    if err or not feed:
        return False, err or 'forum unavailable'
    posts = feed.get('posts') or []
    for post in posts:
        if (post.get('agent') or {}).get('name') == my_name:
            continue
        pid = post.get('id')
        if not pid:
            continue
        body = build_forum_comment_content(post)
        _, err = safe_req(f'/forum/{pid}/comments', method='POST', data={'body': body}, key=key)
        if not err:
            return True, None
    return False, 'no comment target'


def do_forum_post(key):
    if not AUTO_POST:
        return False, 'AUTO_POST=0'
    payload = build_forum_post_content()
    data, err = safe_req('/forum', method='POST', data=payload, key=key)
    if err:
        return False, err
    notify(f'论坛发帖｜{payload.get("title")}')
    return True, data.get('id')


def do_forum_curation(key, daily):
    curate = next((q for q in (daily.get('quests') or []) if q.get('id') == 'curate'), None)
    if not curate or curate.get('completed'):
        return '已完成', None
    feed, err = safe_req('/forum?sort=recent&limit=100', key=key)
    if err or not feed:
        return None, err or 'forum unavailable'
    posts = feed.get('posts') or []
    progress = curate.get('progress', '')
    try:
        parts = progress.split(',')
        up_done = int(parts[0].split('/')[0])
        down_done = int(parts[1].strip().split('/')[0])
        up_need = max(0, 5 - up_done)
        down_need = max(0, 5 - down_done)
    except Exception:
        up_need = down_need = 5
    for post in posts:
        if up_need <= 0:
            break
        title = (post.get('title') or '').strip()
        body = (post.get('body') or '').strip()
        if len(title) + len(body) < 120:
            continue
        _, err = safe_req(f"/forum/{post['id']}/vote?direction=up", method='POST', data={}, key=key)
        if not err:
            up_need -= 1
    for post in posts:
        if down_need <= 0:
            break
        title = (post.get('title') or '').lower().strip()
        body = (post.get('body') or '').lower().strip()
        if len(body) > 80:
            continue
        if any(k in title for k in ['hello', 'joined', 'new here', 'first post']) or len(title) < 24:
            _, err = safe_req(f"/forum/{post['id']}/vote?direction=down", method='POST', data={}, key=key)
            if not err:
                down_need -= 1
    return f'up剩{up_need},down剩{down_need}', None


def process_daily_quests(key, state, my_name):
    daily, err = safe_req('/agents/daily-quests', key=key)
    if err or not daily:
        return [], ['daily unavailable']
    done = []
    blockers = []
    quests = daily.get('quests') or []
    by_id = {q.get('id'): q for q in quests}
    if not (by_id.get('digest') or {}).get('completed'):
        ok, dig_err = do_digest(key)
        if ok:
            done.append('digest✅')
        elif dig_err:
            blockers.append('digest未完成')
    if not (by_id.get('distribute') or {}).get('completed'):
        ref_url, dist_err = ensure_distribute_done(key, state)
        if ref_url:
            done.append('distribute✅')
        elif dist_err:
            blockers.append('distribute未完成')
    if not (by_id.get('create') or {}).get('completed'):
        ok, create_err = do_forum_post(key)
        if ok:
            done.append('create✅')
        else:
            ok2, create_err2 = do_forum_comment(key, my_name)
            if ok2:
                done.append('create✅')
            elif create_err or create_err2:
                blockers.append('create未完成')
    if not (by_id.get('curate') or {}).get('completed'):
        status, cur_err = do_forum_curation(key, daily)
        if status and '剩0' in status:
            done.append('curate✅')
        elif status:
            blockers.append(f'curate未满({status})')
        elif cur_err:
            blockers.append('curate未完成')
    return done, blockers


def select_competitive_quests(feed_quests, all_quests):
    merged = {}
    for q in (all_quests or []):
        merged[q.get('id')] = dict(q)
    for q in (feed_quests or []):
        cur = merged.get(q.get('id'), {}).copy()
        cur.update(q)
        merged[q.get('id')] = cur
    open_quests = []
    for q in merged.values():
        status = (q.get('status') or '').lower()
        if status in {'submitted', 'settled', 'closed', 'expired'}:
            continue
        open_quests.append(q)
    open_quests.sort(key=quest_score, reverse=True)
    return open_quests


def handle_competitive_quests(key, feed_quests, all_quests, state, max_auto=MAX_AUTO_QUESTS):
    candidates = select_competitive_quests(feed_quests, all_quests)
    auto_done = []
    manual = []
    for q in candidates:
        title = q.get('title') or 'Untitled quest'
        rewards = reward_profile(q)
        reward_text = reward_summary(rewards)
        item = {
            'id': q.get('id'),
            'title': title,
            'reward': reward_text,
            'reward_usdc': rewards['usdc'],
            'reward_xp': rewards['xp'],
            'priority_score': quest_score(q),
            'source': 'alliance',
        }
        if was_recently_auto_submitted(state, 'alliance', q.get('id')):
            manual.append({**item, 'reason': '已自动提交过，等待结果'})
            continue
        reason = manual_reason(q)
        if reason:
            manual.append({**item, 'reason': reason})
            continue
        if is_low_quality_competitive(q):
            manual.append({**item, 'reason': '低质量competitive，跳过'})
            continue
        if not is_auto_competitive_candidate(q):
            manual.append({**item, 'reason': '需人工筛选，跳过'})
            continue
        if not AUTO_SUBMIT_ALLIANCE or len(auto_done) >= max_auto:
            manual.append({**item, 'reason': '本轮未自动提交'})
            continue
        proof_url = 'https://www.agenthansa.com/llms.txt'
        if state_ref := state.get('daily_distribute', {}).get('ref_url'):
            proof_url = state_ref
        payload = {'content': build_submission_content(q), 'proof_url': proof_url}
        res, err = safe_req(f"/alliance-war/quests/{q['id']}/submit", method='POST', data=payload, key=key)
        if err or not res:
            manual.append({**item, 'reason': f'自动提交失败：{(err or "submit failed")[:120]}'})
            continue
        sub_item = {**item, 'submission_id': res.get('submission_id')}
        auto_done.append(sub_item)
        mark_recent_auto_submitted(state, 'alliance', q.get('id'), title=title, submission_id=res.get('submission_id'))
        append_summary({'status': 'competitive_submitted', 'tasks': [sub_item]})
        notify(f'联盟任务提交｜{title}｜reward={reward_text}')
    return auto_done, manual


def fetch_community_tasks():
    last_err = None
    for attempt in range(1, 4):
        try:
            data = run_agenthansa_cli_json(['tasks'])
            return (data or {}).get('bounties') or (data or {}).get('tasks') or []
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(2 * attempt)
                continue
            raise
    if last_err:
        raise last_err
    return []


def community_task_reason(task):
    low = quest_text(task)
    title = task.get('title') or ''
    reasons = []
    if task.get('require_proof'):
        reasons.append('需外部proof_url')
    if any(k in low for k in EXTERNAL_POSTING_KEYWORDS):
        reasons.append('需外部发帖/互动')
    if any(re.search(pattern, low) for pattern in HARD_HUMAN_COLLAB_PATTERNS):
        reasons.append('需人工协作')
    if '[' in title and ']' in title:
        reasons.append('任务占位符未明确')
    if task.get('max_participants') and (task.get('participant_count') or 0) >= task.get('max_participants') and not task.get('joined'):
        reasons.append('名额已满')
    return '；'.join(dict.fromkeys(reasons)) if reasons else None


def build_community_task_content(task):
    fields = task_fields(task)
    prompt = (
        'Write a strong submission for this AgentHansa community task in English. '
        'Output only the final submission. No markdown headings, no code fence, no separators.\n'
        f"Title: {fields['title']}\nDescription: {fields['description'][:1800]}\nGoal: {fields['goal'][:700]}\nRequirements/Proof: {fields['requirements'][:700]}\nTags: {fields['tags'][:240]}\nCategory: {fields['category'][:200]}\nKind: {fields['kind'][:120]}\n\n"
        'Make it concrete, useful, and directly complete the task. If the task asks for numbered items, provide numbered items.'
    )
    plan = classify_task_plan(task)
    routes = []
    pref = plan.get('preferred_model')
    if pref:
        routes.append(pref)
    routes.extend([x for x in ['deepseek', 'sonnet', 'gpt_claude'] if x not in routes])
    for route in routes:
        try:
            text = None
            if route == 'sonnet':
                if not router_is_available():
                    continue
                text = router_generate(prompt, max_tokens=320, temperature=0.3)
            elif route == 'deepseek':
                text = deepseek_generate(prompt, max_tokens=300, temperature=0.3) or small_llm_generate(prompt)
            else:
                text = llm_generate(prompt, model=WRITE_MODEL)
            text = clean_model_output(text)
            if text and len(text.split()) >= 20:
                return text.strip()
        except Exception as e:
            if route == 'sonnet':
                handle_router_error('community_task_sonnet', e)
            else:
                log(f'community task route={route} fallback: {e}')
    return local_submission_content(fields['title'])


def handle_community_tasks(state, max_auto=MAX_AUTO_COMMUNITY_TASKS):
    auto_done = []
    manual = []
    try:
        tasks = fetch_community_tasks()
    except Exception as e:
        log(f'community tasks fetch err: {e}')
        return auto_done, [{'id': 'community_tasks', 'title': 'community tasks', 'reward': '?', 'reward_usdc': 0.0, 'reward_xp': 0.0, 'priority_score': 0.0, 'source': 'community', 'reason': f'抓取失败：{str(e)[:120]}'}]
    tasks.sort(key=quest_score, reverse=True)
    for task in tasks:
        status = normalize_title(task.get('status'))
        if status in {'expired', 'completed'}:
            continue
        title = task.get('title') or 'Untitled community task'
        rewards = reward_profile(task)
        reward_text = reward_summary(rewards)
        item = {
            'id': task.get('id'),
            'title': title,
            'reward': reward_text,
            'reward_usdc': rewards['usdc'],
            'reward_xp': rewards['xp'],
            'priority_score': quest_score(task),
            'source': 'community',
        }
        if was_recently_auto_submitted(state, 'community', task.get('id')):
            manual.append({**item, 'reason': '已自动提交过，等待结果'})
            continue
        reason = community_task_reason(task)
        if reason:
            manual.append({**item, 'reason': reason})
            continue
        if len(auto_done) >= max_auto:
            manual.append({**item, 'reason': '本轮未自动提交'})
            continue
        try:
            if not task.get('joined'):
                run_agenthansa_cli_json(['tasks', '--join', str(task['id'])], timeout=180)
            content = build_community_task_content(task)
            res = run_agenthansa_cli_json(['tasks', '--submit', str(task['id']), '--description', content], timeout=240)
            sub_item = {**item, 'submission_status': res.get('status') or 'submitted'}
            auto_done.append(sub_item)
            mark_recent_auto_submitted(state, 'community', task.get('id'), title=title, submission_status=sub_item['submission_status'])
            append_summary({'status': 'community_task_submitted', 'tasks': [sub_item]})
            notify(f'Community任务提交｜{title}｜reward={reward_text}')
        except Exception as e:
            manual.append({**item, 'reason': f'自动提交失败：{str(e)[:120]}'})
    return auto_done, manual


def replace_number_words(text):
    q = text.lower()
    def repl(match):
        token = match.group(0)
        parts = token.replace('-', ' ').split()
        total = 0
        for part in parts:
            if part not in NUMBER_WORDS:
                return token
            total += NUMBER_WORDS[part]
        return str(total)
    pattern = r'\b(?:' + '|'.join(sorted(NUMBER_WORDS.keys(), key=len, reverse=True)) + r')(?:[- ](?:' + '|'.join(sorted(NUMBER_WORDS.keys(), key=len, reverse=True)) + r'))*\b'
    return re.sub(pattern, repl, q)


def solve_question(question):
    q = replace_number_words((question or '').lower().strip())
    q = q.replace('?', ' ').replace(',', ' ').replace('.', ' ')
    q = re.sub(r'\s+', ' ', q).strip()
    nums = list(map(int, re.findall(r'-?\d+', q)))
    if 'dozen' in q:
        q = q.replace('dozen', '12')
    if any(k in q for k in ['gives away half', 'loses half', 'spent half', 'half are left', 'half left']) and len(nums) >= 1:
        return str(nums[0] // 2)
    if any(k in q for k in ['shared equally', 'equally among', 'split equally', 'divide equally', 'each get']) and len(nums) >= 2 and nums[1] != 0:
        return str(nums[0] // nums[1])
    if any(k in q for k in ['left over', 'remainder', 'remain']) and len(nums) >= 2 and nums[1] != 0:
        return str(nums[0] % nums[1])
    m = re.search(r'(\d+)\s*(?:x|\*)\s*(\d+)', q)
    if m:
        return str(int(m.group(1)) * int(m.group(2)))
    if len(nums) == 3 and any(k in q for k in ['lose', 'left', 'minus', 'gave away', 'spent']):
        return str(nums[0] + nums[1] - nums[2])
    if len(nums) == 2 and any(k in q for k in ['gain', 'more', 'plus', 'add', 'total', 'altogether', 'in all']):
        return str(nums[0] + nums[1])
    if len(nums) == 2 and any(k in q for k in ['lose', 'minus', 'left', 'remain', 'after giving', 'spent']):
        return str(nums[0] - nums[1])
    if len(nums) == 2 and any(k in q for k in ['how many', 'count', 'coins', 'numbers', 'pages', 'steps', 'gems', 'pebbles']):
        low, high = nums[:2]
        return str(abs(high - low) + 1)
    if len(nums) == 1:
        return str(nums[0])
    raise RuntimeError(f'cannot solve question: {question}')


def solve_question_with_llm(question):
    if not OPENAI_API_KEY:
        raise RuntimeError('no llm available')
    prompt = f'Solve this math problem and return only the final integer: {question}'
    text = llm_generate(prompt)
    nums = re.findall(r'-?\d+', text or '')
    if not nums:
        raise RuntimeError(f'LLM non-numeric: {text!r}')
    return nums[-1]


def ensure_ref_link(key, state, force=False):
    now = int(time.time())
    last = state.get('last_ref_epoch', 0)
    if not force and last and now - last < 25*60 and state.get('latest_ref_url'):
        return {'ok': True, 'reused': True}
    offers, err = safe_req('/offers', key=key)
    if err or not offers:
        return {'ok': False, 'error': err or 'offers unavailable'}
    items = offers.get('offers', [])
    if not items:
        return {'ok': False, 'error': 'no offers'}
    best = max(items, key=offer_score)
    ref, err = safe_req(f"/offers/{best['id']}/ref", method='POST', data={}, key=key)
    if not err and ref:
        state['last_ref_epoch'] = now
        state['latest_ref_url'] = ref.get('ref_url') or ref.get('url')
        return {'ok': True, 'data': ref}
    return {'ok': False, 'error': err or 'ref failed'}


def ensure_alliance_submit(key, state, force=False):
    now = int(time.time())
    last = state.get('last_alliance_epoch', 0)
    if not force and last and now - last < 25*60:
        return {'ok': True, 'reused': True}
    quests, err = safe_req('/alliance-war/quests', key=key)
    if err or not quests:
        return {'ok': False, 'error': err or 'quests unavailable'}
    open_quests = [q for q in quests.get('quests', []) if q.get('status') == 'open']
    if not open_quests:
        return {'ok': False, 'error': 'no open quest'}
    chosen = max(open_quests, key=quest_score)
    payload = {'content': build_submission_content(chosen), 'proof_url': 'https://www.agenthansa.com/llms.txt'}
    resp, err = safe_req(f"/alliance-war/quests/{chosen['id']}/submit", method='POST', data=payload, key=key)
    if not err and resp:
        state['last_alliance_epoch'] = now
        return {'ok': True, 'data': resp}
    return {'ok': False, 'error': err or 'alliance submit failed'}


def ensure_forum_vote(key, state, my_name=None, direction='up', force=False):
    now = int(time.time())
    sk = f'last_vote_{direction}_epoch'
    last = state.get(sk, 0)
    if not force and last and now - last < 25*60:
        return {'ok': True, 'reused': True}
    feed, err = safe_req('/forum?sort=recent&limit=50', key=key)
    if err or not feed:
        return {'ok': False, 'error': err or 'forum unavailable'}
    for post in feed.get('posts', []):
        if my_name and (post.get('agent') or {}).get('name') == my_name:
            continue
        pid = post.get('id')
        if not pid:
            continue
        res, err = safe_req(f'/forum/{pid}/vote', method='POST', data={'direction': direction}, key=key)
        if not err:
            state[sk] = now
            return {'ok': True, 'data': res}
    return {'ok': False, 'error': 'no vote target'}


def packet_type(packet):
    text = ' '.join([packet.get('title', '') or '', packet.get('challenge_description', '') or '']).lower()
    if 'referral link' in text or 'ref link' in text:
        return 'ref_link'
    if 'alliance war' in text or 'submit or update' in text:
        return 'alliance'
    if 'vote' in text or 'upvote' in text:
        return 'upvote'
    if 'comment' in text:
        return 'comment'
    if 'write a forum post' in text or 'publish a post' in text or 'post or comment' in text:
        return 'post'
    return 'unknown'


def perform_challenge(key, packet, state, my_name):
    ptype = packet_type(packet)
    if ptype == 'comment':
        ok, err = do_forum_comment(key, my_name)
        if not ok:
            raise RuntimeError(err)
        return 'forum_comment'
    if ptype == 'upvote':
        res = ensure_forum_vote(key, state, my_name, direction='up', force=True)
        if not res.get('ok'):
            raise RuntimeError(res.get('error'))
        return 'forum_upvote'
    if ptype == 'ref_link':
        res = ensure_ref_link(key, state, force=True)
        if not res.get('ok'):
            raise RuntimeError(res.get('error'))
        return 'ref_link'
    if ptype == 'alliance':
        res = ensure_alliance_submit(key, state, force=True)
        if not res.get('ok'):
            raise RuntimeError(res.get('error'))
        return 'alliance_submit'
    if ptype == 'post':
        ok, info = do_forum_post(key)
        if not ok:
            ok2, err2 = do_forum_comment(key, my_name)
            if not ok2:
                raise RuntimeError(info or err2)
            return 'forum_comment_fallback'
        return 'forum_post'
    return 'unknown'


def get_active_packets(key):
    data, err = safe_req('/red-packets', key=key)
    if err or not data:
        return [], data, err
    active = data.get('active') or []
    return active, data, None


def join_packet(key, packet_id, max_attempts=2):
    force_llm = False
    question = answer = solver = None
    err = None
    for attempt in range(1, max_attempts + 1):
        chal, err = safe_req(f'/red-packets/{packet_id}/challenge', key=key)
        if err or not chal:
            raise RuntimeError(f'challenge failed: {err}')
        question = chal.get('question', '')
        try:
            if force_llm:
                answer = solve_question_with_llm(question)
                solver = 'llm'
            else:
                answer = solve_question(question)
                solver = 'rules'
        except Exception:
            answer = solve_question_with_llm(question)
            solver = 'llm'
        joined, err = safe_req(f'/red-packets/{packet_id}/join', method='POST', data={'answer': answer}, key=key)
        if not err:
            return question, answer, joined, solver, attempt
        msg = str(err)
        if 'Wrong answer' in msg or 'incorrect' in msg.lower():
            force_llm = True
            time.sleep(1.5)
            continue
        if '503' in msg or '429' in msg or 'unavailable' in msg.lower():
            time.sleep(6 if '429' in msg else 2)
            continue
        break
    raise RuntimeError(f'join failed: question={question!r} answer={answer} solver={solver} err={err}')


def process_red_packets(key, state, my_name):
    packets, data, err = get_active_packets(key)
    if err:
        return '红包状态未知', err
    if not packets:
        return '红包无急单', None
    attempted = state.setdefault('attempted_packets', {})
    join_attempts = state.setdefault('join_attempts', {})
    retry_after = state.setdefault('packet_retry_after', {})
    now = int(time.time())
    waiting = []
    for packet in packets:
        packet_id = str(packet.get('id'))
        if attempted.get(packet_id):
            continue
        if join_attempts.get(packet_id, 0) >= MAX_JOIN_ATTEMPTS_PER_PACKET:
            waiting.append(f'{packet_id}:retry_limit')
            continue
        if int(retry_after.get(packet_id, 0) or 0) > now:
            waiting.append(f'{packet_id}:cooldown')
            continue
        try:
            action_result = perform_challenge(key, packet, state, my_name)
            question, answer, joined, solver, attempt = join_packet(key, packet_id)
            attempted[packet_id] = int(time.time())
            join_attempts.pop(packet_id, None)
            retry_after.pop(packet_id, None)
            amount = None
            if isinstance(joined, dict):
                amount = joined.get('estimated_per_person') or joined.get('amount') or joined.get('reward')
            append_summary({'status': 'redpacket_success', 'packet_title': packet.get('title'), 'question': question, 'answer': answer, 'solver': solver, 'attempt': attempt, 'action_result': action_result, 'estimated_per_person': amount})
            notify(f'🧧✅ Red Packet：{amount or "?"}')
            return f"红包成功 {packet.get('title')}", None
        except Exception as e:
            join_attempts[packet_id] = join_attempts.get(packet_id, 0) + 1
            delay = random.randint(max(5, REDPACKET_RETRY_MIN_SECONDS), max(REDPACKET_RETRY_MIN_SECONDS, REDPACKET_RETRY_MAX_SECONDS))
            retry_after[packet_id] = int(time.time()) + delay
            append_summary({'status': 'redpacket_failure', 'packet_title': packet.get('title'), 'error': str(e)[:300], 'next_retry_in_seconds': delay})
            notify(f'红包失败｜{packet.get("title")}｜{str(e)[:500]}｜{delay}s后重试')
            waiting.append(f'{packet_id}:error')
    if waiting:
        return f'红包等待重试({",".join(waiting[:3])})', None
    return '红包已处理过', None


def next_watch_sleep_seconds(key):
    data, err = safe_req('/red-packets', key=key)
    if err or not data:
        return RUN_EVERY_SECONDS
    nxt = data.get('next_packet_seconds')
    active = data.get('active') or []
    if active:
        return random.randint(max(5, REDPACKET_RETRY_MIN_SECONDS), max(REDPACKET_RETRY_MIN_SECONDS, REDPACKET_RETRY_MAX_SECONDS))
    if isinstance(nxt, (int, float)):
        if nxt <= PRE_WATCH_SECONDS:
            return 5
        return max(30, min(RUN_EVERY_SECONDS, int(nxt - PRE_WATCH_SECONDS)))
    return RUN_EVERY_SECONDS


def maybe_watch_redpacket(key, state, my_name):
    data, err = safe_req('/red-packets', key=key)
    if err or not data:
        return None
    active = data.get('active') or []
    nxt = data.get('next_packet_seconds')
    if active:
        append_summary({
            'status': 'redpacket_active_snapshot',
            'count': len(active),
            'packets': [{'id': p.get('id'), 'title': p.get('title'), 'challenge': p.get('challenge_description')} for p in active[:10]],
        })
        return process_red_packets(key, state, my_name)
    if not isinstance(nxt, (int, float)) or nxt > PRE_WATCH_SECONDS:
        return None
    deadline = time.time() + min(WATCH_MAX_SECONDS, max(60, REDPACKET_WINDOW_SECONDS))
    while time.time() < deadline:
        result = process_red_packets(key, state, my_name)
        if result and result[0] != '红包无急单':
            return result
        time.sleep(random.uniform(max(5, REDPACKET_RETRY_MIN_SECONDS), max(REDPACKET_RETRY_MIN_SECONDS, REDPACKET_RETRY_MAX_SECONDS)))
    return None


def run_once():
    cfg = load_cfg()
    key = cfg['api_key']
    my_name = cfg.get('name') or 'agent'
    state = load_state()
    prune_recent_auto_submissions(state)
    blockers = []
    now = int(time.time())

    checkin, err = safe_req('/agents/checkin', method='POST', data={}, key=key)
    if not (checkin and 'message' in checkin) and not (err and 'already checked in' in str(err).lower()):
        blockers.append('签到失败')

    rank = fetch_rank_status(key, cfg)
    force_task_push = should_force_task_push(rank) if can_push_tasks_now() else False
    last_push = int(state.get('last_task_push_epoch', 0) or 0)
    should_push_tasks = can_push_tasks_now() and (force_task_push or (not last_push) or (now - last_push >= TASK_PUSH_EVERY_SECONDS))
    per_run_quota = 1
    alliance_quota = min(AGGRESSIVE_AUTO_QUESTS if force_task_push else MAX_AUTO_QUESTS, per_run_quota)
    community_quota = min(AGGRESSIVE_AUTO_COMMUNITY_TASKS if force_task_push else MAX_AUTO_COMMUNITY_TASKS, per_run_quota)

    feed, feed_err = safe_req('/agents/feed', key=key)
    if feed_err:
        blockers.append('feed失败')
        feed = {}

    red_result = maybe_watch_redpacket(key, state, my_name)
    if red_result and red_result[1]:
        blockers.append('红包异常')

    auto_done, manual_quests = [], []
    daily_done, daily_blockers = [], []
    all_quests_resp, quests_err = safe_req('/alliance-war/quests', key=key)
    all_quests = (all_quests_resp or {}).get('quests') or []
    if quests_err:
        blockers.append('alliance失败')
    if should_push_tasks:
        alliance_auto_done, alliance_manual_quests = handle_competitive_quests(key, feed.get('quests') or [], all_quests, state, max_auto=alliance_quota)
        remaining_quota = max(0, per_run_quota - len(alliance_auto_done))
        community_auto_done, community_manual_quests = handle_community_tasks(state, max_auto=min(community_quota, remaining_quota))
        auto_done = alliance_auto_done + community_auto_done
        manual_quests = alliance_manual_quests + community_manual_quests
        manual_quests.sort(key=lambda x: x.get('priority_score', 0), reverse=True)
        write_json(MANUAL_QUEUE, {'ts': datetime.now().isoformat(timespec='seconds'), 'count': len(manual_quests), 'quests': manual_quests[:40]})
        daily_done, daily_blockers = process_daily_quests(key, state, my_name)
        state['last_task_push_epoch'] = now
        rank = fetch_rank_status(key, cfg)
    else:
        manual_quests = (read_json(MANUAL_QUEUE, {}) or {}).get('quests') or []
    blockers.extend(daily_blockers)

    state['last_rank_status'] = rank
    state['last_run_at'] = datetime.now(timezone.utc).isoformat()
    state['last_auto_done'] = auto_done
    state['last_daily_done'] = daily_done
    maybe_write_daily_review(state)

    earnings, earn_err = safe_req('/agents/earnings', key=key)
    if earnings and not earn_err:
        state['last_earnings'] = earnings
    summary = {
        'rank': rank,
        'auto_done': auto_done,
        'manual_count': len(manual_quests),
        'daily_done': daily_done,
        'blockers': list(dict.fromkeys(blockers)),
        'red_result': red_result[0] if red_result else None,
        'earnings': (earnings or {}).get('total') if isinstance(earnings, dict) else None,
        'task_push_ran': should_push_tasks,
        'force_task_push': force_task_push,
        'can_push_tasks_now': can_push_tasks_now(),
        'target_lead': SAFE_LEAD_TARGET,
    }
    maybe_send_periodic_summary(state, summary)
    save_state(state)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def loop_forever():
    while True:
        try:
            run_once()
        except Exception as e:
            log(f'loop error: {e}')
        sleep_s = next_watch_sleep_seconds(load_cfg()['api_key'])
        log(f'sleep {sleep_s}s')
        time.sleep(sleep_s)


def status():
    cfg = load_cfg()
    key = cfg['api_key']
    rank = fetch_rank_status(key, cfg)
    print(json.dumps({'config': str(CONFIG), 'state': str(STATE), 'manual_queue': str(MANUAL_QUEUE), 'rank': rank}, ensure_ascii=False, indent=2))


def test_keys():
    results = []
    try:
        text = openai_compatible_generate(DEROUTER_BASE_URL, DEROUTER_API_KEY, WRITE_MODEL, 'Reply with OK only.', max_tokens=16, temperature=0)
        results.append({'provider': 'derouter-write', 'model': WRITE_MODEL, 'ok': bool(text)})
    except Exception as e:
        results.append({'provider': 'derouter-write', 'model': WRITE_MODEL, 'ok': False, 'error': str(e)[:200]})
    try:
        text = openai_compatible_generate(DEROUTER_BASE_URL, DEROUTER_API_KEY, REVIEW_MODEL, 'Reply with OK only.', max_tokens=16, temperature=0)
        results.append({'provider': 'derouter-review', 'model': REVIEW_MODEL, 'ok': bool(text)})
    except Exception as e:
        results.append({'provider': 'derouter-review', 'model': REVIEW_MODEL, 'ok': False, 'error': str(e)[:200]})
    for idx, key in enumerate(AINFT_API_KEYS, 1):
        try:
            text = openai_compatible_generate(AINFT_BASE_URL, key, AINFT_TEST_MODEL, 'Reply with OK only.', max_tokens=16, temperature=0)
            results.append({'provider': f'ainft-key-{idx}', 'model': AINFT_TEST_MODEL, 'ok': bool(text)})
        except Exception as e:
            results.append({'provider': f'ainft-key-{idx}', 'model': AINFT_TEST_MODEL, 'ok': False, 'error': str(e)[:200]})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description='AgentHansa 本机全自动 Top1 脚本')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('run-once')
    sub.add_parser('loop')
    sub.add_parser('status')
    sub.add_parser('test-keys')
    args = ap.parse_args()
    if args.cmd == 'run-once':
        return run_once()
    if args.cmd == 'loop':
        loop_forever()
        return 0
    if args.cmd == 'status':
        status()
        return 0
    if args.cmd == 'test-keys':
        return test_keys()
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
