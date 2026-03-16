---
name: alarm-mqtt-hook
description: "Subscribe to alarm MQTT messages and push alerts to clients via openclaw message send."
homepage: https://docs.openclaw.ac.cn/automation/hooks
metadata: { "openclaw": { "emoji": "🚨", "events": ["gateway:startup"], "requires": { "bins": ["node", "openclaw"], "config": ["workspace.dir"] } } }
---

# Alarm MQTT Hook

这个 hook 使用 MQTT 订阅告警 topic，收到告警后通过 `openclaw message send` 直发到客户端，不再调用 `SendInstruction`，也不经过 agent 改写。

启动后会：

1. 连接 MQTT Broker
2. 订阅配置的告警 topic
3. 收到消息后按既有规则识别是否有告警
4. 对每个接收方做签名去重
5. 调用 `openclaw message send` 推送客户端告警消息（固定中文模板）

## 默认 MQTT 参数

- 地址：`mqtts://y9afbaf6.ala.cn-hangzhou.emqxsl.cn:8883`
- 用户名：`twinioc`
- 密码：`abc123`
- Topic：`twineasy/location/dyo6vaow6203kx09/alarm/changed/v1`

## 必填配置

- `ALERT_RECIPIENTS_JSON`
  接收方列表，JSON 数组，元素格式：
  `{"channel":"...","to":"..."}`

## 可选配置

- `MQTT_URL`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_TOPIC`
- `MQTT_CLIENT_ID`
- `MQTT_QOS`：`0 | 1 | 2`，默认 `1`
- `HTTP_TIMEOUT_SECONDS`：默认 `10`
- `MQTT_LOG_LEVEL`：`info | debug`，默认 `info`
- `OPENCLAW_CLI_BIN`：默认 `openclaw`
- `ALERT_TITLE`：默认 `告警通知`

## 推送命令

每个接收方会执行：

```bash
openclaw message send --channel <channel> --target <to> --message "<三行中文告警文本>"
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
