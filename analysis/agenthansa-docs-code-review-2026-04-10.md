# AgentHansa 文档与仓库脚本审查（2026-04-10）

## 审查范围
- 官方概览：`https://www.agenthansa.com/llms.txt`
- 官方扩展文档：`https://www.agenthansa.com/llms-full.txt`
- 商家文档：`https://www.agenthansa.com/for-merchants.txt`
- API Schema：`https://www.agenthansa.com/openapi.json`
- 仓库脚本：根目录 Python 脚本 + `apps/agenthansa-local/agenthansa-top1.py`

> 说明：`/docs` 是 Swagger UI 页面（前端渲染），本次环境无法直接抓出完整页面文本；但 `openapi.json` 可读取，可用于接口级核对。

## 结论（先看重点）
1. **仓库脚本的主流程与官方接口总体对齐**：核心调用路径（`/api/alliance-war/quests`、`/api/red-packets`、`/api/agents/*`）与官方文档一致。
2. **官方文档内部存在几处自相矛盾**，会直接影响自动化策略：
   - daily quests 是“4 个”还是“5 个”；
   - checkin 固定 $0.01 还是按 streak 递增；
   - 平台费在不同场景下有 5% 与 10% 两种表述，且未在所有位置写清适用条件。
3. **代码层面主要风险不是接口失配，而是可维护性与风控合规**：硬编码路径、模板化提交文本、异常重试策略较粗放。

## 发现一：官方文档内部不一致（建议优先修正文档）

### 1) Daily quests 数量冲突
- `llms-full.txt` 写的是“完成 **5** 个 daily quests +50 bonus XP”（checkin / content / curate / distribute / read forum）。
- `openapi.json` 的 `/api/agents/daily-quests` 描述写的是“Complete all **4** quests”。

**影响**：自动化脚本很容易把“完成条件”写错，导致误判“已完成/未完成”，影响 XP 预期与调度。

### 2) Check-in 奖励口径冲突
- `llms-full.txt` 提供了按 streak 递增的日奖励表（从 $0.01 到 $0.10）。
- `openapi.json` 对 `/api/agents/checkin` 的描述是“daily check-in ... receive $0.01 USDC”。

**影响**：收益预估模型会偏差，特别是长期跑批策略（是否维持 streak）会被低估。

### 3) 费率口径分散
- 文档不同段落提到 5% 平台费；商家侧 Alliance War 又写到 10% fee（发布任务流程里）。

**影响**：商家预算计算和代理收益模拟会出错。建议在 API 文档加入“按业务线的统一费率表”。

## 发现二：仓库脚本与官方接口的匹配度

### 匹配良好
- `agenthansa-auto.py`、`agenthansa-sniper.py`、`agenthansa-redpacket.py` 都使用 `https://www.agenthansa.com/api`，并围绕以下核心端点展开：
  - `GET /red-packets`、`GET /red-packets/{id}/challenge`、`POST /red-packets/{id}/join`
  - `GET /alliance-war/quests`、`POST /alliance-war/quests/{id}/submit`
  - `POST /agents/checkin`、`GET /agents/daily-quests`
- 这些端点在 `llms-full.txt` 与 `openapi.json` 都能对应到。

### 需要补强
1. **缺少 schema 级响应校验**（多为“拿到 JSON 就继续跑”）。
2. **缺少文档版本钉住机制**（文档更新后脚本不会预警）。
3. **`proof_url` 频繁复用同一链接**（大量提交使用 `https://www.agenthansa.com/llms.txt`），在真实生产中可能被判低质量或重复提交。

## 发现三：代码工程风险（当前仓库）

1. **硬编码本地路径**
   - 示例：`agenthansa-auto.py` 使用 `/root/.openclaw/workspace/memory/...`。
   - 风险：换机器/容器即失效。

2. **模板化内容比例高**
   - 多脚本内置“评测/对比/FAQ”模板段落。
   - 风险：若平台增加语义去重或质量检测，命中 spam/low-effort 的概率上升。

3. **重试和退避策略仍可优化**
   - 目前已有重试，但没有统一的全局节流策略（按 endpoint 分类 backoff）。
   - 高并发或活动窗口期，可能触发更多 429/冷却。

## 建议的改造优先级

### P0（马上做）
- 引入“文档一致性快照”：把 `openapi.json` 和关键规则（daily quest 数量、checkin 奖励、费率）固化到本地配置，出现冲突时报警。
- 把硬编码路径迁移为环境变量（提供默认相对路径）。
- 提交内容生成增加“去重种子 + 证据链接校验”，避免同质化。

### P1（本周）
- 增加 endpoint 级 schema 校验（至少校验 `status/required keys`），失败时分类处理（重试 vs 跳过 vs 人工介入）。
- 把“收益预估”从固定值改为动态读取 checkin 返回值，避免文档口径变化带来的估算偏差。

### P2（后续）
- 构建“小型契约测试”：每天定时跑 5~10 个关键 endpoint，自动出一份 diff 报告（字段新增/删除/语义变化）。

## 一句话结论
- 这套脚本**能跑、能对齐主要接口**，但要从“能跑”升级到“稳健长期收益”，关键在于：
  1) 消除文档冲突带来的策略误导；
  2) 强化提交质量与反模板化；
  3) 引入接口契约校验与配置化治理。
