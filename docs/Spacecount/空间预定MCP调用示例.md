# 空间预定 MCP 调用示例

## 1. 适用工具

当前空间预定 MCP 对外提供以下 6 个工具：

- `get_reservable_spaces`
- `check_space_availability`
- `get_space_reservation_status`
- `create_space_reservation`
- `reschedule_space_reservation`
- `cancel_space_reservation`

## 2. 调用前提

### 2.1 公共要求

所有工具都需要：

- `token`：SignalR 连接返回的 6 位 `UniqueId`

### 2.2 时间格式要求

建议统一使用：

```text
yyyy-MM-dd HH:mm:ss
```

例如：

```text
2026-03-28 14:00:00
```

### 2.3 `createdTime` 的含义

`reschedule_space_reservation` 和 `cancel_space_reservation` 中的 `createdTime`：

- 不是预定开始时间
- 不是预定结束时间
- 而是预定记录返回结果中的 `Reservation.CreatedTime`

它对应数据对象的系统字段 `时间`，用于唯一定位一条预定记录。

---

## 3. MCP 调用格式

统一格式如下：

```json
{
  "name": "工具名",
  "arguments": {
    "参数1": "值",
    "参数2": "值"
  }
}
```

---

## 4. 调用示例

### 4.1 查询当前可预定空间

未传 `startTime` / `endTime` 时，表示按“当前时刻”判断是否可预定。

本例传参说明：

- `spaceType`：传空字符串，表示同时查询 `灵活工位` 和 `会议室`
- `startTime`：传空字符串，表示不按指定时间段查询，而是按当前时刻判断
- `endTime`：传空字符串，需要和 `startTime` 一起为空，不能只空一个
- `levelName`：传 `1F`，表示只查 `1F` 层级内的空间
- `regionName`：传空字符串，表示不按区域继续过滤
- `token`：传 SignalR 连接返回的 6 位 `UniqueId`

```json
{
  "name": "get_reservable_spaces",
  "arguments": {
    "spaceType": "",
    "startTime": "",
    "endTime": "",
    "levelName": "1F",
    "regionName": "",
    "token": "123456"
  }
}
```

### 4.2 查询某时间段可预定的灵活工位

本例传参说明：

- `spaceType`：传 `灵活工位`，表示只查灵活工位，不查会议室
- `startTime`：传 `2026-03-28 14:00:00`
- `endTime`：传 `2026-03-28 17:00:00`
- `levelName`：传 `1F`
- `regionName`：传 `灵活工位区A`
- `token`：用于定位当前场景

```json
{
  "name": "get_reservable_spaces",
  "arguments": {
    "spaceType": "灵活工位",
    "startTime": "2026-03-28 14:00:00",
    "endTime": "2026-03-28 17:00:00",
    "levelName": "1F",
    "regionName": "灵活工位区A",
    "token": "123456"
  }
}
```

### 4.3 判断单个会议室是否可用

本例传参说明：

- `spaceId`：传 `MR001`
- `spaceType`：传 `会议室`
- `startTime`：要检查的开始时间
- `endTime`：要检查的结束时间，必须晚于 `startTime`
- `token`：用于定位当前场景

```json
{
  "name": "check_space_availability",
  "arguments": {
    "spaceId": "MR001",
    "spaceType": "会议室",
    "startTime": "2026-03-28 14:00:00",
    "endTime": "2026-03-28 17:00:00",
    "token": "123456"
  }
}
```

### 4.4 查询单个工位当前预定状态

`queryTime` 不传时，默认按当前时间查询。

本例传参说明：

- `spaceId`：传 `FD102`
- `spaceType`：传 `灵活工位`
- `token`：用于定位当前场景
- `queryTime`：传 `2026-03-28 14:30:00`

```json
{
  "name": "get_space_reservation_status",
  "arguments": {
    "spaceId": "FD102",
    "spaceType": "灵活工位",
    "token": "123456",
    "queryTime": "2026-03-28 14:30:00"
  }
}
```

### 4.5 按会议室名称直接创建预定

`create_space_reservation` 需要补充两个必填参数：

- `booker`：预定人
- `usagePurpose`：预定用途

本例传参说明：

- `spaceType`：传 `会议室`
- `startTime`：预定开始时间
- `endTime`：预定结束时间
- `token`：用于定位当前场景
- `booker`：传 `张三`
- `usagePurpose`：传 `项目评审`
- `spaceId`：传空字符串，表示不按 `spaceId` 定位
- `spaceName`：传 `会议室A`

```json
{
  "name": "create_space_reservation",
  "arguments": {
    "spaceType": "会议室",
    "startTime": "2026-03-28 14:00:00",
    "endTime": "2026-03-28 17:00:00",
    "token": "123456",
    "booker": "张三",
    "usagePurpose": "项目评审",
    "spaceId": "",
    "spaceName": "会议室A"
  }
}
```

### 4.6 按空间 ID 创建预定

当已经明确知道 `spaceId` 时，优先传 `spaceId`。

```json
{
  "name": "create_space_reservation",
  "arguments": {
    "spaceType": "灵活工位",
    "startTime": "2026-03-28 14:00:00",
    "endTime": "2026-03-28 17:00:00",
    "token": "123456",
    "booker": "李四",
    "usagePurpose": "专注办公",
    "spaceId": "FD102",
    "spaceName": ""
  }
}
```

### 4.7 不指定具体空间，由服务端分配一个可用空间

当只知道“想预定一个灵活工位”，但没有指定 `spaceId / spaceName` 时，可以这样调用：

```json
{
  "name": "create_space_reservation",
  "arguments": {
    "spaceType": "灵活工位",
    "startTime": "2026-03-28 14:00:00",
    "endTime": "2026-03-28 17:00:00",
    "token": "123456",
    "booker": "李四",
    "usagePurpose": "临时办公",
    "spaceId": "",
    "spaceName": ""
  }
}
```

如果该时间段有多个可用工位，服务端会随机挑选一个可用工位并直接写入预定记录；如果一个可用工位都没有，则返回失败。

### 4.8 改期预定

`createdTime` 必须取自原预定返回结果中的 `Reservation.CreatedTime`。

```json
{
  "name": "reschedule_space_reservation",
  "arguments": {
    "spaceId": "MR001",
    "createdTime": "2026-03-28 10:15:21",
    "newStartTime": "2026-03-29 09:30:00",
    "newEndTime": "2026-03-29 11:00:00",
    "token": "123456"
  }
}
```

### 4.9 取消预定

同样必须传 `spaceId + createdTime`。

```json
{
  "name": "cancel_space_reservation",
  "arguments": {
    "spaceId": "FD102",
    "createdTime": "2026-03-28 10:20:05",
    "token": "123456"
  }
}
```

---

## 5. 常见调用说明

### 5.1 `get_reservable_spaces` 中时间可不传

- `startTime` 和 `endTime` 要么都传
- 要么都不传

如果只传一个，服务端会返回参数错误。

### 5.2 `create_space_reservation` 不会因为冲突拒绝写入

如果指定了明确空间，即使和已有预定时间重叠：

- 服务端仍会写入预定
- 然后重算 `冲突标识`
- 并在返回中给出 `ConflictReservations`

### 5.3 `reschedule_space_reservation` / `cancel_space_reservation` 不支持“上一条上下文”

不能只传“取消刚才的预定”这类模糊请求，必须显式传：

- `spaceId`
- `createdTime`

### 5.4 推荐的上层接入方式

对于“取消刚才预定的工位”“把刚才那个预定改到明天上午”这类问题，建议上层这样处理：

1. 先调用 `create_space_reservation` 或 `get_space_reservation_status`
2. 保存返回结果中的 `Reservation.SpaceId`
3. 保存返回结果中的 `Reservation.CreatedTime`
4. 后续取消或改期时，把这两个值显式传给接口
