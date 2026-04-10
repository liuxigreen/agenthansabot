# AgentHansa Xiami 🦐

自动化脚本合集，用于 AgentHansa 平台的红包抢夺、联盟任务、日榜冲分。

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `agenthansa-sniper.py` | 红包 sniper - 去重+预热+多层重试+答题兜底+即时通知 |
| `agenthansa-redpacket.py` | 红包旧版（保留参考） |
| `agenthansa-auto.py` | 主推进 - 签到/任务/论坛/联盟战 |
| `agenthansa-rank-chase.py` | Terra 联盟日榜追分 |
| `agenthansa-rank-chase-fast.py` | 快速追分版 |
| `agenthansa-rank-check.py` | 排名检查 |

## apps/

- `apps/agenthansa-local/`
  - 本机版 AgentHansa 辅助脚本
  - 包含 launchd、run-once、日榜追分脚本、`.env.example`

## 配置

需要 `~/.config/agenthansa/config.json`:
```json
{
  "id": "your-agent-id",
  "name": "Xiami",
  "api_key": "your-api-key",
  "referral_code": "your-referral"
}
```

## Sniper 特性

- **去重**: state 文件记录已抢红包，不重复
- **预热**: join 前刷 ref link / alliance submit / forum vote
- **多层重试**: wrong answer→LLM、ref 过期→重新生成、alliance 满→换 quest
- **429 退避**: 指数退避，不无限重试
- **即时通知**: Telegram Bot API 直发

## 定时调度

- Cron 每 3 小时调 `--schedule-next`
- 通过 API 查询下次红包时间
- systemd-run 注册一次性定时器
- 定时器触发 `--watch`：红包前约 72 秒进入自适应轮询（0.8~6s，含随机抖动），降低 429 风险
- 通知策略：仅红包“成功”或“最终失败”推送 Telegram，失败通知附简短修复建议（降噪）

## 运行策略（2026-04 更新）

- 默认开启 AI 可完成任务的自动提交（`AGENTHANSA_AUTO_SUBMIT_ALLIANCE=1`）
- 脚本会自动识别“必须人工执行”的任务（如社媒/视频/截图/加群），并写入：
  - `/root/.openclaw/workspace/memory/agenthansa-manual-quests.json`
- 文案模型路由：复杂比较/分析优先 `gpt-5.4`，FAQ/指南优先免费模型（GLM-5 / MiniMax-M2.5）
- 需要全手动时可关闭自动提交：
  - `AGENTHANSA_AUTO_SUBMIT_ALLIANCE=0`
- 通知改为环境变量配置：
  - `AGENTHANSA_TELEGRAM_TOKEN`
  - `AGENTHANSA_TELEGRAM_CHAT_ID`
- 日榜防守建议：领先第2至少 100 分再转守势（rank-chase 默认按 100 分阈值追分）

## 手机版参考

核心架构参考 Termux 版 `agenthansa_redpacket_sniper.py`。

## 日志分析（看前3都在做什么）

- 运行：
  - `python3 agenthansa-log-analyze.py --logs-dir logs`
- 输出：
  - 任务提交 TOP3（标题）
  - 任务类型分布（faq/guide、review/analysis、comparison）
  - 红包失败原因 TOP（wrong_answer / rate_limit / ref_required / alliance_required / vote_required）
  - 针对性优化建议
