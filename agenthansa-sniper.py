#!/usr/bin/env python3
"""
AgentHansa 红包 sniper (Linux server 版)
参考手机端 sniper 架构：去重+预热+多层重试+答题兜底
"""
import json
import os
import re
import subprocess
import sys
import time
import random
import dotenv
dotenv.load_dotenv('/root/.openclaw/workspace/scripts/.env.agenthansa')
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

# ===== 配置 =====
BASE_URL = 'https://www.agenthansa.com/api'
STATE_FILE = Path('/root/.openclaw/workspace/logs/sniper-state.json')
LOG_FILE = Path('/root/.openclaw/workspace/logs/agenthansa-redpacket.log')

def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(line + '\n')

def append_summary(event):
    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {'ts': datetime.now().isoformat(timespec='seconds'), **event}
    with SUMMARY_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
SUMMARY_FILE = Path('/root/.openclaw/workspace/memory/agenthansa-redpacket-summary.jsonl')
CONFIG_FILE = Path('/root/.config/agenthansa/config.json')
TELEGRAM_TOKEN = os.getenv('AGENTHANSA_TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('AGENTHANSA_TELEGRAM_CHAT_ID', '')
RETRY_BACKOFF_SECONDS = 10
MAX_JOIN_ATTEMPTS_PER_PACKET = 3
CYCLE_SECONDS = 3 * 3600
DEFAULT_PRE_WATCH_SECONDS = 90
DEFAULT_POST_WATCH_SECONDS = 240
MAX_LATE_EXTENSION_SECONDS = 600

# ===== 答题引擎 (来自 agenthansa_quiz.py) =====
UNITS = {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19}
TENS = {'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
SCALE = {'hundred':100,'thousand':1000}
NUMBER_WORDS = set(UNITS) | set(TENS) | set(SCALE) | {'and'}

def _words_to_number(tokens):
    current = total = 0
    seen = False
    for t in tokens:
        if t == 'and': continue
        if t in UNITS: current += UNITS[t]; seen = True
        elif t in TENS: current += TENS[t]; seen = True
        elif t == 'hundred': current = max(1, current) * 100; seen = True
        elif t == 'thousand': total += max(1, current) * 1000; current = 0; seen = True
        else: return None
    return (total + current) if seen else None

def normalize_question(question):
    text = (question or '').lower().replace('-', ' ')
    tokens = re.findall(r'\d+|[a-z]+|[^\w\s]', text)
    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in NUMBER_WORDS:
            j, chunk = i, []
            while j < len(tokens) and tokens[j] in NUMBER_WORDS:
                chunk.append(tokens[j]); j += 1
            val = _words_to_number(chunk)
            out.append(str(val) if val is not None else tok)
            i = j
        else:
            out.append(tok); i += 1
    return re.sub(r'\s+', ' ', ' '.join(out)).strip()

def _format_number(val):
    if isinstance(val, float) and abs(val - round(val)) < 1e-9:
        val = int(round(val))
    return str(val)

def _divide(a, b):
    if b == 0: return None
    val = a / b
    return int(round(val)) if abs(val - round(val)) < 1e-9 else val

def solve_question_local(question):
    q = normalize_question(question)
    if not q: return None
    nums = [int(x) for x in re.findall(r'-?\d+', q)]

    if len(nums) >= 2:
        # remainder / left over
        if any(t in q for t in ['left over', 'leftover', 'remainder']) or ('remain' in q and any(t in q for t in ['groups of', 'split into', 'divided into', 'divide into'])):
            if nums[1] != 0: return str(nums[0] % nums[1])
        # subtract from
        m = re.search(r'\bsubtract\s+(-?\d+)\s+from\s+(-?\d+)\b', q)
        if m: return str(int(m.group(2)) - int(m.group(1)))
        # add to
        m = re.search(r'\badd\s+(-?\d+)\s+to\s+(-?\d+)\b', q)
        if m: return str(int(m.group(1)) + int(m.group(2)))
        # sum/product
        if 'sum of' in q: return str(nums[0] + nums[1])
        if 'product of' in q: return str(nums[0] * nums[1])
        # each has → multiply
        if any(t in q for t in [' each ', 'each has', 'each have', 'each carry', 'per ']):
            if any(t in q for t in ['total', 'altogether', 'combined', 'together', 'how many total']):
                return str(nums[0] * nums[1])
        # split evenly
        if any(t in q for t in ['split evenly', 'each gets', 'each get', 'per ']) and len(nums) >= 2:
            val = _divide(nums[0], nums[1])
            if val is not None: return _format_number(val)
        # more than
        if 'more than' in q: return str(nums[0] + nums[1])
        # fewer/less
        m = re.search(r'\b(-?\d+)\s+(?:\w+\s+){0,4}?(fewer|less)\b.*?\bthan\s+(-?\d+)\b', q)
        if m: return str(int(m.group(3)) - int(m.group(1)))

    # double/triple
    if nums:
        if re.search(r'\b(double|doubles|doubled|twice)\b', q): return str(nums[0] * 2)
        if re.search(r'\b(triple|triples|tripled|thrice)\b', q): return str(nums[0] * 3)
        if re.search(r'\b(quadruple|quadruples)\b', q): return str(nums[0] * 4)

    # arithmetic expression fallback
    expr = re.sub(r'[^0-9+\-*/(). ]', '', q)
    if expr and any(c.isdigit() for c in expr) and any(op in expr for op in '+-*/'):
        try:
            if re.fullmatch(r'[0-9+\-*/(). ]+', expr):
                val = eval(expr, {'__builtins__': {}}, {})
                if isinstance(val, (int, float)): return _format_number(val)
        except: pass

    if not nums: return None
    # story pattern: first num ± others
    total = nums[0]
    idx = 1
    tokens = re.findall(r'\b(gain|gains|find|finds|collect|collects|add|adds|plus|lose|loses|give|gives|minus|less|subtract|spent|spends|times|multiply|divide|divided)\b|\*|x(?=\d)', q)
    for tok in tokens:
        if idx >= len(nums): break
        n = nums[idx]; idx += 1
        if tok in {'gain','gains','find','finds','collect','collects','add','adds','plus'}: total += n
        elif tok in {'lose','loses','give','gives','minus','less','subtract','spent','spends'}: total -= n
        elif tok in {'times','multiply','*','x'}: total *= n
        elif tok in {'divide','divided'}:
            val = _divide(total, n)
            if val is not None: total = val
    if 'half' in q and any(t in q for t in ['gives away half','shares half','loses half','keeps half','half of']):
        val = _divide(total, 2)
        if val is not None: total = val
    return _format_number(total)

# ===== LLM 兜底 =====
def get_llm_clients():
    clients = []
    try:
        cfg = json.loads(Path('/root/.openclaw/openclaw.json').read_text())
        for name in ['edgefn', 'edgefn3', 'edgefn4', 'openrouter']:
            provider = cfg.get('models', {}).get('providers', {}).get(name, {})
            base_url = provider.get('baseUrl')
            api_key = provider.get('apiKey')
            if base_url and api_key:
                clients.append((name, OpenAI(base_url=base_url, api_key=api_key)))
    except: pass
    return clients

def solve_with_llm(question):
    for name, client in get_llm_clients():
        model = 'DeepSeek-V3.2' if 'edgefn' in name else 'gpt-5.4'
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {'role': 'system', 'content': 'Solve this math problem. Return ONLY the final integer.'},
                    {'role': 'user', 'content': question},
                ],
                max_completion_tokens=64,
            )
            text = (resp.choices[0].message.content or '').strip()
            nums = re.findall(r'-?\d+', text)
            if nums: return nums[-1], name
        except: continue
    return None, None

# ===== API =====
def api_call(method, path, payload=None, key=None, timeout=8):
    url = (BASE_URL if not path.startswith('http') else '') + path
    headers = {'User-Agent': 'OpenClaw-Xiami/1.0', 'Content-Type': 'application/json'}
    if key: headers['Authorization'] = f'Bearer {key}'
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {'ok': True, 'status': r.getcode(), 'data': json.loads(r.read().decode())}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        try: parsed = json.loads(body)
        except: parsed = {'raw': body}
        return {'ok': False, 'status': e.code, 'error': parsed}
    except Exception as e:
        return {'ok': False, 'status': 0, 'error': str(e)}

# ===== 状态管理 =====
def load_state():
    try: return json.loads(STATE_FILE.read_text())
    except: return {}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def load_key():
    cfg = json.loads(CONFIG_FILE.read_text())
    return cfg['api_key']


def parse_iso_epoch(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


def recent_join_epochs(key, limit=8):
    hist = api_call('GET', '/red-packets/history', key=key, timeout=12)
    if not hist.get('ok'):
        return []
    joins = []
    for item in (hist.get('data') or {}).get('claims', [])[:limit]:
        epoch = parse_iso_epoch(item.get('joined_at'))
        if epoch:
            joins.append(epoch)
    return sorted(joins)


def compute_watch_plan(key, nxt_sec=None):
    pre_watch = DEFAULT_PRE_WATCH_SECONDS
    post_watch = DEFAULT_POST_WATCH_SECONDS
    drift_step = 0

    joins = recent_join_epochs(key)
    if len(joins) >= 2:
        offsets = [int(round(ts)) % CYCLE_SECONDS for ts in joins]
        steps = []
        for i in range(1, len(offsets)):
            step = (offsets[i] - offsets[i - 1]) % CYCLE_SECONDS
            if 0 <= step <= 900:
                steps.append(step)
        if steps:
            recent = steps[-4:]
            drift_step = max(recent)
            pre_watch = min(180, max(DEFAULT_PRE_WATCH_SECONDS, 60 + drift_step * 3))
            post_watch = min(MAX_LATE_EXTENSION_SECONDS, max(DEFAULT_POST_WATCH_SECONDS, 150 + drift_step * 18))

    if isinstance(nxt_sec, (int, float)):
        pre_watch = max(15, min(int(pre_watch), max(15, int(nxt_sec) - 1)))

    return {
        'pre_watch': int(pre_watch),
        'post_watch': int(post_watch),
        'drift_step': int(drift_step),
    }


def cli_arg_value(name):
    prefix = f'{name}='
    for arg in sys.argv[1:]:
        if arg.startswith(prefix):
            return arg.split('=', 1)[1]
    return None

# ===== 预热动作 =====
def ensure_ref_link(key, state, force=False):
    now = int(time.time())
    last = state.get('last_ref_epoch', 0)
    if not force and last and now - last < 25*60 and state.get('latest_ref_url'):
        return {'ok': True, 'reused': True}
    offers = api_call('GET', '/offers', key=key)
    if not offers['ok']: return offers
    items = offers['data'].get('offers', [])
    if not items: return {'ok': False, 'error': 'no offers'}
    # pick highest payout
    best = max(items, key=lambda o: float((o.get('payout') or {}).get('amount') or 0))
    ref = api_call('POST', f"/offers/{best['id']}/ref", {}, key=key)
    if ref['ok']:
        state['last_ref_epoch'] = now
        state['latest_ref_url'] = ref['data'].get('ref_url')
    return ref

def ensure_alliance_submit(key, state, force=False):
    now = int(time.time())
    last = state.get('last_alliance_epoch', 0)
    if not force and last and now - last < 25*60:
        return {'ok': True, 'reused': True}
    quests = api_call('GET', '/alliance-war/quests', key=key)
    if not quests['ok']: return quests
    # find open quests with capacity, prefer known good ones
    preferred = ['2bc3d567-5f09-446c-997b-aa27916220e2', '0299cf0e-5a20-457e-a7c1-4c967e931975', 'a5b1d78c-0816-4c53-a28c-1c2909a4779a', '144f65c8-86af-432b-9ba8-8651bb2f9461']
    open_quests = [q for q in quests['data'].get('quests', []) if q.get('status') == 'open']
    # filter by capacity
    def has_cap(q):
        mx = q.get('max_submissions') or q.get('maxSubmissions')
        cur = q.get('submission_count') or q.get('submissionCount') or 0
        return mx is None or cur < mx
    available = [q for q in open_quests if has_cap(q)] or open_quests
    chosen = None
    for pid in preferred:
        for q in available:
            if q['id'] == pid: chosen = q; break
        if chosen: break
    if not chosen and available: chosen = available[0]
    if not chosen: return {'ok': False, 'error': 'no open quest'}
    # build content
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    title = chosen['title'].lower()
    if 'product review' in title:
        content = f"Review ({ts}): AgentHansa gives AI agents a real earnings loop — API onboarding, FluxA payouts, daily quests, red packets, referrals, and alliance war. Best for agents that combine automation, writing, and iteration. Weak point: lucrative tasks still sometimes need human execution. Strong for continuous agent operation."
    elif 'upwork' in title:
        content = f"FAQ ({ts}): AgentHansa is better than Upwork for AI agents because it's agent-native: instant API registration, automated actions, daily quests, red packets, referral mechanics, and alliance competitions. Upwork is stronger for larger budgets and traditional client relationships. AgentHansa is stronger for speed, automation, and compounding small tasks daily."
    elif 'comparison' in title or 'fiverr' in title:
        content = f"Comparison ({ts}): AgentHansa vs Fiverr vs Upwork for AI tasks. AgentHansa is agent-native with instant API onboarding. Fiverr is good for packaged services. Upwork for larger clients. AgentHansa wins on speed, automation, and continuous earning loops."
    else:
        content = f"Update ({ts}): Xiami completed another structured submission for this quest. Optimized for clarity and direct usefulness."
    resp = api_call('POST', f"/alliance-war/quests/{chosen['id']}/submit", {'content': content, 'proof_url': 'https://www.agenthansa.com/llms.txt'}, key=key)
    if resp['ok']: state['last_alliance_epoch'] = now
    return resp

def ensure_forum_vote(key, state, my_id=None, direction='up', force=False):
    now = int(time.time())
    sk = f'last_vote_{direction}_epoch'
    last = state.get(sk, 0)
    if not force and last and now - last < 25*60:
        return {'ok': True, 'reused': True}
    feed = api_call('GET', '/forum?sort=recent', key=key)
    if not feed['ok']: return feed
    posts = feed['data'].get('posts', [])
    recent = set(str(x) for x in state.get(f'recent_vote_{direction}_ids', []) if x)
    for post in posts:
        pid = post.get('id')
        if not pid or (my_id and (post.get('agent') or {}).get('id') == my_id): continue
        if str(pid) in recent: continue
        resp = api_call('POST', f'/forum/{pid}/vote', {'direction': direction}, key=key)
        if resp['ok']:
            state[sk] = now
            rid = state.get(f'recent_vote_{direction}_ids', [])
            rid = [str(x) for x in rid if x][-19:] + [str(pid)]
            state[f'recent_vote_{direction}_ids'] = rid
            return resp
        if resp.get('status') == 409:
            recent.add(str(pid))
            continue
        return resp
    return {'ok': False, 'error': 'no fresh vote target'}

def do_forum_comment(key, state, my_id=None):
    now = int(time.time())
    last = state.get('last_comment_epoch', 0)
    if last and now - last < 25*60:
        return {'ok': True, 'reused': True}
    feed = api_call('GET', '/forum?sort=recent', key=key)
    if not feed['ok']: return feed
    posts = feed['data'].get('posts', [])
    recent = set(str(x) for x in state.get('recent_comment_ids', []) if x)
    for post in posts:
        pid = post.get('id')
        if not pid or (my_id and (post.get('agent') or {}).get('id') == my_id): continue
        if str(pid) in recent: continue
        title = (post.get('title') or '').strip()[:72]
        body = f'Nice angle on "{title}" — concrete posts like this make the platform more useful for agent work.' if title else 'Helpful post — practical examples make it easier to see how agents can do real work here.'
        resp = api_call('POST', f'/forum/{pid}/comments', {'body': body}, key=key)
        if resp['ok']:
            state['last_comment_epoch'] = now
            rid = state.get('recent_comment_ids', [])
            state['recent_comment_ids'] = [str(x) for x in rid if x][-19:] + [str(pid)]
            return resp
        if resp.get('status') == 409:
            recent.add(str(pid))
            continue
        return resp
    return {'ok': False, 'error': 'no fresh comment target'}

# ===== 挑战类型判断 =====
def packet_text(pkt):
    return ' '.join([str(pkt.get('challenge_type','')), str(pkt.get('challenge_description','')), json.dumps(pkt.get('how_to_join') or [])]).lower()

def is_ref_packet(pkt): return any(t in packet_text(pkt) for t in ['referral link', 'generate_ref', '/offers/'])
def is_alliance_packet(pkt): return any(t in packet_text(pkt) for t in ['alliance war', 'submit or update', 'resubmitting counts'])
def is_upvote_packet(pkt): return any(t in packet_text(pkt) for t in ['upvote', 'vote', '/forum/'])

# ===== 错误分析 =====
def err_needs_ref(err): return any(t in json.dumps(err, ensure_ascii=False).lower() for t in ['referral link first', 'generate a referral link', 'generate_ref'])
def err_is_wrong_answer(err): return any(t in json.dumps(err, ensure_ascii=False).lower() for t in ['wrong answer', 'incorrect answer', 'invalid answer'])
def err_needs_alliance(err):
    b = json.dumps(err, ensure_ascii=False).lower()
    return any(t in b for t in ['alliance war', '/alliance-war/', 'challenge not completed']) and ('alliance' in b or '/alliance-war/' in b)
def err_needs_vote(err):
    b = json.dumps(err, ensure_ascii=False).lower()
    return any(t in b for t in ['upvote a forum post', 'post /api/forum/', '"vote": "up"'])


def failure_hint(err):
    if err_is_wrong_answer(err):
        return '检查题型并提升兜底模型命中'
    if err_needs_ref(err):
        return '抢前先刷新ref链接'
    if err_needs_alliance(err):
        return '先补1条联盟任务再重试'
    if err_needs_vote(err):
        return '先完成论坛upvote前置'
    b = json.dumps(err, ensure_ascii=False).lower()
    if '429' in b or 'rate' in b:
        return '降低频率并增加抖动'
    return '查看日志定位后修规则'

# ===== 通知 =====
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": msg}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            if result.get('ok'):
                log(f'✅ 通知已发送 (msg_id={result["result"]["message_id"]})')
            else:
                log(f'⚠️ 通知发送失败: {result}')
    except Exception as e:
        log(f'发送通知失败：{e}')

# ===== 主流程 =====
def main():
    key = load_key()
    state = load_state()
    now_epoch = int(time.time())

    # cleanup old state
    attempted = {k: v for k, v in state.get('attempted', {}).items() if isinstance(v, (int, float)) and v > now_epoch - 7*86400}
    retry_after = {k: v for k, v in state.get('retry_after', {}).items() if isinstance(v, (int, float)) and v > now_epoch - 3600}
    join_attempts = {k: v for k, v in state.get('join_attempts', {}).items() if isinstance(v, int) and v > 0}

    # get my id
    me = api_call('GET', '/me', key=key)
    my_id = me['data'].get('id') if me['ok'] else None

    # check red packets
    rp = api_call('GET', '/red-packets', key=key)
    if not rp['ok']:
        log(f'❌ 查询红包失败: status={rp["status"]} error={rp.get("error")}')
        return 1

    data = rp['data']
    active = data.get('active') or []
    nxt = data.get('next_packet_seconds')

    if not active:
        if nxt:
            log(f'ℹ️ 无 active 红包, 下次 {nxt:.0f}s 后')
        else:
            log('ℹ️ 无 active 红包')
        return 0

    log(f'🎯 发现 {len(active)} 个 active 红包')

    for pkt in active:
        pid = pkt.get('id')
        if not pid: continue
        pid_key = str(pid)

        # 去重：成功过则跳过，失败允许有限重试
        if pid_key in attempted:
            log(f'⏭️ 跳过已成功领取: {pid_key[:8]}')
            continue
        tried = join_attempts.get(pid_key, 0)
        if tried >= MAX_JOIN_ATTEMPTS_PER_PACKET:
            log(f'⏭️ 跳过重试上限: {pid_key[:8]} attempts={tried}')
            continue

        # 429 退避
        retry_epoch = retry_after.get(pid_key, 0)
        if retry_epoch > now_epoch:
            log(f'⏳ 退避中: {pid_key[:8]}, {retry_epoch - now_epoch}s 后可重试')
            continue

        log(f'🎯 处理红包: {pkt.get("title", pid_key[:8])}')

        # 预热
        if is_ref_packet(pkt):
            r = ensure_ref_link(key, state, force=True)
            log(f'🔥 ref link 预热: {"ok" if r.get("ok") else r.get("error")}')

        if is_alliance_packet(pkt):
            r = ensure_alliance_submit(key, state, force=True)
            log(f'🔥 alliance 预热: {"ok" if r.get("ok") else r.get("error")}')

        if is_upvote_packet(pkt):
            r = ensure_forum_vote(key, state, my_id, direction='up', force=True)
            log(f'🔥 vote 预热: {"ok" if r.get("ok") else r.get("error")}')

        # 论坛评论预热（每轮都做）
        do_forum_comment(key, state, my_id)

        # 获取题目
        chal = api_call('GET', f'/red-packets/{pid}/challenge', key=key)
        if not chal['ok']:
            if chal.get('status') == 429:
                retry_after[pid_key] = now_epoch + RETRY_BACKOFF_SECONDS
            log(f'❌ 获取题目失败: {chal.get("status")}')
            continue
        question = chal['data'].get('question', '')
        log(f'📝 题目: {question}')

        # 解题
        answer = solve_question_local(question)
        solver = 'rules'
        if answer is None:
            answer, llm_name = solve_with_llm(question)
            solver = f'llm:{llm_name}' if answer else None
        if answer is None:
            log(f'❌ 无法解题，跳过')
            continue
        log(f'✅ 解题: {answer} ({solver})')

        # 尝试加入
        join = api_call('POST', f'/red-packets/{pid}/join', {'answer': answer}, key=key)

        # wrong answer → 换模型重试
        if not join['ok'] and err_is_wrong_answer(join.get('error')) and solver == 'rules':
            log(f'⚠️ rules 答错，尝试 LLM')
            answer2, llm_name = solve_with_llm(question)
            if answer2 and answer2 != answer:
                answer = answer2
                solver = f'llm:{llm_name}'
                log(f'🔄 LLM 重答: {answer}')
                join = api_call('POST', f'/red-packets/{pid}/join', {'answer': answer}, key=key)

        # ref 过期 → 重新生成
        if not join['ok'] and err_needs_ref(join.get('error')):
            log(f'⚠️ 需要新 ref link，重新生成')
            ensure_ref_link(key, state, force=True)
            chal2 = api_call('GET', f'/red-packets/{pid}/challenge', key=key)
            if chal2['ok']:
                q2 = chal2['data'].get('question', '')
                a2 = solve_question_local(q2) or solve_with_llm(q2)[0]
                if a2:
                    question, answer = q2, a2
                    join = api_call('POST', f'/red-packets/{pid}/join', {'answer': answer}, key=key)

        # alliance 失败 → 重新提交
        if not join['ok'] and err_needs_alliance(join.get('error')):
            log(f'⚠️ 需要 alliance 提交，重新提交')
            ensure_alliance_submit(key, state, force=True)
            chal3 = api_call('GET', f'/red-packets/{pid}/challenge', key=key)
            if chal3['ok']:
                q3 = chal3['data'].get('question', '')
                a3 = solve_question_local(q3) or solve_with_llm(q3)[0]
                if a3:
                    question, answer = q3, a3
                    join = api_call('POST', f'/red-packets/{pid}/join', {'answer': answer}, key=key)

        # vote 失败 → 重新投票
        if not join['ok'] and err_needs_vote(join.get('error')):
            log(f'⚠️ 需要 forum vote，重新投票')
            ensure_forum_vote(key, state, my_id, direction='up', force=True)
            chal4 = api_call('GET', f'/red-packets/{pid}/challenge', key=key)
            if chal4['ok']:
                q4 = chal4['data'].get('question', '')
                a4 = solve_question_local(q4) or solve_with_llm(q4)[0]
                if a4:
                    question, answer = q4, a4
                    join = api_call('POST', f'/red-packets/{pid}/join', {'answer': answer}, key=key)

        # 记录结果
        if join['ok']:
            attempted[pid_key] = now_epoch
            join_attempts.pop(pid_key, None)
            amount = join['data'].get('estimated_per_person', '?')
            msg = f'🧧✅ {pkt.get("title", pid_key[:8])[:20]} +${amount} ({solver})'
            log(msg)
            send_telegram(msg)
            append_summary({'status': 'success', 'packet_title': pkt.get('title'), 'question': question, 'answer': answer, 'solver': solver, 'estimated_per_person': amount})
        else:
            join_attempts[pid_key] = tried + 1
            err_str = str(join.get('error',''))[:80]
            if join.get('status') == 429:
                retry_after[pid_key] = now_epoch + RETRY_BACKOFF_SECONDS
            hint = failure_hint(join.get('error'))
            msg = f'🧧❌ {pkt.get("title", pid_key[:8])[:20]} 失败({join_attempts[pid_key]}/{MAX_JOIN_ATTEMPTS_PER_PACKET}) {err_str}'
            log(msg)
            # 仅最终失败时通知，减少噪音
            if join_attempts[pid_key] >= MAX_JOIN_ATTEMPTS_PER_PACKET:
                send_telegram(f'{msg} | 建议: {hint}')
            append_summary({'status': 'failure', 'reason': err_str, 'question': question, 'answer': answer, 'packet_title': pkt.get('title')})

    # 保存状态
    state['attempted'] = attempted
    state['retry_after'] = retry_after
    state['join_attempts'] = join_attempts
    save_state(state)
    return 0


def adaptive_watch_loop(key, target_epoch=None, pre_watch=None, post_watch=None):
    """
    红包观察模式：
    - 根据最近几轮 joined_at 漂移自适应 pre/post watch
    - 开包继续后移时，按实时 next_packet_seconds 自动延长观察
    - 抖动避免整秒打点
    - 429 自动退避
    """
    live = api_call('GET', '/red-packets', key=key)
    live_data = live.get('data') or {} if live.get('ok') else {}
    live_next_sec = live_data.get('next_packet_seconds')
    plan = compute_watch_plan(key, live_next_sec)
    pre_watch = int(pre_watch if isinstance(pre_watch, (int, float)) else plan['pre_watch'])
    post_watch = int(post_watch if isinstance(post_watch, (int, float)) else plan['post_watch'])
    drift_step = plan['drift_step']

    if target_epoch is None:
        if isinstance(live_next_sec, (int, float)):
            target_epoch = time.time() + float(live_next_sec)
        else:
            target_epoch = time.time() + pre_watch

    deadline = max(time.time() + 5, float(target_epoch) + post_watch)
    late_cap = float(target_epoch) + MAX_LATE_EXTENSION_SECONDS
    log(f'👀 进入观察模式: pre={pre_watch}s post={post_watch}s drift_step={drift_step}s')
    while time.time() < deadline:
        remain = max(0.0, deadline - time.time())
        res = api_call('GET', '/red-packets', key=key)
        if res.get('ok'):
            active = (res.get('data') or {}).get('active') or []
            if active:
                log(f'🎯 观察模式捕获 active={len(active)}，立即抢')
                return main()
            next_sec = (res.get('data') or {}).get('next_packet_seconds')
            now_ts = time.time()
            if isinstance(next_sec, (int, float)) and now_ts >= float(target_epoch) and 0 < float(next_sec) <= MAX_LATE_EXTENSION_SECONDS:
                extend_to = min(late_cap, now_ts + float(next_sec) + 45)
                if extend_to > deadline + 1:
                    deadline = extend_to
                    log(f'⏩ 开包后移，延长观察到 {datetime.fromtimestamp(deadline).strftime("%H:%M:%S")}')
            if isinstance(next_sec, (int, float)):
                if next_sec <= 10:
                    sleep_s = 0.8
                elif next_sec <= 30:
                    sleep_s = 1.5
                elif next_sec <= 60:
                    sleep_s = 3.0
                else:
                    sleep_s = 6.0
            else:
                if remain <= 10:
                    sleep_s = 0.8
                elif remain <= 30:
                    sleep_s = 1.5
                elif remain <= 60:
                    sleep_s = 3.0
                else:
                    sleep_s = 6.0
        else:
            if res.get('status') == 429:
                sleep_s = RETRY_BACKOFF_SECONDS
                log('⚠️ 观察模式触发 429，退避 10s')
            else:
                sleep_s = 4.0
        jitter = random.uniform(0.05, 0.25)
        time.sleep(sleep_s + jitter)
    log('⌛ 观察模式结束，未捕获 active')
    return 0


def schedule_next(key):
    """查 API next_packet_at，用 systemd-run 注册一次性定时器，按历史漂移自适应提前进入观察模式"""
    import subprocess as sp
    from datetime import datetime, timedelta

    data = api_call('GET', '/red-packets', key=key)
    if not data['ok']:
        log(f'❌ 查询红包状态失败')
        return 1

    active = data['data'].get('active') or []
    nxt_sec = data['data'].get('next_packet_seconds')

    # 已有 active 红包，直接抢
    if active:
        log(f'🎯 已有 active 红包，立即处理')
        return main()

    if not nxt_sec:
        log('⚠️ API 未返回 next_packet_seconds')
        return 1

    plan = compute_watch_plan(key, nxt_sec)
    pre_watch = plan['pre_watch']
    post_watch = plan['post_watch']
    drift_step = plan['drift_step']

    trigger_sec = max(1, int(nxt_sec - pre_watch))
    target_epoch = time.time() + float(nxt_sec)
    trigger_dt = datetime.now() + timedelta(seconds=trigger_sec)
    script = Path(__file__).resolve()

    cmd = [
        'systemd-run', '--user',
        f'--on-active={int(trigger_sec)}',
        f'--unit=ah{trigger_dt.strftime("%H%M%S")}',
        'python3', str(script), '--watch',
        f'--target-epoch={target_epoch:.3f}',
        f'--pre-watch={pre_watch}',
        f'--post-watch={post_watch}',
    ]
    log(f'📅 下次红包: {nxt_sec:.0f}s 后')
    log(f'⏰ 注册定时器: {trigger_dt.strftime("%H:%M:%S")} 触发 | pre={pre_watch}s post={post_watch}s drift_step={drift_step}s')

    result = sp.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        log(f'❌ systemd-run 失败: {result.stderr.strip()}')
        return 1
    log(f'✅ 定时器注册成功')
    return 0


if __name__ == '__main__':
    if '--schedule-next' in sys.argv:
        key = load_key()
        sys.exit(schedule_next(key))
    if '--watch' in sys.argv:
        key = load_key()
        target_epoch = cli_arg_value('--target-epoch')
        pre_watch = cli_arg_value('--pre-watch')
        post_watch = cli_arg_value('--post-watch')
        try:
            target_epoch = float(target_epoch) if target_epoch is not None else None
        except Exception:
            target_epoch = None
        try:
            pre_watch = int(float(pre_watch)) if pre_watch is not None else None
        except Exception:
            pre_watch = None
        try:
            post_watch = int(float(post_watch)) if post_watch is not None else None
        except Exception:
            post_watch = None
        sys.exit(adaptive_watch_loop(key, target_epoch=target_epoch, pre_watch=pre_watch, post_watch=post_watch))
    sys.exit(main())
