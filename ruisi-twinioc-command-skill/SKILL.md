---
name: ruisi-twinioc-command-skill
description: This skill should be used when users need to convert Chinese natural-language TwinEasy scene interaction or video surveillance requests into executable command sequences and send them. Handles A/B/C/D scene interaction instructions AND E-series video surveillance instructions. All instruction generation, execution planning, and SendInstruction dispatching is handled here. Data queries are delegated to the ruisi-twinioc-dataquery-skill skill. The AI handles all reasoning; the Python runtime is a pure execution layer.
---

# 睿思孪易产品指令技能包

> **⚠️ 强制约束（最高优先级，任何情况下不得违反）**
>
> 1. **禁止**用 curl、HTTP 请求或任何其他方式直接调用孪易接口。
> 2. **所有数据查询**（场景信息、孪生体实例列表、传感器数据等）必须通过 `ruisi-twinioc-dataquery-skill` Skill 的 `query.py` 脚本完成：
>    ```
>    python ../ruisi-twinioc-dataquery-skill/scripts/query.py mcp --token <token> --mcp-tool <工具名> [--mcp-args '{"参数":"值"}']
>    ```
> 3. **所有指令执行**（A/B/C/D 系列与 E 系列）必须通过本 Skill 自身的执行脚本完成：
>    ```
>    python scripts/invoke_skill.py --token <token> --query "..." --agent-output "[指令串]"
>    ```
> 4. 脚本返回 JSON，从中读取数据后继续下一步，**不得在未运行脚本的情况下自行推测结果**。

## Overview

本 Skill 负责将用户的中文自然语言请求转换为孪易平台可执行指令串，并通过 Python 执行层将指令下发到场景。

**架构说明（重要）：**

- **加载本文件的 AI（本文档）**：承担全部推理，根据指令库规则独立生成指令串。
- **数据查询层**：所有只读查询委托给 `ruisi-twinioc-dataquery-skill` Skill（`query.py`），本 Skill 不直接访问孪易 MCP/API 接口。
- **指令执行层**：调用本 Skill 自身的 `scripts/invoke_skill.py`，负责 A/B/C/D 与 E 系列指令的 `SendInstruction` HTTP 请求与会话状态管理。

优先保证两件事：

1. 面向用户的返回内容不带指令编码，只展示中文可读结果。
2. 面向执行接口的 `instruction_order` 和 `jsonData` 保留完整指令编码。

## When To Use

在以下场景触发本 Skill：

**场景交互指令（A/B/C/D 系列）：**

- 层级切换、场景复位、图层/图表控制、演示汇报。
- 告警处理（A36/A37/A38/A39 指令）。
- 对象聚焦/选中（B01/B02，含摄像头孪生体对象操作）、搜索、灯光/温控。
- 主题切换/主题生成。
- 询问场景内容、查询孪生体数据等问答类请求（D01）。
- 时间轴播放/暂停/控制（A13/A14 等指令）。

**视频监控指令（E 系列）：**

- 用户明确要求操作**视频画面本身**（切换摄像头视频流、调整视频布局、云台控制）。
- 视频筛选与显示设置、视频翻页与导航、视频轮播控制、视频排序。
- 事件/告警查看（视频面板侧）、事件轮播与筛选。
- 时间模式切换（实时/回放）、回放操作（暂停/播放/跳转/倍速）。
- 单路云台控制（左/右/上/下转、拉近/拉远）。
- 询问摄像头名称列表（E35）、指定摄像头筛选（E34）。

不要在纯闲聊、无孪易场景控制需求、也无指令执行需求的场景触发本 Skill。

**与 `ruisi-twinioc-dataquery-skill` 的边界**：

- 纯查询（无需执行指令） 使用 `ruisi-twinioc-dataquery-skill`。
- 需要执行控制指令（含查询后执行） 使用本 Skill，查询部分委托给 `ruisi-twinioc-dataquery-skill`。

**温度规则联动**：

- 如果 `ruisi-twinioc-dataquery-skill` 的温度查询结果中带有 `rule_match`，说明已经命中 `ruisi-twinioc-opeationrule-skill` 中记录的温度规则。
- 此时先把 `reply` 中附带的确认话术展示给用户，不直接执行。
- 命中规则时，`ruisi-twinioc-dataquery-skill` 会自动把待确认动作写入 `ruisi-twinioc-opeationrule-skill/.runtime/pending_confirmations.json`。
- 当用户下一句只回复“是 / 确认 / 好 / 执行 / 否 / 取消”时，先调用 `python ../ruisi-twinioc-opeationrule-skill/scripts/invoke_recorder.py --get-pending --token <token>` 读取待确认动作。
- 若用户是肯定答复，且返回的 `pending.execute_query` 存在，则使用该值作为新的执行请求进入本 Skill，例如 `关闭大会议室照明灯`、`打开大会议室温控器`；执行后再调用 `--clear-pending` 清理。
- 若用户是否定答复，则调用 `python ../ruisi-twinioc-opeationrule-skill/scripts/invoke_recorder.py --clear-pending --token <token>`，然后回复 `已取消操作`。
- 然后仍按现有规则生成 `B07/B08/B09/B10` 等物理设备指令，并遵守本 Skill 原有的确认与执行流程。

## Required Inputs

处理时默认具备以下输入：

- `query`：用户自然语言问题或控制指令。
- `token`：场景 token，用于查询与执行请求。
- `scene_info`：场景配置、层级、主题、图层、图表、孪生体类别等信息。
- `history_user`：历史用户问题与历史指令内容。
- `history_inter`：历史工具调用记录。

## Core Workflow

### 1. 获取场景上下文

场景上下文由执行层在首次调用时自动加载。如需手动刷新场景信息：

```bash
python ../ruisi-twinioc-dataquery-skill/scripts/query.py mcp --token <token> --mcp-tool get_scene_info
```

获得：

- `scene_info`：场景配置（层级名称、主题、图层、图表、孪生体类别等）
- `history_user`：历史用户问题与对应指令内容
- `history_inter`：历史 MCP 工具调用记录

### 2. 识别请求目标

先判断用户是在做哪一类事情，并确定指令系列：

**A/B/C/D 系列（场景交互）：**

- 场景控制、层级切换
- 图层控制、图表控制
- 环境控制、演示汇报
- 告警处理（A36/A37/A38/A39）
- 对象聚焦/选中/搜索
- 灯光控制、温控
- 主题切换/主题生成
- 查询类问题（D01）

**E 系列（视频监控）：**

- 视频筛选与显示设置
- 视频翻页与导航
- 视频轮播控制、视频排序
- 事件/告警查看（视频面板侧）
- 事件轮播与筛选
- 时间模式切换（实时/回放）
- 回放操作（暂停/播放/跳转/倍速）
- 单路云台控制
- 摄像头名称查询（E35）
- 指定摄像头筛选（E34）

### 3. 获取参数所需数据（委托给 ruisi-twinioc-dataquery-skill）

解析需要参数的指令时，优先使用：

1. 当前问题中的显式信息。
2. `history_user` 中最近一次相关操作。
3. `history_inter` 中已有工具结果。
4. `scene_info` 中可用名称列表。

如需额外数据（如某层级下的孪生体列表），调用 `ruisi-twinioc-dataquery-skill`：

```bash
# 按类别查询孪生体实例列表
python ../ruisi-twinioc-dataquery-skill/scripts/query.py mcp \
  --token <token> \
  --mcp-tool get_twin_category_data \
  --mcp-args '{"twinCategoryName": "类别名称"}'

# 按层级查该层所有孪生体类别
python ../ruisi-twinioc-dataquery-skill/scripts/query.py mcp \
  --token <token> \
  --mcp-tool get_twin_category \
  --mcp-args '{"levelName": "层级名称"}'

# 查温度数据（按安装位置或孪生体实例名称）
python ../ruisi-twinioc-dataquery-skill/scripts/query.py temperature \
  --token <token> \
  --device-query "位置名称"
```

如果仍无法确认名称类参数，返回"场景中没有找到匹配的信息"及相关候选数据，并放入一组 `[]` 中直接输出，不伪造指令，**此条规则非常重要，优先级最高**。

如果上一步来自温度规则命中后的确认执行，则优先使用 `rule_match.parsed_rule.execute_query` 作为当前 `query`，不要丢失规则中已经补全好的设备名称。

如果当前用户输入本身只是肯定词或否定词，先查 `ruisi-twinioc-opeationrule-skill` 的待确认动作；存在待确认动作时，优先按待确认动作处理，不要把“是/否”直接当作普通控制指令解析。

**E 系列额外数据**：涉及摄像头名称（E34、E35）时，先查 `history_inter` 是否已有结果，没有则调用：

```bash
python ../ruisi-twinioc-dataquery-skill/scripts/query.py mcp \
  --token <token> \
  --mcp-tool get_bind_video_instance_names
```

未匹配到摄像头名称时，直接输出 `[视频中没有找到匹配的信息]`，不拼接任何 E 系列指令。

### 4. 生成标准指令串

按下方指令库规则生成原始执行指令，格式示例：

**A/B/C/D 系列：**

- `[A03]`
- `[A36：告警信息：当前&A38：告警信息选中]`
- `[A01：功能切换：分析&C01：主题切换：园区概况]`

**E 系列：**

- `[E08：视频：下一个视频]`
- `[E34：筛选：大会议室摄像头2&E32：单路云台：拉近]`
- `[E02：筛选：设置显示模式，3×3]`

多指令按 `&` 连接；并列操作按 `&` 拼接在同一方括号内。

### 5. 生成用户可见计划文本

将原始指令转换为中文计划文本时：

- 保留动作语义。
- 去掉指令编码，如 `A03`、`B02`、`C01`。
- 保留参数值，如"下一层""摄像头01""园区概况"。

例如：

- `A03` `层级切换：下一层`
- `A08：场景旋转：开始` `场景旋转：开始`
- `B07：打开灯：1F走廊灯` `打开灯：1F走廊灯`
- `E08：视频：下一个视频` `视频：下一个视频`
- `E34：筛选：大会议室摄像头2` `筛选：大会议室摄像头2`
- `E12：事件：事件列表，选中` `事件：事件列表，选中`

最终使用以下格式：

`根据最优策略，已经为您规划如下执行计划：\n1、...\n2、...`

查询类 `D01`（场景查询）和 `E35`（摄像头查询）不加"规划如下执行计划"前缀，直接输出查询内容。

### 6. 组织前端响应（已更新）

- 本 Skill 的执行层现在直接返回一个固定的 JSON 对象到调用方（前端/宿主），不在 stdout 中输出任何分段或分隔标记。
- 返回的 JSON 格式为：

```
{
  "message": "<plan_text 或 AI 原始文本>"
}
```

- 同时，发送到孪易后端的 `jsonData` 字段仍保持格式：`instruction_order$&query$&plan_text`（其中 `instruction_order` 与 `plan_text` 由执行层或 AI 提供）。

- 如果需要兼容旧接收方（仍期待分段标记）的场景，请在接入层做适配；当前代码不再产生这些标记，文档仅作说明。

### 7. 执行指令

**重要：你（加载本文件的 AI）负责推理生成指令串，然后你自己调用下方脚本完成执行。`--agent-output` 参数的值就是你在上一步生成的指令串，由你填入并调用。**

**执行前按指令类型判断是否需要用户确认：**

#### 需要用户确认后再执行（物理设备开关指令）

当指令串中包含以下任意指令时（B07/B08/B09/B10），**必须先向用户展示操作内容并等待确认，收到明确确认后才能调用脚本发送**：

- `B07：打开灯：XXX`
- `B08：关闭灯：XXX`
- `B09：打开温控器：XXX`
- `B10：关闭温控器：XXX`

确认提示格式：

```
即将执行：{操作描述，如"打开灯：1F走廊灯"}，请确认是否执行？（是/否）
```

- 注意：执行层返回给调用方的仍为固定 JSON（键 `message`），不再带任何分隔标记。确认交互请直接检查 `message` 字段中的文本并回复。

用户回复“是”/“确认”/“好”/“好的”/“执行”等肯定词后，再调用执行脚本；用户回复“取消”/“否”/“不”/“算了”等否定词时，不调用脚本，回复“已取消操作”。

确认后调用执行脚本示例（以确认打开大会议室温控器为例）：

```bash
python scripts/invoke_skill.py \\
  --token "<scene-token>" \\
  --query “打开大会议室温控器” \\
  --agent-output "[B09：打开温控器：大会议室温控器]"
```

> **⚠️ 严格要求**：
>
> - `--agent-output` 的值**必须**是你本轮生成的实际指令括号串，例如 `[B09：打开温控器：大会议室温控器]`。**绝对禁止**传入 `[instruction_order]`、`[query]`、`[plan_text]` 等任何文档占位符字符串。
> - `--query` 的值**必须**是用户的原始问题文本（如 `打开大会议室温控器`）。**绝对禁止**传入指令描述文本（如 `打开温控器：大会议室温控器`）或任何含编码前缀的字符串（如 `B09：打开温控器：大会议室温控器`）。

对于温度规则联动场景，这里的“调用执行脚本”前必须先执行：

```bash
python ../ruisi-twinioc-opeationrule-skill/scripts/invoke_recorder.py --get-pending --token <token>
```

- 如果返回存在 `pending.execute_query`，则把 **`execute_query` 的值**（例如 `打开大会议室温控器`）作为 `--query`，并根据该值重新生成指令括号串（例如 `[B09：打开温控器：大会议室温控器]`）作为 `--agent-output`，再调用执行脚本。
- 执行完成后，调用：

```bash
python ../ruisi-twinioc-opeationrule-skill/scripts/invoke_recorder.py --clear-pending --token <token>
```

- 如果是取消，则直接调用同一个 `--clear-pending` 再回复 `已取消操作`。

#### 直接执行（无需用户确认）

所有其他指令（A/C/D/E 系列，以及 B01/B02/B03/B04/B05/B06 等非物理设备指令）统一**直接调用执行脚本，无需等待用户确认**：

```bash
python scripts/invoke_skill.py \\
  --token "<scene-token>" \\
  --query “用户原始问题” \\
  --agent-output "[A03]"
```

> **⚠️ 严格要求**：`--agent-output` 的值是你本轮生成的实际指令括号串（如 `[A03]`），`--query` 是用户的原始问题。两者均**禁止**使用文档中出现的任何占位符名称（如 `instruction_order`、`query`、`plan_text`）。

- 如只想验证指令生成而不下发执行，可追加 `--no-execute`

## Output Requirements

### 用户可见文本

调用脚本执行后，脚本的 stdout 直接就是 `plan_text` 纯文本，**原样作为最终回复输出，不要修改、不要包装**。

示例输出：

```
根据最优策略，已经为您规划如下执行计划：
1、层级切换：上一层
```

询问类（D01）示例：

```
为您查找到相关内容如下：大会议室摄像头2，后门入口摄像头；共2个
```

禁止：

- 输出 `A09`、`A03`、`B07`、`E08`、`E34` 等裸编码给用户。
- 自行编写"已发送指令"、"请查看场景"等替代性描述。
- 把"开始/停止/名称"等参数留空。

### 执行指令文本

必须：

- 保留完整编码。
- 能直接用于 `SendInstruction`。

## 推理规则（AI 生成指令时遵循）

1. 根据用户输入内容，智能匹配并直接输出最符合上述指令格式的内容。
2. 若用户输入中包含多个意图，一次输出多个对应指令。
3. 对于括号中含有"其一"的选项，必须从已知选项中选择最匹配的一个。
4. 对于括号中含有"名称"的选项，首先从 `history_inter` 中查找，没有再调用 `ruisi-twinioc-dataquery-skill`：
   ```bash
   python ../ruisi-twinioc-dataquery-skill/scripts/query.py mcp \
     --token <token> \
     --mcp-tool get_twin_category_data \
     --mcp-args '{"twinCategoryName": "对应类别"}'
   ```
   从返回结果中匹配最接近的一个；如果经过查找仍没有匹配成功，拼接固定语句"场景中没有找到匹配的信息，"以及通过查询接口查找到的相关数据，然后用一个 `[]` 括起来直接输出，且不拼接任何指令，**非常重要优先级最高**。
5. 剩下的智能输出所需内容。
6. 当用户输入"生成XXXX"、"统计XXX"、"创建XXX"、"分析XXX"、"统计一下XXX"等类似表达时，必须识别为"C02：主题生成：XXX"。
7. 当用户输入询问类型的内容时（如"有哪些XXX"、"XXX有什么"），**必须按以下步骤完成，不得跳过**：
   1. 调用 `ruisi-twinioc-dataquery-skill` 获取实例列表，类别名称从 `scene_info.twinCategoryNames` 中匹配最接近的一个：
      ```bash
      python ../ruisi-twinioc-dataquery-skill/scripts/query.py mcp \
        --token <token> \
        --mcp-tool get_twin_category_data \
        --mcp-args '{"twinCategoryName": "XXX类别名称"}'
      ```
   2. 将返回的所有实例名称填入 D01 指令，格式：`D01：名称1，名称2，名称3；共X个`
   3. 调用执行脚本：
      ```bash
      python scripts/invoke_skill.py \
        --token <token> --query "..." --agent-output "[D01：...]"
      ```
   4. 把脚本返回的 `plan_text` 展示给用户。

   **禁止**在未运行查询脚本的情况下发送任何指令，或要求用户自己提供列表。

8. 当用户输入跟聚焦对象和选中对象相关的问题时，对象名称存在时联系上下文，按以下三种情况严格判断：
   - 情况一：对话开始、没有任何历史指令，**或历史指令中存在层级切换（A02/A03/A04/A05/A06）但不存在任何对象操作（B01/B02）** 输出必须包含"A02：层级切换：（对象所在层级）"；
   - 情况二：上一个对象操作（B01/B02）与当前对象在同一层级，且两次对象操作之间的历史指令中不存在任何层级切换指令（A02、A03、A04、A05、A06） 只输出对象指令，不加层级切换；
   - 情况三：上述情况二不满足时（即对象不同层级，或两次对象操作之间存在过 A02/A03/A04/A05/A06 中任意一条） 输出必须包含"A02：层级切换：（对象所在层级）"。

   特别注意：判断"两次对象操作之间是否有层级切换"时，必须检查上一个对象指令之后到本次请求之间的所有历史指令，只要出现过 A02/A03/A04/A05/A06，就必须输出层级切换，即使当前对象与上一个对象处于同一层级。如果对象名称存在多个层级，默认用第一个出现的层级。

   **补充说明（新 token 场景）：当用户携带一个全新 token 发起对话，第一条消息就是聚焦/选中对象请求时，此时 `history_user` 为空，属于情况一，**必须\*\*在对象指令前输出层级切换 `A02：层级切换：（对象所在层级）`，不得省略。

9. 当用户询问有多少对象/孪生体且不带有某个层级时，应输出所有层级下的孪生体类型以及该类型下的对象名称。
10. 当用户输入问题跟主题切换相关时，如果主题名称存在，输出的指令必须包含"A01：功能切换：分析&C01：主题切换：（主题名称）"。
11. 当用户输入问题跟告警相关时：
    - 看一下告警信息 `A36：告警信息：当前`
    - 看一下最新的告警 `A36：告警信息：当前&A38：告警信息选中`
    - 最新的历史告警 `A37：告警信息：历史&A38：告警信息选中`
    - 查看告警触发截图 `A38：告警信息选中&A39：告警截图：打开`

    注意根据上下文判断，如果上一个指令包括告警信息选中，则不用重复输出。

12. 当用户输入问题是打开或关闭XXX灯开关时，对象名称直接从智能开关孪生体中获取，输出"B07：打开灯：（对象名称）"或"B08：关闭灯：（对象名称）"。
13. 当用户输入问题是打开或关闭XXX温控器或者XXX空调时，对象名称直接从温控器孪生体中获取，输出"B09：打开温控器：（对象名称）"或"B10：关闭温控器：（对象名称）"。
14. E34（视频筛选）和 E35（摄像头列表查询）依赖摄像头名称匹配。若通过 `ruisi-twinioc-dataquery-skill get_bind_video_instance_names` 返回的列表中找不到匹配项，输出 `[视频中没有找到匹配的信息]`，不抛出错误。
15. 当用户说"查看XXX摄像头"、"打开XXX视频"时，识别为 E34，筛选参数 = 摄像头名称。
16. 当用户说"XXX摄像头放大/拉近"或"XXX摄像头缩小/拉远"时（含具体摄像头名称），识别为 `E34：筛选：{摄像头名称}&E32：单路云台：拉近` 或 `E34：筛选：{摄像头名称}&E33：单路云台：拉远`；当用户只说"放大、缩小、拉近、拉远、左转、右转、抬头、低头"而不带摄像头名称时，直接输出对应单路云台指令（E28E33）。
17. 当用户说"查看XXX摄像头告警/事件"时（含具体摄像头名称），识别为 `E34：筛选：{摄像头名称}&E12：事件：事件列表，选中`；当用户只说"看一下告警信息"等不含摄像头名称时，直接输出 `E12：事件：事件列表，选中`（E 系列中告警即事件）。
18. 当用户询问"有哪些摄像头"、"摄像头列表"时，识别为 E35。
19. 区分"上/下一页视频"（E05/E06）和"上/下一个视频"（E08/E09），不可混用。
20. 当用户的问题与视频监控 E 系列功能均不匹配时，输出：`您的提问超出了我能回答的范围，请输入跟视频监控相关的问题！`

### 特别注意事项

1. 对用户输入进行模糊匹配，例如"园区概览""园区概况"视为同义。
2. 当用户输入包含多个操作（如"切换到第八层并选中摄像头01"），分别输出多个指令（如：`A02：层级切换：楼层8&B02：选中对象：摄像头01`）。
3. 当用户输入"切换主题到园区""切换到园区主题""切换园区"等类似表达时，也应识别为"A01：功能切换：分析&C01：主题切换：园区概况"。
4. 对象上卷和对象下钻是不同的指令集，跟层级切换无关。
5. 不需要输出思考过程，除物理设备开关指令（B07/B08/B09/B10）需要等待用户确认外，其他情况不要询问用户任何问题，直接按照输出格式输出正确结果。

## 指令库

```
A01：功能切换：？（AI分析、分析、对象、告警、过滤 其一）
A02：层级切换：？（层级名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
A03：层级切换：下一层
A04：层级切换：上一层
A05：层级切换：第一层
A06：层级切换：最后一层
A07：层级列表：？（打开、关闭 其一）
A08：场景旋转：？（开始、停止 其一）
A09：场景复位
A10：视野放缩：拉近，100
A10：视野放缩：远离，100
A11：视野平移：？（前移、后移、左移、右移 其一），100
A12：视野旋转：？（顺时针、逆时针 其一），10
A13：时间轴：播放
A14：时间轴：暂停
A15：时间轴：跳转到？（时间点或关键锚点）
A16：时间轴：？（回放、实时 其一）
A17：图层管理：？（打开、关闭 其一）
A18：显示图层：？（图层名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
A19：隐藏图层：？（图层名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
A20：图层全部显示
A21：图层全部隐藏
A22：图表管理：？（打开、关闭 其一）
A23：显示图表：？（图表名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
A24：关闭图表：？（图表名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
A25：环境控制：？（打开、关闭 其一）
A26：时间切换：？（具体时间点）
A27：季节切换：？（春季、夏季、秋季、冬季 其一）
A28：天气切换：？（晴、晴间多云、阴天、小雨、中雨、大雨、小雪、中雪、大雪、雾、霾、扬沙 其一）
A29：演示汇报：？（打开、关闭 其一）
A30：开始演示：？（演示汇报名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
A31：停止演示
A32：暂停演示
A33：上一步演示
A34：下一步演示
A35：重新演示
A36：告警信息：当前
A37：告警信息：历史
A38：告警信息选中
A39：告警截图：（打开、关闭 其一）
B01：聚焦对象：？（对象名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
B02：选中对象：？（对象名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
B03：取消选中
B04：对象下钻
B05：对象上卷
B06：搜索对象：？（搜索内容）
B07：打开灯：？（对象名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
B08：关闭灯：？（对象名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
B09：打开温控器：？（对象名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
B10：关闭温控器：？（对象名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
C01：主题切换：？（主题名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
C02：主题生成：？（生成的内容）
D01：？，？，？；共X个（询问类内容）
E01：筛选：范围选取：中心点，？；范围，？
E02：筛选：设置显示模式，？（单路、2×2、3×3 其一）
E03：视频：轮播视频，？（开始、停止 其一）
E04：视频：视频排序，？（按对象名称正序、按对象名称倒序、按创建时间正序、按创建时间倒序 其一）
E05：视频：视频上一页
E06：视频：视频下一页
E07：视频：视频指定页，？
E08：视频：下一个视频
E09：视频：上一个视频
E10：视频：第一个视频
E11：视频：末一个视频
E12：事件：事件列表，？（选中、取消 其一）
E13：事件：轮播事件，？（开始、停止 其一）
E14：事件：事件筛选，？
E15：事件：事件排序，？（按时间正序、按时间倒序 其一）
E16：事件：选中事件，？
E17：事件：下一个事件
E18：事件：上一个事件
E19：事件：第一个事件
E20：事件：末一个事件
E21：时间：模式切换，（实时、回放 其一）
E22：回放：暂停
E23：回放：播放
E24：回放：跳转，？
E25：回放：前进，？
E26：回放：回退，？
E27：回放：倍速，？
E28：单路云台：左转
E29：单路云台：右转
E30：单路云台：抬头
E31：单路云台：低头
E32：单路云台：拉近
E33：单路云台：拉远
E34：筛选：？（摄像头名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
E35：名称：？，？，？...（摄像头名称，必须是从 ruisi-twinioc-dataquery-skill 返回的内容）
```

## 输出格式

```
[指令1&指令2&指令3&...]
```

## 输出示例

1. 用户有两个意图：`[A02：层级切换：楼层8&B02：选中对象：摄像头01]`
2. 用户只有一个意图：`[A04：层级切换：上一层]`
3. 用户有多个询问类意图：`[D01：摄像头01，摄像头02，摄像头03；共3个&D01：告警01，告警02；共2个]`
4. 选中摄像头01：`[A02：层级切换：层级2&B02：选中对象：摄像头01]`
5. 情况三示例：上一个对象操作是聚焦传感器10（楼层20），之后执行了"A04：层级切换：上一层"，再聚焦传感器8（楼层20） 两次对象操作之间存在A04，必须输出层级切换：`[A02：层级切换：楼层20&B01：聚焦对象：传感器8]`
6. 下一个视频：`[E08：视频：下一个视频]`
7. 设置视频显示模式为3×3：`[E02：筛选：设置显示模式，3×3]`
8. 查看大门摄像头：`[E34：筛选：大门摄像头]`
9. 询问摄像头列表（返回3个）：`[E35：名称：大会议室摄像头2，后门入口摄像头，前台摄像头]`

## Failure Handling

遇到以下情况时，不要硬编结果：

- 需要名称类参数但未匹配到有效名称。
- 需要状态类参数但未判断出具体值。
- 指令仅返回编码但按规则必须带参数。
- E 系列请求中，通过 `get_bind_video_instance_names` 未找到匹配摄像头名称时，输出：`[视频中没有找到匹配的信息]`
- E 系列请求中，用户问题与视频监控功能无关时，输出：`您的提问超出了我能回答的范围，请输入跟视频监控相关的问题！`

此时应明确指出失败原因或未匹配信息，而不是返回错误的伪结果。

## Resources

### references/command-rules.md

完整指令分类、无参数指令、带参数指令、展示文本规则。

### references/integration.md

响应结构、HTTP 请求格式、字段用途与示例。

### 执行层（本 Skill 自身）

- `scripts/invoke_skill.py`：命令行入口，接收 `--token`、`--query`、`--agent-output` 参数，统一处理 A/B/C/D 与 E 系列指令的下发执行。
- `scripts/skill_runtime.py`：纯执行运行时，合并 A/B/C/D 与 E 系列指令映射，管理会话状态与 `SendInstruction` HTTP 请求。

### 查询层（引用 ruisi-twinioc-dataquery-skill）

- `../ruisi-twinioc-dataquery-skill/scripts/query.py`：统一只读数据查询入口，支持 `mcp` 和 `temperature` 两种模式；其中 `get_bind_video_instance_names` 工具路由至 `video_surveillance_command` 脚本。
