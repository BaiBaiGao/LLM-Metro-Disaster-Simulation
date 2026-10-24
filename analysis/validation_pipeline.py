"""Compare simulated choices with AFC observations."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import subprocess
import sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import spearmanr
ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / 'validation_config.json').read_text(encoding='utf-8'))
PROCESSED = ROOT / 'processed'
TABLES = ROOT / 'tables'
FIGURES = Path(CFG['figure_output_directory']) if CFG.get('figure_output_directory') else ROOT / 'figure_output_not_configured'
QA = ROOT / 'qa'

def save_csv(frame, name, folder=TABLES):
    frame.to_csv(folder / name, index=False, encoding='utf-8-sig')

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()

def make_mapping():
    m = pd.read_csv(CFG['station_file'])
    assert m.sta_id.is_unique
    m['physical_name'] = m.sta_name
    for code, name in {234: '国家会展中心(2号线)', 1722: '国家会展中心(17号线)'}.items():
        m.loc[m.sta_id.eq(code), 'physical_name'] = name
    nec = m.sta_name.eq('国家会展中心')
    m.loc[nec & m.sta_id.between(200, 299), 'physical_name'] = '国家会展中心(2号线)'
    m.loc[nec & m.sta_id.between(1700, 1799), 'physical_name'] = '国家会展中心(17号线)'
    m['physical_id'] = m.groupby('physical_name').sta_id.transform('min').astype(int)
    m['line_code'] = np.where(m.sta_id < 1000, m.sta_id // 100, m.sta_id // 100)
    save_csv(m, 'station_mapping.csv', PROCESSED)
    lookup = m.groupby('physical_name').physical_id.first().to_dict()
    aliases = dict(CFG['name_aliases'])
    aliases.update({'徐泾东': '国家会展中心(2号线)', '诸光路': '国家会展中心(17号线)'})
    aliases.update({name: name for name in aliases if name in lookup})
    (PROCESSED / 'effective_name_aliases.json').write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding='utf-8')
    all_agents = []
    for case in ['Line11', 'Bebinca']:
        c = pd.read_csv(PROCESSED / f'{case}_cohort.csv')
        for field in ['Origin', 'Dest']:
            normal = c[field].astype(str).str.strip().replace(aliases)
            c[field + '_canonical'] = normal
            c[field + '_id'] = normal.map(lookup)
        c['mapping_valid'] = c[['Origin_id', 'Dest_id']].notna().all(axis=1)
        c['od_key'] = (c.Origin_id * 10000 + c.Dest_id).astype('Int64')
        c['Case'] = case
        save_csv(c, f'{case}_mapped_cohort.csv', PROCESSED)
        all_agents.append(c)
        print(case, 'mapped', int(c.mapping_valid.sum()), '/', len(c), 'unique OD', c.od_key.nunique())
    save_csv(pd.concat(all_agents, ignore_index=True), 'agent_mapping.csv', PROCESSED)
    return m

def windows():
    rows = [dict(Case='Line11', Scenario='condition_1', Event_date=20241222, start=515, end=555, label='08:35–09:15'), dict(Case='Line11', Scenario='condition_2', Event_date=20241222, start=560, end=675, label='09:20–11:15'), dict(Case='Line11', Scenario='condition_3', Event_date=20241222, start=680, end=1290, label='11:20–21:30')]
    for date in [20240915, 20240916]:
        for hour in [10, 14, 18, 22]:
            start = hour * 60
            end = start + (20 if date == 20240916 and hour == 18 else 30)
            rows.append(dict(Case='Bebinca', Scenario=f'snapshot_{date}_{hour:02}00', Event_date=date, start=start, end=end, label=f'{hour:02}:00–{end // 60:02}:{end % 60:02}'))
    return pd.DataFrame(rows)

def add(counter, series):
    counter.update({k: int(v) for k, v in series.items()})

def counter_frame(counter, keys, value='flow'):
    rows = [list(k if isinstance(k, tuple) else (k,)) + [v] for k, v in counter.items()]
    return pd.DataFrame(rows, columns=keys + [value]).sort_values(keys).reset_index(drop=True)

def preprocess_afc():
    m = pd.read_csv(PROCESSED / 'station_mapping.csv')
    id_lookup = m.set_index('sta_id').physical_id.to_dict()
    win = windows()
    save_csv(win, 'validation_windows.csv', PROCESSED)
    cohorts = {case: pd.read_csv(PROCESSED / f'{case}_mapped_cohort.csv') for case in ['Line11', 'Bebinca']}
    supported = {case: set(c.loc[c.mapping_valid, 'od_key'].astype(int)) for case, c in cohorts.items()}
    daily, net5, station_day, station_hour = (Counter(), Counter(), Counter(), Counter())
    coded_day, l11_5, gap5, od_windows, network_windows = (Counter(), Counter(), Counter(), Counter(), Counter())
    audit, sources, total_od_daily = ([], [], Counter())
    afc_codes = set()
    for filename in ['pas_od_5min_20241208_20241222.parquet', 'pas_od_5min_20240907_20240923.parquet']:
        path = Path(CFG['afc_directory']) / filename
        case = 'Line11' if '202412' in filename else 'Bebinca'
        ws = win[win.Case.eq(case)].to_dict('records')
        controls = CFG['line11_baseline'] if case == 'Line11' else CFG['bebinca_baseline'] + CFG['bebinca_alternative']
        q = dict(file=filename, rows=0, missing_rows=0, negative_rows=0, negative_flow=0, same_station_rows=0, same_station_flow=0, duplicate_keys=0, next_calendar_day_rows=0, off_grid_rows=0)
        previous_last = None
        previous_tail = pd.DataFrame()
        parquet = pq.ParquetFile(path)
        for batch_i, batch in enumerate(parquet.iter_batches(batch_size=CFG['batch_size'])):
            d = batch.to_pandas()
            q['rows'] += len(d)
            q['missing_rows'] += int(d.isna().any(axis=1).sum())
            if d.isna().any().any():
                raise ValueError(f'Null values in AFC input {filename}; resolve before reporting.')
            for col in ['in_sta_id', 'out_sta_id']:
                afc_codes.update(d[col].unique().tolist())
            keys = ['date', 'ts', 'in_sta_id', 'out_sta_id']
            assert d.ts.is_monotonic_increasing, 'Timestamp sorting needed for exact boundary duplicate check'
            if previous_last is not None:
                assert d.ts.iloc[0] >= previous_last
            q['duplicate_keys'] += int(d.duplicated(keys).sum())
            if not previous_tail.empty and d.ts.iloc[0] == previous_last:
                first = d[d.ts.eq(previous_last)]
                combined = pd.concat([previous_tail[keys], first[keys]])
                q['duplicate_keys'] += int(combined.duplicated(keys).sum() - previous_tail.duplicated(keys).sum() - first.duplicated(keys).sum())
            previous_last = d.ts.iloc[-1]
            previous_tail = d[d.ts.eq(previous_last)][keys]
            q['negative_rows'] += int(d.flow.lt(0).sum())
            q['negative_flow'] += int(d.loc[d.flow.lt(0), 'flow'].sum())
            same = d.in_sta_id.eq(d.out_sta_id)
            q['same_station_rows'] += int(same.sum())
            q['same_station_flow'] += int(d.loc[same, 'flow'].sum())
            dates = pd.to_datetime(d.date.astype(str), format='%Y%m%d')
            day_offset = (d.ts.dt.normalize() - dates).dt.days
            assert day_offset.isin([0, 1]).all()
            q['next_calendar_day_rows'] += int(day_offset.eq(1).sum())
            q['off_grid_rows'] += int((d.ts.dt.minute.mod(5).ne(0) | d.ts.dt.second.ne(0)).sum())
            d['minute'] = d.ts.dt.hour * 60 + d.ts.dt.minute + day_offset * 1440
            d['hour'] = d.minute // 60
            d['origin_id'] = d.in_sta_id.map(id_lookup)
            d['dest_id'] = d.out_sta_id.map(id_lookup)
            assert d[['origin_id', 'dest_id']].notna().all().all()
            d['od_key'] = d.origin_id.astype('int64') * 10000 + d.dest_id.astype('int64')
            add(daily, d.groupby('date').flow.sum())
            add(net5, d.groupby(['date', 'minute']).flow.sum())
            add(station_day, d.groupby(['date', 'origin_id']).flow.sum())
            add(station_hour, d.groupby(['date', 'hour', 'origin_id']).flow.sum())
            add(coded_day, d.groupby(['date', 'in_sta_id']).flow.sum())
            odtotals = d.groupby(['date', 'in_sta_id', 'out_sta_id']).flow.sum().groupby(level=0).sum()
            add(total_od_daily, odtotals)
            l11 = d[d.in_sta_id.between(1114, 1163)]
            segment = np.select([l11.in_sta_id.between(1114, 1135), l11.in_sta_id.between(1136, 1138)], ['west', 'closed'], default='east')
            l11 = l11.assign(segment=segment)
            add(l11_5, l11.groupby(['date', 'minute', 'segment']).flow.sum())
            cross = d.in_sta_id.between(1114, 1135) & d.out_sta_id.between(1139, 1163) | d.out_sta_id.between(1114, 1135) & d.in_sta_id.between(1139, 1163)
            add(gap5, d.loc[cross].groupby(['date', 'minute']).flow.sum())
            sampled = d[d.od_key.isin(supported[case])]
            for w in ws:
                allowed_dates = set(controls + [w['Event_date']])
                mask = sampled.date.isin(allowed_dates) & sampled.minute.ge(w['start']) & sampled.minute.lt(w['end'])
                vals = sampled.loc[mask].groupby(['date', 'od_key']).flow.sum()
                od_windows.update({(case, w['Scenario'], int(day), int(key)): int(value) for (day, key), value in vals.items()})
                mask_full = d.date.isin(allowed_dates) & d.minute.ge(w['start']) & d.minute.lt(w['end'])
                vals_full = d.loc[mask_full].groupby('date').flow.sum()
                network_windows.update({(case, w['Scenario'], int(day)): int(value) for day, value in vals_full.items()})
            if batch_i % 10 == 0:
                print(filename, f'{q['rows']:,} rows processed', flush=True)
        assert q['rows'] == parquet.metadata.num_rows
        audit.append(q)
        sources.append(dict(path=str(path), sha256=sha256(path), size=path.stat().st_size, rows=q['rows']))
    assert afc_codes <= set(m.sta_id)
    frames = {'afc_daily.csv': counter_frame(daily, ['date']), 'afc_network_5min.csv': counter_frame(net5, ['date', 'minute']), 'afc_station_daily.csv': counter_frame(station_day, ['date', 'physical_id']), 'afc_station_hourly.csv': counter_frame(station_hour, ['date', 'hour', 'physical_id']), 'afc_coded_station_daily.csv': counter_frame(coded_day, ['date', 'sta_id']), 'afc_line11_segment_5min.csv': counter_frame(l11_5, ['date', 'minute', 'segment']), 'afc_cross_gap_5min.csv': counter_frame(gap5, ['date', 'minute']), 'afc_matched_od_windows.csv': counter_frame(od_windows, ['Case', 'Scenario', 'date', 'od_key']), 'afc_network_windows.csv': counter_frame(network_windows, ['Case', 'Scenario', 'date'])}
    for name, frame in frames.items():
        save_csv(frame, name, PROCESSED)
    sd = frames['afc_station_daily.csv'].groupby('date').flow.sum()
    assert daily == total_od_daily and daily == Counter(sd.to_dict())
    assert daily == Counter(frames['afc_network_5min.csv'].groupby('date').flow.sum().to_dict())
    save_csv(pd.DataFrame(audit), 'data_quality.csv', QA)
    save_csv(pd.DataFrame({'date': sorted(daily), 'raw_total': [daily[k] for k in sorted(daily)], 'station_total': [sd[k] for k in sorted(daily)], 'od_total': [total_od_daily[k] for k in sorted(daily)]}), 'total_reconciliation.csv', QA)
    sources.append(dict(path=CFG['station_file'], sha256=sha256(CFG['station_file'])))
    (QA / 'source_manifest.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding='utf-8')
    print('AFC totals reconcile; all station codes mapped; no source modification.')
    return pd.DataFrame(audit)

def bool_series(s):
    return s.astype(str).str.lower().isin(['true', '1', '1.0'])

def compare_matched_od():
    raw = pd.read_csv(PROCESSED / 'afc_matched_od_windows.csv')
    net = pd.read_csv(PROCESSED / 'afc_network_windows.csv')
    win = pd.read_csv(PROCESSED / 'validation_windows.csv')
    rows, od_rows, exclusion_rows = ([], [], [])
    for case in ['Line11', 'Bebinca']:
        cohort = pd.read_csv(PROCESSED / f'{case}_mapped_cohort.csv')
        dec = pd.read_csv(PROCESSED / f'{case}_decisions.csv')
        cohort['affected_group'] = bool_series(cohort.Affected_Corridor if case == 'Line11' else cohort.Ever_Affected_Typhoon_State)
        valid = cohort[cohort.mapping_valid].copy()
        for w in win[win.Case.eq(case)].to_dict('records'):
            baseline_sets = [('primary', CFG['line11_baseline'] if case == 'Line11' else CFG['bebinca_baseline'])]
            baseline_sets += [('single_1208', [20241208]), ('single_1215', [20241215])] if case == 'Line11' else [('normal_monday', CFG['bebinca_alternative'])] if w['Event_date'] == 20240916 else []
            decision = dec[dec.Scenario.eq(w['Scenario'])]
            fields = ['PID', 'Action'] + (['Corridor_Crossing_Direction'] if case == 'Line11' else [])
            a = valid.merge(decision[fields], on='PID', validate='one_to_one')
            assert len(a) == len(valid)
            metro_action = 'continue_metro' if case == 'Line11' else 'metro_trip'
            all_keys = np.sort(a.od_key.unique())
            sample_n = a.groupby('od_key').size()
            d = raw[raw.Case.eq(case) & raw.Scenario.eq(w['Scenario'])]
            flow = d.pivot_table(index='od_key', columns='date', values='flow', aggfunc='sum').reindex(all_keys).fillna(0)
            for baseline, dates in baseline_sets:
                b = flow.reindex(columns=dates, fill_value=0).mean(axis=1)
                observed = flow[w['Event_date']] if w['Event_date'] in flow else pd.Series(0, index=flow.index)
                a['baseline_flow'] = a.od_key.map(b)
                a['observed_flow'] = a.od_key.map(observed)
                a['weight'] = a.baseline_flow / a.od_key.map(sample_n)
                use = a.baseline_flow.gt(0)
                for _, x in a.loc[~use].iterrows():
                    exclusion_rows.append(dict(Case=case, Scenario=w['Scenario'], Baseline=baseline, PID=int(x.PID), od_key=int(x.od_key), reason='nonpositive baseline OD flow', baseline_flow=x.baseline_flow))
                groups = [('all', pd.Series(True, index=a.index)), ('affected', a.affected_group), ('unaffected', ~a.affected_group)]
                if case == 'Line11':
                    direction = a.Corridor_Crossing_Direction.map({'嘉定侧→市区侧': 'west_to_east', '市区侧→嘉定侧': 'east_to_west'})
                    groups += [('west_to_east', a.affected_group & direction.eq('west_to_east')), ('east_to_west', a.affected_group & direction.eq('east_to_west'))]
                for group, mask in groups:
                    z = a[use & mask]
                    keys = z.od_key.unique()
                    bsum = float(b.reindex(keys).sum())
                    osum = float(observed.reindex(keys).sum())
                    llm = float(z.loc[z.Action.eq(metro_action), 'weight'].sum() / bsum) if bsum > 0 else np.nan
                    obs = osum / bsum if bsum > 0 else np.nan
                    network_baseline = float(net[net.Case.eq(case) & net.Scenario.eq(w['Scenario']) & net.date.isin(dates)].groupby('date').flow.sum().reindex(dates, fill_value=0).mean())
                    network_observed = float(net[net.Case.eq(case) & net.Scenario.eq(w['Scenario']) & net.date.eq(w['Event_date'])].flow.sum())
                    rows.append(dict(Case=case, Scenario=w['Scenario'], Group=group, Baseline=baseline, baseline_dates=','.join(map(str, dates)), event_date=w['Event_date'], time_window=w['label'], start=w['start'], end=w['end'], observed_flow=osum, baseline_flow=bsum, Observed=obs, LLM=llm, discrepancy_pp=100 * (llm - obs), absolute_error_pp=100 * abs(llm - obs), Agent_N=len(z), Group_sample_N=int(mask.sum()), OD_N=len(keys), sample_OD_N=a.loc[mask, 'od_key'].nunique(), OD_coverage=len(keys) / a.loc[mask, 'od_key'].nunique() if mask.any() else np.nan, network_baseline_flow=network_baseline, baseline_network_coverage=bsum / network_baseline if network_baseline else np.nan, network_observed_ratio=network_observed / network_baseline if network_baseline else np.nan, LLM_unweighted=float(a.loc[mask, 'Action'].eq(metro_action).mean()) if mask.any() else np.nan, Evidence_type='共同OD范围内标准化行为对照', Interpretation='地铁选择份额与客流保持率的标准化差异；不外推至总体，非逐人行为验证'))
                rates = a[use].assign(metro=lambda x: x.Action.eq(metro_action)).groupby('od_key').metro.mean()
                for key in b[b.gt(0)].index:
                    od_rows.append(dict(Case=case, Scenario=w['Scenario'], Baseline=baseline, od_key=int(key), baseline_flow=float(b[key]), observed_flow=float(observed[key]), Observed=float(observed[key] / b[key]), LLM=float(rates[key]), agent_n=int(sample_n[key])))
    result = pd.DataFrame(rows)
    structural = result.Case.eq('Line11') & result.Scenario.isin(['condition_2', 'condition_3']) & result.Group.isin(['affected', 'west_to_east', 'east_to_west'])
    result.loc[structural, 'Evidence_type'] = '运营可达性约束对照'
    result.loc[structural, 'Interpretation'] = '地铁选择为零主要由可行方式约束确定；作为结构相容性证据，不单独证明LLM行为能力'
    save_csv(result, 'matched_comparison.csv')
    save_csv(pd.DataFrame(od_rows), 'matched_od_detail.csv')
    save_csv(pd.DataFrame(exclusion_rows), 'excluded_agent_windows.csv')
    mapping = pd.read_csv(PROCESSED / 'agent_mapping.csv')
    save_csv(mapping[~mapping.mapping_valid], 'unmapped_agents.csv')
    print(result[result.Baseline.eq('primary') & result.Group.eq('all')][['Case', 'Scenario', 'Observed', 'LLM', 'Agent_N', 'OD_N', 'baseline_network_coverage']].to_string(index=False))
    return result

def observed_spatial():
    coded = pd.read_csv(PROCESSED / 'afc_coded_station_daily.csv')
    m = pd.read_csv(PROCESSED / 'station_mapping.csv')
    station = pd.read_csv(PROCESSED / 'afc_station_daily.csv')
    bdates = CFG['line11_baseline']
    rows = []
    for group, lo, hi in [('all_line11', 1114, 1163), ('west', 1114, 1135), ('closed', 1136, 1138), ('east', 1139, 1163)]:
        x = coded[coded.sta_id.between(lo, hi)].groupby('date').flow.sum()
        b = float(x.reindex(bdates, fill_value=0).mean())
        o = float(x.get(20241222, 0))
        rows.append(dict(target=group, Observed=o / b, observed_flow=o, baseline_flow=b, change_pp=100 * (o / b - 1), unit='line-coded station entries'))
    ids = m.groupby('physical_name').physical_id.first().to_dict()
    for name in ['陈翔公路', '南翔', '桃浦新村', '武威路', '祁连山路', '封浜', '乐秀路', '顾唐路', '紫竹高新区']:
        x = station[station.physical_id.eq(ids[name])].groupby('date').flow.sum()
        b = float(x.reindex(bdates, fill_value=0).mean())
        o = float(x.get(20241222, 0))
        rows.append(dict(target=name, Observed=o / b if b > 0 else np.nan, observed_flow=o, baseline_flow=b, change_pp=100 * (o / b - 1) if b > 0 else np.nan, unit='physical station entries'))
    gap = pd.read_csv(PROCESSED / 'afc_cross_gap_5min.csv')
    for label, start, end in [('cross_gap_daily', 0, 2880), ('cross_gap_disruption', 480, 1290)]:
        x = gap[gap.minute.ge(start) & gap.minute.lt(end)].groupby('date').flow.sum()
        b = float(x.reindex(bdates, fill_value=0).mean())
        o = float(x.get(20241222, 0))
        rows.append(dict(target=label, Observed=o / b, observed_flow=o, baseline_flow=b, change_pp=100 * (o / b - 1), unit='west-east Line11 station-coded OD'))
    spatial = pd.DataFrame(rows)
    save_csv(spatial, 'line11_observed_spatial.csv')
    return spatial

def compute_metrics():
    x = pd.read_csv(TABLES / 'matched_comparison.csv')
    rows = []
    for (case, baseline, group), g in x.groupby(['Case', 'Baseline', 'Group'], sort=False):
        good = g[['Observed', 'LLM']].dropna()
        rho = float(spearmanr(good.Observed, good.LLM).statistic) if len(good) >= 3 and good.Observed.nunique() > 1 and (good.LLM.nunique() > 1) else np.nan
        rows.append(dict(Case=case, Baseline=baseline, Group=group, N=len(good), MAE_pp=float((good.LLM - good.Observed).abs().mean() * 100), mean_bias_pp=float((good.LLM - good.Observed).mean() * 100), Spearman=rho, sign_accuracy=float((np.sign(good.Observed - 1) == np.sign(good.LLM - 1)).mean()), note='Across scenario/time responses; no p-value or independent-agent inference. Spearman NA for fewer than 3 values or constant series.'))
    metric = pd.DataFrame(rows)
    save_csv(metric, 'validation_metrics.csv')
    return metric

def observed_temporal_context():
    coded = pd.read_csv(PROCESSED / 'afc_coded_station_daily.csv')
    rows = []
    for baseline, dates in [('primary', CFG['bebinca_baseline']), ('normal_monday', CFG['bebinca_alternative'])]:
        for line in range(1, 19):
            z = coded[coded.sta_id.between(line * 100, (line + 1) * 100 - 1)].groupby('date').flow.sum()
            b = float(z.reindex(dates, fill_value=0).mean())
            o = float(z.get(20240916, 0))
            rows.append(dict(line=line, Baseline=baseline, baseline_dates=','.join(map(str, dates)), event_date=20240916, observed_flow=o, baseline_flow=b, Observed=o / b if b > 0 else np.nan, supply_class='continuously operated underground lines' if line in [12, 13, 14, 15, 18] else 'suspension or shortened service'))
    save_csv(pd.DataFrame(rows), 'bebinca_observed_lines.csv')
    net = pd.read_csv(PROCESSED / 'afc_network_5min.csv')
    net['hour'] = net.minute // 60
    line = pd.read_csv(PROCESSED / 'afc_line11_segment_5min.csv')
    line['hour'] = line.minute // 60
    records = []
    for case, df, event_dates, sets in [('Line11', line, [20241222], [('primary', CFG['line11_baseline'])]), ('Bebinca', net, [20240915, 20240916], [('primary', CFG['bebinca_baseline']), ('normal_monday', CFG['bebinca_alternative'])])]:
        hourly = df.groupby(['date', 'hour']).flow.sum().unstack('date', fill_value=0)
        for event in event_dates:
            for baseline, dates in sets:
                if event == 20240915 and baseline == 'normal_monday':
                    continue
                for hour in range(5, 27):
                    b = float(hourly.reindex(index=[hour], columns=dates, fill_value=0).mean(axis=1).iloc[0])
                    o = float(hourly.reindex(index=[hour], columns=[event], fill_value=0).iloc[0, 0])
                    records.append(dict(Case=case, event_date=event, hour=hour, Baseline=baseline, observed_flow=o, baseline_flow=b, Observed=o / b if b > 0 else np.nan))
    out = pd.DataFrame(records)
    save_csv(out, 'observed_hourly_context.csv')
    return out
