# 空间指标映射

本文档把常见用户请求映射到后端应展示的空间利用指数字段名称和范围语义。

## 当前实际返回的指标字段

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

## 用户请求与展示语义

- “空间利用情况怎么样”
  - 优先展示 `Message`、`RegionData`、`FloorData`
  - 如有需要，再展开 `Indicators`

- “固定工位区的占用率”
  - 只展示固定工位区对应结果里的 `SpaceOccupancyRate`
  - 不把同一条结果里的其他指标一并输出，除非用户继续追问

- “这个楼层怎么样”
  - 对应某个 `levelName` 下的整层结果与区域结果

- “某个区域怎么样”
  - 传入 `regionName`，只展示该区域的 `RegionData`

## 范围提示

- `levelName` 是层级名称，例如 `1F`、`2F`、`B1`
- 如果用户问题没有明确层级，默认使用 `楼层20`
- `regionName` 是区域名称，例如某个固定工位区或会议室区；如果未识别到，默认传 `""`（空字符串）
- `FloorData` 为整层聚合结果，仅在 `regionName` 为空字符串时返回
- `RegionData` 为区域级结果，传入 `regionName` 后只展示这里的结果

## 时间粒度提示

- `Hour`：小时桶起始时间
- `Day`：日桶时间，固定为 `00:00:00`
- `Week`：周一 `00:00:00`
- `Month`：每月 1 号 `00:00:00`
- 如果用户问题没有明确时间范围，默认按当前小时桶查询，`startTime` 为当前小时桶起始时间，`endTime` 为当前小时桶结束时间或当前时刻

## 返回提示

- 始终优先使用后端返回的数值。
- 当用户询问原因、时间边界或粒度语义时，附上后端给出的 `Message` 和本文件中的解释。
- 如果后端返回多个区域结果，先按后端结果展示，不要自行合并或筛选。
