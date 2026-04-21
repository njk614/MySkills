---
name: ruisi-twinioc-envmetric-skill
description: 该技能用于环境舒适度与环境指标查询。适用于温度、湿度、CO2、PM2.5、PM10、TVOC、甲醛、噪声、光照、空气质量、达标率、趋势、温度传感器、环境元数据等问题。明确不用于设备控制、灯光控制、温控器开关、摄像头控制、空间预约、空间利用指数或告警处理动作。所有数据来自环境指标 REST API，不进行本地臆造。
---

# 睿思孪易环境统计技能 - API 驱动版

## 概述

该技能通过调用 **环境指标 REST API** 为用户提供实时的环境舒适度数据查询能力。支持：

- 查询某区域最新环境指标
- 查询某个具体指标的当前值
- 获取指标的时间序列趋势（小时/日/周粒度）
- 查询温度传感器的实时和历史数据
- 获取可用指标和区域的元数据

所有数据直接来自后端 REST API，不做本地计算或臆造。

## 核心接口列表

### 1. 元数据接口

| 接口                           | 用途             | 返回内容                                     |
| ------------------------------ | ---------------- | -------------------------------------------- |
| `GET /api/v1/env/meta/metrics` | 获取可用指标清单 | 所有支持的 metric_code、名称、单位、可用粒度 |
| `GET /api/v1/env/meta/areas`   | 获取可用区域清单 | floor_no 和 area_name 的所有组合             |

### 2. 温度传感器接口

| 接口                                              | 用途                       | 返回内容                     |
| ------------------------------------------------- | -------------------------- | ---------------------------- |
| `GET /api/v1/env/temperature/sensors`             | 获取全部温度传感器当前结果 | 所有传感器的实时温度及派生值 |
| `GET /api/v1/env/temperature/sensors/{sensor_id}` | 获取单个传感器数据         | 指定传感器的最新结果         |

### 3. 区域指标接口

| 接口                                                               | 用途                   | 返回内容                                        |
| ------------------------------------------------------------------ | ---------------------- | ----------------------------------------------- |
| `GET /api/v1/env/areas/{area_name}/metrics/latest`                 | 获取某区域全部最新指标 | 区域级小时指标的最新完整集合                    |
| `GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/latest`   | 获取某指标最新值       | 指定指标的当前值（来自 env_metric_hourly_area） |
| `GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/timeline` | 获取指标趋势           | 指定粒度的时间序列数据（hourly/daily/weekly）   |

## 支持的指标代码

### 温度相关

- `temperature_compliance_rate` - 温度达标率 (%)
- `temperature_fluctuation_1h` - 温度波动幅度 (℃)

### 湿度相关

- `humidity_compliance_rate` - 湿度达标率 (%)
- `humidity_fluctuation_1h` - 湿度波动幅度 (%RH)

### 空气质量相关

- `co2_compliance_rate` - CO2达标率 (%)
- `pm25_compliance_rate` - PM2.5达标率 (%)
- `pm10_compliance_rate` - PM10达标率 (%)
- `formaldehyde_compliance_rate` - 甲醛达标率 (%)
- `tvoc_compliance_rate` - TVOC达标率 (%)
- `air_quality_index` - 综合空气质量指数 (score)

### 噪声相关

- `noise_compliance_rate` - 噪音达标率 (%)
- `noise_fluctuation_1h` - 噪音波动幅度 (dB(A))
- `noise_equivalent_level_1h` - 等效声级 (dB(A))

### 光照相关

- `light_compliance_rate` - 光照达标率 (%)
- `light_uniformity_1h` - 光照均匀度 (ratio)

## 支持的区域

- 主场
- 大会议室
- 小会议室
- 机房

## 用户问题 → API 调用映射

用户问题的几种典型场景与对应API调用：

### 场景 1：查最新环境概览

**用户问题**: "主场现在的环境指标如何？" / "主场当前的环境数据"

**API调用**:

```
GET /api/v1/env/areas/主场/metrics/latest
```

**处理逻辑**:

1. 调用接口获取数据
2. 遍历返回的 items 数组，提取每个指标的 metric_code、metric_name、metric_value、unit
3. 按指标分类（温度、湿度、空气、噪声、光照）组织返回结果
4. 基于 references/environment-metrics.md 中的阈值，对每个数值进行合规性评价

### 场景 2：查单个指标当前值

**用户问题**: "大会议室的温度达标率多少？" / "小会议室的CO2浓度达标吗？"

**API调用**:

```
GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/latest
```

**处理逻辑**:

1. 从用户问题中识别 area_name 和 metric_code（参考上述代码表）
2. 调用接口获取数据
3. 返回 metric_code、metric_name、metric_value、unit、stat_time
4. 根据 references/environment-metrics.md 的阈值说明是否达标

### 场景 3：查指标趋势

**用户问题**: "主场过去 24 小时温度达标率的变化趋势" / "大会议室最近一周的CO2达标率"

**API调用**:

```
GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/timeline?granularity={hourly|daily|weekly}&limit={count}
```

**处理逻辑**:

1. 从用户问题识别 area_name、metric_code 和时间粒度
2. granularity 优先级：用户显式指定 > 根据时间跨度推荐（24小时用hourly、一周用daily、更长用weekly）
3. 调用接口获取数据
4. 返回时间序列，可选绘制曲线或输出数值表格

### 场景 4：查温度传感器

**用户问题**: "所有温度传感器的当前温度" / "传感器 3bTaKlCNKOhIj8N2 的数据"

**API调用**:

```
GET /api/v1/env/temperature/sensors
或
GET /api/v1/env/temperature/sensors/{sensor_id}
```

**处理逻辑**:

1. 如果查询全部，返回 items 数组，按 install_location 分组
2. 如果查询单个，返回该传感器的详细数据

### 场景 5：查元数据

**用户问题**: "系统支持查询哪些环境指标？" / "哪些区域可以查询"

**API调用**:

```
GET /api/v1/env/meta/metrics
GET /api/v1/env/meta/areas
```

## 核心规则

1. **数据源优先级**：
   - 最新值优先从 env_metric_hourly_area 获取
   - 趋势数据按 granularity 参数选择 hourly/daily/weekly 表
   - 传感器数据来自 temp_out

2. **时间粒度推荐**：
   - 用户问"最近 24 小时" → granularity=hourly
   - 用户问"最近一周" → granularity=daily
   - 用户问"最近一月或更长" → granularity=weekly

3. **默认参数**：
   - metric_level: L3（当前实际落库的级别）
   - floor_no: 20（当前固定值）
   - 区域：从参考的 4 个区域中选择

4. **错误处理**：
   - 如果 API 返回 404，说明该区域或指标暂无数据
   - 如果 API 返回异常，返回错误信息给用户

5. **结果表达**：
   - 数值结果包含 metric_code、metric_name、value、unit、stat_time
   - 必要时补充阈值说明和合规性评价
   - 保持单位原样，例如 %、℃、ppm、μg/m³、dB(A)、lux
   - 时间序列结果可输出为表格或简要趋势描述
   - 查询结果必须尽可能包含本次接口实际返回的全部有效数据，不要只挑选部分字段回答
   - 如果返回的是列表、明细集合、指标集合或时间序列，默认优先用 Markdown 表格结构展示，表格中应覆盖接口返回的主要字段和数值
   - 在完整展示数据表格后，必须补充简要总结，并基于本次返回数据给出建议；总结和建议不能脱离接口返回值臆造

## 查询结果输出限制

为减少 OpenClaw 场景下的遗漏回答，所有查询类结果都必须遵守以下输出限制：

1. **完整性优先**：
   - 输出结果应尽量覆盖本次接口返回的全部有效数据。
   - 如果接口返回 `items` 数组、多条时间序列点、多条传感器记录或多项指标集合，不要只返回其中一条或少数几条，除非用户明确要求只看某一个字段。

2. **表格优先**：
   - 只要返回结果适合结构化展示，就优先使用 Markdown 表格返回。
   - 推荐列包括但不限于：`metric_code`、`metric_name`、`metric_value`、`unit`、`stat_time`、`sensor_id`、`install_location`、`granularity`。
   - 如果是时间序列，表格至少要包含时间列和数值列；如果是指标全集，表格至少要包含指标编码、指标名称、数值、单位和时间。

3. **总结必填**：
   - 在表格之后，必须用 1 段到 3 段简要文字总结本次结果。
   - 总结应说明哪些指标正常、哪些指标偏高或偏低、趋势是上升还是下降，前提是这些判断必须能从本次接口返回值或阈值规则中直接得到。

4. **建议必填**：
   - 在总结之后，补充建议。
   - 建议应围绕本次返回的真实指标表现，例如温度偏高、CO2 达标率偏低、噪声超标、光照不足等。
   - 建议条数控制在 1 到 5 条，不要泛泛而谈，不要脱离实际返回值。

5. **特殊情况**：
   - 如果用户明确要求“只看某个指标”“只看最新一条”“只看最近 5 个点”，可以按用户要求裁剪展示范围。
   - 如果后端返回数据量特别大，可先完整概括字段范围，再按时间或类别分段表格展示，但不能直接省略大部分数据而不说明。
   - 如果接口错误或无数据，应直接返回错误信息或无数据说明，此时不强行构造表格。

推荐输出结构：

```text
问题的答案是：XXX

详细数据：
| 列1 | 列2 | 列3 |
| --- | --- | --- |
| ... | ... | ... |

总结：XXX

建议：
1. XXX
2. XXX
```

## 阈值与合规性评价

根据 references/environment-metrics.md，各指标的合规规则如下：

| 指标           | 合规范围 | 单位  |
| -------------- | -------- | ----- |
| 温度           | 22-26    | ℃     |
| 湿度           | 40-60    | %RH   |
| CO2            | <1000    | ppm   |
| PM2.5          | <35      | μg/m³ |
| PM10           | <150     | μg/m³ |
| 甲醛           | <0.08    | mg/m³ |
| TVOC           | <0.6     | mg/m³ |
| 光照           | 300-500  | lux   |
| 噪声（办公区） | ≤55      | dB(A) |
| 噪声（会议室） | ≤45      | dB(A) |

评价方式：

- 对于达标率指标（以 \_compliance_rate 结尾）：直接返回百分比
- 对于波动/等级指标：返回数值，不做达标判断
- 对于综合索引（air_quality_index）：返回分数，无临界值

## API 服务器地址

`http://172.16.1.29:18081`

## 在 OpenClaw 中的使用方式

这个 skill 的主要使用场景是 **在 OpenClaw 中按技能包方式加载**，而不是让最终用户在本地手工执行命令。

### OpenClaw 路由建议

当用户问题的核心目标是“查环境数据”时，应优先触发本 Skill。

优先触发本 Skill 的典型问法：

- 主场现在的环境指标如何
- 大会议室温度达标率多少
- 小会议室 CO2 达标吗
- 主场过去 24 小时温度趋势
- 所有温度传感器的当前温度
- 系统支持哪些环境指标

优先关键词：

- `环境`
- `温度`
- `湿度`
- `CO2`
- `PM2.5`
- `PM10`
- `TVOC`
- `甲醛`
- `噪声`
- `光照`
- `空气质量`
- `达标率`
- `趋势`
- `温度传感器`

不要因为用户说了“查一下”“看一下”“现在怎么样”就把这类问题错误路由到其他 Skill；只要查询对象是环境指标数值、趋势、传感器或环境元数据，优先使用本 Skill。

如果一句话同时包含环境查询和控制动作，例如“先看大会议室温度，再打开空调”，应将环境查询部分交给本 Skill，将控制动作部分交给 `ruisi-twinioc-command-skill`，而不是让单个 Skill 强行承接整句。

OpenClaw 侧真正需要的是：

- `SKILL.md`：定义技能职责、查询范围、参数约束和回答规则
- `agents/openai.yaml`：提供模型侧的意图识别、指标映射、区域映射和接口调用规则
- `references/environment-metrics.md`：提供指标口径、阈值、字段和接口参考

`scripts/query.py` 的定位是 **辅助执行层**，主要用于：

- 本地联调 REST API
- 验证 skill 包是否完整可运行
- 在 OpenClaw 外独立复现查询请求
- 后续如果宿主平台支持脚本执行时，作为可复用的查询入口

所以，这个脚本不是面向最终用户的主入口；如果当前部署方式是在 OpenClaw 内直接消费 skill 文档与规则，那么最终运行时可以不直接使用本地命令行。

## 不适用场景

- 不用于楼宇控制指令（HVAC、照明控制等）
- 不用于空间预定流程
- 不用于告警规则引擎（虽然 API 可能包含告警数据，但 skill 不负责告警逻辑）
- 不用于空间利用指数、占用率、空置率、会议室预约状态等空间计量问题
- 不用于摄像头筛选、视频播放、对象聚焦、图层切换、主题切换等场景控制问题

## 参考说明

- 当前数据库中的 metric_level 实际为 L3。
- air_quality_index 是空气质量族的综合评分。
- light_uniformity_1h 是比值，不是百分数。
- temp_out 是历史温度统计兼容表。
- 区域名称按文档归一为主场、小会议室、大会议室、会议室、机房等名称。

## 实现约束

查询结果能否返回，取决于后端 `/api/v1/env/*` 是否已部署且有实际数据：

- 如果后端接口可用且表中有数据，脚本会按接口原样返回结果。
- 如果后端接口不可用、区域无数据或指标不存在，脚本会返回相应的 HTTP 错误信息。
- skill 负责查询和解释，不伪造任何环境数值。
- 当前两份文档足以支撑“中文统计查询规则说明”，但不足以单独提供一个现成的查询 API 实现。

## Resources

This skill includes example resource directories that demonstrate how to organize different types of bundled resources:

### scripts/

Executable code (Python/Bash/etc.) that can be run directly to perform specific operations.

### references/

Documentation and reference material intended to be loaded into context to inform Claude's process and thinking.

### assets/

Files not intended to be loaded into context, but rather used within the output Claude produces.

**Any unneeded directories can be deleted.** Not every skill requires all three types of resources.
