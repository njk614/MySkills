# ruisi-twinioc-alarm-hook 部署说明（方式2：/hooks/agent）

## 1. 功能

- 订阅 MQTT 告警消息
- 先按 `BelongToLocationID=dyo6vaow6203kx09` 过滤告警记录
- 对每个接收方做去重后，调用 `POST /hooks/agent` 推送消息

当前消息模板：

```text
🚨 通知：{孪生体实例名称} 发生了告警
```

## 2. 必填配置

- `OPENCLAW_HOOK_TOKEN`
  - OpenClaw webhook token，用于调用 `/hooks/agent`
- `ALERT_RECIPIENTS_JSON`
  - JSON 数组字符串
  - 每项格式：`{"channel":"...","to":"..."}`

示例：

```json
"OPENCLAW_HOOK_TOKEN": "your-hooks-token",
"ALERT_RECIPIENTS_JSON": "[{\"channel\":\"feishu\",\"to\":\"ou_xxx\"},{\"channel\":\"xmpp\",\"to\":\"demo01@im.tuguan.net\"}]"
```

## 2.1 OPENCLAW_HOOK_TOKEN 怎么获取

`OPENCLAW_HOOK_TOKEN` 不是自动生成的业务字段，通常做法是你在 OpenClaw 主配置里显式设置一个 `hooks.token`，然后把同一个值配置到 hook 的环境变量 `OPENCLAW_HOOK_TOKEN`。

示例（主配置）：

```json
{
  "gateway": {
    "auth": {
      "token": "gateway-token-abc"
    }
  },
  "hooks": {
    "token": "hooks-token-xyz"
  }
}
```

注意：

- `hooks.token` 必须和 `gateway.auth.token` 不同。
- 如果两者相同，Gateway 会报错：`hooks.token must not match gateway auth token`。

生成 token 示例（任选一种）：

```bash
# Linux/macOS
openssl rand -hex 32
```

```powershell
# Windows PowerShell
[guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
```

然后把生成值同时填到：

1. OpenClaw 主配置 `hooks.token`
2. `ruisi-twinioc-alarm-hook` 的 `env.OPENCLAW_HOOK_TOKEN`

## 3. 可选配置

- `OPENCLAW_HOOK_BASE_URL`（默认 `http://127.0.0.1:18789`）
- `MQTT_URL`（默认 `mqtts://y9afbaf6.ala.cn-hangzhou.emqxsl.cn:8883`）
- `MQTT_USERNAME`（默认 `twinioc`）
- `MQTT_PASSWORD`（默认 `abc123`）
- `MQTT_TOPIC`（默认 `twineasy/location/dyo6vaow6203kx09/alarm/changed/v1`）
- `MQTT_CLIENT_ID`
- `MQTT_QOS`（默认 `1`）
- `MQTT_LOG_LEVEL`（默认 `info`）
- `HTTP_TIMEOUT_SECONDS`（默认 `10`）

## 4. 最小可用配置

```json
{
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": {
        "ruisi-twinioc-alarm-hook": {
          "enabled": true,
          "env": {
            "OPENCLAW_HOOK_TOKEN": "your-hooks-token",
            "ALERT_RECIPIENTS_JSON": "[{\"channel\":\"feishu\",\"to\":\"ou_xxx\"}]"
          }
        }
      }
    }
  }
}
```

校验建议：

- 先重启 Gateway，确认没有 `hooks.token must not match gateway auth token` 报错。
- 再看 hook 日志中是否出现 `push mode=hook ... ok=true ...`。

## 5. 成功日志关键字

- MQTT 连接成功：
  - `Connected to ...`
  - `Subscribed to ...`
- 推送成功：
  - `push mode=hook ... ok=true ...`

## 6. 常见问题

- `Missing required OPENCLAW_HOOK_TOKEN`
  - 未配置 token，hook 会直接退出。
- `Invalid OPENCLAW_HOOK_BASE_URL format`
  - `OPENCLAW_HOOK_BASE_URL` 必须是 `http://` 或 `https://`。
- `No records matched BelongToLocationID=...`
  - 消息里没有匹配位置的告警记录，被过滤跳过。
