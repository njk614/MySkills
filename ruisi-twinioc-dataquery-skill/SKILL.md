---
name: ruisi-twinioc-dataquery-skill
description: Use this skill for all read-only data query and information-retrieval operations on the TwinEasy platform. Handles temperature sensor readings, scene configuration, twin instance lists, environment sensor data, and camera instance names. Does NOT send any control instructions — pure query layer only. Use when users ask about current temperature, scene structure, what layers/charts/twins exist, environment data, or available camera names.
---

# 睿思孪易产品数据获取技能包

> **⚠️ 约束（最高优先级）**
>
> 1. 本 Skill **只做查询，不发送任何控制指令**。
> 2. 所有查询必须通过运行 `scripts/query.py` 脚本完成，禁止直接构造 HTTP 请求。
> 3. 脚本返回 JSON，从中读取结果后继续回复，**不得在未运行脚本的情况下自行推测数据值**。

## Overview

本 Skill 整合了孪易平台所有**只读数据查询**能力，包括：

| 查询类型       | 说明                                                     |
| -------------- | -------------------------------------------------------- |
| 温度传感器     | 按设备安装位置或孪生体实例名称查询当前温度               |
| 场景信息       | 获取场景完整配置（层级、主题、图层、图表、孪生体类别等） |
| 孪生体实例列表 | 按类别名称查询该类别下所有实例                           |
| 层级孪生体类别 | 按层级名称查询该层所有孪生体类别                         |
| 摄像头实例名称 | 获取当前场景绑定的所有摄像头实例名称列表                 |

**与其他 Skill 的职责边界：**

- 本 Skill 负责**查询与信息获取**，获取到数据后如需执行控制指令，再转交 `twinioc-interactive-command` 或 `video-surveillance-command`。
- 温控执行（打开温控器、关灯等）属于 `twinioc-interactive-command`，不在本 Skill 范围内。
- 摄像头视频流切换、视频布局控制属于 `video-surveillance-command`。

## When To Use

在以下场景触发本 Skill：

- 用户询问当前温度、某位置温度（"大厅东侧温度多少？"）
- 用户询问场景有哪些层级、图层、图表、主题
- 用户需要知道某类别下有哪些孪生体实例（"这个场景里有哪些摄像头？"）
- 用户需要查询环境传感器数据（"环境传感器3的湿度是多少？"）
- 其他 Skill 在生成指令前需要获取名称列表（如 twinioc-interactive-command 需要实例名）

不要在以下情况触发本 Skill：

- 用户已明确要求执行控制操作（切换场景、打开灯、发送指令等）
- 纯闲聊或非孪易平台查询

## Required Inputs

- `token`：场景 token（可用默认值 `gj6mxa`）。
- `query`：用户自然语言问题，用于判断查询类型及参数。

## Available Queries & Script Usage

### 1. 温度传感器查询

**触发条件**：用户询问温度，如"大厅东侧现在多少度？""会议室温度高吗？"

```bash
# 按设备位置或名称查询
python scripts/query.py temperature --token <token> --device-query "大厅东侧"

# 不指定设备时使用默认台账
python scripts/query.py temperature --token <token>
```

**返回 JSON：**

```json
{
  "success": true,
  "reply": "大厅东侧当前温度23.5℃"
}
```

设备解析逻辑来自 `temperature-sensor-instruction/data_organized.json`：

- `--device-query` 支持安装位置（如"大厅东侧"）或孪生体实例名称（如"环境传感器5"）。
- 无法匹配时 `reply` 为"设备不存在。"或"当前位置没有设备。"。
- 多设备匹配时提示歧义。

**可选参数：**

- `--location-id`（默认 `dyo6vaow6203kx09`）
- `--timeout`（默认 100 秒）
- `--max-attempts`（默认 5 次）

---

### 2. 场景完整配置

**触发条件**：用户询问场景概况、有哪些层级、图层、图表、孪生体类别等。

```bash
python scripts/query.py mcp --token <token> --mcp-tool get_scene_info
```

返回场景完整配置 JSON（层级名称、主题列表、图层、图表、孪生体类别等）。

---

### 3. 孪生体实例列表（按类别）

**触发条件**：用户询问"有哪些XX？"，如"有哪些摄像头？""有哪些环境传感器？"

```bash
python scripts/query.py mcp --token <token> \
  --mcp-tool get_twin_category_data \
  --mcp-args '{"twinCategoryName": "可控摄像头"}'
```

返回该类别下所有孪生体实例名称列表。

---

### 4. 层级下的孪生体类别

**触发条件**：用户询问某层级有哪些孪生体类别。

```bash
python scripts/query.py mcp --token <token> \
  --mcp-tool get_twin_category \
  --mcp-args '{"levelName": "楼层8"}'
```

---

### 5. 摄像头实例名称列表

**触发条件**：用户询问"有哪些摄像头？""摄像头名称是什么？"，或 `video-surveillance-command` 请求摄像头列表。

```bash
python scripts/query.py mcp --token <token> --mcp-tool get_bind_video_instance_names
```

返回当前场景绑定的所有摄像头实例名称。

---

## Query Workflow

### 1. 识别查询类型

根据用户输入判断属于上方哪种查询，确定 `--mcp-tool` 名称或使用 `temperature` 模式。

### 2. 执行查询脚本

运行对应的 `scripts/query.py` 命令，等待 JSON 结果。

### 3. 解析结果

- `temperature` 模式：读取 `reply` 字段，直接向用户展示。
- `mcp` 模式：解析返回的 JSON，提取用户关心的字段，用中文自然语言整理后回复。

### 4. 后续处理（可选）

若查询结果需要进一步执行控制指令，将数据传递给 `twinioc-interactive-command` 或 `video-surveillance-command`。

## Output Rules

1. 温度回复直接使用 `reply` 字段内容，不做修改。
2. MCP 查询结果以中文可读方式整理，不直接将原始 JSON dump 给用户。
3. 查询失败时如实告知用户原因，并提示可能的解决方向（如"设备不存在，可用名称包括……"）。
4. 不输出任何控制指令编码（如 `A03`、`B01`），本 Skill 只负责展示数据。

## Configuration Defaults

| 参数                     | 默认值                                               |
| ------------------------ | ---------------------------------------------------- |
| token                    | `gj6mxa`                                             |
| base-url                 | `http://test.twinioc.net/api/editor/v1`              |
| location-id              | `dyo6vaow6203kx09`                                   |
| MCP base-url             | `http://test.twinioc.net/api/editor/mcp`             |
| temperature level-id     | `gez4ermd715t31le`                                   |
| default target ledger-id | `R3nazZz8Pyb6o7uc`                                   |
| device catalog           | `temperature-sensor-instruction/data_organized.json` |
