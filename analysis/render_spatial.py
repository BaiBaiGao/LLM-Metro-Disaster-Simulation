"""Export station-entry and section-retention tables."""
from pathlib import Path
import argparse
import json
import pandas as pd
from line11_spatial_figure import make_line11_spatial_figure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    cfg = json.loads((root/'validation_config.json').read_text(encoding='utf-8'))
    for subdir in ['qa', 'tables']:
        (root/subdir).mkdir(exist_ok=True)
    make_line11_spatial_figure(root, cfg)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.read_csv(root/'tables/line11_seven_station_plot_data.csv')[
        ['order','station','label','baseline_flow','observed_flow','baseline_dates','event_date']
    ].to_csv(args.out/'B_stations.csv', index=False, encoding='utf-8-sig')
    segments = pd.read_csv(root/'tables/line11_observed_spatial.csv')
    segments.loc[segments.target.isin(['west','closed','east']), ['target','Observed','unit']].to_csv(
        args.out/'B_segments.csv', index=False, encoding='utf-8-sig')
    print('Figure aggregates exported; detailed audit stays local / 已导出图表汇总，明细核验留在本地。')


if __name__ == '__main__':
    main()
