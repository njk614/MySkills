# 空间预定 MCP 返回结果示例

## 1. 返回类型总览

空间预定 MCP 当前有 4 类响应对象：

| 工具 | 返回类型 |
| --- | --- |
| `get_reservable_spaces` | `ReservableSpacesMcpResponse` |
| `check_space_availability` | `SpaceAvailabilityMcpResponse` |
| `get_space_reservation_status` | `SpaceReservationStatusMcpResponse` |
| `create_space_reservation` / `reschedule_space_reservation` / `cancel_space_reservation` | `SpaceReservationWriteMcpResponse` |

---

## 2. 返回字段结构

### 2.1 `ReservableSpacesMcpResponse`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `Message` | `string` | 执行结果说明 |
| `QueryMode` | `string` | `Current` 或 `Interval` |
| `StartTime` | `string` | 实际查询开始时间 |
| `EndTime` | `string` | 实际查询结束时间 |
| `SpaceList` | `array` | 匹配到的空间列表 |

`SpaceList` 中每项结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `SpaceId` | `string` | 空间 ID |
| `SpaceName` | `string` | 空间名称 |
| `SpaceType` | `string` | `灵活工位` 或 `会议室` |
| `LevelName` | `string` | 层级名称 |
| `RegionName` | `string` | 区域名称 |
| `IsReservable` | `bool` | 是否可预定 |
| `Reason` | `string` | 原因说明 |

### 2.2 `SpaceAvailabilityMcpResponse`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `Message` | `string` | 执行结果说明 |
| `SpaceId` | `string` | 空间 ID |
| `SpaceName` | `string` | 空间名称 |
| `SpaceType` | `string` | 空间类型 |
| `StartTime` | `string` | 查询开始时间 |
| `EndTime` | `string` | 查询结束时间 |
| `IsAvailable` | `bool` | 是否可用 |
| `ConflictReservations` | `array` | 时间冲突的预定记录 |

### 2.3 `SpaceReservationStatusMcpResponse`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `Message` | `string` | 执行结果说明 |
| `SpaceId` | `string` | 空间 ID |
| `SpaceName` | `string` | 空间名称 |
| `SpaceType` | `string` | 空间类型 |
| `QueryTime` | `string` | 查询时间 |
| `CurrentStatus` | `string` | 当前状态描述 |
| `CurrentReservation` | `object/null` | 当前进行中的预定 |
| `NextReservation` | `object/null` | 下一条预定 |
| `LastReservation` | `object/null` | 最近历史预定 |
| `ConflictReservations` | `array` | 当前冲突预定列表 |

### 2.4 `SpaceReservationWriteMcpResponse`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `Succeeded` | `bool` | 是否执行成功 |
| `Message` | `string` | 执行结果说明 |
| `Reservation` | `object/null` | 当前写入后的预定记录 |
| `CandidateSpaces` | `array` | 候选空间列表 |
| `ConflictReservations` | `array` | 与当前预定冲突的其他预定 |

---

## 3. 预定记录对象结构

`CurrentReservation`、`NextReservation`、`LastReservation`、`ConflictReservations`、`Reservation` 中的预定记录结构一致：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ReservationId` | `string` | 预定记录 ID |
| `SpaceId` | `string` | 空间 ID |
| `SpaceName` | `string` | 空间名称 |
| `SpaceType` | `string` | 空间类型 |
| `LevelName` | `string` | 层级名称 |
| `RegionName` | `string` | 区域名称 |
| `StartTime` | `string` | 预定开始时间 |
| `EndTime` | `string` | 预定结束时间 |
| `Status` | `string` | 预定状态 |
| `ReservedByUserId` | `string` | 预定用户 ID |
| `Booker` | `string` | 预定人 |
| `UsagePurpose` | `string` | 预定用途 |
| `CreatedTime` | `string` | 创建时间 |
| `ConflictFlag` | `int` | 冲突标识，`0/1` |
| `ConflictResolvedTime` | `string` | 冲突解决时间，无值时为空字符串 |

重点说明：

- `CreatedTime` 是后续改期、取消时必须回传的值
- `CreatedTime` 不等于 `StartTime`
- `Booker` 和 `UsagePurpose` 会在已预定记录、冲突记录、状态查询记录中一起返回

---

## 4. 返回结果示例

### 4.1 查询可预定空间成功

```json
{
  "Message": "共匹配 4 个空间，其中 2 个可预定。",
  "QueryMode": "Interval",
  "StartTime": "2026-03-28 14:00:00",
  "EndTime": "2026-03-28 17:00:00",
  "SpaceList": [
    {
      "SpaceId": "FD102",
      "SpaceName": "灵活工位102",
      "SpaceType": "灵活工位",
      "LevelName": "1F",
      "RegionName": "灵活工位区A",
      "IsReservable": true,
      "Reason": "可预定"
    },
    {
      "SpaceId": "FD103",
      "SpaceName": "灵活工位103",
      "SpaceType": "灵活工位",
      "LevelName": "1F",
      "RegionName": "灵活工位区A",
      "IsReservable": true,
      "Reason": "可预定"
    },
    {
      "SpaceId": "FD101",
      "SpaceName": "灵活工位101",
      "SpaceType": "灵活工位",
      "LevelName": "1F",
      "RegionName": "灵活工位区A",
      "IsReservable": false,
      "Reason": "该时间段已存在预定"
    },
    {
      "SpaceId": "FD104",
      "SpaceName": "灵活工位104",
      "SpaceType": "灵活工位",
      "LevelName": "1F",
      "RegionName": "灵活工位区A",
      "IsReservable": false,
      "Reason": "该时间段已存在预定"
    }
  ]
}
```

### 4.2 单个空间不可用

```json
{
  "Message": "该时间段已存在预定。",
  "SpaceId": "MR001",
  "SpaceName": "会议室A",
  "SpaceType": "会议室",
  "StartTime": "2026-03-28 14:00:00",
  "EndTime": "2026-03-28 17:00:00",
  "IsAvailable": false,
  "ConflictReservations": [
    {
      "ReservationId": "R20260328001",
      "SpaceId": "MR001",
      "SpaceName": "会议室A",
      "SpaceType": "会议室",
      "LevelName": "1F",
      "RegionName": "会议室区",
      "StartTime": "2026-03-28 13:30:00",
      "EndTime": "2026-03-28 15:00:00",
      "Status": "已预定",
      "ReservedByUserId": "U1001",
      "Booker": "张三",
      "UsagePurpose": "周会",
      "CreatedTime": "2026-03-28 09:12:01",
      "ConflictFlag": 0,
      "ConflictResolvedTime": ""
    }
  ]
}
```

### 4.3 查询空间预定状态

```json
{
  "Message": "获取成功。",
  "SpaceId": "FD102",
  "SpaceName": "灵活工位102",
  "SpaceType": "灵活工位",
  "QueryTime": "2026-03-28 14:30:00",
  "CurrentStatus": "当前已预定",
  "CurrentReservation": {
    "ReservationId": "R20260328008",
    "SpaceId": "FD102",
    "SpaceName": "灵活工位102",
    "SpaceType": "灵活工位",
    "LevelName": "1F",
    "RegionName": "灵活工位区A",
    "StartTime": "2026-03-28 14:00:00",
    "EndTime": "2026-03-28 17:00:00",
    "Status": "已预定",
    "ReservedByUserId": "U2001",
    "Booker": "李四",
    "UsagePurpose": "专注办公",
    "CreatedTime": "2026-03-28 10:20:05",
    "ConflictFlag": 0,
    "ConflictResolvedTime": ""
  },
  "NextReservation": {
    "ReservationId": "R20260328019",
    "SpaceId": "FD102",
    "SpaceName": "灵活工位102",
    "SpaceType": "灵活工位",
    "LevelName": "1F",
    "RegionName": "灵活工位区A",
    "StartTime": "2026-03-29 09:30:00",
    "EndTime": "2026-03-29 12:00:00",
    "Status": "已预定",
    "ReservedByUserId": "U2001",
    "Booker": "李四",
    "UsagePurpose": "专注办公",
    "CreatedTime": "2026-03-28 17:05:11",
    "ConflictFlag": 0,
    "ConflictResolvedTime": ""
  },
  "LastReservation": {
    "ReservationId": "R20260327031",
    "SpaceId": "FD102",
    "SpaceName": "灵活工位102",
    "SpaceType": "灵活工位",
    "LevelName": "1F",
    "RegionName": "灵活工位区A",
    "StartTime": "2026-03-27 09:30:00",
    "EndTime": "2026-03-27 18:00:00",
    "Status": "已预定",
    "ReservedByUserId": "U2001",
    "Booker": "李四",
    "UsagePurpose": "专注办公",
    "CreatedTime": "2026-03-27 08:58:21",
    "ConflictFlag": 0,
    "ConflictResolvedTime": ""
  },
  "ConflictReservations": []
}
```

### 4.4 创建预定成功，无冲突

```json
{
  "Succeeded": true,
  "Message": "预定成功。",
  "Reservation": {
    "ReservationId": "N8sK2pQ7z",
    "SpaceId": "MR001",
    "SpaceName": "会议室A",
    "SpaceType": "会议室",
    "LevelName": "1F",
    "RegionName": "会议室区",
    "StartTime": "2026-03-28 16:00:00",
    "EndTime": "2026-03-28 17:00:00",
    "Status": "已预定",
    "ReservedByUserId": "U3001",
    "Booker": "张三",
    "UsagePurpose": "项目评审",
    "CreatedTime": "2026-03-28 10:15:21",
    "ConflictFlag": 0,
    "ConflictResolvedTime": ""
  },
  "CandidateSpaces": [],
  "ConflictReservations": []
}
```

### 4.5 未指定具体空间时随机命中一个可用空间并创建成功

```json
{
  "Succeeded": true,
  "Message": "预定成功。",
  "Reservation": {
    "ReservationId": "A7c9Lm2Xq",
    "SpaceId": "FD102",
    "SpaceName": "灵活工位102",
    "SpaceType": "灵活工位",
    "LevelName": "1F",
    "RegionName": "灵活工位区A",
    "StartTime": "2026-03-28 14:00:00",
    "EndTime": "2026-03-28 17:00:00",
    "Status": "已预定",
    "ReservedByUserId": "10001",
    "Booker": "李四",
    "UsagePurpose": "临时办公",
    "CreatedTime": "2026-03-28 10:15:21",
    "ConflictFlag": 0,
    "ConflictResolvedTime": ""
  },
  "CandidateSpaces": [],
  "ConflictReservations": []
}
```

### 4.6 创建预定成功，但存在冲突

```json
{
  "Succeeded": true,
  "Message": "预定成功，当前预定存在冲突。",
  "Reservation": {
    "ReservationId": "Q9xT7Lm2A",
    "SpaceId": "MR001",
    "SpaceName": "会议室A",
    "SpaceType": "会议室",
    "LevelName": "1F",
    "RegionName": "会议室区",
    "StartTime": "2026-03-28 14:00:00",
    "EndTime": "2026-03-28 15:30:00",
    "Status": "已预定",
    "ReservedByUserId": "U3001",
    "Booker": "张三",
    "UsagePurpose": "紧急讨论",
    "CreatedTime": "2026-03-28 10:40:12",
    "ConflictFlag": 1,
    "ConflictResolvedTime": ""
  },
  "CandidateSpaces": [],
  "ConflictReservations": [
    {
      "ReservationId": "R20260328001",
      "SpaceId": "MR001",
      "SpaceName": "会议室A",
      "SpaceType": "会议室",
      "LevelName": "1F",
      "RegionName": "会议室区",
      "StartTime": "2026-03-28 13:30:00",
      "EndTime": "2026-03-28 15:00:00",
      "Status": "已预定",
      "ReservedByUserId": "U1001",
      "Booker": "王五",
      "UsagePurpose": "客户接待",
      "CreatedTime": "2026-03-28 09:12:01",
      "ConflictFlag": 1,
      "ConflictResolvedTime": ""
    }
  ]
}
```

### 4.7 改期成功

```json
{
  "Succeeded": true,
  "Message": "改期成功。",
  "Reservation": {
    "ReservationId": "N8sK2pQ7z",
    "SpaceId": "MR001",
    "SpaceName": "会议室A",
    "SpaceType": "会议室",
    "LevelName": "1F",
    "RegionName": "会议室区",
    "StartTime": "2026-03-29 09:30:00",
    "EndTime": "2026-03-29 11:00:00",
    "Status": "已预定",
    "ReservedByUserId": "U3001",
    "Booker": "张三",
    "UsagePurpose": "项目评审",
    "CreatedTime": "2026-03-28 10:15:21",
    "ConflictFlag": 0,
    "ConflictResolvedTime": ""
  },
  "CandidateSpaces": [],
  "ConflictReservations": []
}
```

### 4.8 取消成功

```json
{
  "Succeeded": true,
  "Message": "取消预定成功。",
  "Reservation": {
    "ReservationId": "N8sK2pQ7z",
    "SpaceId": "FD102",
    "SpaceName": "灵活工位102",
    "SpaceType": "灵活工位",
    "LevelName": "1F",
    "RegionName": "灵活工位区A",
    "StartTime": "2026-03-28 14:00:00",
    "EndTime": "2026-03-28 17:00:00",
    "Status": "已取消",
    "ReservedByUserId": "U3001",
    "Booker": "李四",
    "UsagePurpose": "临时办公",
    "CreatedTime": "2026-03-28 10:20:05",
    "ConflictFlag": 0,
    "ConflictResolvedTime": "2026-03-28 11:08:33"
  },
  "CandidateSpaces": [],
  "ConflictReservations": []
}
```

---

## 5. 调用方最需要关注的字段

如果上层要支持：

- “取消刚才预定的工位”
- “把刚才那个预定改到明天上午”

务必保存这两个字段：

- `Reservation.SpaceId`
- `Reservation.CreatedTime`

后续取消或改期时，必须把这两个值显式传回去。
