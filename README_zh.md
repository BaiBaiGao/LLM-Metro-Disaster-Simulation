# 面向地铁灾害仿真的 LLM 乘客智能体

[English](README.md)

本仓库包含三个地铁中断场景的仿真、分析和绘图代码：假设局部扰动、上海地铁11号线侵线事件和贝碧嘉台风。乘客智能体结合个人画像与当前运营条件做出出行选择。

## 安装

使用 Python 3.12 和 Jupyter 环境。

```bash
python -m pip install -r requirements.txt
```

仿真通过 ModelScope 调用 `Qwen/Qwen3.5-27B`，temperature 为 `0.7`。提示词和乘客回答使用中文，绘图字体为 Arial。

## 运行场景

按[数据说明](docs/DATA_SOURCES_zh.md)准备输入，并设置 `METRO_DATA_ROOT`、`METRO_OUTPUT_ROOT` 和 `MODELSCOPE_API_KEY`。

| Notebook | 场景 |
|---|---|
| [Scenario A](Scenario_A.ipynb) | 假设扰动，比较规则与 LLM 的配对决策 |
| [Scenario B](Scenario_B.ipynb) | 11号线侵线事件，三个运营工况 |
| [Scenario C](Scenario_C.ipynb) | 贝碧嘉台风，八个决策时点 |

按顺序运行 notebook 单元格，然后开始计算：

```python
result = run_submission(enable_run=True)
```

[运行与分析指南](docs/WORKFLOW_zh.md)介绍输入设置、重复计算、断点续跑和 AFC 分析。

## 分析和绘图

`analysis/` 包含乘客选择汇总和 AFC 比较程序，`figures/` 包含统计图及网络图程序，图表数据位于 `data/figure_reference/`。

运行以下命令绘制统计子图：

```bash
python figures/render_results.py --data data/figure_reference --out outputs/figures --dpi 900
```

脚本与论文图号的对应关系见[绘图说明](docs/WORKFLOW_zh.md#绘图)。图片输出为 PNG、SVG 和 PDF。

## 数据与引用

仓库包含历史车站权重、地上区段列表、Scenario B 样本、官方通知摘要和图表数据。来源、输入格式及输出字段见[数据说明](docs/DATA_SOURCES_zh.md)。

## 许可

代码采用 [MIT 许可](LICENSE)。
