---
name: ruisi-twinioc-alarm-hook
description: '睿思孪易产品告警推送技能包'
homepage: https://docs.openclaw.ac.cn/automation/hooks
metadata: { 'openclaw': { 'emoji': '🚨', 'events': ['gateway:startup'], 'requires': { 'bins': ['node'], 'config': ['workspace.dir'] } } }
---

# 睿思孪易产品告警推送技能包

本 Hook 使用 MQTT 订阅告警消息，并采用“触发与发送解耦”模式：

1. 固定告警文案通过 `openclaw message send` 直接发送到客户端（文案强约束，不经过 Agent 生成）。
2. 同一条告警再调用 `POST /hooks/agent`，但使用 `deliver=false` 仅触发规则/skill，不向客户端直发自然语言回复。

当收到告警后，还会去匹配 `ruisi-twinioc-opeationrule-skill` 中记录的告警规则：

- 命中规则时，发送规则对应的确认话术，并写入待确认动作，后续由确认流程继续处理。
- 未命中规则时，保持原有告警推送与 agent 触发行为不变。

## 固定告警文案规则

- 模板：`🚨 通知：{孪生体实例名称} 发生了告警`
- 多条记录：保持多行输出（每条记录一行）
- 字段缺失/不合法：丢弃该批次并记录 `invalid_message_template`

## 去重策略

- `recipientSignatures`：按接收方去重固定文案（发送成功才写入状态）
- `agentTriggerSignature`：全局去重 skill 触发（触发成功才写入状态）

这样可避免“多接收方导致 skill 重复执行”。

## 必填配置

- `OPENCLAW_HOOK_TOKEN`
  - 用于调用 `/hooks/agent`
  - 值与 TwinEasy token 使用同一串 token
  - 应与 OpenClaw 主配置 `hooks.token` 一致
- `ALERT_RECIPIENTS_JSON`
  - JSON 数组字符串，元素格式：
  - `{"channel":"...","to":"..."}`

## 可选配置

- `OPENCLAW_HOOK_BASE_URL`：默认 `http://127.0.0.1:18789`
- `OPENCLAW_CLI_BIN`：默认 `openclaw`
- `MQTT_URL`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_TOPIC`
- `MQTT_CLIENT_ID`
- `MQTT_QOS`：`0 | 1 | 2`，默认 `1`
- `HTTP_TIMEOUT_SECONDS`：默认 `10`
- `MQTT_LOG_LEVEL`：`info | debug`，默认 `info`

## `/hooks/agent` 触发语义

Hook 内部调用示例：

```http
POST {OPENCLAW_HOOK_BASE_URL}/hooks/agent
Content-Type: application/json
Authorization: Bearer {OPENCLAW_HOOK_TOKEN}
x-openclaw-token: {OPENCLAW_HOOK_TOKEN}

{
  "token": "{OPENCLAW_HOOK_TOKEN}",
  "message": "ALARM_TRIGGER\nsignature=...\n...",
  "deliver": false
}
```

说明：

- `deliver=false` 仅触发规则/skill，不直接给客户端发送 Agent 自然语言回复。
- 即使触发失败，固定告警文案发送流程仍继续（以告警可见性优先）。

## 状态文件

工作区目录下：

- `.openclaw-ruisi-twinioc-alarm-hook/subscriber.pid`
- `.openclaw-ruisi-twinioc-alarm-hook/subscriber.log`
- `.openclaw-ruisi-twinioc-alarm-hook/consumer.state.json`
