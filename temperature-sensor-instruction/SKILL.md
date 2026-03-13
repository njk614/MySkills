---
name: temperature-sensor-instruction
description: Query the temperature sensor API when the user asks about temperature or 温度, read the temperature for ledger ID R3nazZz8Pyb6o7uc, and send a control instruction when the temperature is above 20℃.
---

# Temperature Sensor Instruction

Use this skill when the user asks about temperature or 温度.

## Output Constraints

The assistant must follow the fixed output templates below and must not paraphrase, expand, or rewrite them.

1. If the measured temperature is greater than 20℃, output exactly:

```text
大会议室当前温度{temperature}℃，稍微有点热，为您打开大会议室温控器，另外，照明灯已帮您关闭。
```

2. If the measured temperature is less than or equal to 20℃, output exactly:

```text
大会议室当前温度{temperature}℃，温度适宜，不需要开温控器
```

3. If the temperature query API fails, the target ledger temperature is missing, or the SendInstruction API fails, output exactly:

```text
温度查询失败，请稍后重试。
```

4. `{temperature}` must be replaced with the actual measured temperature rounded to the nearest integer.

## Workflow

1. Call the temperature API:
   POST /public/location/{locationID}/twinTypeDistinguish/TwinTimeSeries/batchQueryData
2. Query the target ledger ID:
   R3nazZz8Pyb6o7uc
3. Read the temperature value from the response table.
4. If temperature is above 20℃, call:
   POST /location/SendInstruction
5. If the query does not return the target ledger temperature immediately, retry the temperature query before failing.
6. Return a user-facing reply message.
7. Send the fixed instruction payload below when the hot branch is triggered:

```text
B09：关闭温控器：大会议室温控器$&打开温控器：大会议室温控器$&根据最优策略，已经为您规划如下执行计划：
1、关闭温控器：大会议室温控器
```

## Configuration

### Fixed business parameters

- Base URL: http://test.twinioc.net/api/editor/v1
- Location ID: dyo6vaow6203kx09
- Temperature query level ID: gez4ermd715t31le
- Twin category config ID: hcwn2ha6p49661rm
- Target ledger ID: R3nazZz8Pyb6o7uc
- Temperature threshold: 20.0
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
  Ledger ID whose temperature is used for the decision.
  Default: R3nazZz8Pyb6o7uc

- --threshold
  Temperature threshold for sending control instructions.
  The instruction branch runs only when temperature is strictly greater than this value.
  Default: 20.0

- --start-time
  Query window start time.
  Format: YYYY-MM-DD HH:MM:SS
  Default: current local time minus 1 second.

- --end-time
  Query window end time.
  Format: YYYY-MM-DD HH:MM:SS
  Default: current local time.

- --timeout
  HTTP timeout in seconds for both query and send operations.
  Default: 10.0

- --max-attempts
  Maximum number of temperature query attempts.
  Default: 5
  When `--start-time` and `--end-time` are omitted, each retry recalculates the query window and increases the lookback range by 1 second.

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
When `--start-time` and `--end-time` are not provided, retry attempt windows expand like this: `[-1s, now]`, `[-2s, now]`, `[-3s, now]`, and so on until the maximum attempt count is reached.

- If the query still fails after all retries, the target ledger temperature is still missing, or SendInstruction fails, the script returns:

```text
温度查询失败，请稍后重试。
```

- If temperature is greater than 20℃, the script returns the hot reply template and sends the instruction unless --dry-run is enabled.

- If temperature is less than or equal to 20℃, the script returns the normal reply template and does not send any instruction.

## Reply Templates

- Temperature above 20℃:

```text
大会议室当前温度{temperature}℃，稍微有点热，为您打开大会议室温控器，另外，照明灯已帮您关闭。
```

- Temperature less than or equal to 20℃:

```text
大会议室当前温度{temperature}℃，温度适宜，不需要开温控器
```

- API failure reply:

```text
温度查询失败，请稍后重试。
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

Run with explicit parameters:

```powershell
python temperature-sensor-instruction/scripts/check_temperature.py \
  --token gj6mxa \
   --base-url http://test.twinioc.net/api/editor/v1 \
   --location-id dyo6vaow6203kx09 \
   --target-ledger-id R3nazZz8Pyb6o7uc \
   --threshold 20 \
   --start-time "2026-03-12 09:20:00" \
   --end-time "2026-03-12 09:25:30" \
   --timeout 10
```
