# Data

[中文](DATA_SOURCES_zh.md) · [Home](../README.md)

## Included data

| Location | Contents |
|---|---|
| `data/public/historical_station_weights.csv` | Historical station-flow weights from an earlier Shanghai metro project; see Zhang et al. (2020) below |
| `data/public/上海地铁地上线归纳.txt` | Above-ground sections compiled from Shentong Metro information |
| `inputs/scenario_b_cohort.csv` | Scenario B's 500 passenger OD pairs and group assignments |
| `data/notice_observations.csv` | 44 announcement summaries used in Tables 2–3, with sources and times |
| `data/notice_sources.json` | Publication times and accounts for Scenario C |
| `data/templates/official_notices.json` | Scenario C notice-input template |
| `data/figure_reference/` | Tables used by the figure scripts |

Official announcements were collected from the relevant official Weibo accounts. B includes operator statements and news reporting; C includes Shanghai Metro and Shanghai Fabu announcements. All times are Beijing time.

## Inputs

Place the following files in `METRO_DATA_ROOT`:

| File | Source and use |
|---|---|
| `subway.json` | Amap metro topology: [metro map](https://map.amap.com/subway/index.html), [developer documentation](https://lbs.amap.com/api/subway-api/subway-summary/) |
| `线路id与名称对应-20251210.xlsx` | Maps topology line IDs to operating line names |
| `line_schedule_detailed.xlsx` | Timetable prepared from public online metro service information |
| `上海地铁地上线归纳.txt` | Copy from `data/public/` |
| `shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv` | Shanghai Municipal Public Data Open Platform: [全市地铁进出客流量](https://data.sh.gov.cn/view/detail/index.html?type=jk&id=2153) |
| `official_notices.json` | C only: fill the template with the Chinese notice text |

AFC analysis uses five-minute OD records and a station dictionary supplied by the Transport Data Science Research Center, Tongji University. Access requests can be addressed to the corresponding author, subject to approval by the data provider and operator.

The AFC filenames are `pas_od_5min_20241208_20241222.parquet` and `pas_od_5min_20240907_20240923.parquet`. Set their directory and the station-dictionary path in the analysis configuration.

## Formats

| Input | Fields |
|---|---|
| Platform CSV | `time`, `station_name_mapped` or `station`, `inbound`, `outbound` |
| Timetable | `LineID`, `DayType`, `Start_Time`, `End_Time`, `From_Station`, `To_Station`, `Interval_Sec` |
| Line-ID workbook | `Line ID`, `Line Name` |
| AFC Parquet | `date` (YYYYMMDD), `ts` (timestamp), `in_sta_id`, `out_sta_id`, `flow` |
| Station dictionary | `sta_id`, `sta_name` |
| Notice JSON | `Publish_Time_BJT`, `Account`, `Body`, `Title`, plus source fields in the template |

Timetable times use `HH:MM:SS`, headways are in seconds, and day types are `Weekday` or `Weekend`. The platform loader selects 8 August 2025. To map columns from a platform export:

```bash
python tools/prepare_platform_csv.py --source source.csv --out local_inputs/shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv --columns time_column station_column entry_column exit_column
```

Topology JSON contains a line list `l`. Each line has `ln`, `ls` and `st`; stations have `si`, `n` and `sl` (longitude,latitude). Ground-section text uses chains such as `1号线：站点甲-站点乙-站点丙`.

Historical station weights initialize network flows. Platform records supply the entry/exit sampling weights and update network flows; B loads its fixed cohort. AFC baseline OD flows provide the weights for empirical comparisons.

## Outputs

A exports `Passenger_Stats`. B/C export `Cohort`, `Passenger_Decisions` and summary sheets.

| Fields | Meaning |
|---|---|
| `PID`, `Origin`, `Dest` | Passenger ID and OD stations |
| `Age`, `Gender`, `Trip_Purpose`, `OCEAN_O/C/E/A/N`, `Risk_Preference` | Passenger profile; OCEAN and risk scores use 1–5 |
| `Rule_Reachable` and route fields | Metro accessibility and routes |
| Delay and travel-time fields | Minutes; unavailable routes have missing numerical times |
| `Rule_Action`, `LLM_Action`, `Action` | Rule-based and LLM choices |
| `LLM_Reason`, perception and feeling fields | Decision rationale, perceived risk/delay and 1–5 emotional score |
| `LLM_Valid`, `LLM_Model` | Response validity and model |
| `Observed`, `LLM` | AFC retention ratio and baseline-flow-weighted metro-choice share |
| `Agent_N`, `OD_N` | Matched passenger records and OD pairs |
| `Error_low`, `Error_high` | Range across reference-day choices |

## Reference and terms

Zhang, Y., Ayyub, B. M., Saadat, Y., Zhang, D. & Huang, H. A double-weighted vulnerability assessment model for metrorail transit networks and its application in Shanghai metro. *International Journal of Critical Infrastructure Protection* **29**, 100358 (2020). [DOI](https://doi.org/10.1016/j.ijcip.2020.100358).

Please retain the source references when reusing the included data. External datasets follow their providers' terms, including the [Amap terms](https://lbs.amap.com/pages/terms/).
