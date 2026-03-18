---
name: ruisi-twinioc-alarm-hook
description: 'Subscribe to alarm MQTT messages and push alerts to clients via /hooks/agent.'
homepage: https://docs.openclaw.ac.cn/automation/hooks
metadata: { 'openclaw': { 'emoji': '🚨', 'events': ['gateway:startup'], 'requires': { 'bins': ['node'], 'config': ['workspace.dir'] } } }
---

# 睿思孪易产品告警推送技能包

这个 hook 使用 MQTT 订阅告警 topic，收到告警后调用 OpenClaw `POST /hooks/agent` 推送到客户端，不再调用 `SendInstruction`。

启动后会：

1. 连接 MQTT Broker
2. 订阅配置的告警 topic
3. 收到消息后按既有规则识别是否有告警
4. 先按 `BelongToLocationID=dyo6vaow6203kx09` 过滤
5. 对每个接收方做签名去重
6. 调用 `POST /hooks/agent` 推送客户端告警消息

## 默认 MQTT 参数

- 地址：`mqtts://y9afbaf6.ala.cn-hangzhou.emqxsl.cn:8883`
- 用户名：`twinioc`
- 密码：`abc123`
- Topic：`twineasy/location/dyo6vaow6203kx09/alarm/changed/v1`

## 必填配置

- `OPENCLAW_HOOK_TOKEN`
  调用 `/hooks/agent` 的 token。来源建议为 OpenClaw 主配置 `hooks.token`（并且必须与 `gateway.auth.token` 不同）。
- `ALERT_RECIPIENTS_JSON`
  接收方列表，JSON 数组，元素格式：
  `{"channel":"...","to":"..."}`

`OPENCLAW_HOOK_TOKEN` 配置关系：

1. 在 OpenClaw 主配置设置 `hooks.token`
2. 在 `ruisi-twinioc-alarm-hook` 的 `env.OPENCLAW_HOOK_TOKEN` 填同一个值

## 可选配置

- `OPENCLAW_HOOK_BASE_URL`：默认 `http://127.0.0.1:18789`
- `MQTT_URL`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_TOPIC`
- `MQTT_CLIENT_ID`
- `MQTT_QOS`：`0 | 1 | 2`，默认 `1`
- `HTTP_TIMEOUT_SECONDS`：默认 `10`
- `MQTT_LOG_LEVEL`：`info | debug`，默认 `info`
- `ALERT_TITLE`：默认 `告警通知`

## 推送接口

每个接收方会调用：

```http
POST {OPENCLAW_HOOK_BASE_URL}/hooks/agent
Content-Type: application/json
Authorization: Bearer {OPENCLAW_HOOK_TOKEN}
x-openclaw-token: {OPENCLAW_HOOK_TOKEN}

{
  "token": "{OPENCLAW_HOOK_TOKEN}",
  "message": "🚨 通知：{孪生体实例名称} 发生了告警",
  "channel": "<channel>",
  "to": "<to>",
  "deliver": true
}
```

## 告警识别规则

以下字段或结构会被视为有告警：

- `alarmData`
- `alarms`
- `alarmList`
- `items`
- `records`
- `rows`
- `data`
- `result`
- `total`
- `count`
- `size`
- `alarmCount`
- `recordCount`

如果 payload 不是 JSON，只要内容不是空、`null`、`[]`、`{}`、`""`，也会被当作告警消息。

## 去重行为

- 去重粒度是“接收方级别”
- 状态文件保存 `recipientSignatures`
- 相同签名只对已成功推送过的接收方跳过
- 某个接收方失败不会影响其他接收方推送

## 状态文件

运行状态写到工作区：

- `.openclaw-alarm-mqtt/subscriber.pid`
- `.openclaw-alarm-mqtt/subscriber.log`
- `.openclaw-alarm-mqtt/consumer.state.json`
