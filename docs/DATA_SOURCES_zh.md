# 数据说明

[English](DATA_SOURCES.md) · [首页](../README_zh.md)

## 仓库数据

| 位置 | 内容 |
|---|---|
| `data/public/historical_station_weights.csv` | 此前上海地铁项目的历史车站客流权重，相关研究见下方 Zhang et al. (2020) |
| `data/public/上海地铁地上线归纳.txt` | 参考申通地铁资料整理的地上区段 |
| `inputs/scenario_b_cohort.csv` | Scenario B的500组乘客OD及分组 |
| `data/notice_observations.csv` | Table 2–3使用的44条通知摘要及来源、时间 |
| `data/notice_sources.json` | Scenario C的通知发布时间和账号 |
| `data/templates/official_notices.json` | Scenario C的通知输入模板 |
| `data/figure_reference/` | 绘图脚本使用的数据表 |

官方消息整理自相应官方微博。B包括运营方声明和新闻报道，C包括上海地铁与上海发布的通知。时间均为北京时间。

## 输入文件

将以下文件放入 `METRO_DATA_ROOT`：

| 文件 | 来源与用途 |
|---|---|
| `subway.json` | 高德地铁拓扑：[地铁图](https://map.amap.com/subway/index.html)、[开发文档](https://lbs.amap.com/api/subway-api/subway-summary/) |
| `线路id与名称对应-20251210.xlsx` | 拓扑线路ID与运营线路名称的映射 |
| `line_schedule_detailed.xlsx` | 根据网络公开地铁运营信息准备的时刻表 |
| `上海地铁地上线归纳.txt` | 从 `data/public/` 复制 |
| `shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv` | 上海市公共数据开放平台：[全市地铁进出客流量](https://data.sh.gov.cn/view/detail/index.html?type=jk&id=2153) |
| `official_notices.json` | 仅C使用，按模板填入中文通知正文 |

AFC分析使用同济大学交通数据科学研究中心提供的五分钟OD记录及站码表。访问申请可联系通讯作者，由数据提供方和运营方审批。

AFC文件名为 `pas_od_5min_20241208_20241222.parquet` 和 `pas_od_5min_20240907_20240923.parquet`。在分析配置中填写文件目录及站码表路径。

## 输入格式

| 输入 | 字段 |
|---|---|
| 平台CSV | `time`、`station_name_mapped` 或 `station`、`inbound`、`outbound` |
| 时刻表 | `LineID`、`DayType`、`Start_Time`、`End_Time`、`From_Station`、`To_Station`、`Interval_Sec` |
| 线路映射表 | `Line ID`、`Line Name` |
| AFC Parquet | `date`（YYYYMMDD）、`ts`（时间戳）、`in_sta_id`、`out_sta_id`、`flow` |
| 站码表 | `sta_id`、`sta_name` |
| 通知JSON | `Publish_Time_BJT`、`Account`、`Body`、`Title`，以及模板中的来源字段 |

时刻表采用 `HH:MM:SS`，班距单位为秒，日期类型为 `Weekday` 或 `Weekend`。平台数据读取器选择2025年8月8日。其他平台导出文件可通过以下命令映射列名：

```bash
python tools/prepare_platform_csv.py --source source.csv --out local_inputs/shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv --columns time_column station_column entry_column exit_column
```

拓扑JSON的线路列表为 `l`，每条线路包含 `ln`、`ls` 和 `st`；站点包含 `si`、`n` 和 `sl`（经度,纬度）。地上区段文本采用站点链格式，例如 `1号线：站点甲-站点乙-站点丙`。

历史车站权重用于初始化网络客流。平台记录提供进出站抽样权重并更新网络客流，B直接读取固定样本。AFC基准OD流量用于实测比较中的加权。

## 输出字段

A导出 `Passenger_Stats`；B/C导出 `Cohort`、`Passenger_Decisions` 及汇总表。

| 字段 | 含义 |
|---|---|
| `PID`、`Origin`、`Dest` | 乘客标识和起终站 |
| `Age`、`Gender`、`Trip_Purpose`、`OCEAN_O/C/E/A/N`、`Risk_Preference` | 乘客画像；人格及风险偏好评分为1–5 |
| `Rule_Reachable` 及路线字段 | 地铁可达性及路线 |
| 延误和出行时间字段 | 单位为分钟；不可达路线的数值时间为空 |
| `Rule_Action`、`LLM_Action`、`Action` | 规则与LLM选择 |
| `LLM_Reason`、感知及情绪字段 | 决策理由、感知风险和延误、1–5情绪评分 |
| `LLM_Valid`、`LLM_Model` | 响应有效性和模型 |
| `Observed`、`LLM` | AFC客流保留率和基准客流加权的地铁选择比例 |
| `Agent_N`、`OD_N` | 匹配乘客记录数与OD数量 |
| `Error_low`、`Error_high` | 参考日变化范围 |

## 参考文献与使用

Zhang, Y., Ayyub, B. M., Saadat, Y., Zhang, D. & Huang, H. A double-weighted vulnerability assessment model for metrorail transit networks and its application in Shanghai metro. *International Journal of Critical Infrastructure Protection* **29**, 100358 (2020). [DOI](https://doi.org/10.1016/j.ijcip.2020.100358).

复用仓库数据时请保留来源引用。外部数据按提供方的使用条款使用，包括[高德服务条款](https://lbs.amap.com/pages/terms/)。
