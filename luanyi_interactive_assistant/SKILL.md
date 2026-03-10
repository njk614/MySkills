---
name: luanyi-interactive-assistant
description: This skill should be used when users need to convert Chinese natural-language TwinEasy scene interaction requests into executable command sequences, produce segmented response text compatible with the existing front-end format, and prepare or send the SendInstruction HTTP payload.
---

# 孪易交互助手

## Overview

处理孪易场景交互请求时，执行“理解用户意图 → 生成标准指令串 → 输出中文执行计划 → 组织 HTTP 请求体 → 产出分段返回”的完整流程。

优先保证两件事：

1. 面向用户的返回内容不带指令编码，只展示中文可读结果。
2. 面向执行接口的 `instruction_order` 和 `jsonData` 保留完整指令编码。

## When To Use

在以下场景触发本 Skill：

- 需要把中文自然语言转换为孪易标准指令。
- 需要根据已有场景信息、历史操作、工具结果推断最合理的执行指令。
- 需要输出与既有前端兼容的 `THISSECTIONEND` / `AGENTEND` 分段结果。
- 需要组织或发送 `POST /v1/location/SendInstruction` 请求。
- 需要区分“用户可见文本”和“执行用指令编码”。

不要在纯闲聊、无孪易场景控制需求、也无指令执行需求的场景触发本 Skill。

## Required Inputs

处理时默认具备以下输入：

- `query`：用户自然语言问题或控制指令。
- `token`：场景 token，用于工具调用与发送执行请求。
- `session_id`：会话标识，用于关联上下文与历史记录。
- `sceneInfo`：场景配置、层级、主题、图层、图表、孪生体类别等信息。
- `historyUser`：历史用户问题与历史指令内容。
- `historyInter`：历史工具调用记录。

如果宿主系统没有提前注入 `sceneInfo`、`historyUser`、`historyInter`，可直接调用 [scripts/invoke_skill.py](scripts/invoke_skill.py)；脚本会自动完成会话缓存、场景信息拉取、工具调用、模型推理与指令发送。

## Core Workflow

### 1. 识别请求目标

先判断用户是在做哪一类事情：

- 场景控制
- 层级切换
- 图层控制
- 图表控制
- 环境控制
- 演示汇报
- 告警处理
- 对象聚焦/选中/搜索
- 灯光控制
- 主题切换/主题生成
- 查询类问题

### 2. 结合上下文推断参数

解析需要参数的指令时，优先使用：

1. 当前问题中的显式信息。
2. `historyUser` 中最近一次相关操作。
3. `historyInter` 中已有工具结果。
4. `sceneInfo` 中可用名称列表。

如果仍无法确认名称类参数，返回“场景中没有找到匹配的信息”及相关候选数据，并放入一组 `[]` 中直接输出，不伪造指令。

### 3. 生成标准指令串

按孪易指令规范生成原始执行指令，格式示例：

- `[A03]`
- `[A36：告警信息：当前&A38：告警信息选中]`
- `[A01：功能切换：分析$C01：主题切换：园区概况]`

多指令按 `$` 连接；方括号中的并列片段按原有规范保留。

### 4. 生成用户可见计划文本

将原始指令转换为中文计划文本时：

- 保留动作语义。
- 去掉指令编码，如 `A03`、`B02`、`C01`。
- 保留参数值，如“下一层”“摄像头01”“园区概况”。

例如：

- `A03` → `层级切换：下一层`
- `A08：场景旋转：开始` → `场景旋转：开始`
- `B07：打开灯：1F走廊灯` → `打开灯：1F走廊灯`

最终使用以下格式：

`根据最优策略，已经为您规划如下执行计划：\n1、...\n2、...`

查询类 `D01` 不加“规划如下执行计划”前缀，直接输出查询内容。

### 5. 组织前端分段响应

始终按以下顺序拼接：

1. 问候段
2. `THISSECTIONEND`
3. 计划结果段
4. `THISSECTIONEND`
5. `AGENTEND`

格式必须与既有系统兼容，具体结构见 [references/integration.md](references/integration.md)。

### 6. 组织或发送 HTTP 执行请求

需要执行时，按以下规则组织请求：

- 方法：`POST`
- 路径：`/v1/location/SendInstruction`
- 请求体字段：
  - `token`
  - `jsonData`

其中 `jsonData` 必须使用：

`instruction_order$&query$&plan_text`

注意：

- `instruction_order` 保留指令编码。
- `plan_text` 使用中文展示文本。
- 不要把仅用于展示的文本替换掉原始执行指令。

### 7. 执行层脚本

完整执行逻辑位于：

- [scripts/skill_runtime.py](scripts/skill_runtime.py)：工作流核心运行时，负责会话状态、MCP 工具调用、LLM tool calling、执行计划生成与 `SendInstruction` 调用。
- [scripts/invoke_skill.py](scripts/invoke_skill.py)：命令行入口，适合被宿主系统、测试脚本或 API 包装层直接调用。
- [scripts/requirements.txt](scripts/requirements.txt)：当前执行脚本依赖。

典型调用方式：

- `python scripts/invoke_skill.py --query "切换到下一层" --token "<scene-token>" --session-id "demo-session"`
- 如只想验证指令生成而不下发执行，可追加 `--no-execute`

## Output Requirements

### 用户可见文本

必须：

- 不带指令编码。
- 中文可读。
- 与原工作流结果风格一致。

禁止：

- 输出 `A09`、`A03`、`B07` 这类裸编码给用户。
- 把“开始/停止/名称”等参数留空。

### 执行指令文本

必须：

- 保留完整编码。
- 能直接用于 `SendInstruction`。

## Command Handling Rules

处理命令时遵循：

- 无参数固定命令：直接转换为固定中文文本。
- 带参数命令：必须从模型解析结果中读取参数，不在代码层伪造默认参数。
- 查询类命令：直接输出查询结果，不走“规划执行计划”前缀。

完整指令说明见 [references/command-rules.md](references/command-rules.md)。

## Failure Handling

遇到以下情况时，不要硬编结果：

- 需要名称类参数但未匹配到有效名称。
- 需要状态类参数但未判断出具体值。
- 指令仅返回编码但按规则必须带参数。

此时应明确指出失败原因或未匹配信息，而不是返回错误的伪结果。

## Resources

### references/command-rules.md

存放完整指令分类、无参数指令、带参数指令、展示文本规则。

### references/integration.md

存放响应结构、HTTP 请求格式、字段用途与示例。

### scripts/skill_runtime.py

存放与原工作流等价的可执行实现。

### scripts/invoke_skill.py

提供可直接调用的命令行入口。
