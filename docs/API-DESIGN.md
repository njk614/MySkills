# Ruisi Skills — AI 可调用 API 技术设计草案

说明：本设计文档为 `ruisi` 系列 Skill 的规范化基线（Design‑first）。

说明要点：

- 本文件定义 API 契约、认证、异步语义与监控指标，作为生成或验证 `ruisi` Skill 的来源（source of truth）。
- 仓库中的 `ruisi-*` 目录为基于本设计的实现示例（implementation examples），当前存在的实现可用于反向验证，但不应替代本设计作为规范来源。

**概览（设计优先）**

- 目标：首先定义统一的 API 表面（REST+JSON 为首选）及契约，使产品/工程/AI 能以设计为中心协同开发；`ruisi-*` 的实现应遵循并验证本设计。
- 范围：覆盖 query、command、operation-rule 与 alarm-hook 四类能力的接口契约与非功能需求，不包含 MCP 平台私有实现细节。

---

## Skill 能力清单（实现示例）

- `ruisi-twinioc-dataquery-skill`（实现示例）
  - 说明：仓库实现演示如何按本设计执行只读查询（温度查询、场景信息、孪生体实例列表、摄像头列表等），供生成 `ruisi` Skill 时参考。
  - 主要脚本：`scripts/query.py`。
  - 对应设计端点：POST `/v1/skills/data/query`（同步查询，部分查询可返回 `rule_match`）。

- `ruisi-twinioc-command-skill`（实现示例）
  - 说明：仓库实现演示 NL -> instruction 的转换与执行流程，包含确认逻辑与对 dataquery/operation-rule 的依赖调用。
  - 主要脚本：`scripts/invoke_skill.py`。
  - 对应设计端点：POST `/v1/skills/command/invoke`（支持同步/异步执行与确认流）。

- `ruisi-twinioc-opeationrule-skill`（实现示例）
  - 说明：仓库实现演示规则记录、匹配与待确认动作的存储与查询逻辑，应以本设计中定义的 schema 为准来实现。
  - 主要脚本：`scripts/invoke_recorder.py`。
  - 对应设计端点：POST `/v1/skills/operation-rule/record`、POST `/v1/skills/operation-rule/match-temperature`、GET/POST `/v1/skills/operation-rule/pending`、GET `/v1/skills/operation-rule/query`。

- `ruisi-twinioc-alarm-hook`（实现示例）
  - 说明：仓库实现为事件来源（MQTT/外部告警），演示了如何触发内部 agent hook 与 `operation-rule` 的联动行为；建议将其行为映射为 `POST /v1/hooks/alarm` 以纳入统一设计。
  - 主要文件：`HOOK.md`、`handler.ts`、`subscriber.mjs`。
  - 对应设计端点：POST `/v1/hooks/alarm`（接收外部告警并触发内部 skill），以及对 `/v1/hooks/agent` 的映射（`deliver=false`）。

---

## 高层协议与设计决策

- 主协议：HTTP + JSON（REST 风格），采用 OpenAPI v3 描述。可选事件通道：Webhook 用于异步任务回调。
- 认证：首版建议 API Key（Authorization: Bearer <key>），后期可扩展 OAuth2/JWT。
- 同步/异步：大多数查询与短时执行为同步返回；长时执行或与外部系统多步骤交互时返回 202 Accepted + `task_id`，并提供 `GET /v1/tasks/{task_id}` 查询或 webhook 回调。
- 错误模型：统一返回 { code, message, details? }，HTTP 状态码遵循约定（400、401、403、404、429、500）。

---

## 端点草案（摘录；完整定义见 `docs/openapi.yaml`）

- POST /v1/skills/data/query
  - 描述：执行只读查询（temperature, mcp-tool, get_bind_video_instance_names 等）。
  - 请求 body：{ "token": "...", "type": "temperature|mcp|category|video_names", "params": {...}, "request_id": "uuid" }
  - 返回：{ "success": true, "reply": "中文可读文本", "data": {...}, "rule_match": {...}? }

- POST /v1/skills/command/invoke
  - 描述：将自然语言转换为指令串并（可选）下发执行。
  - 请求 body：{ "token":"...","query":"用户原文","context":{...},"confirm_required":boolean,"request_id":"uuid" }
  - 返回（同步快速）：{ "status":"ok","message":"plan_text" }
  - 返回（需确认或异步）：{ "status":"accepted","task_id":"tid" }

- POST /v1/skills/operation-rule/record
  - 描述：记录规则（alarm/temperature/schedule）或保存待确认动作。
  - 请求 body：{ "token":"...","source":"alarm|temperature|schedule","query":"...","parsed_rule":{...} }
  - 返回：{ "success":true, "record":{...} }

- POST /v1/skills/operation-rule/match-temperature
  - 描述：按设备名与温度匹配规则，返回 `matches` 与 `confirmation_text`。
  - 请求 body：{ "token":"...","device_name":"...","temperature":25.0 }
  - 返回：{ "total":N, "matches":[{...}], "confirmation_text":"..." }

---

## Alarm Hook 映射补充

- `ruisi-twinioc-alarm-hook` 为事件来源类型（MQTT/外部告警），其核心契约为接收告警事件并触发内部 Agent/Skill：
  - 建议新增端点：`POST /v1/hooks/alarm`，承载告警元数据并返回触发状态。
  - 支持 `deliver` 标志：当 `deliver=false` 时，仅触发内部 skill（等同于仓库中 `POST /hooks/agent` 的 `deliver=false` 行为）；当 `deliver=true` 则同时发送固定告警文案到客户端。
  - 必填字段示例：`{ "token":"...","alarm_id":"...","device_name":"...","message":"...","deliver":false,"request_id":"uuid" }`。

---

---

## 从设计到 Skill：生成 `ruisi` Skill 的建议流程

1. 以本 `API-DESIGN.md` 与 `docs/openapi.yaml` 为契约基线，确定要生成的 Skill 列表（dataquery, command, operation-rule, alarm-hook）。
2. 使用脚手架模板创建每个 Skill 的目录和基础文件：`SKILL.md`, `scripts/*`, `HOOK.md`（如需要）以及测试用例，使实现严格遵循 OpenAPI 定义的 request/response schema。
3. 在实现中把所有对外请求替换为调用本地 mock server 或 SDK（先验接口），以便单元与契约测试通过。
4. 运行契约测试（OpenAPI contract tests）验证实现与设计一致；把不一致点回写到设计文档并修订 schema。
5. 发布 `ruisi` Skill 套件并把设计文档作为版本化规范（每次变更同时更新 OpenAPI）。

说明：当前仓库中的 `ruisi-*` 为实现示例；本次已把文档表述调整为“设计优先/实现示例”。

## 数据模型要点

- 统一字段：`request_id`（客户端生成 UUID）用于幂等与追踪；`token` 用于场景边界。
- 统一错误：

```json
{ "code":"E_VALIDATION","message":"详细说明","details":{...} }
```

- `rule_match.parsed_rule` 使用仓库中示例结构（见 `ruisi-twinioc-opeationrule-skill` 的 `parsed_rule`）。

---

## 鉴权/权限（建议）

- 管理后台生成 API Key（或 JWT），按 key 绑定场景 token 的访问权限。
- 对执行指令的 API（`/command/invoke`）增加更严格配额与审计日志。

---

## 异步与回调

- 长任务（下发指令并等待平台多轮反馈）采用 202 + `task_id`；支持 `POST /v1/tasks/{task_id}/cancel`。
- 回调：注册 webhook URL（HMAC-SHA256 签名），回调体包含 `task_id, status, result`。

---

## 日志与监控建议

- 记录：`request_id, request_time, latency_ms, status_code, skill_name, token`。
- 指标：成功率、p95 延迟、队列长度、并发执行数、命中规则率（rule_match ratio）。

---

## 交付物（已生成）

- OpenAPI 草案： `docs/openapi.yaml`
- 技术设计草稿： `docs/API-DESIGN.md`（本文件）

---

## MCP 工具列表（dataquery-skill 支持）

`DataQueryRequest` 中 `type=mcp` 时，通过 `mcp_tool` 指定工具名，`mcp_args` 传入工具参数（均为非缓存实时调用）：

| 工具名                          | 说明                                           | 参数                                   |
| ------------------------------- | ---------------------------------------------- | -------------------------------------- |
| `get_scene_info`                | 场景完整配置（层级/主题/图层/图表/孪生体类别） | 无                                     |
| `get_scene_context`             | 场景会话上下文（含历史记录，实时变化）         | 无                                     |
| `get_twin_category_data`        | 按类别名称查询该类别下所有孪生体实例列表       | `{ "twinCategoryName": "可控摄像头" }` |
| `get_twin_category`             | 按层级名称查询该层所有孪生体类别               | `{ "twinCategoryName": "..." }`        |
| `get_bind_video_instance_names` | 获取当前场景绑定的所有摄像头实例名称列表       | 无                                     |

`type=temperature` 时，附带 `device_query` 字段（按安装位置或孪生体实例名称模糊匹配）；不传 `device_query` 时使用默认设备台账。

---

## 上游平台接口层（TwinIoC）

> 以下为 Skill 层内部调用的 TwinIoC 平台原始接口，**不对外直接暴露**，所有 AI 调用均通过统一 `/v1/*` 层。

- **默认基础地址**：`http://test.twinioc.net`
- **地址拼接规则**：未显式传入基础地址时，默认使用 `http://test.twinioc.net`；如果传入了基础地址，则使用该地址继续拼接后续固定路径。

- **MCP 基础路径**：`{base-url}/api/editor/mcp`（JSON-RPC，协议版本 `2025-03-26`）
- **SendInstruction**：`POST {base-url}/api/editor/v1/location/SendInstruction`
  - Header：`Content-Type: application/json`，`Accept: text/plain`
  - Body：`{ "token": "...", "jsonData": "instruction_order$&query$&plan_text" }`

---

## 指令串（jsonData）格式

`SendInstruction` 的 `jsonData` 字段由三段用 `$&` 拼接：

```
instruction_order$&query$&plan_text
```

- `instruction_order`：带编码的执行指令串，多条之间也用 `$&` 连接，如 `A36：告警信息：当前$&A38：告警信息选中`
- `query`：用户原始自然语言问题
- `plan_text`：中文展示文本（不含 A/B/C/D 编码）

**示例：**

```json
{
  "token": "gj6mxa",
  "jsonData": "A09$&场景复位$&根据最优策略，已经为您规划如下执行计划：\n1、场景复位"
}
```

---

## parsed_rule 完整结构

### 温度规则（source=temperature）

```json
{
  "device_name": "大厅东侧",
  "operator": "gt",
  "operator_text": "大于",
  "threshold": 20.0,
  "action_text": "关闭照明灯",
  "execute_query": "关闭大厅东侧照明灯"
}
```

`operator` 枚举：`gt`（大于）、`lt`（小于）、`gte`（大于等于）、`lte`（小于等于）、`eq`（等于）

### 告警规则（source=alarm）

```json
{
  "device_name": "大会议室摄像头",
  "action_text": "关闭大会议室的灯",
  "execute_query": "关闭大会议室的灯"
}
```

> 告警触发来源主要为摄像头（camera），`device_name` 为摄像头孪生体实例名称，alarm-hook 收到 MQTT 消息后按此字段匹配已记录的告警规则。

---

## 待确认动作（Pending Confirmation）流程

温度/告警规则命中后进入两步确认：

1. `match-temperature` 或 alarm-hook 触发 → 命中规则 → 写入 `.runtime/pending_confirmations.json`，并向用户展示确认话术
2. 用户回复"是 / 确认 / 好 / 执行" → `GET /v1/skills/operation-rule/pending` 读取 pending → 取 `execute_query` 作为新请求执行 → 执行后 `DELETE /v1/skills/operation-rule/pending` 清理
3. 用户回复"否 / 取消" → 直接 `DELETE /v1/skills/operation-rule/pending` 清理，回复"已取消操作"

**Pending 存储结构：**

```json
{
  "token": "gj6mxa",
  "matched_rule": {
    "source": "temperature",
    "query": "当大厅温度大于20度时关闭照明灯",
    "confirmation_text": "当前大厅东侧23.5℃，大于规则设定的大于20℃，关闭照明灯，请确认是否执行？",
    "parsed_rule": {
      "device_name": "大厅东侧",
      "operator": "gt",
      "operator_text": "大于",
      "threshold": 20.0,
      "action_text": "关闭照明灯",
      "execute_query": "关闭大厅东侧照明灯"
    }
  }
}
```

---

## MQTT 告警消息配置（alarm-hook）

| 环境变量         | 默认值                                             | 说明               |
| ---------------- | -------------------------------------------------- | ------------------ |
| `MQTT_URL`       | `mqtts://y9afbaf6.ala.cn-hangzhou.emqxsl.cn:8883`  | Broker 地址        |
| `MQTT_USERNAME`  | `twinioc`                                          | 用户名             |
| `MQTT_PASSWORD`  | `abc123`                                           | 密码（生产应替换） |
| `MQTT_TOPIC`     | `twineasy/location/{location_id}/alarm/changed/v1` | 订阅 topic         |
| `MQTT_QOS`       | `1`                                                | QoS 级别（0/1/2）  |
| `MQTT_CLIENT_ID` | 自动生成                                           | 可选，手动指定     |

**Topic 格式**：`twineasy/location/{location_id}/alarm/changed/v1`，默认 `location_id = dyo6vaow6203kx09`。

**告警消息 payload**：须含 `孪生体实例名称` 字段，用于生成固定告警文案：

```
🚨 通知：{孪生体实例名称} 发生了告警
```

无效消息（空串、`null`、`[]`）将被丢弃并记录 `invalid_message_template`。

**去重机制：**

- `recipientSignatures`：按接收方去重固定文案（发送成功才写入状态）
- `agentTriggerSignature`：全局去重 skill 触发（触发成功才写入状态）

---

## 会话缓存

会话状态统一存储于 `ruisi-twinioc-dataquery-skill/.runtime/session_store.json`（command-skill 的 skill_runtime.py 读写此文件）：

| 字段             | 类型   | 说明                                               |
| ---------------- | ------ | -------------------------------------------------- |
| `session_id`     | string | 会话标识                                           |
| `token_judge`    | string | 上一次使用的 token（token 变化时自动重置全部状态） |
| `scene_info`     | string | 最近场景配置 JSON                                  |
| `history_inter`  | array  | MCP 工具调用历史（最多 20 条）                     |
| `mcp_session_id` | string | MCP 协议会话 ID                                    |
| `updated_at`     | float  | 最后更新时间戳（Unix）                             |

---

## 补全端点清单（openapi.yaml 已同步）

| 端点                                       | 说明               |
| ------------------------------------------ | ------------------ |
| `GET /v1/skills/operation-rule/pending`    | 读取当前待确认动作 |
| `DELETE /v1/skills/operation-rule/pending` | 清除待确认动作     |
| `GET /v1/skills/operation-rule/query`      | 查询历史规则记录   |
| `POST /v1/tasks/{task_id}/cancel`          | 取消异步任务       |
