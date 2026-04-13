# 孪生体时序 MCP 调用说明

## 接口名称

`get_twin_realtime_time_series_data`

## 接口说明

根据 `token` 和 `twinId` 或 `twinName`，查询单个孪生体最新一条实时孪生体时序数据。

说明：
`get_twin_realtime_time_series_data` 是 MCP 对外调用的工具名，调用时应放在 `name` 中，不是作为普通业务参数放进 `arguments`。

## 方法签名

```csharp
public async Task<Dictionary<string, object>> GetTwinRealtimeTimeSeriesData(
    string token,
    string? twinId = null,
    string? twinName = null)
```

## 入参说明

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `token` | `string` | 是 | SignalR 连接时返回的 6 位 `UniqueId` |
| `twinId` | `string?` | 否 | 孪生体实例 ID，建议优先传该值精确查询 |
| `twinName` | `string?` | 否 | 孪生体实例名称 |

## 入参约束

1. `token` 必填
2. `twinId` 和 `twinName` 不能同时为空
3. 当 `twinName` 命中多个实例时，会返回提示信息，要求改用 `twinId`

## 调用示例

### MCP 调用格式

```json
{
  "name": "get_twin_realtime_time_series_data",
  "arguments": {
    "token": "A1B2C3",
    "twinId": "camera_001",
    "twinName": null
  }
}
```

### 按孪生体实例 ID 调用

```json
{
  "name": "get_twin_realtime_time_series_data",
  "arguments": {
    "token": "A1B2C3",
    "twinId": "camera_001",
    "twinName": null
  }
}
```

### 按孪生体实例名称调用

```json
{
  "name": "get_twin_realtime_time_series_data",
  "arguments": {
    "token": "A1B2C3",
    "twinId": null,
    "twinName": "1F摄像头01"
  }
}
```

## 成功返回

返回类型：

```csharp
Dictionary<string, object>
```

成功时包含以下字段：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `TwinId` | `string` | 孪生体实例 ID |
| `TwinName` | `string` | 孪生体实例名称 |
| `TwinCategoryConfigID` | `string` | 所属孪生体类别配置 ID |
| `TwinCategoryName` | `string` | 所属孪生体类别名称 |
| `Data` | `object` | 最新一条实时时序数据，实际为 `Dictionary<string, object>` |

成功返回示例：

```json
{
  "TwinId": "camera_001",
  "TwinName": "1F摄像头01",
  "TwinCategoryConfigID": "twc_20260407001",
  "TwinCategoryName": "摄像头",
  "Data": {
    "时间": "2026-04-07 10:30:15",
    "在线状态": "在线",
    "温度": 36.5,
    "电压": 220.0
  }
}
```

## 失败返回

失败时返回：

```csharp
Dictionary<string, object>
```

通常只包含以下字段：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `Message` | `string` | 错误信息 |

失败返回示例：

```json
{
  "Message": "twinId 和 twinName 不能同时为空。"
}
```

```json
{
  "Message": "token无效或已过期，请重新连接SignalR获取新的token"
}
```

```json
{
  "Message": "未找到孪生体实例ID[camera_001]。"
}
```

```json
{
  "Message": "未找到孪生体实例名称[1F摄像头01]。"
}
```

```json
{
  "Message": "孪生体实例名称[1F摄像头01]匹配到多个实例，请改用 twinId 精确查询。"
}
```

```json
{
  "Message": "该孪生体未配置可查询的时序字段。"
}
```

```json
{
  "Message": "未查询到实时孪生体时序数据。"
}
```
