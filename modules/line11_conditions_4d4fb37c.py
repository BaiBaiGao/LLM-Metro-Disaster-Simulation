from dataclasses import dataclass
from datetime import date
from pathlib import Path
import matplotlib.pyplot as plt
CASE_VERSION = 'line11_intrusion_20241222_v2'
CASE_DATE = date(2024, 12, 22)
CASE_DAY_TYPE = 'Weekend'
CASE_OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
CASE_DATA_ROOT = _sr.project_root()
CASE_LOCAL_SCHEDULE = SUBMISSION_SCHEDULE_PATH
CASE_SCHEDULE_PATH = SUBMISSION_SCHEDULE_PATH
CASE_SAMPLE_SIZE = 500
CASE_AFFECTED_COUNT = 300
CASE_SEED = 20260626
CASE_SHUTTLE_SPEED_KMH = 25.0
CASE_SHUTTLE_TRANSFER_MIN = 6.0
CASE_ROAD_DETOUR_FACTOR = 1.25
CASE_OTHER_BUS_SPEED_KMH = 18.0
CASE_OTHER_BUS_WAIT_MIN = 5.0
CASE_TAXI_SPEED_KMH = 30.0
CASE_TAXI_WAIT_MIN = 5.0
PASSENGER_DECISION_MODE = 'llm'
LLM_PASSENGER_RATIO = 1.0
LLM_MAX_PASSENGER_CALLS = CASE_SAMPLE_SIZE
LLM_ALLOWED_ACTIONS = ['continue_metro', 'abandon_trip', 'take_shuttle_bus', 'take_other_surface_bus', 'take_taxi', 'take_other_transport']
CASE_ACTION_CN = {'continue_metro': '继续乘坐地铁', 'abandon_trip': '放弃出行', 'take_shuttle_bus': '乘接驳车', 'take_other_surface_bus': '乘其他地上公交车', 'take_taxi': '打车', 'take_other_transport': '采用其他交通方式'}
CASE_CORRIDOR_SECTIONS = [('马陆', '陈翔公路'), ('陈翔公路', '南翔'), ('南翔', '桃浦新村'), ('桃浦新村', '武威路')]
CASE_SHUTTLE_STATIONS = ['嘉定新城', '马陆', '陈翔公路', '南翔', '桃浦新村', '武威路']
CASE_CHECKPOINT_EVERY_PASSENGERS = 25
CASE_CHECKPOINT_DIR = CASE_OUTPUT_DIR / 'checkpoints'
PERSONALITY_SCORE_GUIDE = {'O': {'label': '开放性 O', 1: ('明显偏好熟悉、已验证的方案', '除非收益非常明确，通常不愿尝试新的短驳或替代方式。'), 2: ('略偏好熟悉方案', '会谨慎评估替代方式，只有时间或便利优势明显时才可能接受。'), 3: ('对熟悉与新方案保持平衡', '是否尝试短驳或替代方式主要取决于时间、可达性和出行目的。'), 4: ('较愿意尝试新的解决方案', '在事实允许时，更可能接受短驳或其他替代方式。'), 5: ('积极愿意尝试新方案', '在不违反可达性和安全边界时，较可能主动接受短驳或替代方式。')}, 'C': {'label': '尽责性 C', 1: ('较随性、计划性较低', '对既定安排的坚持较弱，可能更容易临时改变计划或放弃行程。'), 2: ('略偏随性', '会在便利性与原定安排之间权衡，紧迫性不高时较可能调整计划。'), 3: ('计划性适中', '是否坚持出行主要取决于时间损失、目的紧迫性和替代方式的可用性。'), 4: ('较重视守时和计划', '为完成既定行程，较不愿轻易放弃，可能接受合理的替代方案。'), 5: ('非常重视守时和既定安排', '若出行目的紧迫，通常会积极选择可行替代方式而非轻易放弃。')}, 'E': {'label': '外向性 E', 1: ('偏好独处、不愿主动交流', '较少主动向其他乘客或工作人员询问信息，更依赖已给出的事实。'), 2: ('交流意愿偏低', '通常不会主动寻求额外沟通，但在必要时可接受已有官方信息。'), 3: ('交流意愿适中', '会根据困难程度决定是否关注工作人员或其他乘客提供的既有信息。'), 4: ('较愿意主动交流', '更可能主动询问并接受已经提供的官方指引或替代服务信息。'), 5: ('社交主动性很高', '更愿意与工作人员或其他乘客交流以理解已有官方安排；不能据此虚构新服务。')}, 'A': {'label': '宜人性 A', 1: ('较独立、低从众', '不容易仅因组织安排或他人选择而接受短驳，更看重自身便利和判断。'), 2: ('偏独立', '会参考官方安排，但仍倾向先按自身需求评估。'), 3: ('独立与合作取向平衡', '会同时考虑官方安排、个人时间和便利性。'), 4: ('较愿意合作和配合组织', '在符合个人时间约束时，较可能接受官方短驳安排。'), 5: ('高度合作、愿意配合组织', '在官方短驳可行时，更倾向配合该安排，但不会忽略自身目的和时间成本。')}, 'N': {'label': '神经质 N', 1: ('情绪稳定，能承受不确定性', '面对延误、拥挤或换乘时较平稳，更可能按事实权衡而非因焦虑退出。'), 2: ('情绪较稳定', '会感到不便，但通常能容忍有限延误和不确定性。'), 3: ('对不确定性的敏感度适中', '是否改变方式主要由延误程度、可达性和出行目的决定。'), 4: ('较容易因不确定性焦虑', '面对中断、拥挤或复杂换乘时，更可能偏向可控方式，如出租车或放弃。'), 5: ('对不确定性高度敏感', '面对硬中断或复杂换乘时，明显更偏好可控方式，或在条件很差时取消出行。')}, 'Risk_Preference': {'label': '风险偏好', 1: ('高度风险规避', '更在意拥挤、延误和不确定性，偏好可预测、可控的可行方案。'), 2: ('偏风险规避', '会回避明显拥挤、延误或不确定性，除非替代代价更高。'), 3: ('风险偏好中性', '会在时间、便利、安全感和不确定性之间平衡。'), 4: ('较能容忍风险和不确定性', '在地铁确实可达时，较能接受一定拥挤、延误或不确定性。'), 5: ('风险寻求且容忍度高', '在不违反安全和可达性边界时，较能容忍拥挤、延误和不确定性。')}}

def personality_score_interpretation(dimension, score):
    key = str(dimension)
    if key not in PERSONALITY_SCORE_GUIDE:
        raise KeyError(f'未知人格维度：{dimension}')
    score = int(score)
    if score not in {1, 2, 3, 4, 5}:
        raise ValueError(f'人格分值必须在1至5之间：{score}')
    guide = PERSONALITY_SCORE_GUIDE[key]
    tendency, decision_impact = guide[score]
    return {'指标': guide['label'], '分值': f'{score}/5', '自然语言倾向': tendency, '可能的决策影响': decision_impact}

def personality_guidance_text():
    lines = []
    for dimension in ('O', 'C', 'E', 'A', 'N', 'Risk_Preference'):
        guide = PERSONALITY_SCORE_GUIDE[dimension]
        levels = '；'.join((f'{score}分：{guide[score][0]}（{guide[score][1]}）' for score in range(1, 6)))
        lines.append(f'{guide['label']}：{levels}')
    return '\n'.join(lines)
CASE_ACTION_MEANINGS = {'continue_metro': '仅在当前地铁路线可达时，继续使用当前可达的地铁路径。', 'abandon_trip': '取消本次前往目的地的出行；不包括改乘其他交通方式。', 'take_shuttle_bus': '乘坐官方嘉定新城↔武威路站外短驳，并按事实卡说明衔接后续地铁。', 'take_other_surface_bus': '放弃地铁及官方短驳，改乘常规地面公交。', 'take_taxi': '放弃地铁及公交，改乘出租车或网约车。', 'take_other_transport': '改用自驾、骑行或步行等其他方式，并在理由中说明个人选择。'}

def case_system_prompt():
    return '你现在不是系统分析器，而是一名真实的上海地铁乘客。请站在乘客本人的第一人称视角做决定：可以犹豫、烦躁、怕麻烦、赶时间、担心安全，也可以放松、不在乎或临时改变主意。必须让年龄、性别、出行目的、人格画像和风险偏好真正影响动作选择与措辞；不能为了制造差异而违反事实或可达性约束。你会收到一张由导航和代码计算的事实卡，所有路线、时间、事故状态和可行动作均以它为准。不得编造新路线、新车站、新区间、新事故、新票价、新等候时间或个人条件。\n\n人格与风险偏好是概率性行为倾向，不是机械决策规则。多个维度、出行目的、时间成本与事实卡共同决定选择；高风险偏好绝不能选择不可达地铁，高外向性只表示更愿主动询问或接受已提供的官方信息，不能凭空获得路线或服务。\n五级人格与风险解释：\n' + personality_guidance_text() + '\n\n六类动作的含义必须严格区分：continue_metro 仅表示当前地铁路径确实可达时继续乘地铁；abandon_trip 仅表示取消这次去目的地的出行，不能借此表示改坐其他方式；take_shuttle_bus 是官方嘉定新城↔武威路站外短驳；take_other_surface_bus 是非短驳的常规地面公交；take_taxi 是出租车或网约车；take_other_transport 是自驾、骑行或步行等。如果事实卡说明当前地铁不可达，不能选择 continue_metro，也不能把硬中断说成只是可接受的延误。只能从事实卡中的 allowed_actions 选择 action_choice。\n\nreason 必须是50到120字中文、包含“我”的第一人称当下想法；语气应符合该乘客画像和压力，不能像系统报告、心理评估或规则复述。reason 必须体现行为倾向，但不得直接写 OCEAN、开放性、尽责性、外向性、宜人性、神经质、风险偏好、人格分数、代码字段名、动作代码、JSON、后台变量或虚构事实。risk_perception_level 和 delay_perception_level 只能是 none、low、medium、high、critical。feeling_score 只能是1、2、3、4、5中的整数。只返回严格JSON，不要Markdown、代码块、置信度或任何额外字段。JSON必须且只能包含：action_choice, reason, risk_perception_level, delay_perception_level, feeling_score。'

def case_human_fact_card(context):
    current_route = context.get('current_route', '')
    metro_available = bool(context.get('metro_available'))
    profile = context['profile']
    personality = [personality_score_interpretation('O', profile['OCEAN_O']), personality_score_interpretation('C', profile['OCEAN_C']), personality_score_interpretation('E', profile['OCEAN_E']), personality_score_interpretation('A', profile['OCEAN_A']), personality_score_interpretation('N', profile['OCEAN_N']), personality_score_interpretation('Risk_Preference', profile['Risk_Preference'])]
    return {'乘客画像': {'年龄': profile['Age'], '性别': profile['Gender'], '出行目的': profile['Trip_Purpose']}, '人格与风险偏好解释': personality, '本次出行': {'起点': context['origin'], '终点': context['destination'], '决策时刻': context['time'], '处置工况': context['scenario_name']}, '地铁事实': {'是否经过受影响走廊': '是' if context['affected_corridor'] else '否', '正常路线': context.get('baseline_route') or '无可达正常路线', '正常预计时间': context.get('metro_normal_text'), '当前地铁可达性': '当前地铁仍可达' if metro_available else '当前地铁不可达，不能选择继续乘坐地铁', '当前可达路线': current_route if metro_available else '无', '当前地铁预计时间': context.get('metro_current_text'), '影响说明': context.get('impact_summary')}, '官方短驳': context.get('shuttle_description'), '其他方式时间': {'常规地面公交': f'约{context['surface']['Other_Surface_Bus_Min']:.1f}分钟', '出租车或网约车': f'约{context['surface']['Taxi_Min']:.1f}分钟', '道路距离': f'约{context['surface']['Road_Distance_KM']:.1f}公里', '步行': f'约{context['surface']['walking_min']:.1f}分钟', '骑行': f'约{context['surface']['cycling_min']:.1f}分钟', '私家车': f'约{context['surface']['private_car_min']:.1f}分钟'}, 'allowed_actions': [{'action_choice': action, '含义': CASE_ACTION_MEANINGS[action]} for action in context['allowed_actions']]}

def case_llm_prompt(context):
    """Build the Chinese user fact card; behavioral instructions remain in the system prompt."""
    return json.dumps(context['fact_card'], ensure_ascii=False, separators=(',', ':'))

def case_json_safe(value):
    return runtime_json_safe(value)

def case_run_id(cohort_df):
    material = cohort_df[['PID', 'Origin', 'Dest', 'Affected_Corridor']].to_csv(index=False)
    return f'{CASE_VERSION}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:12]}'

def case_checkpoint_paths(run_id):
    CASE_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return {'jsonl': CASE_CHECKPOINT_DIR / f'{run_id}.jsonl', 'excel': CASE_CHECKPOINT_DIR / f'{run_id}_partial.xlsx'}

def case_load_resume(path):
    _sr.validate_checkpoint(path, conditions=CASE_SCENARIOS)
    records, logs = ({}, [])
    if not path.exists():
        return (records, logs)
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            try:
                payload = json.loads(line)
                record = payload['record']
                records[record['Scenario'], int(record['PID'])] = record
                logs.extend(payload.get('llm_logs', []))
            except _sr.SubmissionStop:
                raise
            except Exception:
                raise
    return (records, logs)

def case_append_checkpoint(path, record, attempt_logs):
    payload = {'record': case_json_safe(record), 'llm_logs': case_json_safe(attempt_logs)}
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')

def case_write_partial_excel(path, records, logs, cohort_df, run_id):
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        pd.DataFrame(records).to_excel(writer, sheet_name='Passenger_Decisions_Partial', index=False)
        pd.DataFrame(logs).to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        pd.DataFrame([{'Run_ID': run_id, 'Completed_Decisions': len(records)}]).to_excel(writer, sheet_name='Checkpoint_Status', index=False)

@dataclass(frozen=True)
class IncidentScenario:
    key: str
    name: str
    start_min: int
    end_min: int
    line_state: str
    north_service: str
    shuttle_active: bool
CASE_SCENARIOS = [IncidentScenario('condition_1', '工况1：限速、间隔延长、短驳', 8 * 60 + 31, 9 * 60 + 17, 'slowed', 'normal', True), IncidentScenario('condition_2', '工况2：北段停运、短驳', 9 * 60 + 17, 11 * 60 + 19, 'broken', 'stopped', True), IncidentScenario('condition_3', '工况3：三组小交路、短驳', 11 * 60 + 19, 22 * 60 + 50, 'broken', 'short_turn', True), IncidentScenario('normal_recovered', '22:50后：正常恢复', 22 * 60 + 50, 24 * 60, 'normal', 'normal', False)]
CASE_SCENARIO_BY_KEY = {scenario.key: scenario for scenario in CASE_SCENARIOS}

def case_hhmm(minute_of_day):
    minute_of_day = int(minute_of_day) % 1440
    return f'{minute_of_day // 60:02d}:{minute_of_day % 60:02d}'

def case_active_scenario(minute_of_day):
    minute_of_day = int(minute_of_day)
    for scenario in CASE_SCENARIOS:
        if scenario.start_min <= minute_of_day < scenario.end_min:
            return scenario
    return CASE_SCENARIO_BY_KEY['normal_recovered']

def case_require_inputs():
    required = [CASE_DATA_ROOT / 'subway.json', CASE_DATA_ROOT / '进站客流.xlsx', CASE_SCHEDULE_PATH]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError('案例输入文件缺失：' + ' | '.join(missing))

def case_normalize_line_id(value):
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float) and float(value).is_integer():
        return str(int(value))
    return str(value).strip()

def case_minutes(value):
    parsed = pd.to_datetime(str(value), errors='coerce')
    if pd.isna(parsed):
        if hasattr(value, 'hour'):
            return int(value.hour) * 60 + int(value.minute)
        return 0
    return int(parsed.hour) * 60 + int(parsed.minute)

def case_load_schedule_rules():
    """Read the local schedule without modifying its source file."""
    df = pd.read_excel(CASE_SCHEDULE_PATH)
    rules = []
    for _, row in df.iterrows():
        line_id = case_normalize_line_id(row.get('LineID', ''))
        if not line_id:
            continue
        rules.append({'line_id': line_id, 'day_type': str(row.get('DayType', '')).strip(), 'start_min': case_minutes(row.get('Start_Time')), 'end_min': case_minutes(row.get('End_Time')), 'from_st': clean_station_name(row.get('From_Station', '')), 'to_st': clean_station_name(row.get('To_Station', '')), 'interval': float(row.get('Interval_Sec', 0.0)), 'source': 'line_schedule_detailed.xlsx', 'is_default_service': False, 'default_service_key': ''})
    return rules

def case_add_rule(system, line_id, from_st, to_st, start_min, end_min, interval_sec, source):
    system._append_schedule_rule({'line_id': str(line_id), 'day_type': CASE_DAY_TYPE, 'start_min': int(start_min), 'end_min': int(end_min), 'from_st': clean_station_name(from_st), 'to_st': clean_station_name(to_st), 'interval': float(interval_sec), 'source': source, 'is_default_service': False, 'default_service_key': ''})

def case_rule_crosses_corridor(system, rule):
    if str(rule.get('line_id')) != '11':
        return False
    return any((system._rule_covers_service(rule, '11', from_st, to_st) for from_st, to_st in CASE_CORRIDOR_SECTIONS))

def case_install_schedule(system, scenario):
    """Override Line 11 services for the selected condition; retain other lines' schedules."""
    base_rules = case_load_schedule_rules()
    system.schedule_rules = []
    system.schedule_lookup = {}
    for rule in base_rules:
        if str(rule['line_id']) != '11':
            system._append_schedule_rule(dict(rule))
            continue
        if scenario.key == 'normal_recovered':
            system._append_schedule_rule(dict(rule))
        elif scenario.key == 'condition_1':
            adjusted = dict(rule)
            if adjusted['day_type'] == CASE_DAY_TYPE and case_rule_crosses_corridor(system, adjusted):
                adjusted['interval'] = float(adjusted['interval']) * 2.0
                adjusted['source'] = 'condition_1_headway_x2'
            system._append_schedule_rule(adjusted)
    if scenario.key == 'condition_2':
        case_add_rule(system, '11', '武威路', '迪士尼', 0, 20 * 60, 300, 'condition_2_wuwei_disney')
        case_add_rule(system, '11', '武威路', '迪士尼', 20 * 60, 24 * 60, 720, 'condition_2_wuwei_disney')
    elif scenario.key == 'condition_3':
        for from_st, to_st, headway in [('嘉定北', '马陆', 600), ('花桥', '马陆', 600), ('武威路', '迪士尼', 300)]:
            case_add_rule(system, '11', from_st, to_st, 0, 20 * 60, headway, 'condition_3_short_turn')
        for from_st, to_st in [('嘉定北', '马陆'), ('花桥', '马陆'), ('武威路', '迪士尼')]:
            case_add_rule(system, '11', from_st, to_st, 20 * 60, 24 * 60, 720, 'condition_3_short_turn')
    system._route_graph_cache = {}

def case_corridor_edge_indices(system):
    indices = []
    for from_st, to_st in CASE_CORRIDOR_SECTIONS:
        key = ('intra_layer', '11', *sorted((clean_station_name(from_st), clean_station_name(to_st))))
        indices.extend(system.edge_indices_for_key(key))
    return sorted(set(indices))

def case_apply_line_state(system, scenario):
    system.reset_rule_state()
    for edge_idx in case_corridor_edge_indices(system):
        if scenario.line_state == 'slowed':
            system.apply_edge_decision(edge_idx, 0.5, 0.5, 'slowed', scenario.key)
        elif scenario.line_state == 'broken':
            system.apply_edge_decision(edge_idx, 1.0, 0.0, 'suspended', scenario.key)

def build_case_system(scenario, at_min):
    """Build the multilayer network for a selected operational condition."""
    case_require_inputs()
    global DEFAULT_SERVICE_RULES
    DEFAULT_SERVICE_RULES = []
    system = SubwayRuleSystem(CASE_DATA_ROOT, sim_start_time=case_hhmm(at_min))
    case_install_schedule(system, scenario)
    case_apply_line_state(system, scenario)
    return system

def case_station_pos(system, station):
    node = f'{clean_station_name(station)}_车站层'
    pos = system.G.nodes[node].get('pos')
    if not pos:
        raise KeyError(f'未找到车站坐标：{station}')
    return (float(pos[0]), float(pos[1]))

def case_haversine_km(pos_a, pos_b):
    lat1, lon1 = pos_a
    lat2, lon2 = pos_b
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def case_shuttle_info(system, at_min):
    station_positions = [case_station_pos(system, station) for station in CASE_SHUTTLE_STATIONS]
    distance_km = sum((case_haversine_km(a, b) for a, b in zip(station_positions[:-1], station_positions[1:])))
    in_vehicle_min = distance_km / CASE_SHUTTLE_SPEED_KMH * 60.0
    headway_min = 5.0 if int(at_min) < 20 * 60 else 12.0
    expected_wait_min = headway_min / 2.0
    total_min = in_vehicle_min + expected_wait_min + CASE_SHUTTLE_TRANSFER_MIN
    return {'Shuttle_From': '嘉定新城', 'Shuttle_To': '武威路', 'Distance_KM': float(distance_km), 'In_Vehicle_Min': float(in_vehicle_min), 'Headway_Min': float(headway_min), 'Expected_Wait_Min': float(expected_wait_min), 'Transfer_Min': float(CASE_SHUTTLE_TRANSFER_MIN), 'Generalized_Min': float(total_min)}

def case_surface_options(system, origin, destination):
    road_km = case_haversine_km(case_station_pos(system, origin), case_station_pos(system, destination)) * CASE_ROAD_DETOUR_FACTOR
    other_bus_min = road_km / CASE_OTHER_BUS_SPEED_KMH * 60.0 + CASE_OTHER_BUS_WAIT_MIN
    taxi_min = road_km / CASE_TAXI_SPEED_KMH * 60.0 + CASE_TAXI_WAIT_MIN
    other_modes = {'walking_min': road_km / 5.0 * 60.0, 'cycling_min': road_km / 15.0 * 60.0, 'private_car_min': road_km / 25.0 * 60.0}
    return {'Road_Distance_KM': float(road_km), 'Other_Surface_Bus_Min': float(other_bus_min), 'Taxi_Min': float(taxi_min), **{key: float(value) for key, value in other_modes.items()}}

def case_plan_uses_line_11(plan):
    return any((str(record.get('line_id', '')) == '11' for record in plan.get('edge_records', [])))

def case_plan_hits_corridor(plan):
    corridor_pairs = {tuple(sorted(pair)) for pair in CASE_CORRIDOR_SECTIONS}
    for record in plan.get('edge_records', []):
        if record.get('type') != 'riding' or str(record.get('line_id', '')) != '11':
            continue
        pair = tuple(sorted((record.get('from_station', ''), record.get('to_station', ''))))
        if pair in corridor_pairs:
            return True
    return False

def sample_case_cohort():
    """Construct the 300/200 quota cohort using the existing sampling rules, allowing repeated OD pairs."""
    normal = build_case_system(CASE_SCENARIO_BY_KEY['normal_recovered'], 8 * 60 + 31)
    valid_stations = sorted(set(normal.station_names()))
    flow_df = load_flow_data(CASE_DATA_ROOT)
    flow_batch = choose_nearest_flow_batch(flow_df, '08:31', valid_stations)
    sampling_source = '2025-08-08客流代理：最近08:31批次' if flow_batch is not None and (not flow_batch.empty) else '网络站点均匀抽样（客流文件不可用）'
    rng = np.random.default_rng(CASE_SEED)
    sample_od = _make_weighted_od_sampler(normal, flow_df, '08:31', valid_stations, rng)
    affected, unaffected = ([], [])
    attempts, max_attempts = (0, 250000)
    while len(affected) < CASE_AFFECTED_COUNT or len(unaffected) < CASE_SAMPLE_SIZE - CASE_AFFECTED_COUNT:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError('无法在最大重抽样次数内构造满足11号线与受影响区段约束的OD样本。')
        origin, destination = sample_od()
        plan = normal.plan_passenger_route(origin, destination, 0, weight_mode='baseline')
        if not plan.get('reachable') or not case_plan_uses_line_11(plan):
            continue
        is_affected = case_plan_hits_corridor(plan)
        bucket = affected if is_affected else unaffected
        limit = CASE_AFFECTED_COUNT if is_affected else CASE_SAMPLE_SIZE - CASE_AFFECTED_COUNT
        if len(bucket) >= limit:
            continue
        bucket.append({'Origin': str(origin), 'Dest': str(destination), 'Affected_Corridor': bool(is_affected), 'OD_Sample_Group': 'affected_corridor' if is_affected else 'unaffected_line11_control', 'OD_Sampling_Source': sampling_source, 'Baseline_Route': ' -> '.join(plan.get('station_path', []))})
    cohort_records = affected + unaffected
    rng.shuffle(cohort_records)
    for pid, record in enumerate(cohort_records, start=1):
        record['PID'] = pid
    cohort = pd.DataFrame(cohort_records)
    if len(cohort) != CASE_SAMPLE_SIZE or int(cohort['Affected_Corridor'].sum()) != CASE_AFFECTED_COUNT:
        raise AssertionError('OD样本数量或受影响比例校验失败。')
    return cohort

def case_validate_llm_decision(parsed, context):
    if not isinstance(parsed, dict):
        return (False, 'LLM输出不是JSON对象。')
    required = {'action_choice', 'reason', 'risk_perception_level', 'delay_perception_level', 'feeling_score'}
    missing = required - set(parsed)
    extra = set(parsed) - required
    if missing:
        return (False, 'LLM JSON缺失字段：' + ','.join(sorted(missing)))
    if extra:
        return (False, 'LLM JSON包含禁止额外字段：' + ','.join(sorted(map(str, extra))))
    prohibited_fields = [key for key in parsed if 'route' in str(key).lower() or 'station' in str(key).lower()]
    if prohibited_fields:
        return (False, 'LLM JSON包含禁止路线/车站字段。')
    action = str(parsed.get('action_choice', ''))
    allowed = set(context.get('allowed_actions', []))
    if action not in allowed:
        return (False, 'action_choice不在当前可行动作集合中。')
    if action == 'continue_metro' and (not bool(context.get('metro_available'))):
        return (False, '当前地铁不可达时不能选择continue_metro。')
    if action == 'take_shuttle_bus' and (not bool(context.get('shuttle_available'))):
        return (False, '当前没有可用短驳时不能选择take_shuttle_bus。')
    reason = str(parsed.get('reason', '')).strip()
    if len(reason) < 50 or len(reason) > 120 or '我' not in reason:
        return (False, 'reason必须是含“我”的50到120字第一人称中文表达。')
    prohibited_terms = ['action_choice', 'allowed_actions', 'OCEAN', 'Risk_Preference', 'LLM_', 'JSON', '代码', '字段', '人格分数', '开放性', '尽责性', '外向性', '宜人性', '神经质', '风险偏好', 'continue_metro', 'abandon_trip', 'take_shuttle_bus', 'take_other_surface_bus', 'take_taxi', 'take_other_transport']
    lower_reason = reason.lower()
    for term in prohibited_terms:
        if term.lower() in lower_reason:
            return (False, f'reason出现禁止后台术语：{term}')
    if str(parsed.get('risk_perception_level', '')) not in LLM_PERCEPTION_LEVELS:
        return (False, 'risk_perception_level不是标准枚举。')
    if str(parsed.get('delay_perception_level', '')) not in LLM_PERCEPTION_LEVELS:
        return (False, 'delay_perception_level不是标准枚举。')
    _, _, feeling_error = normalize_llm_feeling_score(parsed.get('feeling_score'))
    if feeling_error:
        return (False, feeling_error)
    return (True, '')

def case_parse_json_response(raw_response):
    text = str(raw_response or '').strip()
    if text.startswith('```'):
        text = re.sub('^```(?:json)?\\\\s*|\\\\s*```$', '', text, flags=re.IGNORECASE)
    return json.loads(text)

def case_llm_prompt(context):
    action_lines = '\n'.join((f'- {action}: {CASE_ACTION_CN[action]}' for action in context['allowed_actions']))
    profile = context['profile']
    return f'你是一名上海地铁乘客。请基于自己的画像、当前事故处置和可选方式作出一次真实的出行选择。只能选择允许的动作，不要虚构路线、站名、票价或不存在的服务。\n\n乘客画像：年龄{profile['Age']}，性别{profile['Gender']}，出行目的{profile['Trip_Purpose']}，开放性{profile['OCEAN_O']}/5，尽责性{profile['OCEAN_C']}/5，外向性{profile['OCEAN_E']}/5，宜人性{profile['OCEAN_A']}/5，神经质{profile['OCEAN_N']}/5，风险偏好{profile['Risk_Preference']}/5。\n工况：{context['scenario_name']}，决策时刻{context['time']}。\n正常地铁预计时间：{context['metro_normal_min']}分钟；当前继续乘地铁：{context['metro_current_min']}。\n短驳信息：{context['shuttle_description']}。\n其他地面公交约{context['surface']['Other_Surface_Bus_Min']:.1f}分钟；出租车约{context['surface']['Taxi_Min']:.1f}分钟；道路距离约{context['surface']['Road_Distance_KM']:.1f}km。\n其他交通方式的预计时间：步行{context['surface']['walking_min']:.1f}分钟、骑行{context['surface']['cycling_min']:.1f}分钟、私家车{context['surface']['private_car_min']:.1f}分钟；请结合个人条件判断可用性。\n\n允许动作：\n' + action_lines + '\n\n只返回JSON对象，字段必须为：action_choice、reason、risk_perception_level、delay_perception_level、feeling_score。reason使用中文且不超过120字；risk_perception_level和delay_perception_level只能为none、low、medium、high、critical；feeling_score为1至5整数。'

def case_call_llm(context, llm_call_log):
    return _sr.case_call(globals(), context, llm_call_log)

class CasePassengerAgent(PassengerAgent):
    """Reuse passenger profiles with the six-choice transport action space."""

    def build_case_context(self, normal_system, scenario_system, scenario, at_min, affected_corridor):
        baseline = normal_system.plan_passenger_route(self.origin, self.dest, 0, weight_mode='baseline')
        current = scenario_system.plan_passenger_route(self.origin, self.dest, 0, weight_mode='current')
        self.initial_route_plan = baseline
        self.current_route_plan = current
        self.affected_corridor = bool(affected_corridor)
        metro_available = bool(current.get('reachable')) and np.isfinite(self._duration_value(current.get('current_duration_min', np.nan)))
        shuttle_available = bool(self.affected_corridor and scenario.shuttle_active)
        allowed = []
        if metro_available:
            allowed.append('continue_metro')
        allowed.append('abandon_trip')
        if shuttle_available:
            allowed.append('take_shuttle_bus')
        allowed.extend(['take_other_surface_bus', 'take_taxi', 'take_other_transport'])
        shuttle = case_shuttle_info(scenario_system, at_min) if scenario.shuttle_active else None
        surface = case_surface_options(normal_system, self.origin, self.dest)
        normal_min = self._duration_value(baseline.get('normal_duration_min', np.nan))
        current_min = self._duration_value(current.get('current_duration_min', np.nan))

        def fmt_min(value):
            return f'{value:.1f}分钟' if np.isfinite(value) else '不可用'
        shuttle_description = '当前工况无官方短驳服务。'
        if shuttle is not None:
            shuttle_description = f'嘉定新城↔武威路，物理距离{shuttle['Distance_KM']:.3f}km，车内{shuttle['In_Vehicle_Min']:.1f}分钟，班距{shuttle['Headway_Min']:.0f}分钟、期望候车{shuttle['Expected_Wait_Min']:.1f}分钟、站外换乘{shuttle['Transfer_Min']:.1f}分钟，广义时间{shuttle['Generalized_Min']:.1f}分钟。'
        impact_summary = current.get('impact_summary', '') if metro_available else '受本工况影响，当前地铁网络没有可达路径。'
        self.case_context = {'passenger_id': int(self.pid), 'scenario_key': scenario.key, 'scenario_name': scenario.name, 'time': case_hhmm(at_min), 'origin': self.origin, 'destination': self.dest, 'profile': {'Age': self.age, 'Gender': self.gender, 'Trip_Purpose': self.trip_purpose, 'OCEAN_O': self.ocean_O, 'OCEAN_C': self.ocean_C, 'OCEAN_E': self.ocean_E, 'OCEAN_A': self.ocean_A, 'OCEAN_N': self.ocean_N, 'Risk_Preference': self.risk_preference}, 'affected_corridor': bool(self.affected_corridor), 'allowed_actions': allowed, 'metro_available': metro_available, 'shuttle_available': shuttle_available, 'baseline_route': self._path_text(baseline), 'current_route': self._path_text(current), 'metro_normal_min': None if not np.isfinite(normal_min) else round(float(normal_min), 2), 'metro_current_min': None if not metro_available or not np.isfinite(current_min) else round(float(current_min), 2), 'metro_normal_text': fmt_min(normal_min), 'metro_current_text': fmt_min(current_min) if metro_available else '不可用', 'impact_summary': impact_summary, 'shuttle': shuttle, 'shuttle_description': shuttle_description, 'surface': surface}
        self.case_context['fact_card'] = case_human_fact_card(self.case_context)
        return self.case_context

    def technical_fallback(self, scenario_system, allowed_actions):
        """Construct a rule-based response."""
        import copy
        baseline_snapshot = copy.deepcopy(self.initial_route_plan)
        current_snapshot = copy.deepcopy(self.current_route_plan)
        final_snapshot = copy.deepcopy(self.final_route_plan)
        action_snapshot, status_snapshot, reroute_snapshot = (self.action, self.status, self.reroute_count)
        try:
            self._run_original_rule_decision(scenario_system, 0)
            legacy_action = str(self.action)
        finally:
            self.initial_route_plan = baseline_snapshot
            self.current_route_plan = current_snapshot
            self.final_route_plan = final_snapshot
            self.action, self.status, self.reroute_count = (action_snapshot, status_snapshot, reroute_snapshot)
        if legacy_action.startswith('continue') and 'continue_metro' in allowed_actions:
            choice = 'continue_metro'
        elif legacy_action == 'reroute_to_shortest_time':
            choice = 'take_shuttle_bus' if 'take_shuttle_bus' in allowed_actions else 'take_other_surface_bus'
        elif legacy_action.startswith('abandon'):
            choice = 'abandon_trip'
        elif 'continue_metro' in allowed_actions:
            choice = 'continue_metro'
        elif 'take_shuttle_bus' in allowed_actions:
            choice = 'take_shuttle_bus'
        else:
            choice = 'take_other_surface_bus'
        return (choice, legacy_action)

    def decide_case(self, normal_system, scenario_system, scenario, at_min, affected_corridor, use_live_llm, llm_call_log):
        context = self.build_case_context(normal_system, scenario_system, scenario, at_min, affected_corridor)
        self.llm_selected = True
        self.decision_mode = 'llm'
        self.rule_action_raw = ''
        self.rule_action = ''
        if use_live_llm:
            outcome = case_call_llm(context, llm_call_log)
        else:
            outcome = {'valid': False, 'parsed': {}, 'raw': '', 'error': 'smoke_test_no_live_llm', 'model': '', 'attempted_models': [], 'attempt_count': 0, 'prompt_tokens': 0, 'completion_tokens': 0}
        self.llm_valid = bool(outcome['valid'])
        self.llm_fallback_used = not self.llm_valid
        self.llm_raw_response = outcome.get('raw', '')
        self.llm_error_message = outcome.get('error', '')
        self.llm_model = outcome.get('model', '')
        self.llm_attempted_models = ' | '.join(outcome.get('attempted_models', []))
        self.llm_attempt_count = int(outcome.get('attempt_count', 0))
        self.llm_prompt_tokens = int(outcome.get('prompt_tokens', 0))
        self.llm_completion_tokens = int(outcome.get('completion_tokens', 0))
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
        self.final_route_plan = self.current_route_plan if self.final_action == 'continue_metro' else self.initial_route_plan
        self.reroute_count = int(self.final_action in {'take_shuttle_bus', 'take_other_surface_bus', 'take_taxi', 'take_other_transport'})
        return self

    def case_record(self):
        context = self.case_context
        shuttle = context.get('shuttle') or {}
        surface = context['surface']
        return {'PID': self.pid, 'Scenario': context['scenario_key'], 'Scenario_Name': context['scenario_name'], 'Scenario_Time': context['time'], 'Origin': self.origin, 'Dest': self.dest, 'Affected_Corridor_60pct': bool(self.affected_corridor), 'Allowed_Actions': ' | '.join(context['allowed_actions']), 'Passenger_Fact_Card': json.dumps(context['fact_card'], ensure_ascii=False), 'Status': self.status, 'Action': self.final_action, 'Action_CN': CASE_ACTION_CN[self.final_action], 'Decision_Source': self.decision_source, 'Initial_Route': self._path_text(self.initial_route_plan), 'Current_Route': self._path_text(self.current_route_plan), 'Initial_Normal_Min': context['metro_normal_min'], 'Current_Metro_Min': context['metro_current_min'], 'Shuttle_Distance_KM': shuttle.get('Distance_KM', np.nan), 'Shuttle_In_Vehicle_Min': shuttle.get('In_Vehicle_Min', np.nan), 'Shuttle_Headway_Min': shuttle.get('Headway_Min', np.nan), 'Shuttle_Expected_Wait_Min': shuttle.get('Expected_Wait_Min', np.nan), 'Shuttle_Transfer_Min': shuttle.get('Transfer_Min', np.nan), 'Shuttle_Generalized_Min': shuttle.get('Generalized_Min', np.nan), **surface, 'Age': self.age, 'Gender': self.gender, 'Trip_Purpose': self.trip_purpose, 'OCEAN_O': self.ocean_O, 'OCEAN_C': self.ocean_C, 'OCEAN_E': self.ocean_E, 'OCEAN_A': self.ocean_A, 'OCEAN_N': self.ocean_N, 'Risk_Preference': self.risk_preference, 'LLM_Selected': True, 'LLM_Valid': self.llm_valid, 'LLM_Fallback_Used': self.llm_fallback_used, 'LLM_Action': self.llm_action, 'LLM_Reason': self.llm_reason, 'LLM_Risk_Perception': self.llm_risk_perception, 'LLM_Delay_Perception': self.llm_delay_perception, 'LLM_Feeling_Score': self.llm_feeling_score, 'LLM_Error_Message': self.llm_error_message, 'LLM_Model': self.llm_model, 'LLM_Attempted_Models': self.llm_attempted_models, 'LLM_Attempt_Count': self.llm_attempt_count, 'LLM_Prompt_Tokens': self.llm_prompt_tokens, 'LLM_Completion_Tokens': self.llm_completion_tokens, 'Rule_Action_Raw_On_Fallback': self.rule_action_raw}

def case_summary_table(passenger_df):
    rows = []
    group_specs = [('受影响区段乘客（60%）', passenger_df['Affected_Corridor_60pct'] == True), ('全部11号线乘客（100%）', pd.Series(True, index=passenger_df.index))]
    for scenario in CASE_SCENARIOS[:3]:
        scenario_df = passenger_df[passenger_df['Scenario'] == scenario.key]
        for group_name, mask in group_specs:
            all_group = scenario_df.loc[mask.loc[scenario_df.index]].copy()
            valid_group = all_group[all_group['LLM_Valid'] == True].copy()
            for population_name, frame in [('All_Final', all_group), ('Valid_LLM_Only', valid_group)]:
                total = len(frame)
                valid_n = int(all_group['LLM_Valid'].sum())
                fallback_n = int(all_group['LLM_Fallback_Used'].sum())
                for action in LLM_ALLOWED_ACTIONS:
                    count = int((frame['Action'] == action).sum())
                    rows.append({'Scenario': scenario.key, 'Scenario_Name': scenario.name, 'Scenario_Time': case_hhmm(scenario.start_min), 'Passenger_Group': group_name, 'Decision_Population': population_name, 'Group_N': total, 'Action': action, 'Action_CN': CASE_ACTION_CN[action], 'Count': count, 'Proportion': count / total if total else np.nan, 'Valid_LLM_N': valid_n, 'Fallback_N': fallback_n, 'Fallback_Rate': fallback_n / len(all_group) if len(all_group) else np.nan})
    summary = pd.DataFrame(rows)
    for (_, _, population), frame in summary.groupby(['Scenario', 'Passenger_Group', 'Decision_Population']):
        if int(frame['Group_N'].iloc[0]) > 0 and (not np.isclose(frame['Proportion'].sum(), 1.0)):
            raise AssertionError(f'选择比例不为100%：{population}')
    return summary

def case_efficiency_times():
    start, end = (8 * 60 + 31, 22 * 60 + 50)
    sample = set(range(start, end + 1, 5))
    sample.update({9 * 60 + 17, 11 * 60 + 19, 20 * 60, 22 * 60 + 50})
    return sorted(sample)

def case_network_efficiency_curve():
    systems = {scenario.key: build_case_system(scenario, scenario.start_min) for scenario in CASE_SCENARIOS}
    efficiency_cache = {}
    rows = []
    for at_min in case_efficiency_times():
        scenario = case_active_scenario(at_min)
        schedule_regime = 'before_20_00' if at_min < 20 * 60 else 'from_20_00'
        cache_key = (scenario.key, schedule_regime)
        if cache_key not in efficiency_cache:
            efficiency_cache[cache_key] = systems[scenario.key].calculate_weighted_efficiency(at_min, day_type=CASE_DAY_TYPE)
        relative_efficiency = efficiency_cache[cache_key]
        rows.append({'Time': case_hhmm(at_min), 'Time_Min': at_min, 'Scenario': scenario.key, 'Scenario_Name': scenario.name, 'Relative_Network_Efficiency': float(relative_efficiency)})
    result = pd.DataFrame(rows)
    restored = result.loc[result['Time_Min'] == 22 * 60 + 50, 'Relative_Network_Efficiency']
    if len(restored) != 1 or not np.isclose(float(restored.iloc[0]), 1.0, atol=1e-09):
        raise AssertionError('22:50正常恢复点的相对网络效率必须为1.0。')
    return result

def case_plot_efficiency(efficiency_df, output_dir=CASE_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(13, 5.5), dpi=160)
    ax.step(efficiency_df['Time_Min'], efficiency_df['Relative_Network_Efficiency'], where='post', color='#b22222', linewidth=2.0)
    for scenario in CASE_SCENARIOS:
        if scenario.start_min <= 22 * 60 + 50:
            ax.axvline(scenario.start_min, color='#666666', linestyle='--', linewidth=0.8)
            ax.text(scenario.start_min, ax.get_ylim()[1], case_hhmm(scenario.start_min), rotation=90, va='top', ha='right', fontsize=8)
    ax.set_title('上海地铁11号线侵线施工：相对时间网络效率')
    ax.set_xlabel('时间')
    ax.set_ylabel('相对网络效率  E_incident(t) / E_normal(t)')
    ax.grid(axis='y', alpha=0.25)
    ticks = sorted(set([8 * 60 + 31, 9 * 60 + 17, 11 * 60 + 19, 20 * 60, 22 * 60 + 50]))
    ax.set_xticks(ticks, [case_hhmm(tick) for tick in ticks])
    fig.tight_layout()
    output_path = output_dir / 'Network_Efficiency_Curve.png'
    fig.savefig(output_path, dpi=220, bbox_inches='tight')
    plt.show()
    return output_path

def case_scenario_config_table():
    rows = []
    for scenario in CASE_SCENARIOS:
        rows.append({'Scenario': scenario.key, 'Scenario_Name': scenario.name, 'Start': case_hhmm(scenario.start_min), 'End': case_hhmm(scenario.end_min), 'Line11_Corridor_State': scenario.line_state, 'North_Service': scenario.north_service, 'Shuttle_Active': scenario.shuttle_active, 'Corridor_Speed_Factor': 0.5 if scenario.line_state == 'slowed' else 0.0 if scenario.line_state == 'broken' else 1.0, 'Shuttle_Frequency_Rule': '正常嘉定新城—迪士尼周日班距：20:00前5分钟，之后12分钟' if scenario.shuttle_active else '无'})
    return pd.DataFrame(rows)

def case_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, output_dir=CASE_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'Line11_Incident_LLM_Decisions_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx'
    valid_rate = float(passenger_df['LLM_Valid'].mean()) if not passenger_df.empty else np.nan
    input_audit = pd.DataFrame([{'Input': 'Source_Notebook', 'Path': '20260626上海地铁11号线侵线施工案例-LLM乘客决策与网络效率.ipynb', 'Note': 'v2基于v1案例覆盖层'}, {'Input': 'Schedule', 'Path': str(CASE_SCHEDULE_PATH), 'Note': '只读；优先目标文件夹，否则G盘给定文件'}, {'Input': 'OD_Flow_Proxy', 'Path': str(CASE_DATA_ROOT / 'shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv'), 'Note': '源模型的2025-08-08最近08:31客流代理'}])
    run_summary = pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Cohort_N': len(cohort_df), 'Affected_N': int(cohort_df['Affected_Corridor'].sum()), 'LLM_Valid_Rate': valid_rate, 'LLM_Fallback_N': int(passenger_df['LLM_Fallback_Used'].sum())}])
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Decision_Share_Summary', index=False)
        passenger_df.to_excel(writer, sheet_name='Passenger_Decisions', index=False)
        llm_log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        case_scenario_config_table().to_excel(writer, sheet_name='Scenario_Config', index=False)
        shuttle_df.to_excel(writer, sheet_name='Shuttle_Timing', index=False)
        efficiency_df.to_excel(writer, sheet_name='Network_Efficiency', index=False)
        run_summary.to_excel(writer, sheet_name='Run_Summary', index=False)
        input_audit.to_excel(writer, sheet_name='Input_Audit', index=False)
    return output_path

def run_case_study(use_live_llm=True, compute_efficiency=True, resume=False, run_label=None):
    _sr.require_run()
    case_require_inputs()
    cohort_df = sample_case_cohort()
    base_run_id = case_run_id(cohort_df)
    run_id = base_run_id if resume else f'{base_run_id}_{run_label or datetime.now().strftime('%Y%m%d_%H%M%S')}'
    checkpoint_paths = case_checkpoint_paths(run_id)
    resumed_records, resumed_logs = case_load_resume(checkpoint_paths['jsonl']) if resume else ({}, [])
    all_records = list(resumed_records.values())
    llm_call_log = list(resumed_logs)
    shuttle_rows = []
    for scenario in CASE_SCENARIOS[:3]:
        normal_system = build_case_system(CASE_SCENARIO_BY_KEY['normal_recovered'], scenario.start_min)
        scenario_system = build_case_system(scenario, scenario.start_min)
        shuttle_rows.append({'Scenario': scenario.key, 'Scenario_Time': case_hhmm(scenario.start_min), **case_shuttle_info(scenario_system, scenario.start_min)})
        for _, od in cohort_df.iterrows():
            key = (scenario.key, int(od['PID']))
            if key in resumed_records:
                continue
            log_start = len(llm_call_log)
            passenger = CasePassengerAgent(int(od['PID']), od['Origin'], od['Dest'], scenario.start_min)
            passenger.decide_case(normal_system, scenario_system, scenario, scenario.start_min, bool(od['Affected_Corridor']), use_live_llm, llm_call_log)
            record = passenger.case_record()
            record.update({'OD_Sample_Group': od['OD_Sample_Group'], 'OD_Sampling_Source': od['OD_Sampling_Source'], 'Run_ID': run_id})
            all_records.append(record)
            resumed_records[key] = record
            case_append_checkpoint(checkpoint_paths['jsonl'], record, llm_call_log[log_start:])
            if len(all_records) % CASE_CHECKPOINT_EVERY_PASSENGERS == 0:
                case_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id)
                print(f'checkpoint: {len(all_records)}/{CASE_SAMPLE_SIZE * 3}', flush=True)
    passenger_df = pd.DataFrame(all_records).sort_values(['Scenario', 'PID']).reset_index(drop=True)
    if len(passenger_df) != CASE_SAMPLE_SIZE * 3:
        raise AssertionError('乘客决策记录数量应为500×3。')
    for scenario in CASE_SCENARIOS[:3]:
        frame = passenger_df[passenger_df['Scenario'] == scenario.key]
        if len(frame) != CASE_SAMPLE_SIZE or int(frame['Affected_Corridor_60pct'].sum()) != CASE_AFFECTED_COUNT:
            raise AssertionError(f'{scenario.key}的样本约束不满足。')
        if scenario.key in {'condition_2', 'condition_3'} and bool((frame.loc[frame['Affected_Corridor_60pct'], 'Action'] == 'continue_metro').any()):
            raise AssertionError(f'{scenario.key}中受影响乘客不应选择继续乘坐地铁。')
    summary_df = case_summary_table(passenger_df)
    llm_log_df = pd.DataFrame(llm_call_log)
    shuttle_df = pd.DataFrame(shuttle_rows)
    efficiency_df = case_network_efficiency_curve() if compute_efficiency else pd.DataFrame()
    curve_path = case_plot_efficiency(efficiency_df) if compute_efficiency else None
    excel_path = case_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id)
    fallback_rate = float(passenger_df['LLM_Fallback_Used'].mean())
    if fallback_rate > 0.05:
        print(f'警告：LLM技术回退比例为{fallback_rate:.1%}；研究解释应优先使用Valid_LLM_Only行。', flush=True)
    return {'cohort': cohort_df, 'passenger_decisions': passenger_df, 'decision_share_summary': summary_df, 'llm_call_log': llm_log_df, 'shuttle_timing': shuttle_df, 'network_efficiency': efficiency_df, 'excel_path': excel_path, 'curve_path': curve_path, 'run_id': run_id, 'checkpoint_paths': checkpoint_paths}
