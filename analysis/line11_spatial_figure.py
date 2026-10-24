"""Summarize AFC entries along the shuttle corridor and at Qilianshan Road."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

def make_line11_spatial_figure(root, cfg):
    root = Path(root)
    settings = cfg['line11_spatial_figure']
    style = cfg['figure']
    dates = cfg['line11_baseline'] + [settings['event_date']]
    names = [s['name'] for s in settings['stations']]
    mapping = pd.read_csv(root / 'processed/station_mapping.csv')
    source_mapping = pd.read_csv(cfg['station_file'])
    selected = mapping[mapping.physical_name.isin(names)].copy()
    assert selected.physical_name.nunique() == len(names)
    for row in selected.itertuples():
        assert source_mapping.loc[source_mapping.sta_id.eq(row.sta_id), 'sta_name'].iloc[0] == row.sta_name
    codes = set(selected.sta_id)
    source = Path(cfg['afc_directory']) / 'pas_od_5min_20241208_20241222.parquet'
    parts, line_parts, network_parts = ([], [], [])
    for batch in pq.ParquetFile(source).iter_batches(batch_size=1000000):
        d = batch.to_pandas()
        d = d[d.date.isin(dates)]
        assert not d.isna().any().any()
        parts.append(d[d.in_sta_id.isin(codes)])
        network_parts.append(d[['date', 'ts']].drop_duplicates())
        line_parts.append(d[d.in_sta_id.between(1114, 1163)].groupby(['date', 'in_sta_id']).flow.sum())
    raw = pd.concat(parts, ignore_index=True)
    assert not raw.duplicated(['date', 'ts', 'in_sta_id', 'out_sta_id']).any()
    offset = (raw.ts.dt.normalize() - pd.to_datetime(raw.date.astype(str))).dt.days
    assert offset.isin([0, 1]).all()
    assert (raw.ts.dt.minute.mod(5).eq(0) & raw.ts.dt.second.eq(0)).all()
    network = pd.concat(network_parts).drop_duplicates().groupby('date').ts.nunique()
    processed = pd.read_csv(root / 'processed/afc_station_daily.csv').set_index(['date', 'physical_id']).flow
    raw['physical_id'] = raw.in_sta_id.map(selected.set_index('sta_id').physical_id)
    checks, plot_rows = ([], [])
    for order, station in enumerate(settings['stations']):
        sm = selected[selected.physical_name.eq(station['name'])]
        assert sm.physical_id.nunique() == 1
        pid = int(sm.physical_id.iloc[0])
        flows = {}
        for date in dates:
            d = raw[raw.physical_id.eq(pid) & raw.date.eq(date)]
            total = int(d.flow.sum())
            existing = int(processed.loc[date, pid])
            assert total == existing, (station['name'], date, total, existing)
            flows[date] = total
            checks.append(dict(station=station['name'], sta_codes=';'.join(sm.sta_id.astype(str)), date=date, raw_flow=total, processed_flow=existing, difference=total - existing, raw_rows=len(d), positive_flow=int(d.loc[d.flow.gt(0), 'flow'].sum()), negative_rows=int(d.flow.lt(0).sum()), negative_flow=int(d.loc[d.flow.lt(0), 'flow'].sum()), zero_rows=int(d.flow.eq(0).sum()), same_station_flow=int(d.loc[d.in_sta_id.eq(d.out_sta_id), 'flow'].sum()), represented_5min_bins=d.ts.nunique(), network_represented_5min_bins=int(network.loc[date]), first_timestamp=str(d.ts.min()), last_timestamp=str(d.ts.max())))
        plot_rows.append(dict(order=order, station=station['name'], label=station['label'], physical_id=pid, baseline_flow=float(np.mean([flows[date] for date in cfg['line11_baseline']])), observed_flow=flows[settings['event_date']], baseline_dates=';'.join(map(str, cfg['line11_baseline'])), event_date=settings['event_date']))
    checks = pd.DataFrame(checks)
    values = pd.DataFrame(plot_rows)
    checks.to_csv(root / 'qa/line11_seven_station_raw_check.csv', index=False, encoding='utf-8-sig')
    values.to_csv(root / 'tables/line11_seven_station_plot_data.csv', index=False, encoding='utf-8-sig')
    five = raw.groupby(['date', 'physical_id', 'ts']).flow.sum().reset_index()
    five.to_csv(root / 'qa/line11_seven_station_5min.csv', index=False, encoding='utf-8-sig')
    report = ['# 七站空间客流图：选站依据与原始数据核验', '', settings['selection_rule'], '', f'原始数据：{source}', f'基准运营日期：{cfg['line11_baseline']}；事故运营日期：{settings['event_date']}。', '保留带符号修正记录及同站OD，按源数据的运营日期计入跨午夜记录。', '七站各日期原始记录合计均与现有物理站点聚合表一致；站码与原始站名字典一致。', '', '| 武威路运营日期 | 原始进站量 | 负值修正合计 | 有记录的五分钟单元 |', '|---|---:|---:|---:|']
    for r in checks[checks.station.eq('武威路')].itertuples():
        report.append(f'| {r.date} | {r.raw_flow} | {r.negative_flow} | {r.represented_5min_bins} |')
    report += ['', '逐站逐日结果：line11_seven_station_raw_check.csv；五分钟汇总：line11_seven_station_5min.csv。']
    report += ['', 'Station totals match the source records. Daily totals and five-minute entries are saved in the CSV files above.']
    (root / 'qa/line11_seven_station_audit.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    line = pd.concat(line_parts).groupby(level=[0, 1]).sum().reset_index()
    segments = pd.read_csv(root / 'tables/line11_observed_spatial.csv').set_index('target')
    for key, lo, hi in [('west', 1114, 1135), ('closed', 1136, 1138), ('east', 1139, 1163)]:
        daily = line[line.in_sta_id.between(lo, hi)].groupby('date').flow.sum()
        assert daily.loc[settings['event_date']] == segments.loc[key, 'observed_flow']
        assert daily.reindex(cfg['line11_baseline']).mean() == segments.loc[key, 'baseline_flow']
    return {'station_totals_verified': True, 'segment_totals_verified': True}
