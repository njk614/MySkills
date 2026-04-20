# Ruisi Twinioc Environment Metrics Reference

This reference normalizes the environment-statistics rules from the source documents into a compact guide for the skill.

## Primary Tables

- env_metric_hourly_sensor: sensor-level 1-hour statistics.
- env_metric_hourly_area: area-level hourly metrics.
- env_metric_daily_area: area-level daily metrics, averaged from hourly values.
- env_metric_weekly_area: area-level weekly metrics, averaged from daily values.
- temp_out: legacy temperature-only compatibility table.

## Data Sources

### TwinIOC

- Used for temperature and humidity.
- Typical raw sampling is treated as about 3 seconds per record in the current implementation.

### SensorGen

- Used for CO2, PM2.5, PM10, TVOC, formaldehyde, light, and noise.
- Snapshot polling is treated as about 60 seconds per record in the current implementation.

## Area Normalization

Normalize region names to the documented area buckets when reporting results:

- 主场
- 小会议室
- 大会议室
- 会议室
- 机房

## Validity and Time Rules

- Hourly statistics are the base bucket.
- Daily values are averaged from hourly values.
- Weekly values are averaged from daily values.
- Default working hours are 09:30-19:30 unless explicitly overridden.
- If online rate is below 0.8, treat the corresponding metric as invalid or 0 according to the source result.
- Online rate is a ratio in 0~1, not a percentage.
- Percentage metrics are already stored as percent values.
- light_uniformity_1h uses ratio as its unit.

## Sensor-Level Metric Codes

| metric_code  | metric_name | unit  | source    |
| ------------ | ----------- | ----- | --------- |
| temperature  | 温度        | ℃     | TwinIOC   |
| humidity     | 湿度        | %RH   | TwinIOC   |
| co2          | CO2浓度     | ppm   | SensorGen |
| pm25         | PM2.5浓度   | μg/m³ | SensorGen |
| pm10         | PM10浓度    | μg/m³ | SensorGen |
| tvoc         | TVOC浓度    | mg/m³ | SensorGen |
| formaldehyde | 甲醛浓度    | mg/m³ | SensorGen |
| light        | 光照度      | lux   | SensorGen |
| noise        | 噪声强度    | dB(A) | SensorGen |

## Area-Level L3 Metric Codes

| metric_code                  | metric_name      | unit  | meaning                                                            |
| ---------------------------- | ---------------- | ----- | ------------------------------------------------------------------ |
| temperature_compliance_rate  | 温度达标率       | %     | Temperature seconds within 22-26 ℃ divided by monitored seconds    |
| temperature_fluctuation_1h   | 温度波动幅度     | ℃     | Average of sensor 1-hour max-minus-min values                      |
| humidity_compliance_rate     | 湿度达标率       | %     | Humidity seconds within 40-60 %RH divided by monitored seconds     |
| humidity_fluctuation_1h      | 湿度波动幅度     | %RH   | Average of sensor 1-hour max-minus-min values                      |
| co2_compliance_rate          | CO2达标率        | %     | CO2 seconds below 1000 ppm divided by monitored seconds            |
| pm25_compliance_rate         | PM2.5达标率      | %     | PM2.5 seconds below 35 μg/m³ divided by monitored seconds          |
| pm10_compliance_rate         | PM10达标率       | %     | PM10 seconds below 150 μg/m³ divided by monitored seconds          |
| formaldehyde_compliance_rate | 甲醛达标率       | %     | Formaldehyde seconds below 0.08 mg/m³ divided by monitored seconds |
| tvoc_compliance_rate         | TVOC达标率       | %     | TVOC seconds below 0.6 mg/m³ divided by monitored seconds          |
| air_quality_index            | 综合空气质量指数 | score | Composite air-quality score derived from the air family            |
| noise_compliance_rate        | 噪音达标率       | %     | Noise seconds below area limit divided by monitored seconds        |
| noise_fluctuation_1h         | 噪音波动幅度     | dB(A) | Average of sensor 1-hour max-minus-min values                      |
| noise_equivalent_level_1h    | 等效声级         | dB(A) | Average of sensor 1-hour equivalent levels                         |
| light_compliance_rate        | 光照达标率       | %     | Light seconds within 300-500 lux divided by monitored seconds      |
| light_uniformity_1h          | 光照均匀度       | ratio | Average of rolling 1-hour uniformity values                        |

## L2 Design-Only Metrics

The following are designed but not yet stored as actual database records:

- thermal_comfort
- humidity_comfort
- air_quality_comfort
- acoustic_comfort
- lighting_comfort

## Thresholds

| metric              | compliant when          |
| ------------------- | ----------------------- |
| Temperature         | 22 <= value <= 26       |
| Humidity            | 40 <= value <= 60       |
| CO2                 | < 1000 ppm              |
| PM2.5               | < 35 μg/m³              |
| PM10                | < 150 μg/m³             |
| Formaldehyde        | < 0.08 mg/m³            |
| TVOC                | < 0.6 mg/m³             |
| Light               | 300 <= value <= 500 lux |
| Noise, office area  | <= 55 dB(A)             |
| Noise, meeting room | <= 45 dB(A)             |

## Formula Notes

- Compliance rate: ok_seconds / monitored_seconds × 100
- Fluctuation: 1h max - 1h min
- Equivalent level: 10 × log10(Σ(10^(L/10)) / n)
- Light uniformity: min(light) / avg(light) at the current minute, then averaged over 1 hour
- Air quality index: composite score based on the 1-hour averages and thresholds of the air-quality family

## Reporting Priority

When answering user requests, prefer this order:

1. env_metric_hourly_area
2. env_metric_daily_area
3. env_metric_weekly_area
4. env_metric_hourly_sensor
5. temp_out

## API Implementation Guide

### API Endpoints Structure

All endpoints are REST GET endpoints with base URL `http://172.16.1.29:18081`

#### Meta Endpoints

```
GET /api/v1/env/meta/metrics
  Returns: {items: [{metric_code, metric_name, metric_level, metric_unit, available_granularities}, ...]}

GET /api/v1/env/meta/areas
  Returns: {items: [{floor_no, area_name}, ...]}
```

#### Temperature Sensor Endpoints

```
GET /api/v1/env/temperature/sensors?install_location={optional}
  Returns: {items: [{sensor_id, location, temperature, ...}, ...]}

GET /api/v1/env/temperature/sensors/{sensor_id}
  Returns: {sensor_id, location, temperature, ...}
```

#### Area Metrics Endpoints

```
GET /api/v1/env/areas/{area_name}/metrics/latest?metric_level=L3&floor_no=20
  Returns: {area_name, floor_no, stat_time, items: [{metric_code, metric_name, metric_value, unit, stat_time}, ...]}

GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/latest?metric_level=L3&floor_no=20
  Returns: {metric_code, metric_name, metric_value, unit, stat_time}

GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/timeline?granularity={hourly|daily|weekly}&metric_level=L3&floor_no=20&limit=24
  Returns: {area_name, metric_code, granularity, items: [{stat_time, metric_value}, ...]}
```

### Common Query Patterns

**Pattern 1: User asks "What's the current environment in [area]?"**

```
1. Parse area_name from question
2. Call: GET /api/v1/env/areas/{area_name}/metrics/latest
3. Extract items, group by metric family (temperature, humidity, air, noise, light)
4. Format result with metric_name, metric_value, unit, compliance evaluation
```

**Pattern 2: User asks "What's the [metric_name] in [area]?"**

```
1. Parse area_name and map metric_name to metric_code
2. Call: GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/latest
3. Return metric_code, metric_name, metric_value, unit, stat_time
4. Compare with threshold to determine compliance
```

**Pattern 3: User asks "[metric_name] trend in [area] over [time_period]"**

```
1. Parse area_name, metric_code, and time_period
2. Determine granularity: "24 hours"→hourly, "week"→daily, "month"→weekly
3. Call: GET /api/v1/env/areas/{area_name}/metrics/{metric_code}/timeline?granularity=X&limit=N
4. Return time series data, optionally format as timeline chart or table
```

**Pattern 4: User asks "Temperature sensors current state"**

```
1. Call: GET /api/v1/env/temperature/sensors
2. Group results by install_location
3. Return sensor_id, location, current_temp for each sensor
```

### Error Handling

- HTTP 404: Data not available for this area/metric combination
- HTTP 500: Backend service error
- Timeout: Retry with a reasonable backoff, then return "Service temporarily unavailable"
- Invalid metric_code/area_name: Return "Invalid metric/area name. Use /api/v1/env/meta/\* endpoints to query available options"
