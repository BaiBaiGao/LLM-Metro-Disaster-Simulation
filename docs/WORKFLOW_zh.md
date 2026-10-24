# 运行与分析

[English](WORKFLOW.md) · [首页](../README_zh.md)

以下命令均在仓库根目录运行。

## 环境与输入

在 Python 3.12 环境中安装 `requirements.txt`。按[输入文件表](DATA_SOURCES_zh.md#输入文件)准备 `local_inputs/`，将 `data/public/上海地铁地上线归纳.txt` 复制进去。在加载场景单元格前设置：

```python
from pathlib import Path
from getpass import getpass
import os

os.environ['METRO_DATA_ROOT'] = str(Path('local_inputs').resolve())
os.environ['METRO_OUTPUT_ROOT'] = str(Path('outputs').resolve())
os.environ['MODELSCOPE_API_KEY'] = getpass('ModelScope API key: ')
```

## 仿真

打开 A、B 或 C 的 notebook，按顺序运行单元格，然后调用：

```python
result = run_submission(enable_run=True)
```

| 场景 | 计算设置 |
|---|---|
| A | 保持样本设置相同，重复三次。每次从1,000人的初始池中选择500人评估，其中450名受影响乘客进入配对分析，三次共1,350条记录。 |
| B | 500名乘客，包括300名受影响乘客和200名对照，在三个工况下分别决策。 |
| C | 200名乘客，在2024年9月15–16日每天的10:00、14:00、18:00和22:00决策。 |

每次运行保存工作簿、检查点和 `run_manifest.json`。运行清单记录所用配置及输入标识。B和C可通过以下方式续跑：

```python
result = run_submission(enable_run=True, resume_run='path/to/saved_run')
```

续跑使用相同的模型、参数和输入。A会保存部分结果工作簿，重复A时重新开始计算。API额度用尽时，程序保存进度并停止。

## 分析

A需要提供三次运行的清单：

```bash
python analysis/scenario_a.py --manifests path/to/A1/run_manifest.json path/to/A2/run_manifest.json path/to/A3/run_manifest.json --out outputs/A_analysis
```

B/C先在 `analysis/validation_config.json` 中填写 `afc_directory` 和 `station_file`，然后运行：

```bash
python analysis/run_analysis.py --line11-manifest path/to/B/run_manifest.json --bebinca-manifest path/to/C/run_manifest.json --execute
python analysis/render_spatial.py --out outputs/spatial_data
python analysis/export_figure_data.py --analysis-root analysis --out outputs/figure_data
```

中间数据写入 `analysis/processed/`，汇总表写入 `analysis/tables/`，核验结果写入 `analysis/qa/`。最后一个命令导出绘图用的数据表。

以下均为北京时间：

| 场景 | 仿真区间或决策时点 | AFC观测窗口 | 2024年基准日 |
|---|---|---|---|
| B | 08:31–09:17；09:17–11:19；11:19–22:50 | 08:35–09:15；09:20–11:15；11:20–21:30 | 12月8日、15日 |
| C | 上述八个时点 | 决策后30分钟；9月16日18:00窗口截至18:20 | 9月8日、22日；9日、23日用于星期一敏感性分析 |

比较采用具有正基准客流的共同OD，并按基准客流加权。

## 绘图

绘图脚本使用 Arial。运行以下命令绘制统计子图和八个网络状态：

```bash
python figures/render_results.py --data data/figure_reference --out outputs/figures --dpi 900
python figures/render_network.py --topology local_inputs/subway.json --out outputs/network --dpi 900
```

绘制新结果时，将 `--data` 改为 `outputs/figure_data`。A的矩阵和延误分组表输出到 `outputs/A_analysis`；三个场景一起绘制时，将这两张表复制到同一绘图数据目录。

| 论文子图 | 对应脚本 |
|---|---|
| Fig. 2(c,d)：配对选择、延误分组 | `analysis/scenario_a.py`、`figures/render_results.py` |
| Fig. 3：选择构成、转移、AFC比较及空间结果 | `analysis/export_figure_data.py`、`figures/render_results.py` |
| Fig. 4：网络状态与时间序列 | `figures/render_network.py`、`figures/render_results.py` |

脚本将各子图输出为 PNG、SVG和PDF，供论文排版。B的误差棒表示参考日变化范围，A的重复计算范围表示三次计算之间的变化。
