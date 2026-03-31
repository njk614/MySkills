---
name: ruisi-twinioc-spacecount-skill
description: 该技能用于空间预定与空间利用指数查询。当前已落地的真实能力包括空间预定 MCP（查询可预约空间、校验可用性、查询预约状态、创建预约、改期、取消）以及 get_space_utilization_index_data 空间利用指数查询；所有结果都必须来自后端返回，不得在本地推算。编写时可参考 ruisi-twinioc-command-skill 的组织方式，最终作为大模型可直接调用的技能能力使用。
---

# 睿思孪易空间计量技能包

## Purpose

- 编排空间预定与空间利用指数查询流程。
- 将用户意图转换为后端空间预定接口或空间利用指数查询接口调用。
- 只返回后端实际返回的执行结果、预约结果、区域结果或整层聚合结果。

## 适用场景

- 用户需要查询某层、某区域或整层的空间利用指数结果。
- 用户需要查询可预约空间、校验空间可用性、获取预约状态、创建预约、改期预约或取消预约。
- 用户询问空间利用指数、区域结果、整层聚合结果或对应时间桶数据。
- 用户希望查看返回消息、粒度说明、时间范围、区域过滤后的结果或预约写入结果。

## 核心规则

- 所有空间利用指数结果都必须调用后端查询接口。
- 所有空间预定动作都必须调用后端预定接口，不得在本地模拟预约结果。
- 不得在本地计算任何指标值、时间桶、整层聚合结果或预约可用性。
- 不得伪造测量名称、区域结果、整层结果、预约记录或任何数值。
- 如果层级、时间范围、粒度、区域名称、空间名称或空间 ID 不明确，先追问后再调用接口。
- 如果是预约查询且用户没有明确查询时间，默认使用当前小时桶内的当前时刻，不要扩成全天查询。
- 如果查询的是整天或某个时间段，冲突判断只看与当前查询窗口重叠的预约；已结束且结束时间早于当前查询时刻的预约，不应再被当作不可预约原因。
- 如果后端返回未找到层级、时间格式无效、查询无数据、空间冲突或预约失败等错误，直接用中文返回 `Message` 中的说明。

## 接口调用约定

- 统一接口前缀：`http://test.twinioc.net/api/editor/v1`
- `token` 必须使用用户传入的值，不得写死为固定值
- 所有已落地的空间预定与空间利用指数查询，都通过 `scripts/query.py` 以 MCP 方式调用，不在技能文档里手工拼接 HTTP 请求
- 调用示例：`python scripts/query.py mcp --token <token> --mcp-tool <工具名> [--mcp-args '{"参数":"值"}']`
- `token` 作为请求参数透传给后端，`--mcp-args` 中如未传 `token`，脚本会自动补入
- 当前阶段以 `references/api-contract.md` 中的工具清单为准，真实路径由 MCP 网关统一处理

## 已提供的真实接口

当前已提供的是真实接口包括预定能力与查询能力：

### 空间预定工具

- `get_reservable_spaces`
- `check_space_availability`
- `get_space_reservation_status`
- `create_space_reservation`
- `reschedule_space_reservation`
- `cancel_space_reservation`

### 空间利用指数查询工具

- 工具名：`get_space_utilization_index_data`
- 适用范围：L1 空间利用指数的区域级与整层聚合结果查询
- 调用方式：通过 MCP 工具调用，不直接查询原始工位/会议室时序
- 必填参数：`levelName`、`granularity`、`startTime`、`endTime`、`regionName`、`token`
- `token`：使用用户传入的值，来自 SignalR 连接返回的 6 位 `UniqueId`

参数含义、返回结构与时间粒度规则以 `references/api-contract.md` 和 `references/space-model.md` 为准。

默认值规则：所有参数都需要传入；如果用户问题没有识别到对应参数，直接使用以下默认值。

- 不明确层级时，`levelName` 默认使用 `楼层20`。
- 不明确粒度时，`granularity` 默认使用 `Hour`。
- 不明确时间范围时，`startTime` 默认使用当前小时桶起始时间，例如 `2026-03-28 09:00:00`。
- 不明确时间范围时，`endTime` 默认使用当前小时桶结束时间或当前时刻，例如 `2026-03-28 09:59:59`。
- 不明确区域时，`regionName` 默认传 `""`（空字符串）。

## 接口调用清单

当前已落地的后端能力：

- `get_reservable_spaces`：查询可预约空间
- `check_space_availability`：检查单个空间是否可用
- `get_space_reservation_status`：查询空间预约状态
- `create_space_reservation`：创建预约
- `reschedule_space_reservation`：改期预约
- `cancel_space_reservation`：取消预约
- `get_space_utilization_index_data`：查询空间利用指数结果数据

如果后续补充了其他空间指标接口，再在 `references/api-contract.md` 中扩展，不要在当前技能中预设未实现能力。

## Workflow

### 1. 预约请求

1. 识别资源类型：会议室或灵活工位。
2. 识别用户是要查询可预约空间、检查可用性、查询预约状态，还是创建、改期、取消预约。
3. 明确空间 ID、空间名称、层级、区域、开始时间、结束时间，以及改期/取消所需的 `createdTime`。
4. 调用对应的预定 MCP 工具。
5. 返回后端给出的预约结果、候选空间、冲突预约或状态说明，不在本地补写。

### 2. 指标请求

1. 识别用户要查的层级、粒度、时间范围和区域名称。
2. 如果用户问题没有明确说明这些入参，直接补齐默认值：`levelName = 楼层20`、`granularity = Hour`、`startTime = 当前小时桶起始时间`、`endTime = 当前小时桶结束时间`、`regionName = ""`。
3. 将粒度映射到 `Hour`、`Day`、`Week` 或 `Month`；用户输入若为“小时/日/周/月”，按同义粒度处理。
4. 调用 `get_space_utilization_index_data` 获取结果。
5. 优先返回 `Message`，再根据需要展示 `RegionData`、`FloorData` 和 `Indicators`。
6. 当用户只查询某个区域时，只展示该区域的 `RegionData`，不要自行补写整层结果。

### 3. 歧义处理

如果用户问题比较模糊，例如“这个楼层怎么样”“能不能订一个工位”或“空间利用情况如何”，只在上下文足够明确时直接映射到预定或指数查询；否则先追问以下最关键的一项：

- 层级名称
- 时间粒度
- 开始时间和结束时间
- 是否需要按区域过滤
- 空间类型、空间 ID 或空间名称
- 改期/取消时所需的 `createdTime`

## 指标词汇

当前实际可返回的指标词汇以后端结果为准，技能侧只做展示，不做数值推断。

- `SpaceOccupancyRate`：空间占用率
- `SpaceUsageFrequency`：空间使用频次
- `PerCapitaAreaComplianceRate`：人均面积达标率
- `SpaceReuseIndex`：空间复用指数
- `FlexibleDeskReservationFulfillmentRate`：灵活工位预定兑现率
- `MeetingRoomVacancyScore`：会议室空置得分
- `SpaceConflictResolutionRate`：空间冲突解决率
- `SpaceVitality`：空间活力
- `SpaceIntensity`：空间强度
- `SpaceQuality`：空间质量
- `SpaceUtilizationIndex`：空间利用指数

## 输出要求

- 返回内容保持用户可读且简洁。
- 后端返回了实际数值时，必须原样带上该数值，不得改写或四舍五入。
- 只有在后端提供区域结果、整层结果、执行说明、预约结果或时间边界解释时，才展示这些信息。
- 后端即使返回了完整 `Indicators`，也只展示用户当前问题需要的字段；例如用户问“固定工位区的占用率”时，只返回对应区域的 `SpaceOccupancyRate`，不要把其余指标一起回显。
- 预约接口返回的 `Reservation`、`CandidateSpaces`、`ConflictReservations`、`CurrentReservation`、`NextReservation`、`LastReservation` 也只展示和用户问题相关的部分，不要无条件全量展开。
- `FloorData` 为空时不要伪造整层结果；`regionName` 传入后只读 `RegionData`。
- 除非用户明确要求，不输出内部接口路径、payload 结构或实现细节。

## 参考文件

- `references/api-contract.md`：空间利用指数查询契约与返回结构说明。
- `references/space-model.md`：用户请求到空间利用指数展示语义的映射说明。
