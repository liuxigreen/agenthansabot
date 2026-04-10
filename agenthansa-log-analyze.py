#!/usr/bin/env python3
"""
分析 AgentHansa logs/ 目录，给出：
1) 近周期主要得分来源（红包/任务）
2) 红包失败原因 TOP
3) 可执行优化建议

默认读取 ./logs:
- redpacket-summary.jsonl
- task-summary.jsonl
- redpacket.log
- auto.log
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def classify_task(title: str) -> str:
    low = (title or '').lower()
    if any(k in low for k in ['faq', 'guide', 'how', 'explain']):
        return 'faq/guide'
    if any(k in low for k in ['review', 'analysis', 'research']):
        return 'review/analysis'
    if any(k in low for k in ['comparison', 'compare', 'fiverr', 'upwork']):
        return 'comparison'
    return 'other'


def classify_failure(reason: str) -> str:
    low = (reason or '').lower()
    if 'wrong answer' in low or 'incorrect answer' in low:
        return 'wrong_answer'
    if '429' in low or 'rate' in low:
        return 'rate_limit'
    if 'ref' in low:
        return 'ref_required'
    if 'alliance' in low:
        return 'alliance_required'
    if 'vote' in low:
        return 'vote_required'
    return 'other'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--logs-dir', default='logs', help='日志目录，默认 ./logs')
    args = ap.parse_args()

    logs_dir = Path(args.logs_dir)
    rp_summary = read_jsonl(logs_dir / 'redpacket-summary.jsonl')
    task_summary = read_jsonl(logs_dir / 'task-summary.jsonl')

    packet_ok = [x for x in rp_summary if x.get('status') == 'success']
    packet_fail = [x for x in rp_summary if x.get('status') == 'failure']

    fail_counter = Counter(classify_failure(x.get('reason', '')) for x in packet_fail)

    task_title_counter = Counter()
    task_type_counter = Counter()
    for rec in task_summary:
        tasks = rec.get('tasks') or []
        for t in tasks:
            title = t.get('title') or 'Untitled'
            task_title_counter[title] += 1
            task_type_counter[classify_task(title)] += 1

    print('=== AgentHansa 日志分析 ===')
    print(f'logs_dir: {logs_dir.resolve()}')
    print(f'红包成功: {len(packet_ok)} | 红包失败: {len(packet_fail)}')

    if task_title_counter:
        print('\n[任务提交 TOP3]')
        for title, c in task_title_counter.most_common(3):
            print(f'- {title} : {c}次')

    if task_type_counter:
        print('\n[任务类型分布]')
        for t, c in task_type_counter.most_common():
            print(f'- {t}: {c}')

    if fail_counter:
        print('\n[红包失败原因 TOP]')
        for k, c in fail_counter.most_common(5):
            print(f'- {k}: {c}')

    print('\n[优化建议]')
    if fail_counter.get('rate_limit', 0) > 0:
        print('- 429 偏高：加大 watch 抖动、避免固定 1s 打点。')
    if fail_counter.get('wrong_answer', 0) > 0:
        print('- 答题错误偏高：补充题型规则，失败题落库训练。')
    if fail_counter.get('ref_required', 0) > 0:
        print('- ref 前置不足：在 join 前强制 refresh referral。')
    if fail_counter.get('alliance_required', 0) > 0:
        print('- alliance 前置不足：红包前补 1 条有效联盟任务。')

    if not rp_summary and not task_summary:
        print('- 未找到 redpacket-summary.jsonl / task-summary.jsonl，请先同步 logs。')


if __name__ == '__main__':
    main()
