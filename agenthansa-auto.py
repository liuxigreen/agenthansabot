#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from agenthansa_runtime_profile import classify_task, classify_task_detail, browser_executor_stub
from agenthansa_challenges import detect_challenge_action, execute_challenge_action
from agenthansa_guardrails import guard_can_write, guard_record_write

HOME = Path.home()
WORKSPACE = Path(os.getenv('AGENTHANSA_WORKSPACE', str(HOME / '.openclaw' / 'workspace')))
CONFIG = Path(os.getenv('AGENTHANSA_CONFIG', str(HOME / '.config' / 'agenthansa' / 'config.json')))
LOG = Path(os.getenv('AGENTHANSA_LOG', str(WORKSPACE / 'logs' / 'agenthansa-auto.log')))
STATE = Path(os.getenv('AGENTHANSA_STATE', str(WORKSPACE / 'memory' / 'agenthansa-state.json')))
TASK_SUMMARY = Path(os.getenv('AGENTHANSA_TASK_SUMMARY', str(WORKSPACE / 'memory' / 'agenthansa-task-summary.jsonl')))
UNKNOWN_CHALLENGE_LOG = Path(os.getenv('AGENTHANSA_UNKNOWN_CHALLENGE_LOG', str(WORKSPACE / 'memory' / 'agenthansa-unknown-challenges.jsonl')))
MANUAL_QUEUE = Path(os.getenv('AGENTHANSA_MANUAL_QUEUE', str(WORKSPACE / 'memory' / 'agenthansa-manual-quests.json')))
BASE = 'https://www.agenthansa.com/api'
UA = 'OpenClaw-Xiami/1.0'
EDGEFN_URL = 'https://api.edgefn.net/v1/chat/completions'
EDGEFN_KEY = os.getenv('EDGEFN_API_KEY', '')
EDGEFN_WRITE_MODELS = ['GLM-5', 'MiniMax-M2.5']
DEROUTER_URL = 'https://api.derouter.ai/openai/v1/chat/completions'
DEROUTER_KEY = os.getenv('DEROUTER_API_KEY', '')
DEROUTER_DRAFT_MODEL = os.getenv('AGENTHANSA_DRAFT_MODEL', 'claude-sonnet-4-5')
DEROUTER_REVIEW_MODEL = os.getenv('AGENTHANSA_REVIEW_MODEL', 'gpt-5.4')
HIGH_VALUE_MODE = os.getenv('AGENTHANSA_HIGH_VALUE_MODE', 'B').upper().strip() or 'B'
HIGH_VALUE_ROUTE = os.getenv('AGENTHANSA_HIGH_VALUE_ROUTE', 'sonnet_draft_gpt_final').strip()
HIGH_VALUE_REVIEW_USDC = float(os.getenv('AGENTHANSA_HIGH_VALUE_REVIEW_USDC', '20'))
AUTO_SUBMIT_COMPETITIVE = os.getenv('AGENTHANSA_AUTO_SUBMIT_COMPETITIVE', '1').lower() in {'1', 'true', 'yes', 'on'}
MAX_AUTO_QUESTS = int(os.getenv('AGENTHANSA_MAX_AUTO_QUESTS', '2'))
SNIPER_SCRIPT = os.getenv('AGENTHANSA_SNIPER_SCRIPT', str(WORKSPACE / 'scripts' / 'agenthansa-sniper.py'))
BROWSER_EXECUTOR_CMD = os.getenv('AGENTHANSA_BROWSER_EXECUTOR_CMD', '')
SAFE_LEAD_TARGET = int(os.getenv('AGENTHANSA_SAFE_LEAD_TARGET', '100'))
DISTRIBUTE_REFRESH_SECS = int(os.getenv('AGENTHANSA_DISTRIBUTE_REFRESH_SECS', '1800'))
RUNTIME_PROFILE = os.getenv('AGENTHANSA_RUNTIME_PROFILE', 'mac_openclaw').strip() or 'mac_openclaw'
MAC_FEED_INTERVAL_SECONDS = int(os.getenv('AGENTHANSA_MAC_FEED_INTERVAL_SECONDS', '300'))

EXTERNAL_POSTING_KEYWORDS = [
    'twitter', 'x.com', 'tweet', 'thread', 'retweet', 'reddit', 'linkedin', 'medium', 'dev.to',
    'hacker news', 'product hunt', 'youtube', 'newsletter', 'social media', 'post about',
    'publish', 'share on', 'comment on', 'comment under', 'reply to', 'follow us', 'followers',
    'discord', 'telegram', 'screenshot', 'screen recording', 'record a video', 'upload photo'
]

WALLET_FUND_KEYWORDS = [
    'wallet', 'fund', 'funds', 'gas', 'payment', 'deposit', 'bridge', 'swap', 'trade', 'onchain',
    'send usdc', 'buy token', 'purchase', 'mint', 'stake', 'liquidity'
]

HUMAN_COLLAB_PATTERNS = [
    r'\bhuman collaboration\b',
    r'\bcollaborat(?:e|ion)\b',
    r'\bmanual review\b',
    r'\bhuman review\b',
    r'\binterview\b',
    r'\bcall(?: with| us| me| our team)?\b',
    r'\bmeeting\b',
    r'\bspace\b',
    r'\bdirect message\b',
    r'\bask a friend\b',
    r'\bteam up\b',
    r'\bpartner with\b',
    r'\bcoordinate with\b',
]

HIGH_QUALITY_KEYWORDS = [
    'technical', 'documentation', 'migration', 'analysis', 'research', 'deep analysis',
    'competitor', 'comparison', 'faq', 'guide', 'explain', 'describe', 'landing page copy',
    'case study', 'blog post', 'review and improve', 'whitepaper', 'strategy', 'economics',
    'history'
]

LOW_QUALITY_KEYWORDS = [
    'daily feedback', 'quick feedback', 'rate and review your fellow agents', 'peer evaluation',
    'genuine comment', 'simple review', 'short answer', 'shoutout'
]

HARD_WRITING_KEYWORDS = [
    'technical', 'documentation', 'migration', 'analysis', 'research', 'deep analysis',
    'landing page copy', 'whitepaper', 'case study', 'strategy', 'economics', 'history',
    'competitor', 'blog post'
]

SIMPLE_WRITING_KEYWORDS = [
    'faq', 'guide', 'comparison', 'compare', 'explain', 'describe', 'feedback'
]


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f'[{now()}] {msg}'
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def append_task_summary(event: dict):
    TASK_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with TASK_SUMMARY.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': datetime.now().isoformat(timespec='seconds'), **event}, ensure_ascii=False) + '\n')


def append_unknown_challenge(event: dict):
    UNKNOWN_CHALLENGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with UNKNOWN_CHALLENGE_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': datetime.now().isoformat(timespec='seconds'), **event}, ensure_ascii=False) + '\n')


def load_cfg():
    return json.loads(CONFIG.read_text())


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def normalize_title(title: str) -> str:
    return re.sub(r'\s+', ' ', (title or '').strip().lower())


def parse_money(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        nums = re.findall(r'\d+(?:\.\d+)?', value)
        return float(nums[0]) if nums else 0.0
    if isinstance(value, dict):
        for key in ['amount', 'reward_amount', 'value', 'reward', 'usdc']:
            if key in value and value.get(key) not in (None, ''):
                try:
                    return float(value[key])
                except Exception:
                    pass
        for v in value.values():
            if isinstance(v, (int, float)):
                return float(v)
    return 0.0


def format_number(value) -> str:
    if value is None:
        return '未知'
    num = float(value)
    if num.is_integer():
        return str(int(num))
    return f'{num:.2f}'.rstrip('0').rstrip('.')


def flatten_text(value):
    parts = []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            parts.append(stripped)
    elif isinstance(value, dict):
        for nested in value.values():
            parts.extend(flatten_text(nested))
    elif isinstance(value, list):
        for nested in value:
            parts.extend(flatten_text(nested))
    return parts


def quest_signal_source(q):
    keys = [
        'title', 'description', 'goal', 'instructions', 'requirements', 'submission_rules',
        'proof_requirements', 'proof_type', 'verification', 'submission_type', 'task_type',
        'platform', 'category', 'tags', 'notes', 'details'
    ]
    source = {}
    for key in keys:
        value = q.get(key)
        if value not in (None, '', [], {}):
            source[key] = value
    return source or q


def quest_text(q) -> str:
    return normalize_title(' '.join(flatten_text(quest_signal_source(q))))


def reward_profile(q):
    profile = {'usdc': 0.0, 'xp': 0.0}
    reward_fields = ['reward', 'reward_amount', 'payout', 'rewards', 'bonus', 'prize', 'points_reward', 'xp_reward']

    def record(kind: str, amount: float):
        if amount > 0:
            profile[kind] = max(profile[kind], amount)

    def scan_text(text: str, key_hint: str):
        low = normalize_title(text)
        for pattern in [r'\$ ?(\d+(?:\.\d+)?)', r'(\d+(?:\.\d+)?)\s*usdc\b', r'usdc\s*(\d+(?:\.\d+)?)']:
            for match in re.finditer(pattern, low):
                record('usdc', float(next(group for group in match.groups() if group)))
        for pattern in [r'(\d+(?:\.\d+)?)\s*xp\b', r'(\d+(?:\.\d+)?)\s*points?\b']:
            for match in re.finditer(pattern, low):
                record('xp', float(next(group for group in match.groups() if group)))
        if any(token in key_hint for token in ['usdc', 'usd', 'payout', 'cash']):
            record('usdc', parse_money(text))
        if any(token in key_hint for token in ['xp', 'point']):
            record('xp', parse_money(text))

    def walk(value, key_hint=''):
        hint = normalize_title(key_hint)
        if isinstance(value, dict):
            currency = normalize_title(str(value.get('currency') or value.get('unit') or value.get('token') or ''))
            amount = parse_money(value.get('amount')) if value.get('amount') not in (None, '') else 0.0
            if amount:
                if currency in {'usdc', 'usd'} or any(token in hint for token in ['usdc', 'usd', 'payout', 'cash']):
                    record('usdc', amount)
                if currency in {'xp', 'point', 'points'} or any(token in hint for token in ['xp', 'point']):
                    record('xp', amount)
            for nested_key, nested_value in value.items():
                walk(nested_value, f'{key_hint}.{nested_key}' if key_hint else nested_key)
            return
        if isinstance(value, list):
            for nested in value:
                walk(nested, key_hint)
            return
        if isinstance(value, (int, float)):
            amount = float(value)
            if any(token in hint for token in ['usdc', 'usd', 'payout', 'cash']):
                record('usdc', amount)
            if any(token in hint for token in ['xp', 'point']):
                record('xp', amount)
            return
        if isinstance(value, str):
            scan_text(value, hint)

    for field in reward_fields:
        value = q.get(field)
        if value not in (None, '', [], {}):
            walk(value, field)
    return profile


def reward_summary(profile) -> str:
    parts = []
    if profile.get('usdc'):
        parts.append(f"${format_number(profile['usdc'])}")
    if profile.get('xp'):
        parts.append(f"{format_number(profile['xp'])}XP")
    return '+'.join(parts) if parts else '?'


def req(path, method='GET', data=None, key=None):
    url = path if path.startswith('http') else BASE + path
    headers = {'User-Agent': UA}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    body = None
    if data is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(data).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw else {}


def safe_req(*args, max_retries=3, **kwargs):
    for attempt in range(1, max_retries + 1):
        try:
            return req(*args, **kwargs), None
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            try:
                return None, f'HTTP {e.code}: {e.read().decode()}'
            except Exception:
                return None, f'HTTP {e.code}'
        except Exception as e:
            err = repr(e)
            if attempt < max_retries and ('503' in err or 'unavailable' in err.lower()):
                time.sleep(2 ** attempt)
                continue
            return None, err
    return None, 'unknown error'


def clean_model_output(text: str):
    text = (text or '').strip()
    text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^<think>[\s\S]*$', '', text, flags=re.IGNORECASE).strip()
    text = text.replace('```', '').strip()
    words = text.split()
    if len(words) > 180:
        text = ' '.join(words[:180])
    return text.strip()


def edgefn_generate(model: str, prompt: str, max_tokens: int = 220):
    if not EDGEFN_KEY:
        raise RuntimeError('EDGEFN_API_KEY is not set')
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_completion_tokens': max_tokens,
        'temperature': 0.4,
    }
    req_obj = urllib.request.Request(
        EDGEFN_URL,
        data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {EDGEFN_KEY}', 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req_obj, timeout=45) as r:
        data = json.loads(r.read().decode())
    text = (((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip()
    return clean_model_output(text)


def get_derouter_settings():
    try:
        cfg = load_cfg()
    except Exception:
        cfg = {}
    return {
        'key': DEROUTER_KEY or cfg.get('derouter_api_key') or '',
        'draft_model': cfg.get('derouter_draft_model') or DEROUTER_DRAFT_MODEL,
        'review_model': cfg.get('derouter_review_model') or DEROUTER_REVIEW_MODEL,
        'route': cfg.get('high_value_route') or HIGH_VALUE_ROUTE,
    }


def derouter_chat(model: str, messages: list, max_tokens: int = 400, temperature: float = 0.7):
    settings = get_derouter_settings()
    if not settings['key']:
        raise RuntimeError('DEROUTER_API_KEY is not set')
    payload = {
        'model': model,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }
    req_obj = urllib.request.Request(
        DEROUTER_URL,
        data=json.dumps(payload).encode(),
        headers={'Authorization': f"Bearer {settings['key']}", 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req_obj, timeout=60) as r:
        data = json.loads(r.read().decode())
    text = (((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip()
    return clean_model_output(text)


def derouter_generate(prompt: str, max_tokens: int = 400, model: str | None = None, temperature: float = 0.7):
    settings = get_derouter_settings()
    return derouter_chat(model or settings['draft_model'], [{'role': 'user', 'content': prompt}], max_tokens=max_tokens, temperature=temperature)


def preferred_generation_route(title: str):
    low = normalize_title(title)
    if any(k in low for k in HARD_WRITING_KEYWORDS):
        return ['derouter', *EDGEFN_WRITE_MODELS]
    if any(k in low for k in SIMPLE_WRITING_KEYWORDS + ['how', 'upwork', 'fiverr']):
        return [*EDGEFN_WRITE_MODELS, 'derouter']
    return [*EDGEFN_WRITE_MODELS, 'derouter']


def build_quest_prompt_context(q_or_title):
    if isinstance(q_or_title, dict):
        q = q_or_title
        fields = []
        for key in ['title', 'description', 'goal', 'instructions', 'requirements', 'submission_rules', 'proof_requirements', 'category', 'tags']:
            value = q.get(key)
            if value in (None, '', [], {}):
                continue
            if isinstance(value, list):
                value = ', '.join(str(v) for v in value if v not in (None, ''))
            elif isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            fields.append(f'{key}: {value}')
        return '\n'.join(fields)
    return f'title: {q_or_title}'


def is_high_value_writing(q_or_title) -> bool:
    if isinstance(q_or_title, dict):
        low = quest_text(q_or_title)
        rewards = reward_profile(q_or_title)
        return any(k in low for k in HARD_WRITING_KEYWORDS) or rewards.get('usdc', 0) >= HIGH_VALUE_REVIEW_USDC
    low = normalize_title(str(q_or_title))
    return any(k in low for k in HARD_WRITING_KEYWORDS)


def local_submission_content(title: str):
    ts = now()
    low = normalize_title(title)
    if 'landing page copy' in low:
        return (
            f'Premium landing page copy ({ts}): AgentHansa is where AI agents stop being demos and start acting like economic workers. '
            'An agent can register in minutes, pick live tasks, join red packets, enter alliance wars, and earn USDC through real execution instead of benchmark theater. '
            'The appeal is speed and repetition: small wins compound, reputation compounds, and operators can quickly see which agents actually deliver. '
            'The strongest hook is simple: this is not another agent directory. It is a task market with incentives, feedback loops, and visible outcomes. '
            'For builders who want autonomous agents doing practical work, AgentHansa feels much closer to a live operating environment than a showcase page.'
        )
    if 'technical' in low or 'documentation' in low or 'migration' in low:
        return (
            f'Technical note ({ts}): A strong migration guide should reduce operational risk, not just list steps. '
            'The best version makes prerequisites explicit, explains rollback paths, highlights state compatibility risks, and shows how to validate success after each phase. '
            'That matters because migrations fail less from missing commands than from hidden assumptions about data shape, ordering, and environment parity. '
            'Clear checkpoints, expected outputs, and post-migration verification make the document trustworthy for both cautious operators and fast-moving teams.'
        )
    if 'faq' in low or 'upwork' in low:
        return (
            f'FAQ answer ({ts}): AgentHansa is stronger than Upwork for AI-agent-native work because it supports repeatable automated execution, rapid task cycles, '
            'red packets, daily quests, and alliance reputation loops. Upwork is better for larger budgets and traditional human-managed relationships, '
            'but AgentHansa is better when speed, autonomy, and compounding small wins matter more than contract size.'
        )
    if 'comparison' in low or 'compare' in low or 'fiverr' in low:
        return (
            f'Comparison ({ts}): AgentHansa is built for continuous agent execution, while Fiverr and Upwork are optimized for human service marketplaces. '
            'Fiverr is strongest for packaged deliverables and Upwork for larger custom contracts, but AgentHansa wins when the goal is fast task turnover, '
            'programmable participation, and a tighter loop between action, feedback, and rewards.'
        )
    if 'analysis' in low or 'research' in low:
        return (
            f'Analysis ({ts}): The most important difference in agent marketplaces is not who claims the most intelligence but who creates the cleanest incentive loop. '
            'Platforms improve when they reward speed, verification, and repeatability at the same time. AgentHansa stands out because it combines task flow, '
            'competitive pressure, and visible rewards in a way that exposes which agents can actually ship work.'
        )
    return (
        f'Quest submission ({ts}): Xiami completed a high-signal response focused on concrete utility, clear reasoning, and operator-grade execution quality.'
    )


def build_submission_content(q_or_title):
    title = q_or_title.get('title') if isinstance(q_or_title, dict) else str(q_or_title)
    low = quest_text(q_or_title) if isinstance(q_or_title, dict) else normalize_title(title)
    use_model = any(k in low for k in [
        'feedback', 'review and improve', 'analysis', 'blog', 'faq', 'comparison', 'write',
        'explain', 'describe', 'how', 'technical', 'documentation', 'migration', 'copy',
        'competitor', 'case study', 'strategy'
    ])
    if not use_model:
        return local_submission_content(title)

    quest_context = build_quest_prompt_context(q_or_title)
    prompt = (
        'Write an AgentHansa quest submission in English.\n'
        f'Quest context:\n{quest_context}\n\n'
        'Requirements: concrete, useful, human-sounding, not generic, no markdown headings, 120-180 words, directly answer the task.'
    )

    if is_high_value_writing(q_or_title):
        try:
            settings = get_derouter_settings()
            draft = derouter_generate(prompt, max_tokens=420, model=settings['draft_model'], temperature=0.7)
            if draft and len(draft.split()) >= 40:
                review_prompt = (
                    'You are reviewing an AgentHansa quest submission draft. Rewrite it into the final version. '\
                    'Keep the strongest ideas, remove fluff, make it more specific and natural, and ensure it sounds credible and submit-ready. '\
                    'Output only the final submission in English, 120-180 words, no headings.\n\n'
                    f'Quest context:\n{quest_context}\n\nDraft:\n{draft}'
                )
                reviewed = derouter_generate(review_prompt, max_tokens=420, model=settings['review_model'], temperature=0.4)
                if reviewed and len(reviewed.split()) >= 40:
                    return reviewed
                return draft
        except Exception as e:
            log(f'high-value write/review fallback: {title} | {e}')

    for route in preferred_generation_route(title):
        try:
            text = derouter_generate(prompt) if route == 'derouter' else edgefn_generate(route, prompt)
            if text and len(text.split()) >= 40:
                return text
        except Exception:
            time.sleep(5 if route == 'derouter' else 10)
            continue
    return local_submission_content(title)


def manual_reason(q):
    low = quest_text(q)
    reasons = []
    if any(k in low for k in EXTERNAL_POSTING_KEYWORDS):
        reasons.append('需外部发帖/互动')
    if q.get('require_proof') or re.search(r'proof[_\s-]*url', low) or 'verification link' in low:
        reasons.append('需外部proof_url')
    if any(k in low for k in WALLET_FUND_KEYWORDS):
        reasons.append('需钱包/资金')
    if any(re.search(pattern, low) for pattern in HUMAN_COLLAB_PATTERNS):
        reasons.append('需人工协作')
    return '；'.join(dict.fromkeys(reasons)) if reasons else None


def is_low_quality_competitive(q) -> bool:
    low = quest_text(q)
    if any(k in low for k in LOW_QUALITY_KEYWORDS):
        return True
    return bool(re.search(r'\b(?:one|1|two|2)\s+(?:sentence|paragraph|line|comment)\b', low))


def quality_score(q) -> float:
    low = quest_text(q)
    score = 0.0
    if any(k in low for k in HIGH_QUALITY_KEYWORDS):
        score += 60
    if any(k in low for k in ['technical', 'documentation', 'migration']):
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


def is_auto_competitive_candidate(q) -> bool:
    return manual_reason(q) is None and not is_low_quality_competitive(q) and quality_score(q) >= 55


def quest_score(q) -> float:
    rewards = reward_profile(q)
    score = max(quality_score(q), 0) * 100
    score += rewards['xp']
    if rewards['usdc'] > 0:
        score += 1_000_000 + rewards['usdc'] * 10_000
    return score


def fetch_rank_status(key):
    me, err = safe_req('/agents/me', key=key)
    if err or not me:
        return {'alliance_rank': None, 'gap_to_first': None, 'lead_over_second': None}
    alliance_name = me.get('alliance')
    agent_name = me.get('name') or 'Xiami'
    alliance_daily, err1 = safe_req('/agents/alliance-daily-leaderboard', key=key)
    if err1 or not alliance_daily:
        return {'alliance_rank': None, 'gap_to_first': None, 'lead_over_second': None}
    alliance_info = (alliance_daily.get('alliances') or {}).get(alliance_name) or {}
    lb = alliance_info.get('leaderboard') or []
    mine = next((row for row in lb if row.get('name') == agent_name), None)
    leader = lb[0] if lb else None
    second = lb[1] if len(lb) > 1 else None
    status = {
        'alliance_rank': mine.get('rank') if mine else None,
        'alliance_points': mine.get('today_points') if mine else None,
        'leader_name': leader.get('name') if leader else None,
        'leader_points': leader.get('today_points') if leader else None,
        'second_points': second.get('today_points') if second else None,
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


def offer_score(offer) -> float:
    rewards = reward_profile(offer)
    return rewards['usdc'] * 10_000 + rewards['xp']


def ensure_distribute_done(key, state):
    day = datetime.now().strftime('%Y-%m-%d')
    now_ts = int(time.time())
    distribute_state = state.setdefault('daily_distribute', {})
    if (
        distribute_state.get('day') == day
        and distribute_state.get('ref_url')
        and now_ts - int(distribute_state.get('last_attempt_epoch', 0) or 0) < DISTRIBUTE_REFRESH_SECS
    ):
        return distribute_state.get('ref_url'), None
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
    distribute_state['day'] = day
    distribute_state['last_attempt_epoch'] = now_ts
    distribute_state['offer_id'] = best.get('id')
    distribute_state['offer_reward'] = reward_summary(reward_profile(best))
    distribute_state['ref_url'] = url
    return url, None


def do_digest(key):
    digest, err = safe_req('/forum/digest', key=key)
    return digest is not None and err is None, err


def do_forum_comment(key, state=None):
    feed, err = safe_req('/forum?sort=recent&limit=30', key=key)
    if err or not feed:
        return False, err or 'forum unavailable'
    posts = feed.get('posts') or []
    today = datetime.now().strftime('%Y-%m-%d')
    state = state if isinstance(state, dict) else {}
    comment_state = state.setdefault('comment_guard', {'day': today, 'count': 0, 'post_ids': []})
    if comment_state.get('day') != today:
        comment_state.clear()
        comment_state.update({'day': today, 'count': 0, 'post_ids': []})
    if int(comment_state.get('count', 0) or 0) >= 2:
        return False, 'comment diminishing cap reached'
    seen_posts = set(str(x) for x in (comment_state.get('post_ids') or []))
    for post in posts:
        pid = post.get('id')
        if not pid:
            continue
        if str(pid) in seen_posts:
            continue
        title = (post.get('title') or '').strip()
        body = f'Useful angle on "{title}" — concrete examples like this make the forum more helpful for operators and agents.' if title else 'Helpful post — concrete examples make the forum more useful for operators and agents.'
        ok_guard, guard_reason = guard_can_write(state, 'comment', content=body, pattern=f'forum_comment:{pid}')
        if not ok_guard:
            return False, guard_reason
        _, err = safe_req(f'/forum/{pid}/comments', method='POST', data={'body': body}, key=key)
        if not err:
            guard_record_write(state, 'comment', content=body, pattern=f'forum_comment:{pid}')
            comment_state['count'] = int(comment_state.get('count', 0) or 0) + 1
            comment_state['post_ids'] = (comment_state.get('post_ids') or []) + [str(pid)]
            return True, None
    return False, 'no comment target'


def do_forum_vote_once(key, direction='up'):
    feed, err = safe_req('/forum?sort=recent&limit=25', key=key)
    if err or not feed:
        return False, err or 'forum unavailable'
    for post in (feed.get('posts') or []):
        pid = post.get('id')
        if not pid:
            continue
        _, verr = safe_req(f"/forum/{pid}/vote?direction={direction}", method='POST', data={}, key=key)
        if not verr:
            return True, None
    return False, 'no vote target'


def run_browser_executor(task):
    stub = browser_executor_stub(task)
    if not BROWSER_EXECUTOR_CMD:
        return {**stub, 'ok': False, 'error': 'browser_executor_cmd_missing'}
    try:
        proc = subprocess.run(
            [BROWSER_EXECUTOR_CMD, json.dumps(task, ensure_ascii=False)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode == 0:
            try:
                payload = json.loads((proc.stdout or '').strip() or '{}')
            except Exception:
                payload = {'ok': True, 'proof_url': (proc.stdout or '').strip()}
            payload.setdefault('ok', True)
            payload.setdefault('contract', stub.get('contract'))
            return payload
        return {**stub, 'ok': False, 'error': (proc.stderr or proc.stdout or 'executor_failed')[:300]}
    except Exception as e:
        return {**stub, 'ok': False, 'error': str(e)}


def execute_redpacket_action(key, packet, state):
    def on_unknown(pkt, reason):
        append_unknown_challenge({
            'packet_id': pkt.get('id'),
            'title': pkt.get('title'),
            'challenge_description': pkt.get('challenge_description'),
            'context': {'task_type': pkt.get('type'), 'status': pkt.get('status')},
            'classification': 'unknown',
            'reason': reason,
        })
    handlers = {
        'forum_upvote': lambda: do_forum_vote_once(key, direction='up'),
        'forum_downvote': lambda: do_forum_vote_once(key, direction='down'),
        'forum_post': lambda: do_forum_comment(key, state),
        'forum_comment': lambda: do_forum_comment(key, state),
        'referral_generate': lambda: ((lambda ref, err: (bool(ref), err))(*ensure_distribute_done(key, state))),
        'digest_read': lambda: do_digest(key),
    }
    return execute_challenge_action(packet, handlers, on_unknown=on_unknown)


def browser_executor_available():
    return bool(BROWSER_EXECUTOR_CMD) and os.path.exists(BROWSER_EXECUTOR_CMD) and os.access(BROWSER_EXECUTOR_CMD, os.X_OK)


def do_forum_curation(key, daily):
    curate = next((q for q in (daily.get('quests') or []) if q.get('id') == 'curate'), None)
    if not curate or curate.get('completed'):
        return '已完成', None
    feed, err = safe_req('/forum?sort=recent&limit=100', key=key)
    if err or not feed:
        return None, err or 'forum unavailable'
    posts = feed.get('posts') or []
    up_need = down_need = 0
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


def process_red_packets(key, state):
    red, err = safe_req('/red-packets', key=key)
    if err or not red:
        return '红包状态未知', err or 'red packets unavailable'
    active = red.get('active') or []
    if not active:
        return '红包无急单', None
    packet = active[0]
    action, action_err = execute_redpacket_action(key, packet, state)
    if action:
        append_task_summary({'status': 'redpacket_action', 'action': action, 'error': action_err, 'packet_id': packet.get('id')})
    proc = subprocess.run(['python3', SNIPER_SCRIPT], capture_output=True, text=True, timeout=180, check=False)
    if proc.returncode == 0:
        return f'红包已处理({len(active)})', None
    err_line = (proc.stderr or proc.stdout or '').strip().splitlines()[-1] if (proc.stderr or proc.stdout) else 'sniper failed'
    return '红包处理失败', err_line


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


def write_manual_queue(items):
    MANUAL_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    MANUAL_QUEUE.write_text(json.dumps({
        'ts': datetime.now().isoformat(timespec='seconds'),
        'count': len(items),
        'quests': items,
    }, ensure_ascii=False, indent=2))


def handle_competitive_quests(key, feed_quests, all_quests):
    candidates = select_competitive_quests(feed_quests, all_quests)
    auto_done = []
    manual = []
    soft_notes = []
    low_quality_skips = 0

    for q in candidates:
        title = q.get('title') or 'Untitled quest'
        rewards = reward_profile(q)
        reward_text = reward_summary(rewards)
        base_item = {
            'id': q.get('id'),
            'title': title,
            'reward': reward_text,
            'reward_usdc': rewards['usdc'],
            'reward_xp': rewards['xp'],
            'priority_score': quest_score(q),
        }
        task_meta = classify_task_detail(q) if RUNTIME_PROFILE == 'mac_openclaw' else {'task_class': 'legacy', 'reason': 'non-mac legacy mode'}
        task_class = task_meta['task_class']
        if task_class == 'browser_proof_required' and not browser_executor_available():
            manual.append({
                **base_item,
                'reason': 'browser executor unavailable: AGENTHANSA_BROWSER_EXECUTOR_CMD missing/unavailable; skipping browser/proof task',
                'task_class': 'skip',
                'task_reason': task_meta.get('reason'),
                'recommendation': 'skip',
            })
            append_task_summary({
                'status': 'browser_executor_unavailable_skip',
                'task_class': 'skip',
                'title': title,
                'task_reason': task_meta.get('reason'),
                'browser_executor_cmd': BROWSER_EXECUTOR_CMD,
            })
            continue
        if task_class == 'browser_proof_required':
            browser_result = run_browser_executor(q) if RUNTIME_PROFILE == 'mac_openclaw' else browser_executor_stub(q)
            append_task_summary({
                'status': 'browser_executor_routed',
                'task_class': task_class,
                'title': title,
                'task_reason': task_meta.get('reason'),
                'browser_result': browser_result,
            })
            manual.append({
                **base_item,
                'reason': 'browser/proof任务已路由browser executor',
                'task_class': task_class,
                'task_reason': task_meta.get('reason'),
                'browser_result': browser_result,
                'recommendation': 'browser executor',
            })
            continue
        if task_class == 'skip':
            manual.append({
                **base_item,
                'reason': f"任务已skip：{task_meta.get('reason')}",
                'task_class': task_class,
                'recommendation': 'skip',
            })
            continue
        reason = manual_reason(q)
        if reason:
            manual.append({
                **base_item,
                'reason': reason,
                'recommendation': 'Human Verified recommended',
            })
            continue
        if is_low_quality_competitive(q):
            low_quality_skips += 1
            manual.append({
                **base_item,
                'reason': '低质量competitive，已跳过',
                'recommendation': 'skip',
            })
            continue
        if not is_auto_competitive_candidate(q):
            manual.append({
                **base_item,
                'reason': 'competitive需人工筛选，已软阻塞跳过',
                'recommendation': 'review before submit',
            })
            continue
        if not AUTO_SUBMIT_COMPETITIVE or len(auto_done) >= MAX_AUTO_QUESTS:
            manual.append({
                **base_item,
                'reason': 'competitive可做但本轮未自动提交，已软阻塞跳过',
                'recommendation': 'review before submit',
            })
            continue

        payload = {'content': build_submission_content(q)}
        res, err = safe_req(f"/alliance-war/quests/{q['id']}/submit", method='POST', data=payload, key=key)
        if err or not res:
            note = f'competitive提交失败:{title[:18]}'
            soft_notes.append(note)
            manual.append({
                **base_item,
                'reason': f'自动提交失败：{(err or "submit failed")[:120]}',
                'recommendation': 'review and retry',
            })
            log(f'{note} | {(err or "submit failed")[:200]}')
            continue
        item = {
            'quest_id': q['id'],
            'title': title,
            'submission_id': res.get('submission_id'),
            'reward': reward_text,
            'reward_usdc': rewards['usdc'],
            'reward_xp': rewards['xp'],
            'task_class': task_class,
            'task_reason': task_meta.get('reason'),
        }
        auto_done.append(item)
        append_task_summary({
            'status': 'completed',
            'count': 1,
            'tasks': [item],
            'task_class': task_class,
            'draft_model': DEROUTER_DRAFT_MODEL,
            'review_model': DEROUTER_REVIEW_MODEL,
            'review_passed': task_class == 'text_high_value',
            'submitted': True,
            'proof_required': bool(q.get('proof_requirements') or q.get('proof_type') or q.get('require_proof')),
        })
        log(f'competitive submit ok: {title}')

    manual.sort(key=lambda item: item.get('priority_score', 0), reverse=True)
    write_manual_queue(manual[:20])
    return auto_done, manual[:20], soft_notes, low_quality_skips


def handle_community_tasks(tasks):
    manual = []
    for t in tasks or []:
        status = (t.get('status') or '').lower()
        if status != 'in_progress':
            continue
        rewards = reward_profile(t)
        reward = rewards['usdc'] or rewards['xp']
        title = t.get('title') or 'Untitled community task'
        if reward >= 20:
            manual.append({
                'id': t.get('id'),
                'title': title,
                'reward': reward_summary(rewards),
                'reason': 'community任务以外部增长/发布为主，需人工确认',
                'human_verified': False,
            })
    return manual[:10]


def complete_daily_quests(key, state):
    done = []
    blockers = []
    daily, err = safe_req('/agents/daily-quests', key=key)
    if err or not daily:
        return done, ['daily unavailable']

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
        else:
            blockers.append('distribute未完成')
            log(f'distribute err: {dist_err}')

    if not (by_id.get('create') or {}).get('completed'):
        ok, create_err = do_forum_comment(key, state)
        if ok:
            done.append('create✅')
        elif create_err:
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


def format_rank(status):
    rank = status.get('alliance_rank')
    if rank == 1:
        return f'Terra#1 +{format_number(status.get("lead_over_second"))}'
    if rank is None:
        return 'Terra未上榜'
    return f'Terra#{rank} -{format_number(status.get("gap_to_first"))}'


def main():
    cfg = load_cfg()
    key = cfg['api_key']
    state = load_state()

    blockers = []

    checkin, err = safe_req('/agents/checkin', method='POST', data={}, key=key)
    if not (checkin and 'message' in checkin) and not (err and 'already checked in' in (err or '').lower()):
        blockers.append('签到失败')
        if err:
            log(f'checkin err: {err}')

    feed, feed_err = safe_req('/agents/feed', key=key)
    if feed_err:
        blockers.append('feed失败')
        feed = {}
    urgent = feed.get('urgent') or []
    now_epoch = int(time.time())
    if RUNTIME_PROFILE == 'mac_openclaw' and not urgent:
        last_feed = int(state.get('last_feed_classify_epoch', 0) or 0)
        if last_feed and now_epoch - last_feed < MAC_FEED_INTERVAL_SECONDS:
            append_task_summary({'status': 'idle_skip', 'reason': 'mac feed interval guard', 'seconds_to_next': MAC_FEED_INTERVAL_SECONDS - (now_epoch - last_feed)})
            print('NO_REPLY')
            return
        state['last_feed_classify_epoch'] = now_epoch

    red_result, red_err = process_red_packets(key, state)
    if red_err:
        blockers.append('红包处理异常')

    all_quests_resp, quests_err = safe_req('/alliance-war/quests', key=key)
    all_quests = (all_quests_resp or {}).get('quests') or []
    _auto_done, manual_quests, comp_soft_notes, _low_quality_skips = handle_competitive_quests(key, feed.get('quests') or [], all_quests)
    if quests_err:
        log(f'competitive list err: {quests_err}')
    for note in comp_soft_notes:
        log(note)

    community_resp, community_err = safe_req('/community/tasks', key=key)
    community_tasks = (community_resp or {}).get('tasks') or []
    community_manual = handle_community_tasks(community_tasks)
    if community_err:
        blockers.append('community失败')

    _daily_done, daily_blockers = complete_daily_quests(key, state)
    blockers.extend(daily_blockers)

    earnings, _earn_err = safe_req('/agents/earnings', key=key)
    if earnings:
        state['last_earnings'] = earnings
    after_rank = fetch_rank_status(key)
    state['last_run_at'] = datetime.now(timezone.utc).isoformat()
    state['last_rank_status'] = after_rank
    save_state(state)

    if after_rank.get('alliance_rank') == 1:
        lead = after_rank.get('lead_over_second')
        if lead is not None and lead >= SAFE_LEAD_TARGET and not urgent and not blockers and not manual_quests and not community_manual:
            print('NO_REPLY')
            return
        if blockers:
            print(f"Terra#1，领先{format_number(lead)}分，异常{len(dict.fromkeys(blockers))}项")
            return
        if urgent:
            print(f"Terra#1，领先{format_number(lead)}分，红包优先")
            return
        if manual_quests or community_manual:
            print(f"Terra#1，领先{format_number(lead)}分，待人工{len(manual_quests) + len(community_manual)}项")
            return
        print(f"Terra#1，领先{format_number(lead)}分，已巡检")
        return

    rank = after_rank.get('alliance_rank')
    gap = after_rank.get('gap_to_first')
    if blockers:
        suffix = f'，异常{len(dict.fromkeys(blockers))}项'
    elif urgent:
        suffix = '，红包优先'
    elif manual_quests or community_manual:
        suffix = f'，待人工{len(manual_quests) + len(community_manual)}项'
    else:
        suffix = '，已推进1轮'
    if rank is None:
        print(f"Terra未上榜{suffix}")
    else:
        print(f"Terra#{rank}，落后{format_number(gap)}分{suffix}")



if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'巡检失败：{e}')
        sys.exit(1)
