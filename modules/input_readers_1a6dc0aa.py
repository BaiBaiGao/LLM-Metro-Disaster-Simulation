def clean_station_name(name):
    """Normalize station names consistently across topology, schedules and flow inputs."""
    name = str(name).strip().replace('●', '·').replace(' ', '')
    fixes = {'淞淞发路': '淞发路', '淞淞虹路': '淞虹路', '淞淞滨路': '淞滨路', '临洮洮路': '临洮路', '颛颛桥': '颛桥', '佘佘山': '佘山', '严御路': '康恒路', '黄陂南路': '一大会址·黄陂南路', '一大会址黄陂南路': '一大会址·黄陂南路'}
    return fixes.get(name, name)

def audit_input_files(base_path):
    """List required input files and their availability."""
    records = []
    for fname in INPUT_AUDIT_FILES:
        fpath = Path(base_path) / fname
        records.append({'Version': OUTPUT_VERSION, 'File': fname, 'Path': fname, 'Exists': bool(fpath.exists()), 'Note': 'found' if fpath.exists() else 'missing; optional fallback may be used'})
    print('\n输入文件审计：')
    for row in records:
        mark = 'OK' if row['Exists'] else 'MISSING'
        print(f'  [{mark}] {row['File']}')
    return records

def load_flow_data(base_path):
    """Read 8 August 2025 flows and split Pudian Road between Lines 4 and 6."""
    flow_file = 'shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv'
    flow_path = Path(base_path) / flow_file
    print(f'加载客流文件: {flow_path}')
    try:
        full_df = pd.read_csv(flow_path)
        full_df['time'] = pd.to_datetime(full_df['time'])
        target_date = pd.Timestamp('2025-08-08').date()
        flow_df = full_df[full_df['time'].dt.date == target_date].copy()
        if flow_df.empty:
            raise _sr.SubmissionStop('The platform input has no records for 2025-08-08.')
        flow_df.rename(columns={'station_name_mapped': 'station'}, inplace=True)
        flow_df['station'] = flow_df['station'].apply(clean_station_name)
        pudian_mask = flow_df['station'] == '浦电路'
        if pudian_mask.any():
            pudian_rows = flow_df[pudian_mask].copy()
            pudian_4 = pudian_rows.copy()
            pudian_4['station'] = '浦电路(4号线)'
            pudian_4[['inbound', 'outbound']] /= 2
            pudian_6 = pudian_rows.copy()
            pudian_6['station'] = '浦电路(6号线)'
            pudian_6[['inbound', 'outbound']] /= 2
            flow_df = flow_df[~pudian_mask]
            flow_df = pd.concat([flow_df, pudian_4, pudian_6], ignore_index=True)
        print(f'已加载 2025-08-08 客流数据，共 {len(flow_df)} 条记录')
        return flow_df
    except _sr.SubmissionStop:
        raise
    except Exception as exc:
        raise _sr.SubmissionStop('Platform station-flow input could not be loaded; see docs/DATA_SOURCES.md.') from exc
