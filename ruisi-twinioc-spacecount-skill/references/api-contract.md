# 接口契约与调用约定

本文档用于约定空间利用指数查询技能需要调用的真实接口契约与返回结构。

## 0. 通用调用约定

- 统一接口前缀：`http://test.twinioc.net/api/editor/v1`
- `token` 由用户输入传入，调用时必须透传给后端
- 当前文档只约定接口语义、输入输出和调用约束，真实路径待后端接口文档补充后再落地
- 如果后端采用统一请求体，则 `token` 应作为请求体字段传递；如果后端采用查询参数或 Header，则以真实接口文档为准
- 技能实际调用层统一通过 `scripts/query.py mcp --token <token> --mcp-tool <工具名> [--mcp-args '{"参数":"值"}']` 转发到 MCP 网关

## 0.1 已提供的真实工具

### 0.1.1 空间预定工具

当前已提供以下空间预定 MCP 工具：

- `get_reservable_spaces`：查询可预约空间
- `check_space_availability`：检查单个空间是否可用
- `get_space_reservation_status`：查询空间预约状态
- `create_space_reservation`：创建预约
- `reschedule_space_reservation`：改期预约
- `cancel_space_reservation`：取消预约

#### 通用调用约定

- 所有预定工具都需要 `token`
- 建议统一使用 `yyyy-MM-dd HH:mm:ss` 作为时间格式
- `reschedule_space_reservation` 和 `cancel_space_reservation` 里的 `createdTime` 必须取自原预约返回结果中的 `Reservation.CreatedTime`
- `createdTime` 不是预约开始时间，也不是结束时间
- 调用时建议先按需查询 `get_reservable_spaces`、`check_space_availability` 或 `get_space_reservation_status`，再执行 `create_space_reservation`、`reschedule_space_reservation`、`cancel_space_reservation`

### 0.1.2 空间利用指数查询工具

- 工具名：`get_space_utilization_index_data`
- 作用：查询已经写入 InfluxDB 的空间利用指数结果数据
- 适用范围：楼层、区域、整层聚合结果
- 调用方式：通过 MCP 工具调用，不直接查询原始工位/会议室时序
- 必填参数：`levelName`、`granularity`、`startTime`、`endTime`、`regionName`、`token`
- 如果用户问题没有识别到某个参数，则按默认值补齐后再调用
- `levelName` 默认 `楼层20`
- `granularity` 默认 `Hour`
- `startTime` 默认当前小时桶起始时间
- `endTime` 默认当前小时桶结束时间或当前时刻
- `regionName` 默认 `""`（空字符串）
- `token`：SignalR 连接返回的 6 位 `UniqueId`

### 0.1.1 返回对象

工具返回的顶层对象对应 `SpaceUtilizationIndexMcpResponse`，单条结果对应 `SpaceUtilizationIndexDataPointResponse`。

#### 顶层字段

| 字段          | 类型     | 说明                                                    |
| ------------- | -------- | ------------------------------------------------------- |
| `LevelName`   | `string` | 层级名称                                                |
| `Granularity` | `string` | 返回粒度，固定为 `Hour` / `Day` / `Week` / `Month` 之一 |
| `Message`     | `string` | 执行结果说明                                            |
| `RegionData`  | `array`  | 区域级指标结果                                          |
| `FloorData`   | `array`  | 整层聚合结果；仅在 `regionName` 为空字符串时返回        |

#### 单条结果字段

`RegionData` 与 `FloorData` 内每一项结构相同：

| 字段         | 类型      | 说明                             |
| ------------ | --------- | -------------------------------- |
| `Time`       | `string`  | 时间桶                           |
| `RegionName` | `string`  | 区域名称；整层结果时为层级名称   |
| `RegionType` | `string`  | 区域类型；整层结果固定为 `整层`  |
| `Area`       | `decimal` | 区域面积；整层结果为聚合后的面积 |
| `Indicators` | `object`  | 指标集合                         |

#### `Indicators` 字段

当前返回的指标字段如下：

- `SpaceOccupancyRate`
- `SpaceUsageFrequency`
- `PerCapitaAreaComplianceRate`
- `SpaceReuseIndex`
- `FlexibleDeskReservationFulfillmentRate`
- `MeetingRoomVacancyScore`
- `SpaceConflictResolutionRate`
- `SpaceVitality`
- `SpaceIntensity`
- `SpaceQuality`
- `SpaceUtilizationIndex`

说明：

- 当前实现中这些指标值均为数值型，通常保留 4 位小数
- 若某项没有有效值，通常返回 `0`
- 技能侧不得自行补值、平滑或重新聚合

## 1. 预约接口

用于会议室和工位的预定、改期与取消。

### 1.0 操作名清单

- `get_reservable_spaces`：查询指定范围内可预约空间
- `check_space_availability`：检查指定空间在某时间段是否可用
- `get_space_reservation_status`：查询指定空间在某时刻的预约状态
- `create_space_reservation`：创建新的预约记录
- `reschedule_space_reservation`：修改已有预约记录
- `cancel_space_reservation`：取消已有预约记录

### 1.0.1 请求示意

当真实接口路径明确后，可按如下方式理解调用结构：

- `POST {base-url}/{实际预约路径}`
- 请求体中包含 `token` 和对应业务参数
- 空间名称、空间 ID、层级、区域、开始时间、结束时间、`createdTime` 按各工具要求传入

### 1.1 查询可用资源

- 目的：根据时间范围和范围条件，找出可预定的会议室或工位候选项。
- 预期输入：
  - spaceType：`灵活工位` 或 `会议室`
  - startTime
  - endTime
  - levelName
  - regionName
  - token
- 预期输出：
  - `Message`
  - `QueryMode`
  - `StartTime`
  - `EndTime`
  - `SpaceList`

### 1.2 创建预约

- 目的：创建新的预约。
- 预期输入：
  - spaceType
  - startTime
  - endTime
  - token
  - spaceId
  - spaceName
- 预期输出：
  - `Succeeded`
  - `Message`
  - `Reservation`
  - `CandidateSpaces`
  - `ConflictReservations`

### 1.3 更新预约

- 目的：修改已有预约。
- 预期输入：
  - spaceId
  - createdTime
  - newStartTime
  - newEndTime
  - token
- 预期输出：
  - `Succeeded`
  - `Message`
  - `Reservation`
  - `CandidateSpaces`
  - `ConflictReservations`

### 1.4 取消预约

- 目的：取消已有预约。
- 预期输入：
  - spaceId
  - createdTime
  - token
- 预期输出：
  - `Succeeded`
  - `Message`
  - `Reservation`
  - `CandidateSpaces`
  - `ConflictReservations`

## 2. 指标接口

用于所有空间利用指数查询。当前已提供的真实接口为 `get_space_utilization_index_data`。

### 2.0 操作名清单

- `get_space_utilization_index_data`：查询空间利用指数结果数据

### 2.0.1 请求示意

当真实接口路径明确后，可按如下方式理解调用结构：

- 通过 MCP 调用 `get_space_utilization_index_data`
- 请求参数中包含 `levelName`、`granularity`、`startTime`、`endTime`、`regionName`、`token`
- 用户问题未明确某个参数时，技能侧先补默认值再调用
- `granularity` 可输入英文或中文语义，技能侧统一映射为 `Hour` / `Day` / `Week` / `Month`

默认参数规则：未明确时直接使用以下默认值。

- 当用户问题未明确涉及入参时，`levelName` 默认使用 `楼层20`
- `granularity` 默认使用 `Hour`
- `startTime` 默认使用当前小时桶起始时间，例如 `2026-03-28 09:00:00`
- `endTime` 默认使用当前小时桶结束时间或当前时刻，例如 `2026-03-28 09:59:59`
- 不明确区域时，`regionName` 默认传 `""`（空字符串）

### 2.1 计算指标

- 目的：从后端已写入的空间利用指数结果中返回查询值。
- 预期输入：
  - levelName：层级名称，如 `1F`
  - granularity：`Hour`、`Day`、`Week` 或 `Month`
  - startTime
  - endTime
  - regionName：区域名称；不明确时默认传 `""`（空字符串）
  - token
- 预期输出：
  - RegionData
  - FloorData
  - Message

### 2.2 解释指标依据

- 目的：如果需要解释时间边界、粒度语义或区域/整层聚合规则，则依据文档说明返回。
- 预期输出：
  - 结果点时间解释
  - 粒度说明
  - 区域/整层返回规则
  - 结果过滤范围说明

## 3. 需要的返回字段

当后端返回结构化数据时，技能至少应能提取以下字段：

- 预约响应：
- Message
- QueryMode
- StartTime
- EndTime
- SpaceList
- SpaceId
- SpaceName
- SpaceType
- IsReservable
- Reason
- IsAvailable
- ConflictReservations
- CurrentStatus
- CurrentReservation
- NextReservation
- LastReservation
- Succeeded
- Reservation
- CandidateSpaces
- ReservationId
- LevelName
- RegionName
- Status
- ReservedByUserId
- CreatedTime
- ConflictFlag
- ConflictResolvedTime

空间利用指数响应：

- LevelName
- Granularity
- Message
- RegionData
- FloorData
- Time
- RegionName
- RegionType
- Area
- Indicators

## 4. 当前约束

技能不得在本地编造或计算上述任何值。当前只实现并文档化空间利用指数查询接口；预约相关接口仅保留占位说明。
