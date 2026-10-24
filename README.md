# LLM passenger agents for metro disaster simulation

[中文](README_zh.md)

This repository contains the simulation, analysis and plotting code for three metro disruption scenarios: a hypothetical local disruption, the Shanghai Line 11 incident and Typhoon Bebinca. Passenger agents combine individual profiles with current service conditions to choose how to travel.

## Installation

Use Python 3.12 and a Jupyter environment.

```bash
python -m pip install -r requirements.txt
```

The simulations use `Qwen/Qwen3.5-27B` with temperature `0.7` through ModelScope. Prompts and passenger responses are in Chinese. The plotting scripts use Arial.

## Run a scenario

Prepare the inputs listed in [Data](docs/DATA_SOURCES.md), then set `METRO_DATA_ROOT`, `METRO_OUTPUT_ROOT` and `MODELSCOPE_API_KEY`.

| Notebook | Scenario |
|---|---|
| [Scenario A](Scenario_A.ipynb) | Hypothetical disruption; paired rule-based and LLM decisions |
| [Scenario B](Scenario_B.ipynb) | Line 11 incident; three operating conditions |
| [Scenario C](Scenario_C.ipynb) | Typhoon Bebinca; eight decision times |

Run the notebook cells in order, then start the calculation:

```python
result = run_submission(enable_run=True)
```

[Running and analysis](docs/WORKFLOW.md) describes input setup, repeated runs, resuming and AFC analysis.

## Analysis and figures

`analysis/` contains passenger-choice summaries and AFC comparisons. `figures/` contains the statistical and network plotting scripts. Figure data are in `data/figure_reference/`.

To draw the statistical panels:

```bash
python figures/render_results.py --data data/figure_reference --out outputs/figures --dpi 900
```

See the [figure guide](docs/WORKFLOW.md#figures) for script-to-figure correspondence. Plots are saved as PNG, SVG and PDF.

## Data and references

The repository includes historical station weights, the above-ground section list, the Scenario B cohort, official-announcement summaries and figure data. [Data](docs/DATA_SOURCES.md) lists the sources, input formats and output fields.

## Licence

The code is released under the [MIT licence](LICENSE).
