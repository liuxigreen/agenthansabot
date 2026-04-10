#!/usr/bin/env python3
import json
import urllib.request
import time

CONFIG = '/root/.config/agenthansa/config.json'
BASE = 'https://www.agenthansa.com/api'
UA = 'OpenClaw-Xiami/1.0'

def load_cfg():
    with open(CONFIG, 'r') as f:
        return json.load(f)

def req(path, key, method='GET', data=None):
    url = BASE + path
    headers = {
        'User-Agent': UA,
        'Authorization': f'Bearer {key}',
    }
    
    if data and method == 'POST':
        headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method=method)
    else:
        request = urllib.request.Request(url, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            raw = r.read().decode()
        return json.loads(raw) if raw else {}
    except Exception as e:
        print(f"API请求失败: {e}")
        return {}

def main():
    cfg = load_cfg()
    key = cfg['api_key']
    
    print("1. 执行签到...")
    checkin = req('/agents/checkin', key, 'POST', {})
    print(f"签到结果: {json.dumps(checkin, ensure_ascii=False)}")
    
    time.sleep(1)
    
    print("\n2. 获取任务列表...")
    quests = req('/alliance-war/quests', key)
    
    # 找出可以提交的任务
    available_quests = []
    if isinstance(quests, list):
        for quest in quests[:10]:  # 只看前10个
            quest_id = quest.get('id')
            title = quest.get('title')
            reward = quest.get('reward')
            status = quest.get('status')
            
            if status == 'open':
                available_quests.append({
                    'id': quest_id,
                    'title': title,
                    'reward': reward
                })
    
    print(f"找到 {len(available_quests)} 个开放任务")
    
    # 提交前3个任务
    submitted = 0
    for i, quest in enumerate(available_quests[:3]):
        print(f"\n提交任务 {i+1}: {quest['title']}")
        submit_url = f"/alliance-war/quests/{quest['id']}/submit"
        result = req(submit_url, key, 'POST', {})
        
        if result.get('submission_id'):
            print(f"✅ 提交成功: {result.get('submission_id')}")
            submitted += 1
        else:
            print(f"❌ 提交失败: {json.dumps(result, ensure_ascii=False)}")
        
        time.sleep(2)
    
    print(f"\n总共提交了 {submitted} 个任务")
    
    # 检查新排名
    time.sleep(2)
    print("\n3. 检查新排名...")
    alliance_daily = req('/agents/alliance-daily-leaderboard', key)
    green_alliance = alliance_daily.get('alliances', {}).get('green', {})
    leaderboard = green_alliance.get('leaderboard', [])
    
    xiami_found = False
    for entry in leaderboard:
        if entry.get('name') == 'Xiami':
            xiami_found = True
            rank = entry.get('rank')
            points = entry.get('today_points')
            print(f"Xiami新排名: 第{rank}名, {points}分")
            break
    
    if not xiami_found:
        print("Xiami仍不在榜单上")

if __name__ == '__main__':
    main()