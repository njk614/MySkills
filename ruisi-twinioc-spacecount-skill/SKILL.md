---
name: ruisi-twinioc-spacecount-skill
description: 该技能用于空间预定与空间利用指数查询。适用于会议室预约、灵活工位预约、可预约空间查询、预约状态、创建预约、改期、取消预约，以及空间利用指数、占用率、空置率评分、区域结果、整层结果、时间桶结果和相关公式解释。明确不用于环境温度、湿度、CO2、空气质量、温度传感器等环境统计查询，也不用于灯光、温控器、摄像头、视频、对象聚焦等控制动作。
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

### OpenClaw 路由边界

当用户问题的核心目标是“查空间是否可预约”或“查空间利用情况”时，应优先触发本 Skill。

优先触发本 Skill 的典型问法：

- 明天下午帮我订一个会议室
- 现在有哪些空闲会议室
- 这个工位能不能订
- 楼层20空间利用指数是多少
- 大会议室占用率怎么样
- 这个分数怎么算出来的

优先关键词：

- `预约`
- `预定`
- `可预约`
- `能不能订`
- `会议室空闲`
- `工位`
- `改期`
- `取消预约`
- `空间利用指数`
- `空间利用`
- `占用率`
- `空置率`
- `区域结果`
- `整层结果`

以下情况不要优先触发本 Skill：

- 用户核心问题是温度、湿度、CO2、PM2.5、PM10、TVOC、空气质量、达标率、趋势、温度传感器等环境统计查询
- 用户核心问题是打开或关闭设备、切换摄像头、视频播放、告警处理、对象聚焦、图层切换等执行动作

如果一句话同时包含空间查询和控制动作，例如“查一下哪个会议室空着，然后切到那个会议室摄像头”，应将空间查询部分交给本 Skill，将控制动作部分交给 `ruisi-twinioc-command-skill`。

## 核心规则

- 所有空间利用指数结果都必须调用后端查询接口。
- 所有空间预定动作都必须调用后端预定接口，不得在本地模拟预约结果。
- 不得在本地计算任何指标值、时间桶、整层聚合结果或预约可用性。
- 不得伪造测量名称、区域结果、整层结果、预约记录或任何数值。
- 预约能力仅面向 `会议室` 和 `灵活工位`；`固定工位` 只作为空间利用指数结果展示语义，不作为可预约空间类型。
- 所有接口要求参数，除 `token` 外都应补齐默认值后再调用；预约接口中即使 `spaceId`、`spaceName`、`createdTime` 缺失，也要按空字符串等默认值透传，不要直接省略字段。
- 当用户只提供空间名称而未显式提供 `spaceType` 时，优先根据名称中的“会议室”“工位”等字样补齐 `spaceType`。
- `create_space_reservation` 还必须显式提供预约人和预定用途；如果用户输入里没有这两项，先提示用户补充，不要继续调用后端创建预约。
- 这两个缺失字段的提示必须跟随用户问题语言统一输出：中文场景只说“预定人/预定用途”，英文场景只说“booker/usage purpose”，不要把英文内部字段名和中文说明混在同一句里。
- 如果层级、时间范围、粒度、区域名称等可默认参数不明确，直接套用默认值后再调用接口。
- 如果是预约查询且用户没有明确查询时间，默认使用当前小时桶内的当前时刻，不要扩成全天查询。
- 如果查询的是整天或某个时间段，冲突判断只看与当前查询窗口重叠的预约；已结束且结束时间早于当前查询时刻的预约，不应再被当作不可预约原因。
- 如果后端返回未找到层级、时间格式无效、查询无数据、空间冲突或预约失败等错误，直接用中文返回 `Message` 中的说明。
- 对“会议室现在怎么样”“这个会议室可用吗”这类歧义问法，如果上下文无法判断是环境问题还是空间问题，应优先澄清；不要把本 Skill 当成所有“会议室”问题的默认入口。

## 接口调用约定

- 默认基础地址：`http://test.twinioc.net`
- 未显式传入基础地址时，默认使用 `http://test.twinioc.net`；如传入 `base_url`，则使用该地址继续拼接固定路径。
- 统一接口前缀：`{base-url}/api/editor/v1`
- `token` 必须使用用户传入的值，不得写死为固定值
- 所有已落地的空间预定与空间利用指数查询，都通过 `scripts/query.py` 以 MCP 方式调用，不在技能文档里手工拼接 HTTP 请求
- 调用示例：`python scripts/query.py --token <token> [--base-url <base-url>] --mcp-tool <工具名> [--mcp-args '{"参数":"值"}']`
- 如果用户问题是英文，调用 `scripts/query.py` 时必须补充 `--locale en-US`，这样脚本会把 `spaceType`、`levelName` 等枚举/层级参数转换成英文值再透传给 MCP；中文问题则使用 `--locale zh-CN` 或省略。
- `scripts/query.py` 还会先把中英文字段别名统一成内部参数名，再按约定把枚举值转换成接口要求的英文值后透传给 MCP。
- `token` 作为请求参数透传给后端，`--mcp-args` 中如未传 `token`，脚本会自动补入
- 当前阶段以 `references/api-contract.md` 中的工具清单为准，真实路径由 MCP 网关统一处理

### 中英文字段与值映射

当问题是英文，或 `--locale en-US` 明确指定为英文时，脚本会按下表把字段和值转换后再传给接口；中文问题保持原字段名和原值传入，不做英文改写：

| 中文           | 英文传值/字段          |
| -------------- | ---------------------- |
| 灵活工位       | FlexibleWorkstation    |
| 固定工位       | FixedWorkstation       |
| 会议室         | MeetingRoom            |
| 空间预定记录   | SpaceReservationRecord |
| 机房           | Cabinet                |
| 孪生体实例名称 | Twin Instance Name     |
| 空间类型       | SpaceType              |
| 空间ID         | SpaceID                |
| 预定开始时间   | BookingStartTime       |
| 预定结束时间   | BookingEndTime         |
| 预定状态       | BookingStatus          |
| 预定人ID       | BookingPersonID        |
| 冲突标识       | ConflictFlag           |
| 冲突解决时间   | ConflictResolutionTime |
| 已预定         | Booked                 |
| 已取消         | Canceled               |
| 占用状态       | OccupancyStatus        |
| 面积           | Area                   |
| 区域名称       | Belong Area Name       |
| 在线状态       | OnlineStatus           |
| 空间状态       | SpaceStaus             |

说明：

- 中文问题保持原字段名和原值传入；只有英文问题或 `--locale en-US` 时，才会按上表转换成英文字段/英文值后透传。
- 字段名会先归一成脚本内部参数名，例如 `SpaceType` / `空间类型` 统一归一为 `spaceType`。
- 与预约接口相关的 `spaceType` 枚举只允许 `会议室` 和 `灵活工位`；英文场景分别透传 `MeetingRoom` 和 `FlexibleWorkstation`。
- 未在表中的普通自由文本值默认原样透传，不做额外翻译。

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

- 代码侧默认常量统一维护在 `scripts/defaults.py`；调整默认值时，先修改该文件，再同步更新本文档。

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

### 预约工具必填参数

- `get_reservable_spaces`：`spaceType`、`startTime`、`endTime`、`token`；其中 `startTime`、`endTime`、`levelName`、`regionName` 缺省时自动补默认值，`spaceType` 只允许 `会议室` 或 `灵活工位`
- `check_space_availability`：`spaceType`、`startTime`、`endTime`、`token`，以及 `spaceId`、`spaceName`；缺省时分别自动补为 `会议室`、当前时间、当前小时末、空字符串、空字符串
- `get_space_reservation_status`：`token`、`spaceType`、`spaceId`、`spaceName`；缺省时自动补为 `会议室`、空字符串、空字符串
- `create_space_reservation`：`spaceType`、`startTime`、`endTime`、`token`、`spaceId`、`spaceName`、`booker`、`usagePurpose`；其中预约人和预定用途必须由用户显式提供，缺失时应先提示用户补充
- `reschedule_space_reservation`：`spaceId`、`createdTime`、`newStartTime`、`newEndTime`、`token`；缺省时自动补为 `""`、`""`、当前时间、当前小时末
- `cancel_space_reservation`：`spaceId`、`createdTime`、`token`；缺省时自动补为 `""`、`""`

调用约束：

- 对任一预约工具，除 `token` 外的参数都补默认值再透传，不因为字段缺失而提前中断。
- 对 `create_space_reservation`，`booker` 与 `usagePurpose` 不允许默认空值透传，缺失时应返回提示让用户补充。
- 中文用户缺少这两个字段时，提示语只使用“预定人”“预定用途”；英文用户缺少这两个字段时，提示语只使用“booker”“usage purpose”。
- 当用户表达“帮我预约某个会议室/工位”但未提供 `spaceId` 时，优先使用用户原话中的 `spaceName`；如果也没有，则补空字符串透传。
- 创建预约前，如果用户先问“能不能订”，应优先调用 `check_space_availability` 或 `get_reservable_spaces`；不要跳过校验直接创建预约。

如果后续补充了其他空间指标接口，再在 `references/api-contract.md` 中扩展，不要在当前技能中预设未实现能力。

## Workflow

### 1. 预约请求

1. 识别资源类型：会议室或灵活工位。
2. 识别用户是要查询可预约空间、检查可用性、查询预约状态，还是创建、改期、取消预约。
3. 对层级、区域、开始时间、结束时间、空间 ID、空间名称、`createdTime` 等接口要求字段统一补默认值；除了 `token` 外，不省略字段。
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

如果用户问题比较模糊，例如“这个楼层怎么样”“能不能订一个工位”或“空间利用情况如何”，优先按默认值补齐后直接映射到预定或指数查询：

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

补充说明：

- 用户问“使用率 / 占用率 / 空间利用情况”时，优先对应 `SpaceOccupancyRate` 或 `SpaceUtilizationIndex`，不要误答成空置率。
- 用户问“会议室空置率 / 空置率评分”时，优先对应 `MeetingRoomVacancyScore`，并解释为“被预定但未使用”的评分。
- 如果用户追问“这个分数怎么来的”，要按 `references/space-model.md` 里的公式解释，不要只返回指标名。

## 指标计算知识库规则

- 当用户追问“怎么算出来的”“公式是什么”“为什么是这个分数”时，可以直接引用 `references/space-model.md` 中的指标公式、权重、统计口径和有效性规则进行解释。
- 可以解释公式，不可以脱离后端返回值去本地推导当前楼层、当前区域或当前时间段的真实分数。
- 如果后端已经返回了某个指标值，回答时先给出本次实际值，再解释该指标在知识库中的计算逻辑。
- 如果用户只问公式、不问当前值，可以不调用后端，直接解释指标定义、分子分母、权重和时间粒度。
- 如果用户同时问“现在是多少、怎么算的”，先调用 `get_space_utilization_index_data`，再结合知识库解释。
- 回答“空间利用指数”时，不要只说“后端内部计算”，必须补充默认权重：空间活力 0.3、空间集约度 0.5、空间品质 0.2。
- 回答“空间活力 / 空间集约度 / 空间品质”时，必须补充各自下钻指标与默认权重，避免只报指标名。
- 回答“占用率 / 使用频次 / 人均面积达标率 / 空间复用指数 / 履约率 / 空置率评分 / 冲突解决率”时，应优先说明分子、分母、归一化基准、无数据处理和时间粒度。
- 如果用户问“为什么没有小时值”，要说明部分 L3 指标只支持日/周粒度，小时展示采用日值回填口径。
- 如果用户问“为什么结果是 0”，要优先检查知识库里的有效性口径：单空间在线率低于 80% 会被剔除；若区域内某类有效空间数为 0，则该区域相关指标记 0；整层只对有效区域做面积加权。

## 输出要求

- 返回内容保持用户可读且简洁。
- 输出语言默认跟随用户问题语言：中文问题优先中文输出，英文问题优先英文输出。
- 如果后端 `Message`、区域名称、空间名称或预约名称本身只有一种语言，保留后端原文，不要自行翻译实体名或数值说明。
- 后端返回了实际数值时，必须原样带上该数值，不得改写或四舍五入。
- 只有在后端提供区域结果、整层结果、执行说明、预约结果或时间边界解释时，才展示这些信息。
- 后端即使返回了完整 `Indicators`，也只展示用户当前问题需要的字段；例如用户问“固定工位区的占用率”时，只返回对应区域的 `SpaceOccupancyRate`，不要把其余指标一起回显。
- 如果用户问题与空间相关，先原样展示本次后端返回的实际结果，再让大模型基于这些返回值判断当前结果是偏高、偏低还是正常，并给出结论。
- 输出时不要加“主人”这类称呼，也不要加“（后端返回数据）”这类标记，直接输出自然语言结论和建议。
- 结论只能依据本次后端返回的数值、时间范围、层级和区域信息，不得引入未查询到的外部数据，也不得自行补算指标。
- 如果需要给出意见或建议，建议条数不超过 5 条，内容应围绕当前查询结果的数值表现展开。
- 预约接口返回的 `Reservation`、`CandidateSpaces`、`ConflictReservations`、`CurrentReservation`、`NextReservation`、`LastReservation` 也只展示和用户问题相关的部分，不要无条件全量展开。
- `FloorData` 为空时不要伪造整层结果；`regionName` 传入后只读 `RegionData`。
- 除非用户明确要求，不输出内部接口路径、payload 结构或实现细节。

### 中英文统一输出模板

默认使用以下结构组织回答；没有对应内容的部分可以省略，不要强行补齐空标题。

中文模板：

```text
问题的答案是：XXX
详细内容：
1、XXX
2、XXX
结论：XXX
建议：
1、XXX
2、XXX
```

英文模板：

```text
The answer to your question is: XXX
Details:
1. XXX
2. XXX
Conclusion: XXX
Suggestions:
1. XXX
2. XXX
```

模板约束：

- `问题的答案是` / `The answer to your question is` 为首行主结论，必须先给出。
- `详细内容` / `Details` 只在后端确实返回了列表、候选项、区域明细、预约明细或时间桶明细时输出。
- `结论` / `Conclusion` 只在当前结果适合做高低、好坏、是否可预约、是否冲突等判断时输出。
- `建议` / `Suggestions` 只在当前结果支持提出行动建议时输出；最多 5 条。
- 如果只有一个简短结果，可只输出“问题的答案是：XXX”或“The answer to your question is: XXX”。
- 不要同时混用中英文标题；标题语言必须与本次回复主语言一致。
- 不要把内部字段名如 `Message`、`RegionData`、`FloorData`、`Indicators` 直接作为用户可见标题，除非用户明确要求查看原始字段。
- 如果 `详细内容` 是列表，中文使用 `1、2、3`，英文使用 `1. 2. 3.`。
- 如果答案来自预约接口，优先在“问题的答案是”中概括成功、失败、冲突或可预约状态，再在“详细内容”中补充预约时间、空间名、候选空间或冲突记录。
- 如果答案来自空间利用指数接口，优先在“问题的答案是”中概括用户关心的指标值与范围，再在“详细内容”中列出时间、区域、层级、指标名和对应数值。

## 结果解读

- 当用户询问任何空间相关问题时，先展示后端返回的原始结果，再由大模型根据这些返回值判断当前结果偏高、偏低还是正常。
- 输出时不要显式标注“后端返回数据”，直接给出结论即可。
- 如果结果明显偏低或偏高，结论应直接说明这一点，并补充不超过 5 条可执行建议。
- 如果结果处于中等或正常范围，可以简要给出总体判断，建议可以为空或很少。
- 不要把结论写成新的指标值，也不要把建议写成已经验证过的事实。
- 如果用户是在问“公式/计算逻辑”，不要再回答“无法得知详细计算过程”；应直接按知识库解释公式和权重。

## 参考文件

- `references/api-contract.md`：空间利用指数查询契约与返回结构说明。
- `references/space-model.md`：用户请求到空间利用指数展示语义的映射说明。
