---
name: operation-logger
description: Use this skill to log the first user instruction that follows an alarm event or a temperature query, along with the AI-generated execution result. Only log these two scenarios. Also trigger when the user asks to view or search operation history.
---

# 操作日志记录助手

本 Skill 负责记录**告警触发后**或**温度查询后**用户发出的第一条操作指令及 AI 返回的执行计划，并提供历史查询功能。

## When To Use

**只在以下两种场景写入日志：**

1. **告警产生后**，用户发出第一条操作指令，且 AI 成功返回执行计划 → `--source alarm`
2. **温度查询后**，用户发出第一条操作指令，且 AI 成功返回执行计划 → `--source temperature`

**不记录：**

- 与告警/温度无关的用户操作
- 指令执行失败的结果
- 后续连续操作（只记录第一条）

**容量上限：**

- `alarm` 类型最多保留 **20** 条，超出时自动丢弃最旧的一条
- `temperature` 类型最多保留 **20** 条，超出时自动丢弃最旧的一条

用户查询操作历史时（如"最近执行了哪些操作"、"今天的告警处理记录"）也触发本 Skill。

## 查询结果展示规则

运行查询脚本得到 JSON 后，**不要把原始 JSON 直接展示给用户**，必须转换为中文可读格式：

```
共 {total} 条记录：

1. [{time}] [{source_label}] {query}
   执行计划：{instruction}

2. [{time}] [{source_label}] {query}
   执行计划：{instruction}
...
```

- `{source_label}`：`alarm` 显示为 `告警触发`，`temperature` 显示为 `温度查询`
- `{time}`：将 UTC 时间转换为北京时间（+8h），格式 `YYYY-MM-DD HH:MM`
- `{instruction}` 多行时保持换行展示
- 如果没有记录，回复：`暂无历史操作记录。`

## 日志字段说明

每条记录包含以下字段：

| 字段          | 说明                                   | 示例                                                                      |
| ------------- | -------------------------------------- | ------------------------------------------------------------------------- |
| `time`        | ISO 8601 UTC 时间戳                    | `2026-03-13T09:19:59Z`                                                    |
| `source`      | 触发来源                               | `alarm` / `temperature`                                                   |
| `token`       | 场景 token                             | `kqq1po`                                                                  |
| `query`       | 用户原始输入文字                       | `关闭大会议室灯开关`                                                      |
| `instruction` | AI 生成的中文可读执行计划（plan_text） | `根据最优策略，已经为您规划如下执行计划：\n1、关闭灯：大会议室照明灯开关` |

## 脚本调用方式

### 写入一条记录

```bash
python scripts/invoke_logger.py --write \
  --token <token> \
  --source <alarm|temperature> \
  --query "用户输入文字" \
  --instruction "AI生成的中文执行计划"
```

### 查询历史记录

```bash
# 查询最近 N 条（默认 20）
python scripts/invoke_logger.py --query-log --last 20

# 按 token 过滤
python scripts/invoke_logger.py --query-log --token <token>

# 按日期过滤（格式 YYYY-MM-DD）
python scripts/invoke_logger.py --query-log --date 2026-03-13

# 按触发来源过滤
python scripts/invoke_logger.py --query-log --source alarm

# 组合过滤 + 导出 CSV
python scripts/invoke_logger.py --query-log --token <token> --date 2026-03-13 --format csv
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
    {"time": "...", "source": "...", "token": "...", "query": "...", "instruction": "..."},
    ...
  ]
}
```

## 日志文件存储位置

- 默认路径：`operation-logger/.logs/operations.jsonl`
- 每行一条 JSON 记录（JSON Lines 格式），追加写入。
