# alarm-mqtt-hook 部署说明（CLI 直发模式）

## 1. 功能

- 订阅 MQTT 告警消息
- 识别到告警后，执行 `openclaw message send` 直发到客户端
- 消息固定三行中文模板，不走 agent 改写

## 2. 必须配置

### 2.1 OpenClaw 运行前提

- 机器上可执行 `openclaw` 命令
- `openclaw message send` 可正常发送消息（先手工验证一次）

可先执行：

```bash
openclaw message send --channel feishu --target ou_xxx --message "测试消息"
```

### 2.2 hook 环境变量（必填）

- `ALERT_RECIPIENTS_JSON`
  - JSON 数组字符串
  - 每项必须是 `{"channel":"...","to":"..."}`

示例：

```json
"ALERT_RECIPIENTS_JSON": "[{\"channel\":\"feishu\",\"to\":\"ou_xxx\"}]"
```

## 3. 可选配置（仅在需要时设置）

- `OPENCLAW_CLI_BIN`（默认 `openclaw`）
- `MQTT_URL`（默认 `mqtts://y9afbaf6.ala.cn-hangzhou.emqxsl.cn:8883`）
- `MQTT_USERNAME`（默认 `twinioc`）
- `MQTT_PASSWORD`（默认 `abc123`）
- `MQTT_TOPIC`（默认 `twineasy/location/dyo6vaow6203kx09/alarm/changed/v1`）
- `MQTT_QOS`（默认 `1`）
- `MQTT_LOG_LEVEL`（默认 `info`）
- `HTTP_TIMEOUT_SECONDS`（默认 `10`）
- `ALERT_TITLE`（默认 `告警通知`）

## 4. 最小可用配置

```json
{
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": {
        "alarm-mqtt-hook": {
          "enabled": true,
          "env": {
            "ALERT_RECIPIENTS_JSON": "[{\"channel\":\"feishu\",\"to\":\"ou_xxx\"}]"
          }
        }
      }
    }
  }
}
```

## 5. 安装与启动

1. 在 `hooks/alarm-mqtt-hook` 目录执行：

```bash
npm install
```

2. 保存配置并重启 OpenClaw Gateway。
3. 查看日志：
   - `E:\Desktop\skill\.openclaw-alarm-mqtt\subscriber.log`

## 6. 成功日志特征

- MQTT 连接成功：
  - `Connected to mqtts://...`
  - `Subscribed to ... with qos=1`
- 推送成功：
  - `push mode=cli ... ok=true ... cmd="openclaw message send ..."`

## 7. 常见问题

- `spawn ENOENT` / `openclaw is not recognized`  
  - 说明找不到 CLI，设置 `OPENCLAW_CLI_BIN` 为可执行文件完整路径，或修复 PATH。

- 有 MQTT 告警但不推送  
  - 检查 `ALERT_RECIPIENTS_JSON` 格式是否正确。
  - 空数据（`{}`、`[]`、`null`）会被判定为无告警并跳过。

- 推送文案不对  
  - 当前固定模板是三行中文，若实际不一致，先确认日志中是 `push mode=cli`。
