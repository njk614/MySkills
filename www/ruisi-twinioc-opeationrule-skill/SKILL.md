---
name: ruisi-twinioc-opeationrule-skill
description: Use this skill to record user queries that ask what operation to perform in response to a temperature reading or an alarm event, or that set up a scheduled/recurring task rule. Supports both Chinese and English rule text for temperature and alarm scenarios. Only record these three scenarios. Also trigger when the user asks to view, search, or list all recorded rules or operation history.
---

# 睿思孪易产品操作规则记录技能包

本 Skill 负责记录用户**针对温度数据或告警事件询问应执行何种操作**，或**设定定时任务规则**时的提问及 AI 返回的执行计划，并提供历史查询功能。

## 基础地址说明

- 本 Skill 不直接调用 TwinEasy 的 `/api/editor/*` HTTP 接口，因此不消费 `base_url`。
- 它只读写本地规则记录，并被 `ruisi-twinioc-dataquery-skill`、`ruisi-twinioc-command-skill` 或 `ruisi-twinioc-alarm-hook` 以本地脚本方式调用。
- 如果上游目录传入了 `base_url`，无需向本 Skill 继续透传。

对于温度规则，本 Skill 现在还承担两项运行时能力：

- 写入时自动把自然语言规则解析为结构化条件，例如“设备 + 比较符 + 阈值 + 动作”。
- 在温度查询完成后，按“当前设备名 + 当前温度值”匹配已记录规则，并返回确认话术。

对于温度规则和告警规则，本 Skill 目前已支持以下多语言能力：

- 支持中文、英文规则文本解析，例如“当大会议室温度大于20度时关闭照明灯”和 “When the Large Meeting Room temperature is above 20 degrees then turn off the lights”。
- 温度规则匹配可借助传感器位置别名做中英文归一，因为温度查询最终按传感器台账 ID 命中。
- 除温度传感器位置外，其他实体仍按当前语言中的实际名称参与匹配，不额外建立通用中英对应关系。

## When To Use

**只在以下三种场景写入记录：**

1. 用户的问题是**以温度为条件、指定要执行什么操作**的，且 AI 成功返回执行计划 → `--source temperature`
   - ✅ 记录："当大会议室温度大于20度时，打开大会议室温控器"

- ✅ 记录："When the Large Meeting Room temperature is above 20 degrees then turn on the air conditioner"
- ✅ 记录："温度太高了，帮我把温控器打开"
- ❌ 不记录："大会议室当前的温度是多少？"（纯查询，无操作指令）

2. 用户的问题是**以告警事件为条件、指定要执行什么操作**的，且 AI 成功返回执行计划 → `--source alarm`
   - ✅ 记录："告警了，帮我关闭大会议室的灯"

- ✅ 记录："When the Large Meeting Room camera alarm occurs then turn on the lights"
- ✅ 记录："出现告警后执行场景复位"
- ❌ 不记录："当前有哪些告警？"（纯查询，无操作指令）

3. 用户要求**设定定时/周期性任务规则**的，且 AI 成功返回执行计划 → `--source schedule`
   - ✅ 记录："帮我设置一个定时任务，每隔1小时查一下大会议室温度"
   - ✅ 记录："每天上午9点自动打开大会议室的灯"
   - ✅ 记录："每隔30分钟检查一次设备告警状态"
   - ❌ 不记录："现在大会议室的灯是开着的吗？"（非定时规则）

**核心判断依据：用户的输入中是否包含"基于温度/告警场景要执行某个操作"或"设定周期/定时执行规则"的意图。纯查询类问题不记录。**

**不记录：**

- 与告警/温度/定时规则无关的用户操作
- 单纯查询温度数值（如"XX区域温度是多少"）
- 单纯查询告警信息（如"有哪些告警"、"告警详情是什么"）
- 指令执行失败的结果

**容量上限：**

- `alarm` 类型最多保留 **100** 条，超出时自动丢弃最旧的一条
- `temperature` 类型最多保留 **100** 条，超出时自动丢弃最旧的一条
- `schedule` 类型最多保留 **100** 条，超出时自动丢弃最旧的一条

用户查询操作历史或规则记录时（如"最近执行了哪些操作"、"今天的告警处理记录"、"记录了哪些规则"、"有哪些定时任务规则"、"帮我列一下所有规则"）也触发本 Skill。

## 查询结果展示规则

### 普通查询（按时间顺序）

运行查询脚本得到 JSON 后，**不要把原始 JSON 直接展示给用户**，必须转换为中文可读格式：

```
共 {total} 条记录：

1. [{time}] [{source_label}] {query}

2. [{time}] [{source_label}] {query}
...
```

- `{source_label}`：`alarm` 显示为 `告警触发`，`temperature` 显示为 `温度查询`，`schedule` 显示为 `定时任务`
- `{time}`：将 UTC 时间转换为北京时间（+8h），格式 `YYYY-MM-DD HH:MM`
- `{instruction}` 多行时保持换行展示
- 如果没有记录，回复：`暂无历史操作记录。`

### 按分类查看所有规则（当用户询问"记录了哪些规则"、"有哪些规则"时使用）

依次对每个 source 分类调用一次查询脚本，然后**按分类分组**展示，每组内按时间从旧到新排列：

**调用方式：**

```bash
python scripts/invoke_recorder.py --query-log --source temperature --last 20
python scripts/invoke_recorder.py --query-log --source alarm --last 20
python scripts/invoke_recorder.py --query-log --source schedule --last 20
```

**展示格式：**

```
📋 已记录规则共 {total} 条：

【温度查询规则】（共 N 条）
1. [{time}] {query}
2. ...

【告警触发规则】（共 N 条）
1. [{time}] {query}
2. ...

【定时任务规则】（共 N 条）
1. [{time}] {query}
2. ...
```

- 某分类无记录时，显示该分类标题后写：`暂无记录`
- 所有分类均无记录时，回复：`暂无任何已记录规则。`

## 字段说明

每条记录包含以下字段：

| 字段     | 说明                | 示例                                 |
| -------- | ------------------- | ------------------------------------ |
| `time`   | ISO 8601 UTC 时间戳 | `2026-03-13T09:19:59Z`               |
| `source` | 触发来源            | `alarm` / `temperature` / `schedule` |
| `token`  | 场景 token          | `kqq1po`                             |
| `query`  | 用户原始输入文字    | `当大会议室温度大于20度时打开温控器` |

温度规则或告警规则记录若可解析，还会额外包含：

| 字段                   | 说明                                          | 示例                 |
| ---------------------- | --------------------------------------------- | -------------------- |
| `parsed_rule`          | 结构化温度规则，仅温度规则有                  | 见下方示例           |
| `device_name`          | 规则中原始设备/区域名称                       | `大会议室`           |
| `standard_device_name` | 归一后的后端标准实体名称                      | `Large Meeting Room` |
| `operator`             | 比较运算符                                    | `gt` / `lte`         |
| `threshold`            | 阈值                                          | `20.0`               |
| `action_text`          | 匹配后建议执行的动作文本                      | `关闭照明灯`         |
| `execute_query`        | 用户确认后可直接交给 command skill 的执行语句 | `关闭大会议室照明灯` |

`parsed_rule` 示例：

```json
{
  "kind": "temperature_threshold",
  "device_name": "大会议室",
  "standard_device_name": "Large Meeting Room",
  "operator": "gt",
  "operator_text": "大于",
  "threshold": 20.0,
  "threshold_text": "20",
  "action_text": "关闭照明灯",
  "execute_query": "关闭大会议室照明灯"
}
```

## 脚本调用方式

### 写入一条记录

```bash
python scripts/invoke_recorder.py --write \
  --token <token> \
  --source <alarm|temperature|schedule> \
  --query "用户输入文字"
```

### 查询历史记录

```bash
# 查询最近 N 条（默认 20）
python scripts/invoke_recorder.py --query-log --last 20

# 按 token 过滤
python scripts/invoke_recorder.py --query-log --token <token>

# 按日期过滤（格式 YYYY-MM-DD）
python scripts/invoke_recorder.py --query-log --date 2026-03-13

# 按触发来源过滤
python scripts/invoke_recorder.py --query-log --source alarm

# 组合过滤 + 导出 CSV
python scripts/invoke_recorder.py --query-log --token <token> --date 2026-03-13 --format csv
```

### 按当前温度匹配规则

当 `ruisi-twinioc-dataquery-skill` 已经查到当前温度后，调用：

```bash
python scripts/invoke_recorder.py --match-temperature \
  --token <token> \
  --device-name "大会议室" \
  --temperature-value 25
```

返回 JSON：

```json
{
  "total": 1,
  "matches": [
    {
      "time": "2026-03-18T09:00:00Z",
      "source": "temperature",
      "query": "当大会议室温度大于20度时关闭照明灯",
      "parsed_rule": {
        "device_name": "大会议室",
        "standard_device_name": "Large Meeting Room",
        "operator": "gt",
        "operator_text": "大于",
        "threshold": 20.0,
        "action_text": "关闭照明灯",
        "execute_query": "关闭大会议室照明灯"
      },
      "current_temperature": 25,
      "confirmation_text": "当前大会议室25℃，大于规则设定的大于20℃，关闭照明灯，请确认是否执行？"
    }
  ]
}
```

### 保存待确认动作

当温度查询命中规则且需要等待用户“是/否”确认时，调用：

```bash
python scripts/invoke_recorder.py --save-pending \
  --token <token> \
  --source temperature \
  --confirmation-text "当前大会议室25℃，大于规则设定的大于20℃，关闭照明灯，请确认是否执行？" \
  --execute-query "关闭大会议室照明灯" \
  --matched-rule-json '{"query":"当大会议室温度大于20度时关闭照明灯"}'
```

### 读取待确认动作

当用户下一句只回复“是 / 确认 / 好 / 否 / 取消”时，先调用：

```bash
python scripts/invoke_recorder.py --get-pending --token <token>
```

返回 JSON：

```json
{
  "success": true,
  "pending": {
    "time": "2026-03-18T09:05:00Z",
    "source": "temperature",
    "confirmation_text": "当前大会议室25℃，大于规则设定的大于20℃，关闭照明灯，请确认是否执行？",
    "execute_query": "关闭大会议室照明灯"
  }
}
```

### 清理待确认动作

用户确认执行后，或明确取消后，调用：

```bash
python scripts/invoke_recorder.py --clear-pending --token <token>
```

## 返回格式

### 写入成功

```json
{"success": true, "record": { ...记录内容... }}
```

### 查询结果

```json
{
  "total": 5,
  "records": [
    {"time": "...", "source": "...", "query": "..."},
    ...
  ]
}
```

## 记录文件存储位置

- 默认路径：`ruisi-twinioc-opeationrule-skill/.logs/operations.jsonl`
- 每行一条 JSON 记录（JSON Lines 格式），追加写入。
- 待确认动作默认路径：`ruisi-twinioc-opeationrule-skill/.runtime/pending_confirmations.json`
