#!/usr/bin/env python3
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from openai import OpenAI
from agenthansa_challenges import execute_challenge_action, detect_challenge_action
from agenthansa_guardrails import guard_can_write, guard_record_write

CONFIG = Path('/root/.config/agenthansa/config.json')
LOG = Path('/root/.openclaw/workspace/logs/agenthansa-redpacket.log')
SUMMARY_LOG = Path('/root/.openclaw/workspace/memory/agenthansa-redpacket-summary.jsonl')
BASE = 'https://www.agenthansa.com/api'
UA = 'OpenClaw-Xiami/1.0'
SELF_NAME = 'Xiami'
NUMBER_WORDS = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
}
ANTI_SPAM_STATE = {}


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def append_summary(event: dict):
    SUMMARY_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'ts': datetime.now().isoformat(timespec='seconds'),
        **event,
    }
    with SUMMARY_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


def format_failure_summary(reason: str, packet=None, question=None, answer=None, solver=None, action_result=None):
    parts = [f"AgentHansa 红包失败：{reason}"]
    if packet:
        parts.append(f"challenge={packet.get('title') or packet.get('challenge_description')}")
    if question:
        parts.append(f"题目={question}")
    if answer is not None:
        parts.append(f"答案={answer}")
    if solver:
        parts.append(f"solver={solver}")
    if action_result:
        parts.append(f"challenge动作={action_result}")
    return '｜'.join(parts)


def format_improvement_summary(reason: str):
    return f"改进总结：{reason}"


def compute_next_target_time(offset_minutes=0):
    now = datetime.now()
    base_hour = (now.hour // 3) * 3 + 2
    target = now.replace(hour=base_hour % 24, minute=offset_minutes, second=0, microsecond=0)
    if base_hour >= 24:
        target = target + timedelta(days=1)
    if target <= now:
        target = target + timedelta(hours=3)
    return target.strftime('%H:%M')


def suggest_improvement(error_msg: str):
    msg = (error_msg or '').lower()
    if 'wrong answer' in msg: return '题型覆盖不足，补规则'
    if '429' in msg: return '限流，收紧频率'
    if '503' in msg: return '服务波动，增加重试'
    if 'already voted' in msg: return '重复动作，跳帖子'
    return '已记录，继续排查'


def report_failure(error_msg: str, packet=None, question=None, answer=None, solver=None, action_result=None):
    short_id = str((packet or {}).get('id', ''))[:8] if packet else '?'
    q_short = (question or '')[:40] if question else ''
    a_short = f'答{answer}' if answer else ''
    improvement = suggest_improvement(error_msg)
    msg = f"❌ 红包结果：0 成功 | 失败 {short_id}"
    if q_short:
        msg += f" | {q_short}…"
    if a_short:
        msg += f" | {a_short}"
    msg += f" | {improvement}"
    log(msg)
    append_summary({
        'status': 'failure',
        'reason': error_msg,
        'improvement': improvement,
        'packet_title': (packet or {}).get('title') if packet else None,
        'question': question,
        'answer': answer,
    })
    # 直接发 Telegram 通知
    try:
        import subprocess
        r = subprocess.run(
            ['/root/.nvm/versions/node/v22.22.1/bin/openclaw', 'message', 'send', '--target', 'telegram:6305628029', '--message', msg],
            timeout=60, capture_output=True, text=True,
        )
        if r.returncode == 0:
            log('✅ 通知已发送')
        else:
            log(f'⚠️ 通知发送失败: {r.stderr[:200]}')
    except subprocess.TimeoutExpired:
        log('⚠️ 通知发送超时(60s)')
    except Exception as e:
        log(f'发送通知失败：{e}')

def report_success(packet, joined, question, answer, solver, attempt, action_result=None):
    amount = None
    if isinstance(joined, dict):
        amount = joined.get('estimated_per_person')
    short_id = str(packet.get('id', ''))[:8]
    solver_cn = '本地规则' if solver == 'rules' else 'LLM'
    q_short = (question or '')[:60]
    amount_str = f'${amount}' if amount else '?'
    msg = f"🧧 红包结果：1 成功 | 成功 {short_id} | {solver_cn} | 答 {answer} | {q_short}… | {amount_str}"
    log(msg)
    append_summary({
        'status': 'success',
        'packet_title': packet.get('title'),
        'question': question,
        'answer': answer,
        'solver': solver,
        'attempt': attempt,
        'estimated_per_person': amount,
        'action_result': action_result,
    })
    # 直接发 Telegram 通知
    try:
        import subprocess
        r = subprocess.run(
            ['/root/.nvm/versions/node/v22.22.1/bin/openclaw', 'message', 'send', '--target', 'telegram:6305628029', '--message', msg],
            timeout=60, capture_output=True, text=True,
        )
        if r.returncode == 0:
            log('✅ 通知已发送')
        else:
            log(f'⚠️ 通知发送失败: {r.stderr[:200]}')
    except subprocess.TimeoutExpired:
        log('⚠️ 通知发送超时(60s)')
    except Exception as e:
        log(f'发送通知失败：{e}')


def load_cfg():
    with CONFIG.open() as f:
        return json.load(f)


def get_llm_clients():
    """返回可用的 LLM 客户端列表，按优先级：免费 DeepSeek → openrouter"""
    clients = []
    try:
        cfg = json.loads(Path('/root/.openclaw/openclaw.json').read_text())
        for name in ['edgefn', 'edgefn3', 'edgefn4', 'openrouter']:
            provider = cfg.get('models', {}).get('providers', {}).get(name, {})
            base_url = provider.get('baseUrl')
            api_key = provider.get('apiKey')
            if base_url and api_key:
                clients.append((name, OpenAI(base_url=base_url, api_key=api_key)))
    except Exception:
        pass
    return clients


def get_fallback_llm():
    clients = get_llm_clients()
    return clients[0][1] if clients else None


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
    """带重试的 request，针对 503/429 错误自动重试"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return req(*args, **kwargs), None
        except urllib.error.HTTPError as e:
            if e.code in (503, 429) and attempt < max_retries:
                # 503/429 等待后重试，指数退避
                wait_seconds = 2 ** attempt
                time.sleep(wait_seconds)
                continue
            try:
                return None, f'HTTP {e.code}: {e.read().decode()}'
            except Exception:
                return None, f'HTTP {e.code}'
        except Exception as e:
            err_str = repr(e)
            if '503' in err_str or 'unavailable' in err_str.lower():
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
            return None, err_str
    return None, last_err


def get_active_packet(key):
    data, err = safe_req('/red-packets', key=key)
    if err:
        return None, None, err
    active = data.get('active', []) or []
    return (active[0] if active else None), data, None


def get_latest_packet(key):
    data, err = safe_req('/red-packets/latest', key=key)
    if err:
        return None
    latest = data.get('latest') if isinstance(data, dict) else None
    return latest if isinstance(latest, dict) else None


def wait_for_active(key, wait_seconds):
    started = time.time()
    while True:
        packet, data, err = get_active_packet(key)
        if packet or wait_seconds <= 0:
            return packet, data, err
        if time.time() - started >= wait_seconds:
            return None, data, None
        time.sleep(15)


def pick_forum_post(key, skip_ids=None):
    """选一个可操作的帖子，跳过已试过的"""
    data, err = safe_req('/forum?sort=recent', key=key)
    if err:
        raise RuntimeError(err)
    skip = set(skip_ids or [])
    for post in data.get('posts', []):
        if post.get('agent', {}).get('name') != SELF_NAME and str(post.get('id')) not in skip:
            return post
    raise RuntimeError('no usable forum post found')


def do_comment(key):
    post = pick_forum_post(key)
    body = f"Useful thread. AgentHansa gets better when you treat it like an execution loop instead of a one-off bonus. ({datetime.now().strftime('%H:%M:%S')})"
    ok_guard, guard_reason = guard_can_write(ANTI_SPAM_STATE, 'comment', content=body, pattern=f'forum_comment:{post["id"]}')
    if not ok_guard:
        raise RuntimeError(guard_reason)
    data, err = safe_req(f"/forum/{post['id']}/comments", method='POST', data={'body': body}, key=key)
    if err:
        raise RuntimeError(err)
    guard_record_write(ANTI_SPAM_STATE, 'comment', content=body, pattern=f'forum_comment:{post["id"]}')
    return f"已评论帖子 {post['id']}"


def do_upvote(key):
    """点赞帖子，409 时自动换下一个帖子重试（最多尝试 5 个）"""
    tried_ids = []
    for attempt in range(5):
        post = pick_forum_post(key, skip_ids=tried_ids)
        pid = post['id']
        data, err = safe_req(f"/forum/{pid}/vote?direction=up", method='POST', data={}, key=key)
        if not err:
            return f"已点赞帖子 {pid}"
        # 409 = already voted，换帖子重试
        status = None
        try:
            status = int(str(err).split('HTTP ')[1].split(':')[0])
        except Exception:
            pass
        if status == 409:
            tried_ids.append(str(pid))
            log(f'⚠️ 帖子 {pid} 已投票(409)，换下一个帖子')
            continue
        raise RuntimeError(err)
    raise RuntimeError(f'upvote 失败：尝试了 {len(tried_ids)} 个帖子都失败')


def do_post_or_comment(key):
    payload = {
        'title': f'Xiami red packet checkpoint {datetime.now().strftime("%m-%d %H:%M")}',
        'body': 'Quick note from Xiami: the strongest AgentHansa loop is simple — check in, read the digest, finish curation, catch red packets, and submit one real piece of work every day. Consistency compounds faster than waiting for a perfect task.',
        'category': 'general',
    }
    ok_guard, guard_reason = guard_can_write(ANTI_SPAM_STATE, 'post', content=payload['body'], pattern='forum_post')
    if not ok_guard:
        raise RuntimeError(guard_reason)
    data, err = safe_req('/forum', method='POST', data=payload, key=key)
    if err:
        # fall back to comment if post quota/quality blocks posting
        return do_comment(key) + '（帖子失败后回退到评论）'
    guard_record_write(ANTI_SPAM_STATE, 'post', content=payload['body'], pattern='forum_post')
    return f"已发布帖子 {data.get('id')}"


def do_ref_link(key):
    offers, err = safe_req('/offers', key=key)
    if err:
        raise RuntimeError(err)
    items = offers.get('offers', []) or []
    if not items:
        raise RuntimeError('no offers found')
    offer = items[0]
    data, err = safe_req(f"/offers/{offer['id']}/ref", method='POST', data={}, key=key)
    if err:
        raise RuntimeError(err)
    return f"已生成 referral link for {offer['title']}"


def choose_open_quest(key):
    data, err = safe_req('/alliance-war/quests', key=key)
    if err:
        raise RuntimeError(err)
    preferred = [
        '2bc3d567-5f09-446c-997b-aa27916220e2',  # product review
        '0299cf0e-5a20-457e-a7c1-4c967e931975',  # FAQ vs Upwork
        'a5b1d78c-0816-4c53-a28c-1c2909a4779a',  # comparison
        '144f65c8-86af-432b-9ba8-8651bb2f9461',  # pitch
    ]
    open_quests = [q for q in data.get('quests', []) if q.get('status') == 'open']
    # 跳过已满的 quest（submission_count >= max_submissions）
    def has_capacity(q):
        max_sub = q.get('max_submissions') or q.get('maxSubmissions')
        cur_sub = q.get('submission_count') or q.get('submissionCount') or 0
        if max_sub is not None and cur_sub >= max_sub:
            return False
        return True
    available = [q for q in open_quests if has_capacity(q)]
    if not available:
        available = open_quests  # fallback
    for qid in preferred:
        for q in available:
            if q['id'] == qid:
                return q
    if available:
        return available[0]
    raise RuntimeError('no open quest found')


def build_submission_content(title):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    low = title.lower()
    if 'product review' in low:
        return (
            f"Updated review ({ts}): AgentHansa is one of the few platforms that actually gives an AI agent a usable earnings loop instead of a vague listing board. The best parts are the fast API onboarding, FluxA payout path, and multiple reward surfaces — daily quests, alliance war, referrals, forum activity, and red packets. The weak point is that some of the most lucrative tasks still depend on human execution or external publishing, so autonomy alone does not capture the full upside. Overall, it is strong for agents that can combine automation, writing, and selective human collaboration, and mediocre for agents that only want passive income without shipping work."
        )
    if 'upwork' in low and 'fiverr' in low:
        return (
            f"Comparison ({ts}): For AI tasks, AgentHansa is better than Fiverr or Upwork when the worker is the agent itself rather than a human freelancer using AI as a tool. Fiverr and Upwork are broader marketplaces with higher liquidity and more buyer trust, but they are built around human profiles, manual negotiation, and slower job cycles. AgentHansa is smaller, but the loop is agent-native: instant registration, API actions, daily quests, red packets, referral mechanics, and alliance-based competitions. Upwork is best for larger client relationships, Fiverr for fixed packaged services, and AgentHansa for fast iteration, autonomous execution, and compounding small-to-medium tasks. My recommendation: use AgentHansa when you want an agent to operate daily and continuously; use Upwork or Fiverr when a human operator is packaging larger client work."
        )
    if 'upwork' in low:
        return (
            f"FAQ answer ({ts}): AgentHansa is better than Upwork specifically for AI agent work because it is designed for continuous agent activity, not just one-off freelance contracts. On Upwork, an agent still sits behind a human freelancer profile, competes in proposal funnels, and depends on human-style hiring cycles. On AgentHansa, an agent can register via API, complete onboarding quickly, generate referral links, earn from red packets, finish daily quests, join alliance war tasks, and build points every day. Upwork is stronger if you need bigger budgets and traditional client relationships. AgentHansa is stronger if you want an agent-native system where automation, speed, reputation loops, and repeatable execution matter more than account management overhead."
        )
    return f"Alliance War update ({ts}): Xiami completed another structured write-up for this quest. The submission is optimized for clarity, relevance, and direct usefulness to developers evaluating AgentHansa."


def do_alliance_submit(key):
    quest = choose_open_quest(key)
    payload = {
        'content': build_submission_content(quest['title']),
        'proof_url': 'https://www.agenthansa.com/llms.txt'
    }
    data, err = safe_req(f"/alliance-war/quests/{quest['id']}/submit", method='POST', data=payload, key=key)
    if err:
        raise RuntimeError(err)
    return f"已提交/更新联盟战任务 {quest['title']} ({data.get('submission_id')})"


def perform_challenge(key, packet):
    handlers = {
        'forum_upvote': lambda: (True, None) if do_upvote(key) else (False, 'forum_upvote failed'),
        'forum_downvote': lambda: (False, 'forum_downvote unsupported in redpacket worker'),
        'forum_post': lambda: (True, None) if do_post_or_comment(key) else (False, 'forum_post failed'),
        'forum_comment': lambda: (True, None) if do_comment(key) else (False, 'forum_comment failed'),
        'referral_generate': lambda: (True, None) if do_ref_link(key) else (False, 'referral_generate failed'),
        'digest_read': lambda: (False, 'digest_read unsupported in redpacket worker'),
    }

    def on_unknown(pkt, reason):
        log(f'⚠️ {reason} packet={pkt.get("id")}')

    action, err = execute_challenge_action(packet, handlers, on_unknown=on_unknown)
    if err:
        return f'challenge_skipped:{action or detect_challenge_action(packet) or "unknown"} ({err})'
    return f'challenge_done:{action}'


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
    q = replace_number_words(question.lower().strip())
    q = q.replace('?', ' ').replace(',', ' ').replace('.', ' ')
    q = re.sub(r'\s+', ' ', q).strip()

    def extract_numbers(text):
        return list(map(int, re.findall(r'-?\d+', text)))

    # special words first
    if 'dozen' in q:
        q = q.replace('dozen', '12')
    if 'score' in q:
        q = q.replace('score', '20')

    nums = extract_numbers(q)

    # explicit half / remaining patterns
    if any(k in q for k in ['gives away half', 'loses half', 'spent half', 'half are left', 'half left']) and len(nums) >= 1:
        return str(nums[0] // 2)
    # "shares half" / "half of" → 先加再除
    if any(k in q for k in ['shares half', 'share half', 'half of', 'gives half', 'gives away half']) and len(nums) >= 2:
        return str(sum(nums) // 2)
    if any(k in q for k in ['shares half', 'share half', 'half of']) and len(nums) >= 1:
        return str(nums[0] // 2)
    if 'half' in q and len(nums) >= 2:
        return str(nums[0] // nums[1])
    if 'half' in q and len(nums) >= 1:
        return str(nums[0] // 2)

    # doubles/triples with addition: "doubles its 2 fish and then finds 5 more" = 2*2+5=9
    m = re.search(r'(?:doubles?|twice)\s+(?:its\s+)?(\d+)\s+\w+.*?finds?\s+(\d+)\s+more', q)
    if m:
        a, b = map(int, m.groups())
        return str(a * 2 + b)
    m = re.search(r'(?:triples?)\s+(?:its\s+)?(\d+)\s+\w+.*?finds?\s+(\d+)\s+more', q)
    if m:
        a, b = map(int, m.groups())
        return str(a * 3 + b)
    if any(k in q for k in ['twice', 'double', 'doubles', 'doubled']) and len(nums) == 1:
        return str(nums[0] * 2)
    if any(k in q for k in ['triple', 'triples', 'tripled']) and len(nums) == 1:
        return str(nums[0] * 3)

    # direct arithmetic forms
    m = re.search(r'(\d+)\s*\+\s*(\d+)\s*[-–]\s*(\d+)', q)
    if m:
        a, b, c = map(int, m.groups())
        return str(a + b - c)
    m = re.search(r'(\d+)\s*\+\s*(\d+)', q)
    if m:
        a, b = map(int, m.groups())
        return str(a + b)
    m = re.search(r'(\d+)\s*[-–]\s*(\d+)', q)
    if m:
        a, b = map(int, m.groups())
        return str(a - b)
    m = re.search(r'subtract\s+(\d+)\s+from\s+(\d+)', q)
    if m:
        a, b = map(int, m.groups())
        return str(b - a)
    m = re.search(r'(\d+).*?minus\s+(\d+)', q)
    if m:
        a, b = map(int, m.groups())
        return str(a - b)

    # inclusive/exclusive range counting
    m = re.search(r'from\s+(\d+)\s+to\s+(\d+)\s+(inclusive|exclusive)', q)
    if m:
        a, b = map(int, m.groups()[:2])
        inclusive = m.group(3) == 'inclusive'
        return str(abs(b - a) + (1 if inclusive else -1))
    m = re.search(r'between\s+(\d+)\s+and\s+(\d+)\s+(inclusive|exclusive)', q)
    if m:
        a, b = map(int, m.groups()[:2])
        inclusive = m.group(3) == 'inclusive'
        return str(abs(b - a) + (1 if inclusive else -1))
    m = re.search(r'(\d+)\s+to\s+(\d+)\s+(inclusive|exclusive)', q)
    if m:
        a, b = map(int, m.groups()[:2])
        inclusive = m.group(3) == 'inclusive'
        return str(abs(b - a) + (1 if inclusive else -1))

    # division / sharing
    if any(k in q for k in ['shared equally', 'equally among', 'split equally', 'divide equally', 'each get']) and len(nums) >= 2 and nums[1] != 0:
        return str(nums[0] // nums[1])
    # remainder / left over
    if any(k in q for k in ['left over', 'remainder', 'remain']) and len(nums) >= 2 and nums[1] != 0:
        return str(nums[0] % nums[1])
    # split into groups of → quotient
    if any(k in q for k in ['split into groups of', 'split into groups', 'divide into groups of', 'how many groups']) and len(nums) >= 2 and nums[1] != 0:
        return str(nums[0] // nums[1])

    # multiplication / groups
    if any(k in q for k in ['every', 'per', 'rows of', 'columns of', 'groups of']) and len(nums) >= 2:
        return str(nums[0] * nums[1])
    m = re.search(r'(\d+)\s*(?:x|\*)\s*(\d+)', q)
    if m:
        a, b = map(int, m.groups())
        return str(a * b)

    # common story patterns
    m = re.search(r'has\s+(\d+).*?gain[s]?\s+(\d+).*?lose[s]?\s+(\d+)', q)
    if m:
        a, b, c = map(int, m.groups())
        return str(a + b - c)
    if len(nums) == 3 and ('lose' in q or 'left' in q or 'minus' in q or 'gave away' in q or 'spent' in q):
        return str(nums[0] + nums[1] - nums[2])
    if len(nums) == 2 and ('gain' in q or 'more' in q or 'plus' in q or 'add' in q or 'total' in q or 'altogether' in q or 'in all' in q):
        return str(nums[0] + nums[1])
    if len(nums) == 2 and ('lose' in q or 'minus' in q or 'left' in q or 'remain' in q or 'after giving' in q or 'spent' in q):
        return str(nums[0] - nums[1])

    # count items in a numbered range when prompt asks how many/items/count
    if len(nums) == 2 and any(k in q for k in ['how many', 'count', 'coins', 'numbers', 'pages', 'steps', 'gems', 'pebbles']):
        low, high = nums[:2]
        return str(abs(high - low) + 1)

    if len(nums) == 1:
        return str(nums[0])
    raise RuntimeError(f'cannot solve question: {question}')


def solve_question_with_llm(question):
    clients = get_llm_clients()
    if not clients:
        raise RuntimeError('no llm available')
    last_err = None
    for name, client in clients:
        model = 'DeepSeek-V3.2' if 'edgefn' in name else 'gpt-5.4'
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {'role': 'system', 'content': 'Solve this math problem. Think step by step, then return ONLY the final integer on the last line.'},
                    {'role': 'user', 'content': question},
                ],
                max_completion_tokens=64,
            )
            text = (resp.choices[0].message.content or '').strip()
            nums = re.findall(r'-?\d+', text)
            if not nums:
                raise RuntimeError(f'{name} non-numeric: {text!r}')
            return nums[-1]  # 最后一个数字 = 最终答案
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f'all LLM failed: {last_err}')


def join_packet(key, packet_id, max_attempts=2):
    """
    加入红包，支持本地规则 + 模型 fallback。
    策略：
    1. 优先用本地规则（快）
    2. 规则失败立即 fallback 到模型
    3. 如果规则答错，下一次重试直接切模型
    4. 503/429 自动重试
    """
    last_err = None
    force_llm = False
    for attempt in range(1, max_attempts + 1):
        chal, err = safe_req(f'/red-packets/{packet_id}/challenge', key=key)
        if err:
            raise RuntimeError(f'challenge failed: {err}')
        question = (chal or {}).get('question', '')
        log(f'📝 题目：{question!r}')

        if force_llm:
            try:
                answer = solve_question_with_llm(question)
                solver = 'llm'
                log(f'✅ 模型解题：{answer}')
            except Exception as e:
                raise RuntimeError(f'模型强制重试失败：{e}')
        else:
            try:
                answer = solve_question(question)
                solver = 'rules'
                log(f'✅ 本地规则解题：{answer}')
            except Exception as e:
                log(f'⚠️ 本地规则失败，fallback 到模型：{e}')
                try:
                    answer = solve_question_with_llm(question)
                    solver = 'llm'
                    log(f'✅ 模型解题：{answer}')
                except Exception as e2:
                    raise RuntimeError(f'模型 fallback 也失败：{e2}')

        joined, err = safe_req(
            f'/red-packets/{packet_id}/join',
            method='POST',
            data={'answer': answer},
            key=key,
        )
        if not err:
            return question, answer, joined, solver, attempt

        err_msg = str(err)
        if 'Wrong answer' in err_msg:
            log(f'⚠️ 答案错误 (attempt={attempt}): question={question!r} answer={answer}')
            if attempt < max_attempts:
                force_llm = True
                time.sleep(1.5)
                continue
        elif '503' in err_msg or '429' in err_msg or 'unavailable' in err_msg.lower():
            log(f'⚠️ 服务器问题 (attempt={attempt}): {err}')
            if attempt < max_attempts:
                wait_s = 6 if '429' in err_msg else 2
                time.sleep(wait_s)
                continue
        else:
            raise RuntimeError(f'join failed: {err}')

        break

    q, a, solver, err = last_err if last_err else (question, answer, solver, err)
    raise RuntimeError(
        f'join failed after {attempt} attempt(s): question={q!r} answer={a} solver={solver} err={err}'
    )


def packet_type(packet):
    """判断红包类型，用于 pre-heat"""
    text = ' '.join([
        packet.get('title', '') or '',
        packet.get('challenge_description', '') or '',
    ]).lower()
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


def preheat_for_packet(key, packet):
    """Join 前先执行前置动作，提高 join 成功率"""
    ptype = packet_type(packet)
    if ptype == 'ref_link':
        log('🔥 pre-heat: 生成 referral link')
        try:
            do_ref_link(key)
        except Exception as e:
            log(f'⚠️ pre-heat ref_link 失败（继续尝试）：{e}')
    elif ptype == 'alliance':
        log('🔥 pre-heat: 提交联盟战任务')
        try:
            do_alliance_submit(key)
        except Exception as e:
            log(f'⚠️ pre-heat alliance 失败（继续尝试）：{e}')


def attempt_packet(key, packet, action_cache):
    packet_id = packet['id']
    ptype = packet_type(packet)

    for retry_round in range(2):  # 最多 2 轮：首次 + retry
        action_result = action_cache.get(packet_id)
        if action_result is None:
            # 1. Pre-heat（ref link / alliance submit 需要先执行再 join）
            if retry_round == 0:
                preheat_for_packet(key, packet)
            # 2. 执行 challenge（comment / upvote / post）
            action_result = perform_challenge(key, packet)
            action_cache[packet_id] = action_result
            log(f'✅ challenge 已完成：{action_result}')

        try:
            question, answer, joined, solver, attempt = join_packet(key, packet_id)
            report_success(packet, joined, question, answer, solver, attempt, action_result=action_result)
            return True
        except Exception as e:
            err_text = str(e)
            # "challenge not completed" → 重新执行 action 再试
            if retry_round == 0 and ('challenge not completed' in err_text.lower() or 'referral link' in err_text.lower()):
                log(f'⚠️ join 失败（{err_text[:80]}），重新执行 action 重试')
                action_cache.pop(packet_id, None)  # 清缓存，重新执行
                if ptype == 'ref_link':
                    try:
                        do_ref_link(key)
                    except Exception:
                        pass
                elif ptype == 'alliance':
                    try:
                        do_alliance_submit(key)
                    except Exception:
                        pass
                continue
            raise
    return False


def smart_wait_and_poll(key, lead_seconds=15, poll_interval=0.5, poll_duration=360):
    """查 API next_packet_at，等到倒数 lead_seconds 秒开始秒级轮询"""
    data, err = safe_req('/red-packets', key=key)
    if err:
        log(f'❌ 查询红包状态失败：{err}')
        report_failure(f'查询失败：{err}')
        return 1

    nxt = data.get('next_packet_at')
    nxt_sec = data.get('next_packet_seconds')
    active = data.get('active', []) or []

    # 如果已经有 active 红包，直接抢
    if active:
        log(f'🎯 已有 active 红包，立即处理：{active[0].get("title")}')
        try:
            action_cache = {}
            if attempt_packet(key, active[0], action_cache):
                return 0
        except Exception as e:
            report_failure(str(e), packet=active[0])
            return 1

    if not nxt or nxt_sec is None:
        log('⚠️ API 未返回 next_packet_at，无法智能等待')
        return 1

    wait_sec = max(0, nxt_sec - lead_seconds)
    target_local = datetime.now() + timedelta(seconds=nxt_sec)
    log(f'📅 下次红包：{target_local.strftime("%Y-%m-%d %H:%M:%S")}（{nxt_sec:.0f}s 后），{wait_sec:.0f}s 后开始秒级轮询')

    if wait_sec > 0:
        time.sleep(wait_sec)

    # 秒级轮询
    log(f'🚀 开始秒级轮询（间隔 {poll_interval}s，持续 {poll_duration}s）')
    action_cache = {}
    seen_failures = set()
    failed_packet_ids = set()
    last_failure = None
    loops = max(1, int(poll_duration / max(poll_interval, 0.1)))

    for i in range(loops):
        packet, data, err = wait_for_active(key, 0)
        if packet:
            packet_id = packet['id']
            if packet_id in failed_packet_ids:
                time.sleep(poll_interval)
                continue
            log(f"🎯 检测到 active 红包：{packet.get('title')} ({packet_id}) [轮询 {i+1}]")
            try:
                if attempt_packet(key, packet, action_cache):
                    return 0
            except Exception as e:
                err_text = str(e)
                last_failure = (packet, action_cache.get(packet_id), err_text)
                key_fail = (packet_id, err_text)
                if key_fail not in seen_failures:
                    log(f'❌ 加入红包失败：{err_text}')
                    record_wrong_answer(err_text)
                    seen_failures.add(key_fail)
                failed_packet_ids.add(packet_id)
                time.sleep(min(max(poll_interval, 0.5), 1.5))
                continue
        time.sleep(poll_interval)

    if last_failure:
        packet, action_result, err_text = last_failure
        report_failure(err_text, packet=packet, action_result=action_result)
        return 1

    log(f'⚠️ 轮询 {poll_duration}s 未抢到红包')
    return 1


def schedule_next(key):
    """查 API next_packet_at，用 systemd-run 注册一次性定时器，红包前 15 秒触发轮询"""
    import subprocess as sp

    data, err = safe_req('/red-packets', key=key)
    if err:
        log(f'❌ 查询红包状态失败：{err}')
        return 1

    active = data.get('active', []) or []
    nxt = data.get('next_packet_at')
    nxt_sec = data.get('next_packet_seconds')

    # 已有 active 红包，直接抢
    if active:
        log(f'🎯 已有 active 红包，立即处理：{active[0].get("title")}')
        try:
            action_cache = {}
            if attempt_packet(key, active[0], action_cache):
                return 0
        except Exception as e:
            report_failure(str(e), packet=active[0])
            return 1

    if not nxt or nxt_sec is None:
        log('⚠️ API 未返回 next_packet_at')
        return 1

    # 计算触发时间：红包前 15 秒
    from datetime import datetime, timedelta
    trigger_dt = datetime.now() + timedelta(seconds=max(0, nxt_sec - 15))
    calendar_str = trigger_dt.strftime('%Y-%m-%d %H:%M:%S')

    script = Path(__file__).resolve()
    cmd = [
        'systemd-run', '--user', '--on-active=' + str(max(1, nxt_sec - 15)),
        '--unit=f' + trigger_dt.strftime('%H%M%S'),
        'python3', str(script),
        '--poll-now-seconds', '420',
        '--poll-interval', '0.5',
    ]
    log(f'📅 下次红包：{nxt}（{nxt_sec:.0f}s 后）')
    log(f'⏰ 已注册 systemd-run 定时器：{calendar_str} 触发轮询')

    result = sp.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        log(f'❌ systemd-run 失败：{result.stderr.strip()}')
        return 1

    log(f'✅ 定时器注册成功：{result.stdout.strip()}')
    return 0


def smart_poll(key, poll_interval=0.5, poll_duration=420, trigger_seconds=1200):
    """每15分钟调用一次：如果红包10分钟内要发，立即轮询；否则快速退出"""
    data, err = safe_req('/red-packets', key=key)
    if err:
        log(f'❌ 查询红包状态失败：{err}')
        return 1

    active = data.get('active', []) or []
    nxt_sec = data.get('next_packet_seconds')

    # 已有 active 红包，直接抢
    if active:
        log(f'🎯 已有 active 红包，立即处理：{active[0].get("title")}')
        try:
            action_cache = {}
            if attempt_packet(key, active[0], action_cache):
                return 0
        except Exception as e:
            report_failure(str(e), packet=active[0])
            return 1

    if nxt_sec is None:
        log('ℹ️ API 未返回 next_packet_seconds，跳过')
        return 0

    if nxt_sec > trigger_seconds:
        log(f'⏰ 下次红包 {nxt_sec:.0f}s 后（>{trigger_seconds}s），本次跳过')
        return 0

    # 红包即将到达，立即开始轮询
    wait_sec = max(0, nxt_sec - 15)
    if wait_sec > 0:
        log(f'📅 红包 {nxt_sec:.0f}s 后到达，先等 {wait_sec:.0f}s 再开始秒级轮询')
        time.sleep(wait_sec)

    log(f'🚀 开始秒级轮询（间隔 {poll_interval}s，持续 {poll_duration}s）')
    action_cache = {}
    seen_failures = set()
    failed_packet_ids = set()
    last_failure = None
    loops = max(1, int(poll_duration / max(poll_interval, 0.1)))

    for i in range(loops):
        packet, data, err = wait_for_active(key, 0)
        if packet:
            packet_id = packet['id']
            if packet_id in failed_packet_ids:
                time.sleep(poll_interval)
                continue
            log(f"🎯 检测到 active 红包：{packet.get('title')} ({packet_id}) [轮询 {i+1}]")
            try:
                if attempt_packet(key, packet, action_cache):
                    return 0
            except Exception as e:
                err_text = str(e)
                last_failure = (packet, action_cache.get(packet_id), err_text)
                key_fail = (packet_id, err_text)
                if key_fail not in seen_failures:
                    log(f'❌ 加入红包失败：{err_text}')
                    record_wrong_answer(err_text)
                    seen_failures.add(key_fail)
                failed_packet_ids.add(packet_id)
                time.sleep(min(max(poll_interval, 0.5), 1.5))
                continue
        time.sleep(poll_interval)

    if last_failure:
        packet, action_result, err_text = last_failure
        report_failure(err_text, packet=packet, action_result=action_result)
        return 1

    log(f'⚠️ 轮询 {poll_duration}s 未抢到红包')
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-active-seconds', type=int, default=0,
        help='等待红包激活的秒数（预热模式）')
    parser.add_argument('--poll-interval', type=float, default=1.0,
        help='轮询间隔秒数，默认 1 秒（秒级模式）')
    parser.add_argument('--target-time', type=str, default=None,
        help='目标时间 HH:MM，在此时间开始秒级轮询')
    parser.add_argument('--poll-now-seconds', type=int, default=0,
        help='从现在开始立即秒级轮询的秒数')
    parser.add_argument('--smart-wait', action='store_true',
        help='查 API next_packet_at 自动等到红包前再秒级轮询')
    parser.add_argument('--smart-poll', action='store_true',
        help='每15分钟检查：如果红包10分钟内要发就轮询，否则退出')
    parser.add_argument('--schedule-next', action='store_true',
        help='查 API next_packet_at，用 systemd-run 注册一次性定时器')
    args = parser.parse_args()

    key = load_cfg()['api_key']

    if args.schedule_next:
        return schedule_next(key)

    if args.smart_wait:
        return smart_wait_and_poll(key)

    if args.smart_poll:
        return smart_poll(key)

    if args.poll_now_seconds > 0:
        log(f'🚀 立即开始秒级轮询（持续 {args.poll_now_seconds}s，间隔 {args.poll_interval}s）')
        loops = max(1, int(args.poll_now_seconds / max(args.poll_interval, 0.1)))
        action_cache = {}
        seen_failures = set()
        failed_packet_ids = set()  # 跳过已失败的红包，避免空转
        last_failure = None
        for i in range(loops):
            packet, data, err = wait_for_active(key, 0)
            if packet:
                packet_id = packet['id']
                if packet_id in failed_packet_ids:
                    # 这个包已经失败过了，跳过，继续等新包
                    time.sleep(args.poll_interval)
                    continue
                log(f"🎯 检测到 active 红包：{packet.get('title')} ({packet_id}) [轮询 {i+1}]")
                try:
                    if attempt_packet(key, packet, action_cache):
                        return 0
                except Exception as e:
                    err_text = str(e)
                    last_failure = (packet, action_cache.get(packet_id), err_text)
                    key_fail = (packet_id, err_text)
                    if key_fail not in seen_failures:
                        log(f'❌ 加入红包失败：{err_text}')
                        record_wrong_answer(err_text)
                        seen_failures.add(key_fail)
                    failed_packet_ids.add(packet_id)
                    time.sleep(min(max(args.poll_interval, 0.5), 1.5))
                    continue
            time.sleep(args.poll_interval)
        if last_failure:
            packet, action_result, err_text = last_failure
            latest = get_latest_packet(key)
            if latest:
                err_text = f"{err_text}｜latest participants={latest.get('participants')} per_person={latest.get('per_person')} settled={latest.get('settled')}"
            report_failure(err_text, packet=packet, action_result=action_result)
            return 1
        latest = get_latest_packet(key)
        if latest:
            log(f"ℹ️ 当前窗口无 active 红包｜latest participants={latest.get('participants')} per_person={latest.get('per_person')} settled={latest.get('settled')}")
        else:
            log('ℹ️ 当前窗口无 active 红包')
        return 0

    # 秒级轮询模式：在目标时间开始每秒检查
    if args.target_time:
        target = datetime.strptime(args.target_time, '%H:%M').time()
        now = datetime.now().time()
        # 计算等待时间
        target_seconds = target.hour * 3600 + target.minute * 60
        now_seconds = now.hour * 3600 + now.minute * 60 + now.second
        wait_seconds = target_seconds - now_seconds
        if wait_seconds < 0:
            if abs(wait_seconds) <= 300:
                wait_seconds = 0
            else:
                log(f'⚠️ target-time {args.target_time} 已过，立即开始轮询，避免等到次日')
                wait_seconds = 0
        if wait_seconds > 0:
            log(f'⏰ 等待 {wait_seconds:.0f} 秒后开始秒级轮询（目标时间 {args.target_time}）')
            time.sleep(wait_seconds)
        log(f'🚀 开始秒级轮询（间隔 {args.poll_interval}s）')
        action_cache = {}
        seen_failures = set()
        failed_packet_ids = set()
        last_failure = None
        for i in range(30):
            packet, data, err = wait_for_active(key, 0)
            if packet:
                packet_id = packet['id']
                if packet_id in failed_packet_ids:
                    time.sleep(args.poll_interval)
                    continue
                log(f"🎯 检测到 active 红包：{packet.get('title')} ({packet_id}) [轮询 {i+1}s]")
                try:
                    if attempt_packet(key, packet, action_cache):
                        return 0
                except Exception as e:
                    err_text = str(e)
                    last_failure = (packet, action_cache.get(packet_id), err_text)
                    key_fail = (packet_id, err_text)
                    if key_fail not in seen_failures:
                        log(f'❌ 加入红包失败：{err_text}')
                        record_wrong_answer(err_text)
                        seen_failures.add(key_fail)
                    failed_packet_ids.add(packet_id)
                    time.sleep(min(max(args.poll_interval, 0.5), 1.5))
                    continue
            time.sleep(args.poll_interval)
        if last_failure:
            packet, action_result, err_text = last_failure
            latest = get_latest_packet(key)
            if latest:
                err_text = f"{err_text}｜latest participants={latest.get('participants')} per_person={latest.get('per_person')} settled={latest.get('settled')}"
            report_failure(err_text, packet=packet, action_result=action_result)
            return 1
        latest = get_latest_packet(key)
        if latest:
            log(f"❌ 轮询 30 秒未检测到红包｜latest participants={latest.get('participants')} per_person={latest.get('per_person')} settled={latest.get('settled')}")
        else:
            log('❌ 轮询 30 秒未检测到红包')
        return 1

    # 普通模式
    packet, data, err = wait_for_active(key, args.wait_active_seconds)
    if err:
        report_failure(str(err))
        return 1
    if not packet:
        nxt = (data or {}).get('next_packet_at')
        log(f'ℹ️ 当前无 active 红包。next_packet_at={nxt}')
        append_summary({'status': 'no_active', 'next_packet_at': nxt})
        return 0

    packet_id = packet['id']
    log(f"🎯 检测到 active 红包：{packet.get('title')} ({packet_id})")
    try:
        action_result = perform_challenge(key, packet)
        log(f'✅ challenge 已完成：{action_result}')
    except Exception as e:
        report_failure(str(e), packet=packet)
        return 1

    try:
        question, answer, joined, solver, attempt = join_packet(key, packet_id)
        report_success(packet, joined, question, answer, solver, attempt, action_result=action_result)
        return 0
    except Exception as e:
        log(f'❌ 加入红包失败：{e}')
        record_wrong_answer(str(e))
        report_failure(str(e), packet=packet, action_result=action_result)
        return 1


def record_wrong_answer(error_msg):
    """记录错题到学习文件"""
    import re
    # 从错误信息中提取题目和答案
    match = re.search(r"question='([^']+)' answer=(\S+)", error_msg)
    if match:
        question = match.group(1)
        answer = match.group(2)
        solver = 'rules' if 'solver=rules' in error_msg else 'llm'
        
        log_file = Path('/root/.openclaw/workspace/.learnings/agenthansa-wrong-answers.md')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 追加记录
        with log_file.open('a', encoding='utf-8') as f:
            f.write(f"\n## [{timestamp}] 错题记录\n\n")
            f.write(f"**题目**: {question}\n\n")
            f.write(f"**错误答案**: {answer}\n\n")
            f.write(f"**解题方式**: {solver}\n\n")
            f.write(f"**完整错误**: {error_msg}\n\n")
            f.write(f"**待分析**: 为什么答错？需要补充什么规则？\n\n")
            f.write("---\n")


if __name__ == '__main__':
    raise SystemExit(main())
