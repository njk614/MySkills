# 睿思孪易产品告警推送技能包部署指南

## 1. 安装 Hook 包

```powershell
$zip = Get-ChildItem . -Recurse -Filter ruisi-twinioc-alarm-hook.zip | `
  Sort-Object LastWriteTime -Descending | `
  Select-Object -First 1 -ExpandProperty FullName

openclaw hooks install $zip
```

安装后重启 Gateway。

## 2. 配置 `openclaw.json`

请确保：

- `hooks.enabled = true`
- `hooks.token` 已配置
- `hooks.token` 与 `gateway.auth.token` 不同

并在 `hooks.internal.entries.ruisi-twinioc-alarm-hook.env` 中配置：

- `OPENCLAW_HOOK_TOKEN`（与 `hooks.token` 一致）
- `ALERT_RECIPIENTS_JSON`
- 可选：`OPENCLAW_HOOK_BASE_URL`
- 可选：`OPENCLAW_CLI_BIN`（默认 `openclaw`）

最小示例：

```json
{
  "gateway": {
    "auth": {
      "token": "gateway-token-abc"
    }
  },
  "hooks": {
    "enabled": true,
    "token": "hooks-token-xyz",
    "internal": {
      "enabled": true,
      "entries": {
        "ruisi-twinioc-alarm-hook": {
          "enabled": true,
          "env": {
            "OPENCLAW_HOOK_TOKEN": "hooks-token-xyz",
            "ALERT_RECIPIENTS_JSON": "[{\"channel\":\"xmpp\",\"to\":\"demo01@im.tuguan.net\"}]",
            "OPENCLAW_CLI_BIN": "openclaw"
          }
        }
      }
    }
  }
}
```

## 3. `ALERT_RECIPIENTS_JSON` 规则

- 必须是 JSON 数组字符串
- 每一项必须包含：
  - `channel`：已启用通道（如 `xmpp`、`feishu`）
  - `to`：该通道目标 ID

示例：

```json
"ALERT_RECIPIENTS_JSON": "[{\"channel\":\"xmpp\",\"to\":\"demo01@im.tuguan.net\"},{\"channel\":\"feishu\",\"to\":\"ou_xxx\"}]"
```

## 4. 运行机制（重要）

当前版本采用“触发与发送解耦”：

1. 告警固定文案先用 `openclaw message send` 发送给接收方。
2. 再调用 `POST /hooks/agent`，并设置 `deliver=false`，仅触发规则/skill。

说明：
- 固定文案模板：`🚨 通知：{孪生体实例名称} 发生了告警`
- `/hooks/agent` 调用失败不会阻断固定告警发送（优先保证告警可见性）
- 同签名告警触发采用 `agentTriggerSignature` 去重

## 5. 验证

重启后检查：

- `openclaw hooks list` 显示 `ruisi-twinioc-alarm-hook` 为 `ready`
- 日志目录：`.openclaw-ruisi-twinioc-alarm-hook`
- 日志关键字：
  - `flow=fixed_send`
  - `flow=agent_trigger`
  - `event=invalid_message_template|fixed_send_failed|agent_trigger_failed|completed`

## 6. 常见问题

- `Missing required OPENCLAW_HOOK_TOKEN`
  - 检查 `env.OPENCLAW_HOOK_TOKEN` 是否为空，是否与 `hooks.token` 一致
- `Invalid OPENCLAW_CLI_BIN value`
  - 检查 `OPENCLAW_CLI_BIN` 是否为空，或命令是否可执行
- `status=401/403`（agent 触发）
  - 多为 token 不一致或无效
- `status=404`（agent 触发）
  - 多为 hooks 未启用或 `OPENCLAW_HOOK_BASE_URL` 错误
