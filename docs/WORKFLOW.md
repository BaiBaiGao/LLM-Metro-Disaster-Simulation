# Running and analysis

[中文](WORKFLOW_zh.md) · [Home](../README.md)

Run the commands below from the repository root.

## Setup

Install `requirements.txt` in a Python 3.12 environment. Prepare `local_inputs/` using the [input table](DATA_SOURCES.md#inputs), and copy `data/public/上海地铁地上线归纳.txt` into it. Before loading the scenario cells, set:

```python
from pathlib import Path
from getpass import getpass
import os

os.environ['METRO_DATA_ROOT'] = str(Path('local_inputs').resolve())
os.environ['METRO_OUTPUT_ROOT'] = str(Path('outputs').resolve())
os.environ['MODELSCOPE_API_KEY'] = getpass('ModelScope API key: ')
```

## Simulations

Open the notebook for A, B or C, run its cells in order, then call:

```python
result = run_submission(enable_run=True)
```

| Scenario | Calculation |
|---|---|
| A | Repeat three times with the same cohort settings. Each run evaluates 500 passengers from an initial pool of 1,000; the paired analysis uses 450 affected passengers, giving 1,350 decisions across three runs. |
| B | 500 passengers: 300 affected and 200 controls, evaluated under three conditions. |
| C | 200 passengers at 10:00, 14:00, 18:00 and 22:00 on 15–16 September 2024. |

Each run saves a workbook, checkpoints and `run_manifest.json`. The manifest records the configuration and input identifiers. For B and C, resume with:

```python
result = run_submission(enable_run=True, resume_run='path/to/saved_run')
```

Resuming requires the same model, settings and inputs. A saves partial workbooks; restart the calculation to repeat A. If the API allowance is exhausted, the calculation saves its progress and stops.

## Analysis

For A, supply the manifests from the three runs:

```bash
python analysis/scenario_a.py --manifests path/to/A1/run_manifest.json path/to/A2/run_manifest.json path/to/A3/run_manifest.json --out outputs/A_analysis
```

For B/C, set `afc_directory` and `station_file` in `analysis/validation_config.json`, then run:

```bash
python analysis/run_analysis.py --line11-manifest path/to/B/run_manifest.json --bebinca-manifest path/to/C/run_manifest.json --execute
python analysis/render_spatial.py --out outputs/spatial_data
python analysis/export_figure_data.py --analysis-root analysis --out outputs/figure_data
```

Intermediate data go to `analysis/processed/`, summaries to `analysis/tables/` and checks to `analysis/qa/`. The last command exports the figure tables.

All times are Beijing time:

| Scenario | Simulation or decision times | AFC windows | Reference days in 2024 |
|---|---|---|---|
| B | 08:31–09:17; 09:17–11:19; 11:19–22:50 | 08:35–09:15; 09:20–11:15; 11:20–21:30 | 8 and 15 December |
| C | Eight times listed above | 30 minutes after each decision; the 16 September 18:00 window ends at 18:20 | 8 and 22 September; 9 and 23 September for Monday sensitivity |

The comparison uses common OD pairs with positive baseline ridership and baseline-flow weighting.

## Figures

Install Arial for plotting. To draw the figure tables and eight network states:

```bash
python figures/render_results.py --data data/figure_reference --out outputs/figures --dpi 900
python figures/render_network.py --topology local_inputs/subway.json --out outputs/network --dpi 900
```

For newly calculated results, pass `outputs/figure_data` to `--data`. A's matrix and delay tables are written to `outputs/A_analysis`; copy those two tables into the same figure-data directory when drawing all scenarios together.

| Figure panels | Scripts |
|---|---|
| Fig. 2(c,d): paired choices and delay groups | `analysis/scenario_a.py`, `figures/render_results.py` |
| Fig. 3: choices, transitions, AFC comparisons and spatial results | `analysis/export_figure_data.py`, `figures/render_results.py` |
| Fig. 4: network states and time series | `figures/render_network.py`, `figures/render_results.py` |

The scripts export individual panels as PNG, SVG and PDF for manuscript layout. B's error bars show the range across reference days; A's repeated-run ranges show variation across the three calculations.
