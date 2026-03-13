---
name: alarm-poller-instruction
description: Poll TwinEasy alarm endpoint at a fixed interval (default 1 second) for one or more level IDs, and call SendInstruction automatically when alarm data exists. Use when users ask to build or run real-time alarm polling, automatic alarm forwarding, or command-trigger integration from alarm APIs.
---

# Alarm Poller Instruction

本 skill 仅负责“告警查询 + 告警后续发送指令”。
温度传感器查询与温控指令请使用独立 skill：`temperature-sensor-instruction`。

Implement and run a Python poller that:

1. Calls `POST /public/location/{locationID}/batchAlarmData` every second.
2. Uses required `locationID` and `levelID` values.
3. Calls `POST /location/SendInstruction` when alarm data is found.

## Use the bundled script

Use [`scripts/alarm_poller.py`](scripts/alarm_poller.py). Do not rewrite the polling loop unless requirements change.

Default values are already aligned with this task:

- `base-url`: `http://test.twinioc.net/api/editor/v1`
- `location-id`: `dyo6vaow6203kx09`
- `level-ids`: `rsy0t4jdpr41oyii`, `gez4ermd715t31le`
- `interval`: `1.0` second
- `token`: `gj6mxa` (default value)
- `jsonData` (default):

```text
B08: close light: main meeting room light
B01: focus target: main meeting room camera 1
E02: filter: set display mode, 3x3
```

## Supported options

```bash
python scripts/alarm_poller.py \
	--location-id dyo6vaow6203kx09 \
	--level-ids rsy0t4jdpr41oyii gez4ermd715t31le \
	--token <your_token> \
	--begin-generation-time "2026-03-12 09:41:04" \
	--end-generation-time "2026-03-12 09:41:05" \
	--json-data-1 "..." \
	--json-data-2 "..." \
	--timeout 10 \
	--verbose
```

If `--token` is omitted, the script falls back to `gj6mxa`.

- Override fixed `jsonData`:

```bash
python scripts/alarm_poller.py --json-data "{\"event\":\"alarm\"}"
```

- Enable dynamic `jsonData`:

```bash
python scripts/alarm_poller.py --dynamic-json-data
```

- Override IDs:

```bash
python scripts/alarm_poller.py --location-id dyo6vaow6203kx09 --level-ids rsy0t4jdpr41oyii gez4ermd715t31le
```

## Editing rules

- Keep polling interval default at `1.0` second unless user explicitly asks to change.
- Keep both required `levelID` defaults unless user explicitly asks to replace.
- Keep the fixed command-line `jsonData` as default unless the user explicitly asks to change it.
