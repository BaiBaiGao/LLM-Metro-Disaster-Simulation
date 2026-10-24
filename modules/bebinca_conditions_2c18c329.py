from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
CASE_VERSION = 'bebinca_typhoon_notice_20240916_shmetro_shanghai_release_8snapshots_promptonly_20260706'
CASE_DATE = date(2024, 9, 16)
CASE_DAY_TYPE = 'Weekend'
BEBINCA_DECISION_SNAPSHOT_TIMES_BJT = ['2024-09-15 10:00', '2024-09-15 14:00', '2024-09-15 18:00', '2024-09-15 22:00', '2024-09-16 10:00', '2024-09-16 14:00', '2024-09-16 18:00', '2024-09-16 22:00']
BEBINCA_DECISION_MIN = 10 * 60
BEBINCA_CASE_FOLDER_NAME = '20260703上海地铁贝碧嘉台风计算'

def _bebinca_resolve_output_dir():
    return SUBMISSION_OUTPUT_DIR
BEBINCA_REQUIRED_INPUT_FILES = ['subway.json', '进站客流.xlsx', 'line_schedule_detailed.xlsx', '上海地铁地上线归纳.txt', '线路id与名称对应-20251210.xlsx']

def _bebinca_unique_relative_paths(paths):
    unique = []
    seen = set()
    for path in paths:
        path = Path(path)
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique

def _bebinca_input_search_roots(output_dir=None):
    return [_sr.project_root(), SUBMISSION_SOURCE_DIR]

def _bebinca_resolve_data_root(output_dir):
    return _sr.project_root()

def _bebinca_find_input_file(filename):
    for root in _bebinca_input_search_roots(CASE_OUTPUT_DIR):
        candidate = root / filename
        if candidate.exists():
            return candidate
    return CASE_DATA_ROOT / filename
CASE_OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
CASE_DATA_ROOT = _sr.project_root()
BASE_PATH = _sr.project_root()
OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
CASE_SCHEDULE_PATH = SUBMISSION_SCHEDULE_PATH
BEBINCA_GROUND_SEGMENT_PATH = _bebinca_find_input_file('上海地铁地上线归纳.txt')
CASE_CHECKPOINT_DIR = CASE_OUTPUT_DIR / 'checkpoints_bebinca_notice_8snapshots_shanghai_release_promptonly_20260706'
CASE_SAMPLE_SIZE = 200
CASE_AFFECTED_COUNT = None
CASE_CONTROL_COUNT = None
CASE_SEED = 20260703
PASSENGER_DECISION_MODE = 'llm'
LLM_PASSENGER_RATIO = 1.0
LLM_ALLOWED_ACTIONS = ['abandon_trip', 'metro_trip', 'non_metro_trip']
CASE_ACTION_CN = {'abandon_trip': '放弃出行', 'metro_trip': '地铁出行', 'non_metro_trip': '非地铁出行'}
CASE_ACTION_MEANINGS = {'abandon_trip': '取消或推迟本次去目的地的出行。', 'metro_trip': '在当前地铁网络仍可达时，继续或改用可达的地铁路径完成出行。', 'non_metro_trip': '不坐地铁，改用非地铁方式完成出行；不再细分公交、出租车、网约车、私家车、骑行或步行。'}
BEBINCA_FULL_SUSPENDED_LINES = ['3', '5', '16', '17', 'PJ', 'Maglev']
BEBINCA_GROUND_SUSPENDED_LINES = ['1', '2', '4', '6', '7', '8', '9', '10', '11']
BEBINCA_NIGHT_LIMITED_LINES = ['2', '5', '11', '16', 'PJ']
BEBINCA_METRO_ACCOUNT = '上海地铁shmetro'
BEBINCA_CITY_ACCOUNT = '上海发布'
BEBINCA_OFFICIAL_ACCOUNT = BEBINCA_METRO_ACCOUNT
BEBINCA_NOTICE_SOURCE_MODE = 'hardcoded_shmetro_and_shanghai_release_weibo_timeline'
BEBINCA_OFFICIAL_NOTICE_TIMELINE = _sr.load_notice_rows('metro')
BEBINCA_METRO_NOTICE_TIMELINE = [dict(row) for row in BEBINCA_OFFICIAL_NOTICE_TIMELINE]
BEBINCA_CITY_NOTICE_TIMELINE = _sr.load_notice_rows('city')
BEBINCA_OFFICIAL_NOTICE_TIMELINE = sorted([dict(row) for row in BEBINCA_METRO_NOTICE_TIMELINE] + [dict(row) for row in BEBINCA_CITY_NOTICE_TIMELINE], key=lambda row: row['Publish_Time_BJT'])
BEBINCA_TIME_FMT = '%Y-%m-%d %H:%M'

def _bebinca_parse_bjt(value):
    return datetime.strptime(str(value), BEBINCA_TIME_FMT)

def _bebinca_minute_of_day(value):
    dt = _bebinca_parse_bjt(value) if isinstance(value, str) else value
    return int(dt.hour) * 60 + int(dt.minute)

def _bebinca_known_notice_rows(decision_time_bjt, timeline=None):
    dt = _bebinca_parse_bjt(decision_time_bjt)
    rows = BEBINCA_OFFICIAL_NOTICE_TIMELINE if timeline is None else timeline
    return [dict(row) for row in rows if _bebinca_parse_bjt(row['Publish_Time_BJT']) <= dt]

def _bebinca_notice_text(decision_time_bjt, known_rows, source_label):
    if not known_rows:
        return f'截至北京时间{decision_time_bjt}，{source_label}尚未发布本实验收录范围内的贝碧嘉台风相关通知。'
    parts = [f'截至北京时间{decision_time_bjt}，乘客已能看到以下{source_label}：']
    for idx, row in enumerate(known_rows, start=1):
        time_bits = f'发布时间（北京时间）：{row['Publish_Time_BJT']}'
        if row.get('Publish_Time_Italy'):
            time_bits += f'；原始发表时间（意大利时间）：{row.get('Publish_Time_Italy', '')}'
        if row.get('Account'):
            time_bits += f'；账号：{row.get('Account', '')}'
        if row.get('Source'):
            time_bits += f'；来源：{row.get('Source', '')}'
        if row.get('URL'):
            time_bits += f'；链接：{row.get('URL', '')}'
        parts.append(f'[{idx}] {time_bits}\n{row.get('Body', '')}')
    return '\n\n'.join(parts)

def _bebinca_notice_features(known_rows):
    text = ' '.join((str(row.get('Body', '')) for row in known_rows))
    count = len(known_rows)
    has_recovery = '恢复正常运营' in text or '恢复运营' in text or '预警解除' in text or ('均已解除' in text)
    has_suspension = '停运' in text or '暂停运营' in text or '缩线运营' in text
    has_speed_limit = '限速' in text or '提前结束运营' in text
    has_exact_time = bool(re.search('\\d{1,2}\\s*时|\\d{1,2}:\\d{2}|\\d{1,2}月\\d{1,2}日', text))
    has_line = bool(re.search('\\d+号线|磁浮线|浦江线', text))
    has_city_warning = '预警' in text or '防汛防台' in text or '城市积涝' in text or ('交通拥堵' in text)
    has_orange_or_red = any((term in text for term in ['橙色预警', '红色预警', '一红', '两橙', '海浪红色', '台风橙色', '暴雨橙色']))
    has_nonessential_warning = any((term in text for term in ['非必要不出门', '致灾风险很高', '特别加强防范', '城市积涝', '交通拥堵']))
    return {'Severity': 5 if has_suspension or has_orange_or_red else 4 if has_speed_limit or has_city_warning else 2 if count else 1, 'Clarity': 5 if has_suspension or has_recovery or has_orange_or_red else 3 if count else 0, 'Detail': 5 if has_line and has_city_warning else 5 if has_line else 3 if has_city_warning else 2 if count else 0, 'Actionability': 5 if has_suspension or has_nonessential_warning else 4 if has_recovery else 3 if has_city_warning else 2 if count else 0, 'Safety_Cue': 5 if has_suspension or has_speed_limit or has_orange_or_red or has_nonessential_warning else 3 if count else 1, 'Uncertainty': 2 if has_recovery else 4 if count else 5, 'Line_Specific': 1 if has_line else 0, 'Time_Specific': 1 if has_exact_time else 0}

def _bebinca_notice_row_for_snapshot(decision_time_bjt):
    metro_known = _bebinca_known_notice_rows(decision_time_bjt, BEBINCA_METRO_NOTICE_TIMELINE)
    city_known = _bebinca_known_notice_rows(decision_time_bjt, BEBINCA_CITY_NOTICE_TIMELINE)
    known = sorted(metro_known + city_known, key=lambda row: _bebinca_parse_bjt(row['Publish_Time_BJT']))
    latest = known[-1] if known else {}
    latest_metro = metro_known[-1] if metro_known else {}
    latest_city = city_known[-1] if city_known else {}
    dt = _bebinca_parse_bjt(decision_time_bjt)
    key = f'snapshot_{dt.strftime('%Y%m%d_%H%M')}'
    features = _bebinca_notice_features(known)
    row = {'Notice_Key': key, 'Notice_Label': f'真实官微与上海发布截至{dt.strftime('%m-%d %H:%M')}北京时间', 'Decision_Time_BJT': decision_time_bjt, 'Notice_Publish_Time_BJT': latest.get('Publish_Time_BJT', ''), 'Notice_Text': _bebinca_notice_text(decision_time_bjt, known, '上海地铁官方运营信息和上海发布城市预警信息'), 'Metro_Notice_Text': _bebinca_notice_text(decision_time_bjt, metro_known, '上海地铁官方运营信息'), 'City_Notice_Text': _bebinca_notice_text(decision_time_bjt, city_known, '上海发布城市预警信息'), 'Notice_Source_URL': latest.get('URL', ''), 'Metro_Notice_Source_URL': latest_metro.get('URL', ''), 'City_Notice_Source_URL': latest_city.get('URL', ''), 'Notice_Is_Synthetic': False, 'Known_Notice_Count': len(known), 'Metro_Known_Notice_Count': len(metro_known), 'City_Known_Notice_Count': len(city_known), 'Latest_Notice_Account': latest.get('Account', ''), 'Latest_Notice_Time_Italy': latest.get('Publish_Time_Italy', ''), 'Latest_Notice_Time_BJT': latest.get('Publish_Time_BJT', ''), 'Latest_Notice_Title': latest.get('Title', ''), 'Latest_Metro_Notice_Time_BJT': latest_metro.get('Publish_Time_BJT', ''), 'Latest_City_Notice_Time_BJT': latest_city.get('Publish_Time_BJT', '')}
    row.update(features)
    return row
BEBINCA_NOTICE_TREATMENTS = [_bebinca_notice_row_for_snapshot(t) for t in BEBINCA_DECISION_SNAPSHOT_TIMES_BJT]
BEBINCA_NOTICE_BY_KEY = {row['Notice_Key']: dict(row) for row in BEBINCA_NOTICE_TREATMENTS}

@dataclass
class BebincaNoticeScenario:
    key: str
    name: str
    decision_time_bjt: str
    start_min: int
    end_min: int
    notice_key: str

    @property
    def notice(self):
        return BEBINCA_NOTICE_BY_KEY[self.notice_key]

def _bebinca_make_scenario(decision_time_bjt):
    dt = _bebinca_parse_bjt(decision_time_bjt)
    key = f'snapshot_{dt.strftime('%Y%m%d_%H%M')}'
    minute = _bebinca_minute_of_day(dt)
    return BebincaNoticeScenario(key, f'真实官微与上海发布截至{dt.strftime('%Y-%m-%d %H:%M')}北京时间', decision_time_bjt, minute, minute + 1, key)
CASE_SCENARIOS = [_bebinca_make_scenario(t) for t in BEBINCA_DECISION_SNAPSHOT_TIMES_BJT]
CASE_SCENARIO_BY_KEY = {scenario.key: scenario for scenario in CASE_SCENARIOS}
CASE_SCENARIO_BY_KEY['normal_recovered'] = BebincaNoticeScenario('normal_recovered', '无台风停运基准', BEBINCA_DECISION_SNAPSHOT_TIMES_BJT[-1], 22 * 60, 22 * 60 + 1, CASE_SCENARIOS[-1].notice_key)
LLM_MAX_PASSENGER_CALLS = CASE_SAMPLE_SIZE * len(CASE_SCENARIOS)

def case_hhmm(minute_of_day):
    minute_of_day = int(minute_of_day) % 1440
    return f'{minute_of_day // 60:02d}:{minute_of_day % 60:02d}'

def case_require_inputs():
    required = {name: _bebinca_find_input_file(name) for name in BEBINCA_REQUIRED_INPUT_FILES}
    search_roots = _bebinca_input_search_roots(CASE_OUTPUT_DIR)
    missing = []
    for name, path in required.items():
        if not path.exists():
            searched = ', '.join((str(root / name) for root in search_roots))
            missing.append(f'{name} (searched: {searched})')
    if missing:
        raise FileNotFoundError('贝碧嘉案例输入文件缺失：' + ' | '.join(missing))
    return required

def bebinca_notice_treatments_df():
    return pd.DataFrame(BEBINCA_NOTICE_TREATMENTS)

def bebinca_official_notice_timeline_df():
    return pd.DataFrame(BEBINCA_OFFICIAL_NOTICE_TIMELINE)

def bebinca_metro_notice_timeline_df():
    return pd.DataFrame(BEBINCA_METRO_NOTICE_TIMELINE)

def bebinca_city_notice_timeline_df():
    return pd.DataFrame(BEBINCA_CITY_NOTICE_TIMELINE)

def bebinca_line_id_from_label(label):
    text = str(label)
    if '浦江' in text:
        return 'PJ'
    if '磁' in text:
        return 'Maglev'
    match = re.search('(\\d+)', text)
    return match.group(1) if match else text.strip()

def bebinca_line_display_name(line_id):
    line_id = str(line_id)
    if line_id == 'PJ':
        return '浦江线'
    if line_id == 'Maglev':
        return '磁浮线'
    return f'{line_id}号线'

def bebinca_load_ground_segment_chains():
    case_require_inputs()
    chains = {}
    text = BEBINCA_GROUND_SEGMENT_PATH.read_text(encoding='utf-8')
    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line or '：' not in raw_line:
            continue
        label, body = raw_line.split('：', 1)
        line_id = bebinca_line_id_from_label(label)
        parts = [part.strip() for part in re.split('[，,；;]', body) if part.strip()]
        chains[line_id] = []
        for part in parts:
            stations = [clean_station_name(st) for st in part.split('-') if st.strip()]
            if len(stations) >= 2:
                chains[line_id].append(stations)
    return chains

def bebinca_edge_key(line_id, from_st, to_st):
    return ('intra_layer', str(line_id), *sorted((clean_station_name(from_st), clean_station_name(to_st))))

def bebinca_edge_station_pair(system, edge_idx):
    u, v, _k = system.edge_list[edge_idx]
    return (clean_station_name(system.station_name_from_node(u)), clean_station_name(system.station_name_from_node(v)))

def bebinca_suspended_edge_keys(system):
    keys = set()
    for idx, sd in enumerate(system.fast_edge_data):
        if sd.get('type') != 'riding':
            continue
        if sd.get('agent_override') == 'suspended' or float(sd.get('speed_factor', 1.0) or 1.0) <= 0:
            from_st, to_st = bebinca_edge_station_pair(system, idx)
            keys.add((str(sd.get('line_id')), *sorted((from_st, to_st))))
    return keys

def bebinca_affected_edge_keys(system):
    keys = set()
    for idx, sd in enumerate(system.fast_edge_data):
        if sd.get('type') != 'riding':
            continue
        if sd.get('agent_override') != 'normal' or float(sd.get('speed_factor', 1.0) or 1.0) < 1.0:
            from_st, to_st = bebinca_edge_station_pair(system, idx)
            keys.add((str(sd.get('line_id')), *sorted((from_st, to_st))))
    return keys

def _bebinca_apply_edge_state(system, edge_idx, line_id, speed_factor, override, source, state_type, applied_rows, applied_edge_indices):
    if edge_idx in applied_edge_indices:
        return
    from_st, to_st = bebinca_edge_station_pair(system, edge_idx)
    intensity = 1.0 if override == 'suspended' or float(speed_factor) <= 0 else max(0.0, 1.0 - float(speed_factor))
    system.apply_edge_decision(edge_idx, intensity, speed_factor, override, source)
    applied_edge_indices.add(edge_idx)
    applied_rows.append({'Line_ID': str(line_id), 'Line_Name': bebinca_line_display_name(line_id), 'From_Station': from_st, 'To_Station': to_st, 'State_Type': state_type, 'Speed_Factor': float(speed_factor), 'Override': override, 'Source': source})

def _bebinca_apply_full_line_state(system, line_id, speed_factor, override, source, state_type, applied_rows, missing_rows, applied_edge_indices):
    indices = list(system.edge_indices_for_line(line_id, 'riding'))
    if not indices:
        missing_rows.append({'Line_ID': str(line_id), 'Line_Name': bebinca_line_display_name(line_id), 'Section': 'FULL_LINE', 'Reason': 'no riding edges found'})
    for edge_idx in indices:
        _bebinca_apply_edge_state(system, edge_idx, line_id, speed_factor, override, source, state_type, applied_rows, applied_edge_indices)

def _bebinca_apply_ground_chain_state(system, line_id, speed_factor, override, source, state_type, applied_rows, missing_rows, applied_edge_indices):
    chains = bebinca_load_ground_segment_chains()
    for stations in chains.get(str(line_id), []):
        for from_st, to_st in zip(stations[:-1], stations[1:]):
            key = bebinca_edge_key(line_id, from_st, to_st)
            indices = list(system.edge_indices_for_key(key))
            if not indices:
                missing_rows.append({'Line_ID': str(line_id), 'Line_Name': bebinca_line_display_name(line_id), 'Section': f'{from_st}->{to_st}', 'Reason': 'ground segment edge not found'})
                continue
            for edge_idx in indices:
                _bebinca_apply_edge_state(system, edge_idx, line_id, speed_factor, override, source, state_type, applied_rows, applied_edge_indices)

def _bebinca_edge_in_section(system, edge_idx, line_id, from_st, to_st):
    sd = system.fast_edge_data[edge_idx]
    if sd.get('type') != 'riding' or str(sd.get('line_id')) != str(line_id):
        return False
    a, b = bebinca_edge_station_pair(system, edge_idx)
    return system._is_station_in_section(str(line_id), a, clean_station_name(from_st), clean_station_name(to_st)) and system._is_station_in_section(str(line_id), b, clean_station_name(from_st), clean_station_name(to_st))

def _bebinca_apply_section_state(system, line_id, from_st, to_st, speed_factor, override, source, state_type, applied_rows, missing_rows, applied_edge_indices):
    indices = [idx for idx, sd in enumerate(system.fast_edge_data) if _bebinca_edge_in_section(system, idx, line_id, from_st, to_st)]
    if not indices:
        missing_rows.append({'Line_ID': str(line_id), 'Line_Name': bebinca_line_display_name(line_id), 'Section': f'{from_st}->{to_st}', 'Reason': 'section edges not found'})
    for edge_idx in indices:
        _bebinca_apply_edge_state(system, edge_idx, line_id, speed_factor, override, source, state_type, applied_rows, applied_edge_indices)

def _bebinca_dt(value):
    return _bebinca_parse_bjt(value) if isinstance(value, str) else value

def bebinca_active_network_specs(decision_time_bjt):
    dt = _bebinca_dt(decision_time_bjt)
    t_0915_limit = _bebinca_parse_bjt('2024-09-15 21:30')
    t_0916_start = _bebinca_parse_bjt('2024-09-16 05:30')
    t_full_recovered = _bebinca_parse_bjt('2024-09-16 18:39')
    specs = {'label': 'normal', 'full_suspended': [], 'ground_suspended': [], 'ground_slowed': [], 'section_suspended': []}
    if dt >= t_full_recovered:
        specs['label'] = 'all_network_recovered_after_2024-09-16_18:39_BJT'
        return specs
    if dt < t_0915_limit:
        specs['label'] = 'normal_before_2024-09-15_21:30_BJT_adjustment'
        return specs
    if dt < t_0916_start:
        specs['label'] = '2024-09-15_night_speed_limited_and_maglev_ended'
        specs['full_suspended'].append(('Maglev', '20240915_2130_maglev_early_end'))
        for line_id in BEBINCA_NIGHT_LIMITED_LINES:
            specs['ground_slowed'].append((line_id, '20240915_2130_ground_elevated_speed_limit'))
        return specs
    specs['label'] = '2024-09-16_typhoon_suspension_or_partial_recovery'
    full_recovery = {'3': '2024-09-16 16:20', '5': '2024-09-16 17:00', '16': '2024-09-16 15:15', '17': '2024-09-16 15:00', 'PJ': '2024-09-16 14:00', 'Maglev': '2024-09-16 14:00'}
    for line_id, recover_time in full_recovery.items():
        if dt < _bebinca_parse_bjt(recover_time):
            specs['full_suspended'].append((line_id, f'full_suspension_until_{recover_time}'))
    ground_recovery = {'1': '2024-09-16 16:20', '2': '2024-09-16 14:30', '4': '2024-09-16 16:20', '6': '2024-09-16 16:40', '7': '2024-09-16 14:30', '8': '2024-09-16 14:00', '9': '2024-09-16 14:30', '10': '2024-09-16 15:45', '11': '2024-09-16 16:20'}
    for line_id, recover_time in ground_recovery.items():
        if dt < _bebinca_parse_bjt(recover_time):
            specs['ground_suspended'].append((line_id, f'ground_elevated_suspension_until_{recover_time}'))
    section_rules = [('1', '富锦路', '上海火车站', '2024-09-16 16:20', 'line1_north_short_turn_suspension'), ('1', '徐家汇', '莘庄', '2024-09-16 16:20', 'line1_south_short_turn_suspension'), ('2', '龙阳路', '浦东国际机场', '2024-09-16 14:30', 'line2_airport_section_suspension'), ('8', '芦恒路', '沈杜公路', '2024-09-16 14:00', 'line8_south_section_suspension'), ('9', '松江新城', '中春路', '2024-09-16 14:30', 'line9_west_section_suspension'), ('6', '港城路', '巨峰路', '2024-09-16 18:20', 'line6_gangcheng_jufeng_suspension'), ('11', '花桥', '兆丰路', '2024-09-16 16:40', 'line11_huaqiao_zhaofeng_suspension')]
    for line_id, from_st, to_st, recover_time, source in section_rules:
        if dt < _bebinca_parse_bjt(recover_time):
            specs['section_suspended'].append((line_id, from_st, to_st, source))
    return specs

def bebinca_apply_typhoon_state(system, scenario=None, decision_time_bjt=None):
    if decision_time_bjt is None:
        decision_time_bjt = getattr(scenario, 'decision_time_bjt', BEBINCA_DECISION_SNAPSHOT_TIMES_BJT[4])
    specs = bebinca_active_network_specs(decision_time_bjt)
    applied_rows, missing_rows, applied_edge_indices = ([], [], set())
    for line_id, source in specs['ground_slowed']:
        _bebinca_apply_ground_chain_state(system, line_id, 0.5, 'normal', source, 'ground_elevated_speed_limited', applied_rows, missing_rows, applied_edge_indices)
    for line_id, source in specs['full_suspended']:
        _bebinca_apply_full_line_state(system, line_id, 0.0, 'suspended', source, 'full_line_suspension', applied_rows, missing_rows, applied_edge_indices)
    for line_id, source in specs['ground_suspended']:
        _bebinca_apply_ground_chain_state(system, line_id, 0.0, 'suspended', source, 'ground_elevated_suspension', applied_rows, missing_rows, applied_edge_indices)
    for line_id, from_st, to_st, source in specs['section_suspended']:
        _bebinca_apply_section_state(system, line_id, from_st, to_st, 0.0, 'suspended', source, 'explicit_section_suspension', applied_rows, missing_rows, applied_edge_indices)
    system.bebinca_applied_suspensions = pd.DataFrame(applied_rows)
    system.bebinca_missing_suspensions = pd.DataFrame(missing_rows)
    system.bebinca_suspended_edge_key_set = bebinca_suspended_edge_keys(system)
    system.bebinca_affected_edge_key_set = bebinca_affected_edge_keys(system)
    system.bebinca_active_state_label = specs['label']
    system.bebinca_decision_time_bjt = decision_time_bjt
    system._route_graph_cache = {}
    return system

def bebinca_closure_edges_df(system):
    frame = getattr(system, 'bebinca_applied_suspensions', pd.DataFrame()).copy()
    if frame.empty:
        return frame
    if 'Suspension_Type' not in frame.columns and 'State_Type' in frame.columns:
        frame['Suspension_Type'] = frame['State_Type']
    sort_cols = [col for col in ['Line_ID', 'Suspension_Type', 'From_Station', 'To_Station'] if col in frame.columns]
    return frame.sort_values(sort_cols).reset_index(drop=True) if sort_cols else frame.reset_index(drop=True)

def bebinca_missing_closure_edges_df(system):
    return getattr(system, 'bebinca_missing_suspensions', pd.DataFrame()).copy()

def case_install_schedule(system, scenario=None):
    base_rules = case_load_schedule_rules()
    system.schedule_rules = []
    system.schedule_lookup = {}
    for rule in base_rules:
        system._append_schedule_rule(dict(rule))
    system._route_graph_cache = {}
    return system

def build_bebinca_normal_system(at_min=None):
    case_require_inputs()
    global DEFAULT_SERVICE_RULES
    DEFAULT_SERVICE_RULES = []
    sim_min = BEBINCA_DECISION_MIN
    system = SubwayRuleSystem(CASE_DATA_ROOT, sim_start_time=case_hhmm(sim_min))
    case_install_schedule(system, CASE_SCENARIO_BY_KEY['normal_recovered'])
    system.reset_rule_state()
    system.bebinca_active_state_label = 'normal'
    system.bebinca_decision_time_bjt = ''
    return system

def build_bebinca_typhoon_system(scenario=None, at_min=None):
    if scenario is None:
        scenario = CASE_SCENARIOS[4]
    sim_min = int(at_min if at_min is not None else scenario.start_min)
    system = build_bebinca_normal_system(sim_min)
    bebinca_apply_typhoon_state(system, scenario=scenario, decision_time_bjt=getattr(scenario, 'decision_time_bjt', None))
    return system

def build_case_system(scenario, at_min):
    if getattr(scenario, 'key', '') == 'normal_recovered':
        return build_bebinca_normal_system(at_min)
    return build_bebinca_typhoon_system(scenario, at_min)

def bebinca_plan_hits_suspended_edges(plan, suspended_keys):
    for rec in plan.get('edge_records', []) if isinstance(plan, dict) else []:
        if rec.get('type') != 'riding':
            continue
        key = (str(rec.get('line_id')), *sorted((str(rec.get('from_station')), str(rec.get('to_station')))))
        if key in suspended_keys:
            return True
    return False

def bebinca_plan_hits_affected_edges(plan, affected_keys):
    for rec in plan.get('edge_records', []) if isinstance(plan, dict) else []:
        if rec.get('type') != 'riding':
            continue
        key = (str(rec.get('line_id')), *sorted((str(rec.get('from_station')), str(rec.get('to_station')))))
        if key in affected_keys:
            return True
    return False

def sample_case_cohort():
    normal = build_bebinca_normal_system(BEBINCA_DECISION_MIN)
    valid_stations = sorted(set(normal.station_names()))
    flow_df = load_flow_data(CASE_DATA_ROOT)
    flow_time = case_hhmm(BEBINCA_DECISION_MIN)
    flow_batch = choose_nearest_flow_batch(flow_df, flow_time, valid_stations)
    sampling_source = f'Shanghai open-data platform 2025-08-08: nearest {flow_time} batch' if flow_batch is not None and (not flow_batch.empty) else '网络站点均匀抽样（客流文件不可用）'
    rng = np.random.default_rng(CASE_SEED)
    sample_od = _make_weighted_od_sampler(normal, flow_df, flow_time, valid_stations, rng)
    cohort_records = []
    attempts, max_attempts = (0, 500000)
    while len(cohort_records) < CASE_SAMPLE_SIZE:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(f'无法在最大重抽样次数内构造贝碧嘉OD样本：sampled={len(cohort_records)}')
        origin, destination = sample_od()
        if origin == destination:
            continue
        baseline = normal.plan_passenger_route(origin, destination, BEBINCA_DECISION_MIN, weight_mode='baseline')
        if not baseline.get('reachable'):
            continue
        cohort_records.append({'Origin': str(origin), 'Dest': str(destination), 'OD_Sample_Group': 'flow_weighted_random', 'OD_Sampling_Source': sampling_source, 'Baseline_Route': ' -> '.join(baseline.get('station_path', []))})
    scenario_systems = {scenario.key: build_case_system(scenario, scenario.start_min) for scenario in CASE_SCENARIOS}
    for record in cohort_records:
        baseline = normal.plan_passenger_route(record['Origin'], record['Dest'], BEBINCA_DECISION_MIN, weight_mode='baseline')
        ever_affected = False
        first_current_route = ''
        first_reachable = False
        first_hits_suspended = False
        for scenario in CASE_SCENARIOS:
            system = scenario_systems[scenario.key]
            current = system.plan_passenger_route(record['Origin'], record['Dest'], scenario.start_min, weight_mode='current')
            affected_keys = getattr(system, 'bebinca_affected_edge_key_set', set())
            suspended_keys = getattr(system, 'bebinca_suspended_edge_key_set', set())
            hits_affected = bebinca_plan_hits_affected_edges(baseline, affected_keys)
            hits_suspended = bebinca_plan_hits_suspended_edges(baseline, suspended_keys)
            current_reachable = bool(current.get('reachable')) and np.isfinite(PassengerAgent._duration_value(current.get('current_duration_min', np.nan)))
            ever_affected = bool(ever_affected or hits_affected or (not current_reachable))
            if not first_current_route and (hits_affected or not current_reachable):
                first_current_route = ' -> '.join(current.get('station_path', [])) if current_reachable else '不可达'
                first_reachable = bool(current_reachable)
                first_hits_suspended = bool(hits_suspended)
        record.update({'Affected_Corridor': bool(ever_affected), 'Ever_Affected_Typhoon_State': bool(ever_affected), 'Affected_Typhoon_State': bool(ever_affected), 'Current_Route_Under_Typhoon': first_current_route or record['Baseline_Route'], 'Baseline_Hits_Suspended_Edge': bool(first_hits_suspended), 'Current_Metro_Reachable': bool(first_reachable) if first_current_route else True})
    rng.shuffle(cohort_records)
    for pid, record in enumerate(cohort_records, start=1):
        record['PID'] = pid
    cohort = pd.DataFrame(cohort_records)
    if len(cohort) != CASE_SAMPLE_SIZE:
        raise AssertionError('贝碧嘉OD样本数量校验失败。')
    return cohort

def bebinca_non_metro_time_values(context):
    surface = context.get('surface', {}) or {}
    prefs = context.get('personal_transport_profile', {}) or {}
    values = []
    for key in ['Other_Surface_Bus_Min', 'Taxi_Min']:
        try:
            val = float(surface.get(key, np.nan))
            if np.isfinite(val):
                values.append(val)
        except _sr.SubmissionStop:
            raise
        except Exception:
            pass
    if prefs.get('Private_Car_Available'):
        values.append(float(surface.get('private_car_min', np.nan)))
    if prefs.get('Cycling_Acceptable'):
        values.append(float(surface.get('cycling_min', np.nan)))
    if int(prefs.get('Walking_Tolerance', 1) or 1) >= 4:
        values.append(float(surface.get('walking_min', np.nan)))
    return [float(v) for v in values if np.isfinite(v)]

def bebinca_non_metro_time_text(context):
    values = bebinca_non_metro_time_values(context)
    if not values:
        return '非地铁方式可选，但代码未估计出稳定时间'
    return f'约{min(values):.1f}-{max(values):.1f}分钟（聚合估计，不细分具体非地铁方式）'

def v5_action_time_min(context, action):
    if action == 'metro_trip':
        return float(context.get('metro_current_min', np.nan))
    if action == 'non_metro_trip':
        values = bebinca_non_metro_time_values(context)
        return min(values) if values else np.nan
    return np.nan

def v5_action_time_for_card(context, action):
    if action == 'non_metro_trip':
        return bebinca_non_metro_time_text(context)
    value = v5_action_time_min(context, action)
    return '' if not np.isfinite(value) else f'{float(value):.1f}分钟'

def v5_action_comparison(context):
    allowed = list(context.get('allowed_actions', []))
    prefs = context.get('personal_transport_profile') or v5_personal_transport_profile(context)
    proxy = context.get('operational_proxy') or {}
    rows = []
    for action in allowed:
        row = {'action_choice': action, '含义': CASE_ACTION_MEANINGS.get(action, action), '估计时间': v5_action_time_for_card(context, action)}
        if action == 'metro_trip':
            row.update({'稳定性': f'当前OD仍有地铁可达路径；运营代理等级{proxy.get('level', 'unknown')}', '成本/负担': '保持轨道交通出行，但可能需要绕行、等待或接受台风期间不确定性。', '个人适配': '适合目的紧迫、信任地铁可达性且能接受台风期间延误的乘客。'})
        elif action == 'non_metro_trip':
            row.update({'稳定性': '避开地铁停运约束，但受道路风雨、排队和费用影响；本研究不细分具体非地铁方式。', '成本/负担': '可能比地铁成本更高或体力负担更大。', '个人适配': f'成本敏感度{prefs.get('Cost_Sensitivity', 3)}/5；网约车接受度{prefs.get('Ridehail_Acceptance', 3)}/5；赶时间或风险规避时可考虑。'})
        elif action == 'abandon_trip':
            row.update({'稳定性': '取消或推迟本次出行，不再前往目的地。', '成本/负担': '避免台风出行风险和交通不确定性，但损失本次出行目标。', '个人适配': f'时间紧迫度{prefs.get('Time_Urgency', 3)}/5；紧迫度低、风险敏感时更可能接受。'})
        rows.append(row)
    return rows

def case_system_prompt():
    return '你现在不是交通系统分析器，也不是规则分类器，而是一名真实的上海地铁乘客。请站在乘客本人的第一人称视角，在台风天气做一个关于出行的决定。现在是中秋假期，上海地铁部分线路因贝碧嘉台风停运，上海市也可能处于台风、暴雨、海浪和防汛防台响应等城市级预警环境。你必须把上海发布的城市预警与上海地铁运营信息视为同等重要的事实来源：前者说明当前城市出行环境是否危险，后者说明地铁网络是否可达。你可以犹豫、烦躁、赶时间、怕麻烦、担心换乘、担心迟到、嫌非地铁方式贵，也可以觉得还好、愿意等等、愿意听从官方通知安排。你的回答要像一个真实乘客在心里盘算后的选择，而不是像论文摘要、系统报告、心理测评或规则解释。\n\n你会收到一张由导航和代码计算出的结果。该结果是唯一事实来源，里面的OD、路线、时间、台风状态、官方通知、个人交通条件和 allowed_actions 都必须严格遵守。不得编造新路线、新车站、新区间、新台风信息、新票价、新等候时间、新公交服务、私家车条件或其他外部信息。如果告诉你的信息中没有说某个条件存在，就不要假设它存在。\n\n年龄、性别、出行目的、人格画像、风险偏好和个人交通属性必须真实影响你的选择和语气。例如：赶着上班、上学、就医的人会更在意迟到；休闲出行的人可能更容易接受等待或取消；年纪较大的人可能更在意换乘、步行、风雨和不确定性；成本敏感的人会更犹豫是否改用非地铁方式；愿意尝试新方案的人可能更容易接受非地铁出行；焦虑或风险规避的人可能更想选择可控方式或取消出行。但这些都只是概率性倾向，不是机械规则，不能违反告诉你的可达性、可选动作和官方城市预警事实。\n\n人格与风险偏好是行为倾向，不是后台字段。你可以让这些倾向自然体现在理由里，比如怕折腾、想稳一点、想省钱、想快点到、愿意听官方安排；但不要直接写 OCEAN、开放性、尽责性、外向性、宜人性、神经质、风险偏好、人格分数、代码字段名或后台变量。\n五级人格与风险解释：\n' + personality_guidance_text() + "\n\n三类动作的含义必须严格区分：abandon_trip 仅表示取消或推迟这次去目的地的出行；metro_trip 仅表示当前地铁路径确实可达时，继续或改用可达地铁路径出行；non_metro_trip 表示不坐地铁，改用非地铁方式出行，本研究不要求也不允许进一步细分公交、出租车、网约车、私家车、骑行或步行。\n\n硬约束：action_choice 必须且只能从 allowed_actions 里选择。如果当前地铁不可达，绝不能选择 metro_trip，也不能把硬停运说成只是可以忍受的延误。non_metro_trip 是聚合类别，不能在输出中自行增加新的动作代码或把它拆成多个动作。\n\nreason 必须是中文，尽量使用第一人称，写出这个乘客当下真实的想法。建议50到120字，重点写为什么这个选择对我来说更合适。可以有情绪和生活化表达，包括但不限于怕耽误、嫌麻烦、想稳一点、台风天不想折腾、担心风雨和积水、非地铁方式太贵、官方通知和城市预警说得很明确或不够明确等。需要考虑到当前是中国传统节日，中秋节。你的出行目的要考虑今天是假期，任何出行目的都要在这个环境下考虑，一般事情的出行意愿偏弱（尤其是台风最猛烈的时候），除非加班、值班、或者身体不舒服、或者早已计划好的全家出游、或者回家，需要仔细的斟酌纠结一下。若上海发布显示台风橙色、暴雨橙色、海浪红色、防汛防台二级响应、非必要不出门、城市积涝或交通拥堵风险，非刚性的节日出行应倾向取消或推迟；即使地铁路径仍可达，也要把进出站路面风雨、积水和返程不确定性纳入考虑。不要把事实卡里的时间逐项机械复述一遍，也不要写成'根据成本敏感度和风险偏好综合评估'这种报告口吻。不得输出Markdown、解释过程、置信度或额外字段。\n\nrisk_perception_level 和 delay_perception_level 只能是 none、low、medium、high、critical。feeling_score 只能是1、2、3、4、5中的整数。只返回严格JSON对象，必须且只能包含：action_choice, reason, risk_perception_level, delay_perception_level, feeling_score。"

def bebinca_order_allowed_actions(context):
    order = []
    if context.get('metro_available'):
        order.append('metro_trip')
    order.append('non_metro_trip')
    order.append('abandon_trip')
    return [action for action in order if action in context.get('allowed_actions', [])]

def case_human_fact_card(context):
    notice = context.get('notice', {}) or {}
    ordered_actions = context.get('allowed_actions_ordered') or context.get('allowed_actions') or []
    decision_time = context.get('decision_time_bjt', context.get('time', ''))
    return {'研究场景': f'{decision_time} 贝碧嘉台风期间上海地铁真实官微通知实验', '固定天气与网络状态说明': '代码按该决策时刻的真实贝碧嘉运营状态计算当前OD地铁可达性；乘客不能假设事实卡外的地铁服务或恢复安排。', 'passenger_id': context.get('passenger_id'), 'scenario_key': context.get('scenario_key'), 'scenario_name': context.get('scenario_name'), 'time': context.get('time'), 'origin': context.get('origin'), 'destination': context.get('destination'), 'profile': context.get('profile', {}), '官方通知概览': {'Notice_Label': notice.get('Notice_Label', ''), 'Latest_Notice_Account': notice.get('Latest_Notice_Account', ''), 'Notice_Publish_Time_BJT': notice.get('Notice_Publish_Time_BJT', ''), 'Known_Notice_Count': int(notice.get('Known_Notice_Count', 0) or 0), 'Metro_Known_Notice_Count': int(notice.get('Metro_Known_Notice_Count', 0) or 0), 'City_Known_Notice_Count': int(notice.get('City_Known_Notice_Count', 0) or 0), 'Notice_Is_Synthetic': bool(notice.get('Notice_Is_Synthetic', False))}, '上海地铁官方运营信息': {'Account': BEBINCA_METRO_ACCOUNT, 'Known_Notice_Count': int(notice.get('Metro_Known_Notice_Count', 0) or 0), 'Latest_Notice_Time_BJT': notice.get('Latest_Metro_Notice_Time_BJT', ''), 'Notice_Source_URL': notice.get('Metro_Notice_Source_URL', ''), 'Notice_Text': notice.get('Metro_Notice_Text', '')}, '上海发布城市预警信息': {'Account': BEBINCA_CITY_ACCOUNT, 'Known_Notice_Count': int(notice.get('City_Known_Notice_Count', 0) or 0), 'Latest_Notice_Time_BJT': notice.get('Latest_City_Notice_Time_BJT', ''), 'Notice_Source_URL': notice.get('City_Notice_Source_URL', ''), 'Notice_Text': notice.get('City_Notice_Text', ''), '阅读提示': '这是与地铁运营信息平级的城市出行环境事实；它描述风雨、积涝、海浪、防汛响应和非必要出行风险。'}, '通知结构化特征': {key: notice.get(key, '') for key in ['Severity', 'Clarity', 'Detail', 'Actionability', 'Safety_Cue', 'Uncertainty', 'Line_Specific', 'Time_Specific']}, 'affected_by_typhoon_closure': bool(context.get('affected_corridor')), 'metro_available': bool(context.get('metro_available')), 'baseline_route': context.get('baseline_route', ''), 'current_metro_route': context.get('current_route', ''), 'metro_normal_text': context.get('metro_normal_text', ''), 'metro_current_text': context.get('metro_current_text', ''), 'impact_summary': context.get('impact_summary', ''), 'non_metro_estimate': bebinca_non_metro_time_text(context), 'surface': context.get('surface', {}), 'personal_transport_profile': context.get('personal_transport_profile', {}), 'allowed_actions': [{'action_choice': action, '含义': CASE_ACTION_MEANINGS[action]} for action in ordered_actions], '动作比较表': context.get('action_comparison', []), '动作选择提示': '三类动作都是真实候选。请同时比较上海地铁运营信息、上海发布城市预警、台风风险、地铁可达性、时间、成本、换乘/体力负担和个人交通条件；在台风橙色、暴雨橙色、海浪红色、防汛防台二级响应或明确提醒非必要不出门时，非刚性的节日出行应明显更倾向取消或推迟；不要因为地铁仍可达就机械选择地铁，也不要因为台风两个字就机械放弃刚性出行。'}

def case_llm_prompt(context):
    return json.dumps(context['fact_card'], ensure_ascii=False, separators=(',', ':'))

def v5_validate_llm_decision(parsed, context):
    warnings = []
    if not isinstance(parsed, dict):
        return (False, 'LLM输出不是JSON对象。', warnings)
    required = {'action_choice', 'reason', 'risk_perception_level', 'delay_perception_level', 'feeling_score'}
    missing = required - set(parsed)
    if missing:
        return (False, 'LLM JSON缺失字段：' + ','.join(sorted(missing)), warnings)
    action = str(parsed.get('action_choice', '')).strip()
    allowed = set(context.get('allowed_actions', []))
    if action not in allowed:
        return (False, 'action_choice不在当前可行动作集合中。', warnings)
    if action == 'metro_trip' and (not bool(context.get('metro_available'))):
        return (False, '当前地铁不可达时不能选择metro_trip。', warnings)
    reason = str(parsed.get('reason', '')).strip()
    if not reason:
        return (False, 'reason为空。', warnings)
    if len(reason) > 260:
        return (False, 'reason过长，应控制在260字以内。', warnings)
    hard_terms = ['action_choice', 'allowed_actions', 'LLM_', 'JSON', '```']
    lower_reason = reason.lower()
    for term in hard_terms:
        if term.lower() in lower_reason:
            return (False, f'reason出现明显后台/格式术语：{term}', warnings)
    soft_terms = ['OCEAN', 'Risk_Preference', '人格分数', '开放性', '尽责性', '外向性', '宜人性', '神经质', '风险偏好']
    for term in soft_terms:
        if term.lower() in lower_reason:
            warnings.append(f'reason含研究术语但允许：{term}')
    risk_level = str(parsed.get('risk_perception_level', '')).strip()
    delay_level = str(parsed.get('delay_perception_level', '')).strip()
    if risk_level not in LLM_PERCEPTION_LEVELS:
        return (False, 'risk_perception_level不是标准枚举。', warnings)
    if delay_level not in LLM_PERCEPTION_LEVELS:
        return (False, 'delay_perception_level不是标准枚举。', warnings)
    _, _, feeling_error = normalize_llm_feeling_score(parsed.get('feeling_score'))
    if feeling_error:
        return (False, feeling_error, warnings)
    return (True, '', warnings)

def case_validate_llm_decision(parsed, context):
    valid, error, _warnings = v5_validate_llm_decision(parsed, context)
    return (valid, error)

def bebinca_build_case_context(self, normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=None, od_groups=None):
    baseline = normal_system.plan_passenger_route(self.origin, self.dest, BEBINCA_DECISION_MIN, weight_mode='baseline')
    current = scenario_system.plan_passenger_route(self.origin, self.dest, at_min, weight_mode='current')
    self.initial_route_plan = baseline
    self.current_route_plan = current
    self.affected_corridor = bool(affected_corridor)
    metro_available = bool(current.get('reachable')) and np.isfinite(self._duration_value(current.get('current_duration_min', np.nan)))
    allowed = []
    if metro_available:
        allowed.append('metro_trip')
    allowed.extend(['non_metro_trip', 'abandon_trip'])
    surface = case_surface_options(normal_system, self.origin, self.dest)
    normal_min = self._duration_value(baseline.get('normal_duration_min', np.nan))
    current_min = self._duration_value(current.get('current_duration_min', np.nan))

    def fmt_min(value):
        return f'{value:.1f}分钟' if np.isfinite(value) else '不可用'
    impact_summary = current.get('impact_summary', '') if metro_available else '受贝碧嘉台风停运影响，当前地铁网络没有可达路径。'
    notice = dict(scenario.notice)
    context = {'passenger_id': int(self.pid), 'scenario_key': scenario.key, 'scenario_name': scenario.name, 'time': case_hhmm(at_min), 'decision_time_bjt': getattr(scenario, 'decision_time_bjt', ''), 'known_notice_count': int(notice.get('Known_Notice_Count', 0) or 0), 'metro_known_notice_count': int(notice.get('Metro_Known_Notice_Count', 0) or 0), 'city_known_notice_count': int(notice.get('City_Known_Notice_Count', 0) or 0), 'latest_notice_account': notice.get('Latest_Notice_Account', ''), 'latest_notice_time_bjt': notice.get('Latest_Notice_Time_BJT', ''), 'latest_notice_title': notice.get('Latest_Notice_Title', ''), 'active_network_state_label': getattr(scenario_system, 'bebinca_active_state_label', 'normal'), 'origin': self.origin, 'destination': self.dest, 'profile': {'Age': self.age, 'Gender': self.gender, 'Trip_Purpose': self.trip_purpose, 'OCEAN_O': self.ocean_O, 'OCEAN_C': self.ocean_C, 'OCEAN_E': self.ocean_E, 'OCEAN_A': self.ocean_A, 'OCEAN_N': self.ocean_N, 'Risk_Preference': self.risk_preference}, 'notice': notice, 'affected_corridor': bool(self.affected_corridor), 'allowed_actions': allowed, 'metro_available': bool(metro_available), 'baseline_route': self._path_text(baseline), 'current_route': self._path_text(current), 'metro_normal_min': None if not np.isfinite(normal_min) else round(float(normal_min), 2), 'metro_current_min': None if not metro_available or not np.isfinite(current_min) else round(float(current_min), 2), 'metro_normal_text': fmt_min(normal_min), 'metro_current_text': fmt_min(current_min) if metro_available else '不可用', 'impact_summary': impact_summary, 'shuttle': None, 'shuttle_description': '贝碧嘉官方停运公告未向本OD提供可编码的地铁短驳服务；本研究动作不单列短驳。', 'surface': surface, 'od_groups': od_groups or {}, 'operational_proxy': operational_proxy or {}}
    context['personal_transport_profile'] = v5_personal_transport_profile(context)
    context['transport_feasibility'] = []
    context['action_comparison'] = v5_action_comparison(context)
    context['allowed_actions_ordered'] = bebinca_order_allowed_actions(context)
    context['fact_card'] = case_human_fact_card(context)
    self.case_context = context
    return context

def v5_utility_fallback_choice(context):
    allowed = list(context.get('allowed_actions', []))
    profile = context.get('profile', {})
    prefs = context.get('personal_transport_profile') or {}
    notice = context.get('notice', {}) or {}
    urgency = int(prefs.get('Time_Urgency', 3) or 3)
    cost = int(prefs.get('Cost_Sensitivity', 3) or 3)
    ridehail = int(prefs.get('Ridehail_Acceptance', 3) or 3)
    N = int(profile.get('OCEAN_N', 3) or 3)
    C = int(profile.get('OCEAN_C', 3) or 3)
    R = int(profile.get('Risk_Preference', 3) or 3)
    severity = float(notice.get('Severity', 3) or 3)
    clarity = float(notice.get('Clarity', 3) or 3)
    safety = float(notice.get('Safety_Cue', 3) or 3)
    material = f'bebinca_fallback|{context.get('passenger_id')}|{context.get('scenario_key')}|{context.get('origin')}|{context.get('destination')}'
    rng = random.Random(int(hashlib.sha256(material.encode('utf-8')).hexdigest()[:12], 16))
    utilities = {}
    for action in allowed:
        if action == 'abandon_trip':
            utilities[action] = -1.1 + (3 - urgency) * 0.3 + (N - 3) * 0.18 - (C - 3) * 0.1 + (severity - 3) * 0.18 + (safety - 3) * 0.2
        elif action == 'metro_trip':
            t = v5_action_time_min(context, action)
            utilities[action] = 0.15 - (t / 60.0 if np.isfinite(t) else 2.0) + (R - 3) * 0.08 - (severity - 3) * 0.16 - (clarity - 3) * 0.08
        elif action == 'non_metro_trip':
            t = v5_action_time_min(context, action)
            utilities[action] = -0.1 - (t / 70.0 if np.isfinite(t) else 1.8) + (urgency - 3) * 0.2 + (ridehail - 3) * 0.12 - (cost - 3) * 0.12 + (severity - 3) * 0.08
        utilities[action] += rng.uniform(-0.2, 0.2)
    choice = max(utilities, key=utilities.get)
    return (choice, 'bebinca_utility_fallback:' + json.dumps({k: round(float(v), 3) for k, v in utilities.items()}, ensure_ascii=False))

def v5_technical_fallback(self, scenario_system, allowed_actions):
    return v5_utility_fallback_choice(self.case_context)

def v5_decide_case(self, normal_system, scenario_system, scenario, at_min, affected_corridor, use_live_llm, llm_call_log, operational_proxy=None, od_groups=None):
    context = self.build_case_context(normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=operational_proxy, od_groups=od_groups)
    self.llm_selected = True
    self.decision_mode = 'llm'
    self.rule_action_raw = ''
    self.rule_action = ''
    if use_live_llm:
        outcome = case_call_llm(context, llm_call_log)
    else:
        outcome = {'valid': False, 'parsed': {}, 'raw': '', 'error': 'smoke_test_no_live_llm', 'model': '', 'attempted_models': [], 'attempt_count': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'repair_applied': False, 'repair_details': '', 'failure_category': 'smoke_test', 'total_elapsed_sec': 0.0, 'quota_stop': False, 'reason_warnings': '', 'stop_policy': 'no_live_fallback', 'passenger_model_exhausted': False}
    self.llm_valid = bool(outcome['valid'])
    self.llm_fallback_used = not self.llm_valid
    self.llm_raw_response = outcome.get('raw', '')
    self.llm_error_message = outcome.get('error', '')
    self.llm_model = outcome.get('model', '')
    self.llm_attempted_models = ' | '.join(outcome.get('attempted_models', []))
    self.llm_attempt_count = int(outcome.get('attempt_count', 0))
    self.llm_prompt_tokens = int(outcome.get('prompt_tokens', 0))
    self.llm_completion_tokens = int(outcome.get('completion_tokens', 0))
    self.llm_repair_applied = bool(outcome.get('repair_applied', False))
    self.llm_repair_details = str(outcome.get('repair_details', ''))
    self.llm_failure_category = str(outcome.get('failure_category', ''))
    self.llm_total_elapsed_sec = float(outcome.get('total_elapsed_sec', 0.0) or 0.0)
    self.llm_quota_stop = bool(outcome.get('quota_stop', False))
    self.llm_reason_warnings = str(outcome.get('reason_warnings', ''))
    self.llm_stop_policy = str(outcome.get('stop_policy', ''))
    self.llm_passenger_model_exhausted = bool(outcome.get('passenger_model_exhausted', False))
    if self.llm_valid:
        parsed = outcome['parsed']
        self.llm_action = str(parsed['action_choice'])
        self.final_action = self.llm_action
        self.decision_source = 'LLM'
        self.llm_reason = str(parsed.get('reason', ''))
        self.llm_risk_perception = str(parsed.get('risk_perception_level', 'none'))
        self.llm_delay_perception = str(parsed.get('delay_perception_level', 'none'))
        self.llm_feeling_score, self.llm_feeling_score_raw, _ = normalize_llm_feeling_score(parsed.get('feeling_score'))
    else:
        self.final_action, self.rule_action_raw = self.technical_fallback(scenario_system, context['allowed_actions'])
        self.rule_action = self.rule_action_raw
        self.llm_action = ''
        self.decision_source = 'Rule_Fallback'
        self.llm_reason = ''
        self.llm_risk_perception = ''
        self.llm_delay_perception = ''
        self.llm_feeling_score = np.nan
        self.llm_feeling_score_raw = ''
    self.action = self.final_action
    self.status = 'abandoned' if self.final_action == 'abandon_trip' else 'finished'
    self.final_route_plan = self.current_route_plan if self.final_action == 'metro_trip' else self.initial_route_plan
    self.reroute_count = int(self.final_action == 'non_metro_trip')
    return self

def v5_case_record(self):
    record = V5_BASE_CASE_RECORD(self)
    context = getattr(self, 'case_context', {}) or {}
    prefs = context.get('personal_transport_profile', {}) or {}
    notice = context.get('notice', {}) or {}
    record.update({'Affected_Typhoon_State': bool(context.get('affected_corridor', False)), 'Decision_Time_BJT': context.get('decision_time_bjt', ''), 'Known_Notice_Count': int(context.get('known_notice_count', 0) or 0), 'Metro_Known_Notice_Count': int(context.get('metro_known_notice_count', 0) or 0), 'City_Known_Notice_Count': int(context.get('city_known_notice_count', 0) or 0), 'Latest_Notice_Account': context.get('latest_notice_account', ''), 'Latest_Notice_Time_BJT': context.get('latest_notice_time_bjt', ''), 'Latest_Notice_Title': context.get('latest_notice_title', ''), 'Active_Network_State_Label': context.get('active_network_state_label', ''), 'Notice_Key': notice.get('Notice_Key', ''), 'Notice_Label': notice.get('Notice_Label', ''), 'Notice_Publish_Time_BJT': notice.get('Notice_Publish_Time_BJT', ''), 'Notice_Source_URL': notice.get('Notice_Source_URL', ''), 'Notice_Is_Synthetic': bool(notice.get('Notice_Is_Synthetic', False)), 'Notice_Severity': notice.get('Severity', ''), 'Notice_Clarity': notice.get('Clarity', ''), 'Notice_Detail': notice.get('Detail', ''), 'Notice_Actionability': notice.get('Actionability', ''), 'Notice_Safety_Cue': notice.get('Safety_Cue', ''), 'Notice_Uncertainty': notice.get('Uncertainty', ''), 'Notice_Line_Specific': notice.get('Line_Specific', ''), 'Notice_Time_Specific': notice.get('Time_Specific', ''), 'Will_Travel': bool(self.final_action != 'abandon_trip'), 'Travel_Mode_Group': 'not_travel' if self.final_action == 'abandon_trip' else 'metro' if self.final_action == 'metro_trip' else 'non_metro', 'Personal_Time_Urgency': prefs.get('Time_Urgency', ''), 'Personal_Cost_Sensitivity': prefs.get('Cost_Sensitivity', ''), 'Personal_Transfer_Tolerance': prefs.get('Transfer_Tolerance', ''), 'Personal_Ridehail_Acceptance': prefs.get('Ridehail_Acceptance', ''), 'Personal_Private_Car_Available': prefs.get('Private_Car_Available', ''), 'Personal_Cycling_Acceptable': prefs.get('Cycling_Acceptable', ''), 'Personal_Walking_Tolerance': prefs.get('Walking_Tolerance', ''), 'Action_Comparison_Input': json.dumps(context.get('action_comparison', []), ensure_ascii=False), 'LLM_Reason_Warnings': str(getattr(self, 'llm_reason_warnings', '')), 'LLM_Stop_Policy': str(getattr(self, 'llm_stop_policy', '')), 'LLM_Passenger_Model_Exhausted': bool(getattr(self, 'llm_passenger_model_exhausted', False))})
    return record
CasePassengerAgent.build_case_context = bebinca_build_case_context
CasePassengerAgent.technical_fallback = v5_technical_fallback
CasePassengerAgent.decide_case = v5_decide_case
CasePassengerAgent.case_record = v5_case_record

def case_summary_table(passenger_df):
    rows = []
    for scenario in CASE_SCENARIOS:
        scenario_df = passenger_df[passenger_df['Scenario'] == scenario.key]
        group_specs = [('受影响乘客', scenario_df['Affected_Typhoon_State'] == True), ('相对未受影响乘客', scenario_df['Affected_Typhoon_State'] == False), ('全部乘客', pd.Series(True, index=scenario_df.index))]
        for group_name, mask in group_specs:
            all_group = scenario_df.loc[mask].copy()
            valid_group = all_group[all_group['LLM_Valid'] == True].copy()
            for population_name, frame in [('All_Final', all_group), ('Valid_LLM_Only', valid_group)]:
                total = len(frame)
                valid_n = int(all_group['LLM_Valid'].sum()) if len(all_group) else 0
                fallback_n = int(all_group['LLM_Fallback_Used'].sum()) if len(all_group) else 0
                for action in LLM_ALLOWED_ACTIONS:
                    count = int((frame['Action'] == action).sum()) if total else 0
                    rows.append({'Scenario': scenario.key, 'Scenario_Name': scenario.name, 'Scenario_Time': case_hhmm(scenario.start_min), 'Decision_Time_BJT': getattr(scenario, 'decision_time_bjt', ''), 'Notice_Label': scenario.notice.get('Notice_Label', ''), 'Known_Notice_Count': scenario.notice.get('Known_Notice_Count', 0), 'Passenger_Group': group_name, 'Decision_Population': population_name, 'Group_N': total, 'Action': action, 'Action_CN': CASE_ACTION_CN[action], 'Count': count, 'Proportion': count / total if total else np.nan, 'Valid_LLM_N': valid_n, 'Fallback_N': fallback_n, 'Fallback_Rate': fallback_n / len(all_group) if len(all_group) else np.nan})
                will_n = int(frame.get('Will_Travel', pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if total else 0
                rows.append({'Scenario': scenario.key, 'Scenario_Name': scenario.name, 'Scenario_Time': case_hhmm(scenario.start_min), 'Decision_Time_BJT': getattr(scenario, 'decision_time_bjt', ''), 'Notice_Label': scenario.notice.get('Notice_Label', ''), 'Known_Notice_Count': scenario.notice.get('Known_Notice_Count', 0), 'Passenger_Group': group_name, 'Decision_Population': population_name, 'Group_N': total, 'Action': 'will_travel', 'Action_CN': '是否出行', 'Count': will_n, 'Proportion': will_n / total if total else np.nan, 'Valid_LLM_N': valid_n, 'Fallback_N': fallback_n, 'Fallback_Rate': fallback_n / len(all_group) if len(all_group) else np.nan})
    return pd.DataFrame(rows)

def bebinca_travel_probability_summary(passenger_df):
    if passenger_df is None or passenger_df.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in passenger_df.groupby(['Scenario', 'Scenario_Name', 'Notice_Label', 'Decision_Time_BJT', 'Affected_Typhoon_State'], dropna=False):
        scenario, scenario_name, notice_label, decision_time_bjt, affected = keys
        total = len(group)
        row = {'Scenario': scenario, 'Scenario_Name': scenario_name, 'Notice_Label': notice_label, 'Decision_Time_BJT': decision_time_bjt, 'Passenger_Group': 'affected_typhoon' if bool(affected) else 'control', 'N': total, 'Will_Travel_Prob': float(group['Will_Travel'].mean()) if total else np.nan}
        for action in LLM_ALLOWED_ACTIONS:
            row[f'P_{action}'] = float((group['Action'] == action).mean()) if total else np.nan
        rows.append(row)
    for keys, group in passenger_df.groupby(['Scenario', 'Scenario_Name', 'Notice_Label', 'Decision_Time_BJT'], dropna=False):
        scenario, scenario_name, notice_label, decision_time_bjt = keys
        total = len(group)
        row = {'Scenario': scenario, 'Scenario_Name': scenario_name, 'Notice_Label': notice_label, 'Decision_Time_BJT': decision_time_bjt, 'Passenger_Group': 'all', 'N': total, 'Will_Travel_Prob': float(group['Will_Travel'].mean()) if total else np.nan}
        for action in LLM_ALLOWED_ACTIONS:
            row[f'P_{action}'] = float((group['Action'] == action).mean()) if total else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values(['Passenger_Group', 'Scenario']).reset_index(drop=True)

def bebinca_notice_feature_effects_df(passenger_df):
    summary = bebinca_travel_probability_summary(passenger_df)
    if summary.empty:
        return summary
    notice_df = bebinca_notice_treatments_df()
    merged = summary.merge(notice_df, left_on='Scenario', right_on='Notice_Key', how='left')
    base_key = CASE_SCENARIOS[0].key if CASE_SCENARIOS else ''
    base = merged[(merged['Scenario'] == base_key) & (merged['Passenger_Group'] == 'all')]
    base_prob = float(base['Will_Travel_Prob'].iloc[0]) if not base.empty else np.nan
    merged['Delta_Will_Travel_vs_First_Snapshot_All'] = merged['Will_Travel_Prob'] - base_prob if np.isfinite(base_prob) else np.nan
    return merged

def v5_write_partial_excel(path, records, logs, cohort_df, run_id, quota_stop_message='', quota_probe_df=None):
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        record_df = pd.DataFrame(records)
        record_df.to_excel(writer, sheet_name='Passenger_Decisions_Partial', index=False)
        log_df = pd.DataFrame(logs)
        log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        v5_llm_error_summary_df(log_df).to_excel(writer, sheet_name='LLM_Error_Summary', index=False)
        v5_llm_model_status_df().to_excel(writer, sheet_name='LLM_Model_Status', index=False)
        pd.DataFrame(quota_probe_df if quota_probe_df is not None else V6_QUOTA_PROBE_ROWS).to_excel(writer, sheet_name='LLM_Quota_Probe', index=False)
        v5_choice_coverage_diagnostics(record_df).to_excel(writer, sheet_name='Choice_Coverage_Diagnostics', index=False)
        if not record_df.empty:
            bebinca_travel_probability_summary(record_df).to_excel(writer, sheet_name='Travel_Probability_Summary', index=False)
            bebinca_notice_feature_effects_df(record_df).to_excel(writer, sheet_name='Notice_Feature_Effects', index=False)
        bebinca_notice_treatments_df().to_excel(writer, sheet_name='Notice_Treatments', index=False)
        bebinca_official_notice_timeline_df().to_excel(writer, sheet_name='Official_Notice_Timeline', index=False)
        bebinca_metro_notice_timeline_df().to_excel(writer, sheet_name='Metro_Notice_Timeline', index=False)
        bebinca_city_notice_timeline_df().to_excel(writer, sheet_name='City_Notice_Timeline', index=False)
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Completed_Decisions': len(records), 'Expected_Decisions': len(cohort_df) * len(CASE_SCENARIOS), 'Quota_Stop_Message': quota_stop_message, 'Stop_Policy': V6_RUN_STOP_POLICY, 'Saved_At_BJT': v4_beijing_now().strftime('%Y-%m-%d %H:%M:%S BJT')}]).to_excel(writer, sheet_name='Checkpoint_Status', index=False)

def v5_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_df, quota_probe_df=None, output_dir=CASE_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'Bebinca_Typhoon_Notice_LLM_TravelDecision_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx'
    log_df = pd.DataFrame(llm_log_df)
    zero_attempt_fallback = int(((passenger_df.get('LLM_Attempt_Count', pd.Series(dtype=float)).fillna(0).astype(float) == 0) & (passenger_df.get('Decision_Source', pd.Series(dtype=str)) == 'Rule_Fallback')).sum()) if not passenger_df.empty else 0
    passenger_model_exhausted_n = int(passenger_df.get('LLM_Passenger_Model_Exhausted', pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not passenger_df.empty else 0
    audit_system = build_case_system(CASE_SCENARIOS[4], CASE_SCENARIOS[4].start_min) if len(CASE_SCENARIOS) > 4 else build_bebinca_typhoon_system()
    run_summary = pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Scenario_Filter': V6_SCENARIO_FILTER_FOR_RUN, 'Expected_Decisions': V6_EXPECTED_DECISIONS, 'Cohort_N': len(cohort_df), 'Ever_Affected_N': int(cohort_df.get('Ever_Affected_Typhoon_State', pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not cohort_df.empty else 0, 'LLM_Valid_Rate': float(passenger_df['LLM_Valid'].mean()) if not passenger_df.empty else np.nan, 'LLM_Fallback_N': int(passenger_df['LLM_Fallback_Used'].sum()) if not passenger_df.empty else 0, 'LLM_Fallback_Rate': float(passenger_df['LLM_Fallback_Used'].mean()) if not passenger_df.empty else np.nan, 'Zero_Attempt_Fallback_N': zero_attempt_fallback, 'Passenger_Model_Exhausted_N': passenger_model_exhausted_n, 'Decision_Times_BJT': ' | '.join(BEBINCA_DECISION_SNAPSHOT_TIMES_BJT), 'Notice_Source_Mode': BEBINCA_NOTICE_SOURCE_MODE}])
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Decision_Share_Summary', index=False)
        passenger_df.to_excel(writer, sheet_name='Passenger_Decisions', index=False)
        bebinca_travel_probability_summary(passenger_df).to_excel(writer, sheet_name='Travel_Probability_Summary', index=False)
        bebinca_notice_feature_effects_df(passenger_df).to_excel(writer, sheet_name='Notice_Feature_Effects', index=False)
        bebinca_notice_treatments_df().to_excel(writer, sheet_name='Notice_Treatments', index=False)
        bebinca_official_notice_timeline_df().to_excel(writer, sheet_name='Official_Notice_Timeline', index=False)
        bebinca_metro_notice_timeline_df().to_excel(writer, sheet_name='Metro_Notice_Timeline', index=False)
        bebinca_city_notice_timeline_df().to_excel(writer, sheet_name='City_Notice_Timeline', index=False)
        log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        v5_llm_error_summary_df(log_df).to_excel(writer, sheet_name='LLM_Error_Summary', index=False)
        v5_llm_model_status_df().to_excel(writer, sheet_name='LLM_Model_Status', index=False)
        pd.DataFrame(quota_probe_df if quota_probe_df is not None else V6_QUOTA_PROBE_ROWS).to_excel(writer, sheet_name='LLM_Quota_Probe', index=False)
        v5_choice_coverage_diagnostics(passenger_df).to_excel(writer, sheet_name='Choice_Coverage_Diagnostics', index=False)
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        bebinca_closure_edges_df(audit_system).to_excel(writer, sheet_name='Closure_Edges_0916_1000', index=False)
        bebinca_missing_closure_edges_df(audit_system).to_excel(writer, sheet_name='Closure_Missing_Edges', index=False)
        pd.DataFrame(proxy_df).to_excel(writer, sheet_name='Operational_Proxy', index=False)
        run_summary.to_excel(writer, sheet_name='Run_Summary', index=False)
    return output_path

def run_case_study_bebinca(use_live_llm=True, resume=False, run_label=None, quota_probe=False):
    _sr.require_run()
    quota_probe = False
    global V6_RUN_STOP_POLICY, V6_SCENARIO_FILTER_FOR_RUN, V6_EXPECTED_DECISIONS
    v6_reset_model_runtime()
    case_require_inputs()
    cohort_df = sample_case_cohort()
    selected_scenarios = list(CASE_SCENARIOS)
    V6_SCENARIO_FILTER_FOR_RUN = ','.join((scenario.key for scenario in selected_scenarios))
    V6_EXPECTED_DECISIONS = len(cohort_df) * len(selected_scenarios)
    base_run_id = case_run_id(cohort_df)
    run_id = base_run_id if resume else f'{base_run_id}_{run_label or _dt.now().strftime('%Y%m%d_%H%M%S')}'
    checkpoint_paths = case_checkpoint_paths(run_id)
    resumed_records, resumed_logs = case_load_resume(checkpoint_paths['jsonl']) if resume else ({}, [])
    quota_probe_df = v6_probe_model_quotas() if use_live_llm and quota_probe else pd.DataFrame(V6_QUOTA_PROBE_ROWS)
    all_records, llm_call_log = (list(resumed_records.values()), list(resumed_logs))
    proxy_rows = []
    try:
        for scenario in selected_scenarios:
            normal_system = build_bebinca_normal_system(scenario.start_min)
            scenario_system = build_case_system(scenario, scenario.start_min)
            affected_keys = getattr(scenario_system, 'bebinca_affected_edge_key_set', set())
            suspended_keys = getattr(scenario_system, 'bebinca_suspended_edge_key_set', set())
            for _, od in cohort_df.iterrows():
                key = (scenario.key, int(od['PID']))
                if key in resumed_records:
                    continue
                baseline_plan = normal_system.plan_passenger_route(od['Origin'], od['Dest'], BEBINCA_DECISION_MIN, weight_mode='baseline')
                current_plan = scenario_system.plan_passenger_route(od['Origin'], od['Dest'], scenario.start_min, weight_mode='current')
                current_reachable = bool(current_plan.get('reachable')) and np.isfinite(PassengerAgent._duration_value(current_plan.get('current_duration_min', np.nan)))
                hits_suspended = bebinca_plan_hits_suspended_edges(baseline_plan, suspended_keys)
                hits_affected = bebinca_plan_hits_affected_edges(baseline_plan, affected_keys)
                is_affected = bool(hits_affected or not current_reachable)
                if not current_reachable:
                    proxy = {'level': 'unreachable', 'score': 5}
                elif hits_suspended:
                    proxy = {'level': 'suspended_on_baseline', 'score': 4}
                elif hits_affected:
                    proxy = {'level': 'speed_limited_or_adjusted', 'score': 2}
                else:
                    proxy = {'level': 'reachable', 'score': 0}
                proxy_rows.append({'Scenario': scenario.key, 'Decision_Time_BJT': scenario.decision_time_bjt, 'PID': int(od['PID']), **proxy})
                od_groups = {'抽样组': od['OD_Sample_Group'], '台风影响组': 'affected' if is_affected else 'unaffected'}
                log_start = len(llm_call_log)
                passenger = CasePassengerAgent(int(od['PID']), od['Origin'], od['Dest'], scenario.start_min)
                passenger.decide_case(normal_system, scenario_system, scenario, scenario.start_min, is_affected, use_live_llm, llm_call_log, operational_proxy=proxy, od_groups=od_groups)
                record = passenger.case_record()
                record.update({'OD_Sample_Group': od['OD_Sample_Group'], 'OD_Sampling_Source': od['OD_Sampling_Source'], 'Baseline_Hits_Suspended_Edge': bool(hits_suspended), 'Baseline_Hits_Affected_Edge': bool(hits_affected), 'Current_Metro_Reachable_Cohort': bool(current_reachable), 'Run_ID': run_id})
                all_records.append(record)
                resumed_records[key] = record
                case_append_checkpoint(checkpoint_paths['jsonl'], record, llm_call_log[log_start:])
                if len(all_records) % CASE_CHECKPOINT_EVERY_PASSENGERS == 0:
                    v5_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id, quota_probe_df=quota_probe_df)
                    print(f'bebinca checkpoint: {len(all_records)}/{V6_EXPECTED_DECISIONS}', flush=True)
    except (V5AccountQuotaExhausted, _sr.SubmissionStop) as exc:
        V6_RUN_STOP_POLICY = 'all_account_quota_stop_during_decision'
        v5_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id, quota_stop_message=str(exc), quota_probe_df=quota_probe_df)
        raise RuntimeError(f'Bebinca run saved checkpoint and stopped: {exc}') from exc
    passenger_df = pd.DataFrame(all_records).sort_values(['Scenario', 'PID']).reset_index(drop=True)
    if len(passenger_df) != V6_EXPECTED_DECISIONS:
        raise AssertionError(f'Passenger decision records should be {V6_EXPECTED_DECISIONS}; incomplete runs must be resumed before analysis.')
    if set(passenger_df['Action'].dropna().unique()) - set(LLM_ALLOWED_ACTIONS):
        raise AssertionError('Passenger_Decisions 出现三类动作以外的选择。')
    passenger_df['Will_Travel'] = passenger_df['Action'] != 'abandon_trip'
    summary_df = case_summary_table(passenger_df)
    llm_log_df = pd.DataFrame(llm_call_log)
    excel_path = v5_export_workbook(summary_df, passenger_df, llm_log_df, pd.DataFrame(), pd.DataFrame(), cohort_df, run_id, {}, None, proxy_rows, quota_probe_df=quota_probe_df)
    return {'cohort': cohort_df, 'passenger_decisions': passenger_df, 'decision_share_summary': summary_df, 'travel_probability_summary': bebinca_travel_probability_summary(passenger_df), 'notice_feature_effects': bebinca_notice_feature_effects_df(passenger_df), 'llm_call_log': llm_log_df, 'quota_probe': quota_probe_df, 'excel_path': excel_path, 'run_id': run_id, 'checkpoint_paths': checkpoint_paths, 'expected_decisions': V6_EXPECTED_DECISIONS, 'scenario_filter': V6_SCENARIO_FILTER_FOR_RUN, 'llm_model_status': v5_llm_model_status_df()}
