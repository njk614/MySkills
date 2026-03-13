---
name: temperature-sensor-instruction
description: Query the temperature sensor API when the user asks about temperature or 温度, resolve user input to a device by 安装位置/孪生体实例名称 from data_organized.json, read the matched 用户台账ID temperature, and reply with the current temperature.
---

# Temperature Sensor Instruction

Use this skill when the user asks about temperature or 温度.

## Output Constraints

The assistant must follow the output rules below.

1. After successfully reading the temperature, reply in this pattern:

```text
{device}当前温度{temperature}℃
```

2. If the temperature query API fails, the target ledger temperature is missing, output exactly:

```text
温度查询失败，请稍后重试。
```

3. If the user input matches no device:

```text
设备不存在。
```

4. If the user input is a location and no device exists there:

```text
当前位置没有设备。
```

5. If the user input matches multiple devices with the same confidence, output exactly:

```text
当前位置存在多个设备，请提供更具体的孪生体实例名称。
```

6. `{temperature}` must be replaced with the actual measured temperature value (keep decimals when present).
7. `{device}` must be the matched device display name (prefer 安装位置).

## Workflow

1. Call the temperature API:
   POST /public/location/{locationID}/twinTypeDistinguish/TwinTimeSeries/batchQueryData
2. Load `data_organized.json` and resolve user input to a target 用户台账ID.
   - Input may be 安装位置 or 孪生体实例名称.
   - If no match, return `设备不存在。` or `当前位置没有设备。`.
3. Read the matched ledger temperature value from the response table.
4. If the query does not return the target ledger temperature immediately, retry the temperature query before failing.
5. Assess the temperature and return a user-facing reply following the Output Constraints above.

## Configuration

### Fixed business parameters

- Base URL: http://test.twinioc.net/api/editor/v1
- Location ID: dyo6vaow6203kx09
- Temperature query level ID: gez4ermd715t31le
- Twin category config ID: hcwn2ha6p49661rm
- Target ledger ID: R3nazZz8Pyb6o7uc
- Device catalog file: temperature-sensor-instruction/data_organized.json
- SendInstruction location placeholder: `__INSTALL_LOCATION__`
- Default maximum query attempts: 5
- Default retry interval: 1.0 second

### Default token

- Built-in default token: gj6mxa
- Resolution order:
  1. `--token`
  2. built-in default `gj6mxa`

### CLI parameters

- --token
  SendInstruction token.
  Default: fall back to `gj6mxa`.

- --base-url
  API base URL.
  Default: http://test.twinioc.net/api/editor/v1

- --location-id
  Location ID used by the temperature query API.
  Default: dyo6vaow6203kx09

- --target-ledger-id
  Fallback ledger ID when `--device-query` is not provided.
  Default: R3nazZz8Pyb6o7uc

- --device-query
  User input to resolve device by 安装位置 or 孪生体实例名称.

- --device-data-file
  Path to `data_organized.json`.
  Default: `temperature-sensor-instruction/data_organized.json`

- --threshold
  Temperature threshold for sending control instructions.
  The instruction branch runs only when temperature is strictly greater than this value.
  Default: 20.0

- --start-time
  Reserved parameter (backward compatibility).
  Format: YYYY-MM-DD HH:MM:SS
  Not sent to batchQueryData request body.

- --end-time
  Reserved parameter (backward compatibility).
  Format: YYYY-MM-DD HH:MM:SS
  Not sent to batchQueryData request body.

- --timeout
  HTTP timeout in seconds for both query and send operations.
  Default: 100.0

- --max-attempts
  Maximum number of temperature query attempts.
  Default: 5
  Retries repeat the same request body without `conditonTime`.

- --retry-interval
  Delay in seconds between temperature query retries.
  Default: 1.0

- --dry-run
  Run the full decision workflow without actually calling SendInstruction.
  The script still prints the final reply template.

- --quiet
  Suppress verbose runtime logs.
  The final reply message is also suppressed in quiet mode.

### Response behavior

- If the query fails, the target ledger temperature is missing, or SendInstruction fails, the script returns:

Before the script gives up, it retries temperature queries because the sensor may not publish data every second.

- If the query still fails after all retries, the target ledger temperature is still missing, or SendInstruction fails, the script returns:

```text
温度查询失败，请稍后重试。
```

- If temperature is greater than 20℃, the script returns the hot reply template and sends the instruction unless --dry-run is enabled.
  Before SendInstruction, `jsonData` is rendered dynamically using matched installation location.

- If temperature is less than or equal to 20℃, the script returns the normal reply template and does not send any instruction.

- If device matching fails, the script returns:
  - `设备不存在。` or
  - `当前位置没有设备。`
  - `当前位置存在多个设备，请提供更具体的孪生体实例名称。`

## Reply Templates

- Temperature above 20℃:

```text
{device}当前温度{temperature}℃，稍微有点热，为您打开{device}温控器，另外，照明灯已帮您关闭。
```

- Temperature less than or equal to 20℃:

```text
{device}当前温度{temperature}℃，温度适宜，不需要开温控器
```

- API failure reply:

```text
温度查询失败，请稍后重试。
```

- Device not found reply:

```text
设备不存在。
```

- No device at location reply:

```text
当前位置没有设备。
```

- Ambiguous location/device reply:

```text
当前位置存在多个设备，请提供更具体的孪生体实例名称。
```

## Scripts

- scripts/check_temperature.py
  Command-line entry point for the skill.

- scripts/temperature_checker.py
  Core workflow module for query, decision, reply generation, and instruction sending.

## Usage

Run from the workspace root:

```powershell
python temperature-sensor-instruction/scripts/check_temperature.py
```

Run without sending instructions:

```powershell
python temperature-sensor-instruction/scripts/check_temperature.py --dry-run
```

Run with dynamic location resolution:

```powershell
python temperature-sensor-instruction/scripts/check_temperature.py --dry-run --device-query "小会议室"
```

Run with explicit parameters:

```powershell
python temperature-sensor-instruction/scripts/check_temperature.py \
  --token gj6mxa \
   --base-url http://test.twinioc.net/api/editor/v1 \
   --location-id dyo6vaow6203kx09 \
   --device-query "大会议室" \
   --target-ledger-id R3nazZz8Pyb6o7uc \
   --threshold 20 \
   --start-time "2026-03-12 09:20:00" \
   --end-time "2026-03-12 09:25:30" \
   --timeout 100
```
