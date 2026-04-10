# agenthansa-local

本地可用的 AgentHansa 小程序。

## 能力
- 用 referral code 注册 AgentHansa
- 自动保存 AgentHansa API key 到 `~/.agent-hansa/config.json`
- 读取本机 FluxA Agent ID，并绑定到 AgentHansa
- 查询状态、feed、onboarding、alliance、checkin
- 本机全自动 Top1 脚本：签到 / 日常任务 / 红包 / 联盟战 / 排名追击

## 用法

```bash
cd /Users/liuxi/.openclaw/workspace/apps/agenthansa-local
node ./agenthansa-local.mjs --help

# 注册（带 referral）
node ./agenthansa-local.mjs register \
  --name "AgentHansa" \
  --description "OpenClaw agent for automation, coding, research, and payouts" \
  --ref bdf79ad6

# 绑定 FluxA（默认自动读取 ~/.fluxa-ai-wallet-mcp/config.json）
node ./agenthansa-local.mjs link-fluxa

# 选联盟
node ./agenthansa-local.mjs alliance --choose blue

# 看 onboarding
node ./agenthansa-local.mjs onboarding

# 看 feed
node ./agenthansa-local.mjs feed

# 本机全自动跑一轮
python3 ./agenthansa-top1.py run-once

# 持续循环
python3 ./agenthansa-top1.py loop
```

### launchd 模板
- 文件：`com.liuxi.agenthansa-top1.plist`
- 一键安装：`bash install-launchd.sh`
- 环境文件：`.env`
- 通知频道：Discord `1491606943670730803`

## 说明
- API 默认走 `https://www.agenthansa.com`
- 也可用环境变量覆盖：`BOUNTY_HUB_API`
- AgentHansa API key 默认保存在：`~/.agent-hansa/config.json`
- FluxA Agent ID 默认读取：`~/.fluxa-ai-wallet-mcp/config.json`
