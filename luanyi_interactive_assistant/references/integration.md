# 集成说明

## 目标

保持两套输出同时成立：

1. 面向用户的可读中文结果
2. 面向执行接口的原始编码指令

## 原始响应分段格式

兼容格式如下：

```text
{
"response": "您好我是孪易交互助手，正在执行任务，请稍等~"
}THISSECTIONEND{
"response": "根据最优策略，已经为您规划如下执行计划：\n1、场景复位"
}THISSECTIONEND
AGENTEND
```

## 分段规则

按固定顺序输出：

1. 问候 JSON
2. `THISSECTIONEND`
3. 计划结果 JSON
4. `THISSECTIONEND`
5. 换行后 `AGENTEND`

## HTTP 执行请求

### 请求方法

- `POST`

### 请求路径

- `/v1/location/SendInstruction`

### 请求头

- `Content-Type: application/json`
- `Accept: text/plain`

### 请求体

```json
{
  "token": "场景 token",
  "jsonData": "instruction_order$&query$&plan_text"
}
```

### 字段解释

- `instruction_order`：带编码的执行指令串，如 `A09` 或 `A36：告警信息：当前$A38：告警信息选中`
- `query`：原始用户问题
- `plan_text`：中文展示文本，不带编码

## 关键原则

### 展示文本

必须：

- 不带 `A/B/C/D` 编码
- 中文可读
- 与原工作流展示风格一致

### 执行文本

必须：

- 保留原始指令编码
- 可直接拼入 `jsonData`

## 示例

### 示例 1：场景复位

- `instruction_order`: `A09`
- `plan_text`: `根据最优策略，已经为您规划如下执行计划：\n1、场景复位`
- `jsonData`: `A09$&场景复位$&根据最优策略，已经为您规划如下执行计划：\n1、场景复位`

### 示例 2：告警截图

- `instruction_order`: `A36：告警信息：当前$A38：告警信息选中$A39：告警截图：打开`
- `plan_text`: `根据最优策略，已经为您规划如下执行计划：\n1、告警信息：当前\n2、告警信息选中\n3、告警截图：打开`

## 历史上下文

如宿主系统支持会话状态，保存：

- `historyUser`: 最近问题与原始方括号指令内容
- `historyInter`: 工具调用名与工具返回结果
- `sceneInfo`: 最近场景配置
- `tokenJudge`: 最近一次 token

建议最多保留最近 20 条记录。

## 参考执行入口

当前 Skill 包已提供可执行脚本：

- [scripts/invoke_skill.py](../scripts/invoke_skill.py)：命令行调用入口
- [scripts/skill_runtime.py](../scripts/skill_runtime.py)：核心运行时实现

命令行示例：

```text
python scripts/invoke_skill.py --query "打开当前告警并查看截图" --token "场景 token" --session-id "test-session"
```

如仅验证推理与格式化，不实际发送 `SendInstruction`，可使用：

```text
python scripts/invoke_skill.py --query "切换到下一层" --token "场景 token" --no-execute
```
