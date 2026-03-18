---
name: ruisi-twinioc-opeationrule-skill
description: Use this skill to record user queries that ask what operation to perform in response to a temperature reading or an alarm event, or that set up a scheduled/recurring task rule. Only record these three scenarios. Also trigger when the user asks to view, search, or list all recorded rules or operation history.
---

# 睿思孪易产品操作规则记录技能包

本 Skill 负责记录用户**针对温度数据或告警事件询问应执行何种操作**，或**设定定时任务规则**时的提问及 AI 返回的执行计划，并提供历史查询功能。

## When To Use

**只在以下三种场景写入记录：**

1. 用户的问题是**以温度为条件、指定要执行什么操作**的，且 AI 成功返回执行计划 → `--source temperature`
   - ✅ 记录："当大会议室温度大于20度时，打开大会议室温控器"
   - ✅ 记录："温度太高了，帮我把温控器打开"
   - ❌ 不记录："大会议室当前的温度是多少？"（纯查询，无操作指令）

2. 用户的问题是**以告警事件为条件、指定要执行什么操作**的，且 AI 成功返回执行计划 → `--source alarm`
   - ✅ 记录："告警了，帮我关闭大会议室的灯"
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
