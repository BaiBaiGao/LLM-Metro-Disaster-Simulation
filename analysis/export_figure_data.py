"""Export figure tables from the AFC analysis."""
import argparse
import json
from pathlib import Path
import pandas as pd

SCENARIOS = ['condition_1', 'condition_2', 'condition_3']


def export(analysis_root, out):
    root, out = Path(analysis_root), Path(out)
    tables, processed = root / 'tables', root / 'processed'
    comp = pd.read_csv(tables / 'matched_comparison.csv')
    b = pd.read_csv(processed / 'Line11_decisions.csv')
    cohort = pd.read_csv(processed / 'Line11_cohort.csv')
    if 'Affected_Corridor' not in b:
        b = b.merge(cohort[['PID', 'Affected_Corridor']], on='PID', validate='many_to_one')
    b['Affected'] = b.Affected_Corridor.astype(str).str.lower().isin(['true', '1'])
    shares = b.groupby(['Scenario', 'Affected', 'Action']).size().rename('Count').reset_index()
    shares['Group_N'] = shares.groupby(['Scenario', 'Affected']).Count.transform('sum')
    shares['Proportion'] = shares.Count / shares.Group_N
    wide = b[b.Affected].pivot(index='PID', columns='Scenario', values='Action')
    transition = []
    for stage in [0, 1]:
        counts = wide.groupby([SCENARIOS[stage], SCENARIOS[stage+1]]).size()
        transition.extend({'stage':stage, 'source':s, 'target':t, 'count':int(n)} for (s,t),n in counts.items())
    response = []
    primary = comp[comp.Case.eq('Line11') & comp.Baseline.eq('primary')]
    for _, r in primary[primary.Group.isin(['all','affected','unaffected'])].iterrows():
        peers = comp[comp.Case.eq('Line11') & comp.Scenario.eq(r.Scenario) & comp.Group.eq(r.Group)]
        for series in ['Observed','LLM']:
            response.append({'Group':r.Group,'Scenario':r.Scenario,'Series':series,'Value':r[series],
                             'Error_low':max(0,r[series]-peers[series].min()),
                             'Error_high':max(0,peers[series].max()-r[series])})
    c = pd.read_csv(processed / 'Bebinca_decisions.csv')
    counts = c.groupby(['Scenario','Action']).size().unstack(fill_value=0).reindex(columns=['abandon_trip','metro_trip','non_metro_trip'], fill_value=0).sort_index()
    choices = pd.DataFrame({'Decision time':pd.to_datetime(counts.index.str.replace('snapshot_',''),format='%Y%m%d_%H%M'), 'N':counts.sum(axis=1).to_numpy()})
    for action in ['abandon_trip','metro_trip','non_metro_trip']:
        choices[action+'_n'] = counts[action].to_numpy()
        choices[action+'_pct'] = 100 * choices[action+'_n'] / choices.N
    choices['travel_participation_pct'] = 100 - choices.abandon_trip_pct
    data = {'B_choice_shares.csv':shares, 'B_transitions.csv':pd.DataFrame(transition),
            'B_comparison.csv':pd.DataFrame(response), 'C_choices.csv':choices}
    for baseline, filename in [('primary','C_comparison.csv'),('normal_monday','C_monday.csv')]:
        data[filename] = comp[comp.Case.eq('Bebinca') & comp.Group.eq('all') & comp.Baseline.eq(baseline)][['Scenario','Observed','LLM','Agent_N','OD_N']].sort_values('Scenario')
    segments = pd.read_csv(tables / 'line11_observed_spatial.csv')
    data['B_segments.csv'] = segments.loc[segments.target.isin(['west','closed','east']), ['target','Observed','unit']]
    station_path = tables / 'line11_seven_station_plot_data.csv'
    if not station_path.is_file():
        raise FileNotFoundError('Generate the seven-station aggregate with line11_spatial_figure before export.')
    data['B_stations.csv'] = pd.read_csv(station_path)[['order','station','label','baseline_flow','observed_flow','baseline_dates','event_date']]
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in data.items():
        frame.to_csv(out / name, index=False, encoding='utf-8-sig')
    (out/'manifest.json').write_text(json.dumps({'role_en':'Figure-level aggregates exported from explicit local analyses.',
        'role_zh':'从明确指定的本地分析导出的图表级汇总。','files':list(data)},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--analysis-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    export(args.analysis_root,args.out)
