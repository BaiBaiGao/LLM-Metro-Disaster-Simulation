"""Combine three Scenario A runs into choice summaries."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from submission_runtime import MODEL, VERSION
from scenario_a_candidates import INPUT_COLUMNS, boolean, read_data, dimensions, summarize


def aggregate(manifests, out):
    if len(manifests) != 3:
        raise ValueError('Provide exactly three repeated-run manifests for the fixed cohort.')
    rows = []
    configs = []
    for index, path in enumerate(manifests, 1):
        path = Path(path).resolve()
        meta = json.loads(path.read_text(encoding='utf-8'))
        cfg = meta['configuration']
        if meta.get('status') != 'completed' or cfg.get('scenario') != 'A' or cfg.get('model') != MODEL or cfg.get('version') != VERSION:
            raise ValueError('A completed Scenario A manifest from this release is required.')
        configs.append(meta['configuration_hash'])
        book = (path.parent / meta['outputs']['output_path']).resolve()
        if path.parent not in book.parents:
            raise ValueError('Workbook must belong to its run directory.')
        frame = pd.read_excel(book, sheet_name='Passenger_Stats')
        frame['Run_Order'] = index
        selected = boolean(frame.LLM_Selected) & boolean(frame.LLM_Valid)
        logs = pd.read_excel(book, sheet_name='LLM_Call_Log')
        if logs.empty or not logs.Model.eq(MODEL).all():
            raise ValueError('Unexpected model in selected decisions.')
        successful = logs.loc[boolean(logs.Valid), 'Passenger_ID']
        if set(successful) != set(frame.loc[selected, 'PID']) or successful.duplicated().any():
            raise ValueError('Selected decisions and successful call records do not match.')
        rows.append(frame[INPUT_COLUMNS])
    if len(set(configs)) != 1:
        raise ValueError('Repeated runs must use the same input, profile and code configuration.')
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    raw = pd.concat(rows, ignore_index=True)
    path = out / 'synthetic_decisions.csv'
    raw.to_csv(path, index=False, encoding='utf-8-sig')
    frame = read_data(path)
    dims = dimensions(frame)
    pooled, by_run = summarize(frame, dims)
    pooled.to_csv(out / 'group_summary.csv', index=False)
    by_run.to_csv(out / 'group_summary_by_run.csv', index=False)
    pooled[pooled.dimension.eq('01_delay')].to_csv(out / 'A_delay.csv', index=False)
    labels = ['Continue along the original route', 'Reroute to the shortest-time metro path', 'Forgo metro travel']
    matrix = pd.crosstab(frame.Rule_Choice, frame.Choice).reindex(index=labels, columns=labels, fill_value=0)
    matrix.index = ['OR', 'RR', 'FM']; matrix.columns = ['OR', 'RR', 'FM']
    matrix.rename_axis('Rule').to_csv(out / 'A_matrix.csv')
    return pooled


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifests', nargs=3, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    aggregate(args.manifests, args.out)
