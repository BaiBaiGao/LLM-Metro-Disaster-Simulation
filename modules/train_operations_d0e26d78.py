import copy
from io import BytesIO
CASE_VERSION = 'line11_intrusion_20241222_v3'
V3_SIM_START_MIN = 8 * 60 + 31
V3_SIM_END_MIN = 22 * 60 + 50
V3_INTERNAL_STEP_SEC = 10
V3_LOG_STEP_SEC = 60
V3_GIF_FRAME_SEC = 300
V3_PROXY_HORIZON_MIN = 15
V3_TERMINAL_STATUSES = {'finished', 'cancelled', 'incident_terminated'}

def v3_headway_seconds(self, line_id, clock_min, default_seconds=300.0, station_name=None):
    """Compute waiting time using the case-specific non-working-day schedule."""
    day_type = getattr(self, 'service_day_type', CASE_DAY_TYPE)
    rules = self._active_rules_for_line(str(line_id), clock_min, day_type)
    if station_name:
        station_name = clean_station_name(station_name)
        station_rules = [rule for rule in rules if self._is_station_in_section(str(line_id), station_name, clean_station_name(rule['from_st']), clean_station_name(rule['to_st']))]
        if station_rules:
            rules = station_rules
    return float(min((float(rule['interval']) for rule in rules))) if rules else float(default_seconds)
SubwayRuleSystem.headway_seconds = v3_headway_seconds

def v3_rule_slice(system, rule, start_min, end_min, source, interval_multiplier=1.0, scenario='normal'):
    start = max(int(rule['start_min']), int(start_min))
    end = min(int(rule['end_min']), int(end_min))
    if end <= start:
        return
    system._append_schedule_rule({'line_id': str(rule['line_id']), 'day_type': CASE_DAY_TYPE, 'start_min': start, 'end_min': end, 'from_st': clean_station_name(rule['from_st']), 'to_st': clean_station_name(rule['to_st']), 'interval': float(rule['interval']) * float(interval_multiplier), 'source': source, 'is_default_service': False, 'default_service_key': '', 'scenario': scenario})

def v3_add_service(system, from_station, to_station, start_min, end_min, interval_sec, scenario, source):
    system._append_schedule_rule({'line_id': '11', 'day_type': CASE_DAY_TYPE, 'start_min': int(start_min), 'end_min': int(end_min), 'from_st': clean_station_name(from_station), 'to_st': clean_station_name(to_station), 'interval': float(interval_sec), 'source': source, 'is_default_service': False, 'default_service_key': '', 'scenario': scenario})

def v3_install_continuous_schedule(system):
    """Construct the network Sunday timetable with time-varying Line 11 services."""
    base_rules = case_load_schedule_rules()
    system.schedule_rules = []
    system.schedule_lookup = {}
    system.service_day_type = CASE_DAY_TYPE
    normal_windows = [(0, V3_SIM_START_MIN), (V3_SIM_END_MIN, 24 * 60)]
    for rule in base_rules:
        if rule['day_type'] != CASE_DAY_TYPE:
            continue
        if str(rule['line_id']) != '11':
            v3_rule_slice(system, rule, 0, 24 * 60, 'v3_normal_network', scenario='normal')
            continue
        for start, end in normal_windows:
            v3_rule_slice(system, rule, start, end, 'v3_normal_line11', scenario='normal')
        v3_rule_slice(system, rule, V3_SIM_START_MIN, 9 * 60 + 17, 'v3_condition_1_headway_x2' if case_rule_crosses_corridor(system, rule) else 'v3_condition_1_normal_service', interval_multiplier=2.0 if case_rule_crosses_corridor(system, rule) else 1.0, scenario='condition_1')
    v3_add_service(system, '武威路', '迪士尼', 9 * 60 + 17, 11 * 60 + 19, 300, 'condition_2', 'v3_condition_2_wuwei_disney')
    for origin, destination, headway in [('嘉定北', '马陆', 600), ('花桥', '马陆', 600), ('武威路', '迪士尼', 300)]:
        v3_add_service(system, origin, destination, 11 * 60 + 19, 20 * 60, headway, 'condition_3', 'v3_condition_3_short_turn')
    for origin, destination in [('嘉定北', '马陆'), ('花桥', '马陆'), ('武威路', '迪士尼')]:
        v3_add_service(system, origin, destination, 20 * 60, V3_SIM_END_MIN, 720, 'condition_3', 'v3_condition_3_short_turn')
    system._route_graph_cache = {}

def build_v3_dynamic_system():
    case_require_inputs()
    global DEFAULT_SERVICE_RULES
    DEFAULT_SERVICE_RULES = []
    system = SubwayRuleSystem(CASE_DATA_ROOT, sim_start_time=case_hhmm(V3_SIM_START_MIN))
    v3_install_continuous_schedule(system)
    system.reset_rule_state()
    return system

class DynamicTrainAgent(TrainAgent):

    def __init__(self, *args, segment_state_provider=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.segment_state_provider = segment_state_provider
        self.dynamic_now_abs_sec = 0
        self.incident_terminated_at = ''
        self.incident_terminated_abs_sec = np.nan
        self.incident_termination_reason = ''

    def _can_enter_segment(self, segment, occupied_directed_edges):
        state = self.segment_state_provider(segment, self.dynamic_now_abs_sec) if self.segment_state_provider else {'status': 'normal', 'speed_factor': 1.0, 'reason': ''}
        segment['edge_status'] = state['status']
        segment['speed_factor'] = state['speed_factor']
        segment['runtime_sec'] = float('inf') if state['speed_factor'] <= 0 else float(segment['base_runtime_sec']) / max(float(state['speed_factor']), 1e-06)
        if state['status'] in {'suspended', 'closed', 'train_blocked'} or state['speed_factor'] <= 0:
            self.incident_termination_reason = state.get('reason', 'incident_service_unavailable')
            return (False, 'incident_termination')
        return super()._can_enter_segment(segment, occupied_directed_edges)

class ContinuousScenarioTrainSimulationEngine(TrainSimulationEngine):

    def __init__(self, system, day_type=CASE_DAY_TYPE):
        super().__init__(system, day_type=day_type)
        self.event_rows = []
        self.transition_rows = []
        self._allowed_line11_pairs = self._build_allowed_line11_pairs()

    def _pairs_for_service(self, origin, destination):
        return {tuple(sorted((seg['from_station'], seg['to_station']))) for seg in self._build_segments_for_rule('11', origin, destination, reverse=False)}

    def _build_allowed_line11_pairs(self):
        return {'condition_2': self._pairs_for_service('武威路', '迪士尼'), 'condition_3': self._pairs_for_service('嘉定北', '马陆') | self._pairs_for_service('花桥', '马陆') | self._pairs_for_service('武威路', '迪士尼')}

    @staticmethod
    def _scenario_at(now_abs_sec):
        return case_active_scenario(int(now_abs_sec // 60))

    def segment_state(self, segment, now_abs_sec):
        scenario = self._scenario_at(now_abs_sec)
        line_id = str(segment['line_id'])
        pair = tuple(sorted((segment['from_station'], segment['to_station'])))
        if line_id != '11':
            return {'status': 'normal', 'speed_factor': 1.0, 'reason': '', 'scenario': scenario.key}
        if scenario.key == 'condition_1' and pair in {tuple(sorted(edge)) for edge in CASE_CORRIDOR_SECTIONS}:
            return {'status': 'slowed', 'speed_factor': 0.5, 'reason': 'condition_1_speed_restriction', 'scenario': scenario.key}
        if scenario.key in {'condition_2', 'condition_3'}:
            allowed = self._allowed_line11_pairs[scenario.key]
            if pair not in allowed:
                return {'status': 'suspended', 'speed_factor': 0.0, 'reason': f'{scenario.key}_service_not_operating', 'scenario': scenario.key}
        return {'status': 'normal', 'speed_factor': 1.0, 'reason': '', 'scenario': scenario.key}

    def build_service_patterns(self):
        patterns = super().build_service_patterns()
        for pattern in patterns:
            source = str(pattern.get('source', ''))
            if 'condition_1' in source:
                pattern['scenario'] = 'condition_1'
            elif 'condition_2' in source:
                pattern['scenario'] = 'condition_2'
            elif 'condition_3' in source:
                pattern['scenario'] = 'condition_3'
            else:
                pattern['scenario'] = 'normal'
        return patterns

    def build_trains(self, sim_start_abs_sec, sim_end_abs_sec):
        if not self.service_patterns:
            self.build_service_patterns()
        max_runtime = max([p['route_runtime_sec'] for p in self.service_patterns], default=0.0)
        warm_start = sim_start_abs_sec - int(max(WARM_START_LOOKBACK_MIN * 60, max_runtime + TERMINAL_DWELL_SEC))
        train_id = 1
        for pattern in self.service_patterns:
            for departure in self._departure_times(pattern, warm_start, sim_end_abs_sec):
                train = DynamicTrainAgent(f'TR{train_id:05d}', pattern['service_id'], pattern['line_id'], pattern['direction'], departure, copy.deepcopy(pattern['segments']), segment_state_provider=self.segment_state)
                self.trains.append(train)
                self.timetable_rows.append({'Train_ID': train.train_id, 'Service_ID': pattern['service_id'], 'Line_ID': pattern['line_id'], 'Direction': pattern['direction'], 'Departure_Abs_Sec': int(departure), 'Departure_Rel_Sec': int(departure - sim_start_abs_sec), 'From_Station': pattern['from_station'], 'To_Station': pattern['to_station'], 'Interval_Sec': pattern['interval_sec'], 'Station_Count': pattern['station_count'], 'Route_Runtime_Sec': pattern['route_runtime_sec'], 'Is_Ring': pattern['is_ring'], 'Source': pattern['source'], 'Scenario': pattern.get('scenario', 'normal'), 'Is_Default_Service': pattern['is_default_service'], 'Default_Service_Key': pattern['default_service_key'], 'Source_From_Station': pattern['source_from_station'], 'Source_To_Station': pattern['source_to_station']})
                train_id += 1
        return self.trains

    def _log_positions_and_counts_v3(self, now_abs_sec, sim_start_abs_sec):
        scenario = self._scenario_at(now_abs_sec)
        rel_sec = int(now_abs_sec - sim_start_abs_sec)
        active = [train for train in self.trains if train.status not in {'scheduled', *V3_TERMINAL_STATUSES}]
        for train in active:
            row = train.position_record(rel_sec)
            row.update({'Abs_Time_Sec': int(now_abs_sec), 'Clock_Time': case_hhmm(now_abs_sec // 60), 'Scenario': scenario.key, 'Scenario_Name': scenario.name})
            self.position_rows.append(row)
        counts = {}
        for train in active:
            if train.status != 'running' or train.current_segment is None:
                continue
            segment = train.current_segment
            key = (segment['line_id'], segment['edge_name'], train.direction)
            counts[key] = counts.get(key, 0) + 1
        for (line_id, edge_name, direction), count in counts.items():
            self.edge_count_rows.append({'Time_Sec': rel_sec, 'Abs_Time_Sec': int(now_abs_sec), 'Clock_Time': case_hhmm(now_abs_sec // 60), 'Scenario': scenario.key, 'Line_ID': line_id, 'Edge_Name': edge_name, 'Direction': direction, 'Train_Count': int(count)})

    def _terminate_after_transition(self, train, now_abs_sec):
        if train.status == 'dwell' and train.wait_reason == 'incident_termination':
            train.status = 'incident_terminated'
            train.incident_terminated_at = train.current_station
            train.incident_terminated_abs_sec = int(now_abs_sec)
            self.event_rows.append({'Abs_Time_Sec': int(now_abs_sec), 'Clock_Time': case_hhmm(now_abs_sec // 60), 'Scenario': self._scenario_at(now_abs_sec).key, 'Event_Type': 'incident_terminated', 'Train_ID': train.train_id, 'Line_ID': train.line_id, 'Station': train.current_station, 'Reason': train.incident_termination_reason})

    def run_continuous(self, sim_start_min=V3_SIM_START_MIN, sim_end_min=V3_SIM_END_MIN):
        _sr.require_run()
        sim_start_abs_sec = int(sim_start_min * 60)
        sim_end_abs_sec = int(sim_end_min * 60)
        self.build_service_patterns()
        self.build_trains(sim_start_abs_sec, sim_end_abs_sec)
        warm_start_abs_sec = min((train.departure_abs_sec for train in self.trains), default=sim_start_abs_sec)
        previous_scenario = None
        now = warm_start_abs_sec
        while now <= sim_end_abs_sec:
            scenario = self._scenario_at(now)
            if now >= sim_start_abs_sec and scenario.key != previous_scenario:
                self.transition_rows.append({'Abs_Time_Sec': int(now), 'Clock_Time': case_hhmm(now // 60), 'Scenario': scenario.key, 'Scenario_Name': scenario.name, 'Event_Type': 'scenario_transition'})
                previous_scenario = scenario.key
            occupied = self._active_running_occupancy()
            for train in self.trains:
                if train.status in V3_TERMINAL_STATUSES:
                    continue
                train.dynamic_now_abs_sec = int(now)
                train.step(now, V3_INTERNAL_STEP_SEC, occupied)
                self._terminate_after_transition(train, now)
            if now >= sim_start_abs_sec and (now - sim_start_abs_sec) % V3_LOG_STEP_SEC == 0:
                self._log_positions_and_counts_v3(now, sim_start_abs_sec)
            now += V3_INTERNAL_STEP_SEC
        return self.to_dataframes_v3()

    def to_dataframes_v3(self):
        base = self.to_dataframes()
        status = pd.DataFrame([{'Train_ID': train.train_id, 'Actual_Final_Status': train.status, 'Incident_Terminated_At': train.incident_terminated_at, 'Incident_Terminated_Abs_Sec': train.incident_terminated_abs_sec, 'Incident_Termination_Reason': train.incident_termination_reason} for train in self.trains])
        timetable = pd.DataFrame(self.timetable_rows).merge(status, on='Train_ID', how='left') if self.timetable_rows else pd.DataFrame()
        patterns = base['service_patterns'].copy()
        if not patterns.empty:
            patterns['Scenario'] = patterns['Source'].astype(str).map(lambda src: 'condition_1' if 'condition_1' in src else 'condition_2' if 'condition_2' in src else 'condition_3' if 'condition_3' in src else 'normal')
        train_summary = timetable.groupby(['Scenario', 'Actual_Final_Status'], dropna=False).size().reset_index(name='Train_Count') if not timetable.empty else pd.DataFrame()
        return {**base, 'service_patterns': patterns, 'train_timetable': timetable, 'train_position_log': pd.DataFrame(self.position_rows), 'edge_train_counts': pd.DataFrame(self.edge_count_rows), 'train_event_log': pd.DataFrame(self.transition_rows + self.event_rows), 'scenario_train_summary': train_summary}

def v3_gif_frame_times(train_position_df):
    if train_position_df is None or train_position_df.empty:
        return []
    times = sorted((int(value) for value in train_position_df['Time_Sec'].dropna().unique()))
    selected = [value for value in times if value % V3_GIF_FRAME_SEC == 0]
    return selected or times

def generate_v3_train_gif(train_position_df, system, output_dir=CASE_OUTPUT_DIR):
    _sr.require_run()
    if train_position_df is None or train_position_df.empty:
        raise ValueError('Train_Position_Log为空，无法生成GIF。')
    from PIL import Image
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    corridor = {tuple(sorted(pair)) for pair in CASE_CORRIDOR_SECTIONS}
    line_edges = []
    for u, v, k, attr in system.G.edges(keys=True, data=True):
        if attr.get('type') != 'riding':
            continue
        p1, p2 = (system.G.nodes[u]['pos'], system.G.nodes[v]['pos'])
        line_id = str(attr.get('line_id', ''))
        pair = tuple(sorted((system.station_name_from_node(u), system.station_name_from_node(v))))
        line_edges.append((p1[1], p1[0], p2[1], p2[0], line_id, pair))
    frames = []
    for rel_sec in v3_gif_frame_times(train_position_df):
        frame = train_position_df[train_position_df['Time_Sec'] == rel_sec]
        scenario_key = str(frame['Scenario'].iloc[0]) if not frame.empty else case_active_scenario(V3_SIM_START_MIN + rel_sec // 60).key
        fig, ax = plt.subplots(figsize=(8.5, 7.2))
        for x1, y1, x2, y2, line_id, pair in line_edges:
            color, width = ('#d5d5d5', 0.45)
            if line_id == '11' and pair in corridor:
                if scenario_key == 'condition_1':
                    color, width = ('#f39c12', 1.2)
                elif scenario_key in {'condition_2', 'condition_3'}:
                    color, width = ('#c0392b', 1.3)
            ax.plot([x1, x2], [y1, y2], color=color, linewidth=width, zorder=1)
        if not frame.empty:
            colors = ['#d62728' if status == 'running' else '#1f77b4' for status in frame['Status']]
            ax.scatter(frame['Lon'], frame['Lat'], s=8, c=colors, alpha=0.82, edgecolors='none', zorder=3)
            clock = str(frame['Clock_Time'].iloc[0])
            active = int(frame['Train_ID'].nunique())
        else:
            clock, active = (case_hhmm(V3_SIM_START_MIN + rel_sec // 60), 0)
        ax.set_title(f'上海地铁连续列车微观仿真 | {clock} | {scenario_key} | active={active}')
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.set_aspect('equal', adjustable='box')
        ax.grid(False)
        fig.tight_layout()
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=105)
        plt.close(fig)
        buffer.seek(0)
        frames.append(Image.open(buffer).convert('P', palette=Image.ADAPTIVE))
    if len(frames) < 2:
        raise ValueError('GIF帧数不足。')
    path = output_dir / f'Line11_Continuous_Train_Movement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif'
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=260, loop=0)
    return path

def v3_corridor_direction(plan):
    for record in plan.get('edge_records', []):
        if record.get('type') != 'riding' or str(record.get('line_id')) != '11':
            continue
        start, end = (record.get('from_station', ''), record.get('to_station', ''))
        if (start, end) in CASE_CORRIDOR_SECTIONS:
            return '嘉定侧→市区侧'
        if (end, start) in CASE_CORRIDOR_SECTIONS:
            return '市区侧→嘉定侧'
    return '不跨越受影响走廊'

def v3_od_operation_group(scenario_key, affected, current_reachable):
    if affected:
        if scenario_key == 'condition_1':
            return '受影响：限速运行且地铁可达' if current_reachable else '受影响：限速下地铁不可达'
        if scenario_key == 'condition_2':
            return '受影响：区间断开、短驳可用'
        if scenario_key == 'condition_3':
            return '受影响：区间断开、小交路与短驳可用'
    return '未受影响：当前11号线相关服务可达' if current_reachable else '未受影响：当前11号线相关服务不可达'

def v3_operational_proxy(train_outputs, plan, scenario_start_min, normal_system, scenario_system):
    positions = train_outputs.get('train_position_log', pd.DataFrame())
    counts = train_outputs.get('edge_train_counts', pd.DataFrame())
    start_abs = int(scenario_start_min * 60)
    end_abs = start_abs + V3_PROXY_HORIZON_MIN * 60
    route_edges = {str(record.get('edge_name', '')) for record in plan.get('edge_records', []) if record.get('type') == 'riding'}
    route_lines = {str(record.get('line_id', '')) for record in plan.get('edge_records', []) if record.get('type') == 'riding'}
    pos_window = positions[(positions.get('Abs_Time_Sec', pd.Series(dtype=float)) >= start_abs) & (positions.get('Abs_Time_Sec', pd.Series(dtype=float)) < end_abs)] if not positions.empty else pd.DataFrame()
    count_window = counts[(counts.get('Abs_Time_Sec', pd.Series(dtype=float)) >= start_abs) & (counts.get('Abs_Time_Sec', pd.Series(dtype=float)) < end_abs)] if not counts.empty else pd.DataFrame()
    if route_edges and (not count_window.empty):
        count_window = count_window[count_window['Edge_Name'].isin(route_edges)]
    elif route_lines and (not count_window.empty):
        count_window = count_window[count_window['Line_ID'].astype(str).isin(route_lines)]
    if route_lines and (not pos_window.empty):
        pos_window = pos_window[pos_window['Line_ID'].astype(str).isin(route_lines)]
    density = float(count_window['Train_Count'].mean()) if not count_window.empty else 0.0
    peak_density = float(count_window['Train_Count'].max()) if not count_window.empty else 0.0
    wait_share = float((pos_window['Wait_Reason'].fillna('') != '').mean()) if not pos_window.empty else 0.0
    first_line = next(iter(route_lines), '11')
    origin = plan.get('origin', '')
    normal_hw = normal_system.headway_seconds(first_line, scenario_start_min, station_name=origin) / 60.0
    current_hw = scenario_system.headway_seconds(first_line, scenario_start_min, station_name=origin) / 60.0
    headway_ratio = current_hw / max(normal_hw, 1e-06)
    reachable = bool(plan.get('reachable'))
    if not reachable:
        level, score = ('critical', 4)
    else:
        score = int(headway_ratio >= 1.5) + int(density >= 0.5) + int(wait_share >= 0.1) + int(peak_density >= 1.0 and wait_share >= 0.25)
        level = ['none', 'low', 'medium', 'high', 'critical'][min(4, score)]
    return {'level': level, 'score': int(score), 'horizon_min': V3_PROXY_HORIZON_MIN, 'normal_headway_min': float(normal_hw), 'current_headway_min': float(current_hw), 'headway_ratio': float(headway_ratio), 'avg_route_train_occupancy': density, 'peak_route_train_occupancy': peak_density, 'blocked_wait_share': wait_share, 'note': '该指标反映实际服务班距、列车区间占用和等待/阻断，不代表车厢乘客负载率。'}
V2_FACT_CARD = case_human_fact_card
V2_BUILD_CONTEXT = CasePassengerAgent.build_case_context

def v3_case_human_fact_card(context):
    card = V2_FACT_CARD(context)
    proxy = context.get('operational_proxy') or {}
    if proxy:
        card['运营拥挤与服务可靠性'] = {'等级': proxy['level'], '观察窗口': f'工况开始后{proxy['horizon_min']}分钟', '正常班距': f'{proxy['normal_headway_min']:.1f}分钟', '当前班距': f'{proxy['current_headway_min']:.1f}分钟', '班距比': round(proxy['headway_ratio'], 2), '路径相关平均列车占用': round(proxy['avg_route_train_occupancy'], 3), '路径相关等待比例': round(proxy['blocked_wait_share'], 3), '说明': proxy['note']}
    if context.get('od_groups'):
        card['OD细分群组'] = context['od_groups']
    return card
case_human_fact_card = v3_case_human_fact_card

def v3_build_case_context(self, normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=None, od_groups=None):
    context = V2_BUILD_CONTEXT(self, normal_system, scenario_system, scenario, at_min, affected_corridor)
    context['operational_proxy'] = operational_proxy or {}
    context['od_groups'] = od_groups or {}
    context['fact_card'] = case_human_fact_card(context)
    self.case_context = context
    return context

def v3_decide_case(self, normal_system, scenario_system, scenario, at_min, affected_corridor, use_live_llm, llm_call_log, operational_proxy=None, od_groups=None):
    context = self.build_case_context(normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=operational_proxy, od_groups=od_groups)
    self.llm_selected = True
    self.decision_mode = 'llm'
    self.rule_action_raw = ''
    self.rule_action = ''
    outcome = case_call_llm(context, llm_call_log) if use_live_llm else {'valid': False, 'parsed': {}, 'raw': '', 'error': 'smoke_test_no_live_llm', 'model': '', 'attempted_models': [], 'attempt_count': 0, 'prompt_tokens': 0, 'completion_tokens': 0}
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
CasePassengerAgent.build_case_context = v3_build_case_context
CasePassengerAgent.decide_case = v3_decide_case

def v3_od_group_definitions():
    return pd.DataFrame([{'Field': 'OD_Sample_Group', 'Value': 'affected_corridor', 'Definition': '基线路径经过马陆—武威路四段受影响走廊。'}, {'Field': 'OD_Sample_Group', 'Value': 'unaffected_line11_control', 'Definition': '基线路径经过11号线但不经过受影响走廊。'}, {'Field': 'Corridor_Crossing_Direction', 'Value': '嘉定侧→市区侧 / 市区侧→嘉定侧', 'Definition': '受影响OD在11号线走廊的跨越方向。'}, {'Field': 'Scenario_OD_Operation_Group', 'Value': '动态标签', 'Definition': '按限速、断开、短驳、小交路及当前可达性给出的工况状态。'}])

def v3_od_group_summary(passenger_df):
    rows = []
    group_cols = ['Scenario', 'OD_Sample_Group', 'Corridor_Crossing_Direction', 'Scenario_OD_Operation_Group']
    for keys, frame in passenger_df.groupby(group_cols, dropna=False):
        for population, subset in [('All_Final', frame), ('Valid_LLM_Only', frame[frame['LLM_Valid'] == True])]:
            total = len(subset)
            for action in LLM_ALLOWED_ACTIONS:
                rows.append({**dict(zip(group_cols, keys)), 'Decision_Population': population, 'Group_N': total, 'Action': action, 'Action_CN': CASE_ACTION_CN[action], 'Count': int((subset['Action'] == action).sum()), 'Proportion': int((subset['Action'] == action).sum()) / total if total else np.nan, 'Valid_LLM_N': int(frame['LLM_Valid'].sum()), 'Fallback_N': int(frame['LLM_Fallback_Used'].sum()), 'Fallback_Rate': float(frame['LLM_Fallback_Used'].mean())})
    return pd.DataFrame(rows)

def v3_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_df, output_dir=CASE_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'Line11_Incident_LLM_TrainSimulation_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx'
    run_summary = pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Cohort_N': len(cohort_df), 'Affected_N': int(cohort_df['Affected_Corridor'].sum()), 'LLM_Valid_Rate': float(passenger_df['LLM_Valid'].mean()), 'LLM_Fallback_N': int(passenger_df['LLM_Fallback_Used'].sum()), 'Train_Log_Step_Sec': V3_LOG_STEP_SEC, 'GIF_Frame_Sec': V3_GIF_FRAME_SEC, 'GIF_Path': str(gif_path or '')}])
    gif_manifest = pd.DataFrame([{'GIF_Path': str(gif_path or ''), 'Frame_Interval_Sec': V3_GIF_FRAME_SEC, 'Start': case_hhmm(V3_SIM_START_MIN), 'End': case_hhmm(V3_SIM_END_MIN), 'Scope': '全网列车，11号线工况高亮'}])
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Decision_Share_Summary', index=False)
        passenger_df.to_excel(writer, sheet_name='Passenger_Decisions', index=False)
        llm_log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        v3_od_group_definitions().to_excel(writer, sheet_name='OD_Group_Definitions', index=False)
        v3_od_group_summary(passenger_df).to_excel(writer, sheet_name='OD_Group_Summary', index=False)
        pd.DataFrame(proxy_df).to_excel(writer, sheet_name='Operational_Proxy_Summary', index=False)
        train_outputs['service_patterns'].to_excel(writer, sheet_name='Service_Patterns', index=False)
        train_outputs['train_timetable'].to_excel(writer, sheet_name='Train_Timetable', index=False)
        train_outputs['train_position_log'].to_excel(writer, sheet_name='Train_Position_Log', index=False)
        train_outputs['edge_train_counts'].to_excel(writer, sheet_name='Edge_Train_Counts', index=False)
        train_outputs['train_event_log'].to_excel(writer, sheet_name='Train_Event_Log', index=False)
        train_outputs['scenario_train_summary'].to_excel(writer, sheet_name='Scenario_Train_Summary', index=False)
        gif_manifest.to_excel(writer, sheet_name='GIF_Manifest', index=False)
        case_scenario_config_table().to_excel(writer, sheet_name='Scenario_Config', index=False)
        shuttle_df.to_excel(writer, sheet_name='Shuttle_Timing', index=False)
        efficiency_df.to_excel(writer, sheet_name='Network_Efficiency', index=False)
        run_summary.to_excel(writer, sheet_name='Run_Summary', index=False)
    return output_path

def run_case_study_v3(use_live_llm=True, compute_efficiency=True, generate_gif=False, resume=False, run_label=None):
    _sr.require_run()
    case_require_inputs()
    cohort_df = sample_case_cohort()
    base_run_id = case_run_id(cohort_df)
    run_id = base_run_id if resume else f'{base_run_id}_{run_label or datetime.now().strftime('%Y%m%d_%H%M%S')}'
    checkpoint_paths = case_checkpoint_paths(run_id)
    resumed_records, resumed_logs = case_load_resume(checkpoint_paths['jsonl']) if resume else ({}, [])
    dynamic_system = build_v3_dynamic_system()
    train_engine = ContinuousScenarioTrainSimulationEngine(dynamic_system, day_type=CASE_DAY_TYPE)
    train_outputs = train_engine.run_continuous()
    gif_path = generate_v3_train_gif(train_outputs['train_position_log'], dynamic_system) if generate_gif else None
    all_records, llm_call_log, proxy_rows = (list(resumed_records.values()), list(resumed_logs), [])
    shuttle_rows = []
    for scenario in CASE_SCENARIOS[:3]:
        normal_system = build_case_system(CASE_SCENARIO_BY_KEY['normal_recovered'], scenario.start_min)
        normal_system.service_day_type = CASE_DAY_TYPE
        scenario_system = build_case_system(scenario, scenario.start_min)
        scenario_system.service_day_type = CASE_DAY_TYPE
        shuttle_rows.append({'Scenario': scenario.key, 'Scenario_Time': case_hhmm(scenario.start_min), **case_shuttle_info(scenario_system, scenario.start_min)})
        for _, od in cohort_df.iterrows():
            key = (scenario.key, int(od['PID']))
            if key in resumed_records:
                continue
            baseline_plan = normal_system.plan_passenger_route(od['Origin'], od['Dest'], 0, weight_mode='baseline')
            current_plan = scenario_system.plan_passenger_route(od['Origin'], od['Dest'], 0, weight_mode='current')
            direction = v3_corridor_direction(baseline_plan)
            operation_group = v3_od_operation_group(scenario.key, bool(od['Affected_Corridor']), bool(current_plan.get('reachable')))
            od_groups = {'抽样组': od['OD_Sample_Group'], '跨走廊方向': direction, '工况运营组': operation_group}
            proxy_plan = current_plan if current_plan.get('reachable') else baseline_plan
            proxy = v3_operational_proxy(train_outputs, proxy_plan, scenario.start_min, normal_system, scenario_system)
            proxy_rows.append({'Scenario': scenario.key, 'PID': int(od['PID']), **proxy})
            log_start = len(llm_call_log)
            passenger = CasePassengerAgent(int(od['PID']), od['Origin'], od['Dest'], scenario.start_min)
            passenger.decide_case(normal_system, scenario_system, scenario, scenario.start_min, bool(od['Affected_Corridor']), use_live_llm, llm_call_log, operational_proxy=proxy, od_groups=od_groups)
            record = passenger.case_record()
            record.update({'OD_Sample_Group': od['OD_Sample_Group'], 'OD_Sampling_Source': od['OD_Sampling_Source'], 'Corridor_Crossing_Direction': direction, 'Scenario_OD_Operation_Group': operation_group, 'Operational_Proxy_Level': proxy['level'], 'Operational_Proxy_Score': proxy['score'], 'Run_ID': run_id})
            all_records.append(record)
            resumed_records[key] = record
            case_append_checkpoint(checkpoint_paths['jsonl'], record, llm_call_log[log_start:])
            if len(all_records) % CASE_CHECKPOINT_EVERY_PASSENGERS == 0:
                case_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id)
                print(f'checkpoint: {len(all_records)}/{CASE_SAMPLE_SIZE * 3}', flush=True)
    passenger_df = pd.DataFrame(all_records).sort_values(['Scenario', 'PID']).reset_index(drop=True)
    if len(passenger_df) != CASE_SAMPLE_SIZE * 3:
        raise AssertionError('乘客决策记录数量应为500×3。')
    summary_df = case_summary_table(passenger_df)
    llm_log_df = pd.DataFrame(llm_call_log)
    shuttle_df = pd.DataFrame(shuttle_rows)
    efficiency_df = case_network_efficiency_curve() if compute_efficiency else pd.DataFrame()
    curve_path = case_plot_efficiency(efficiency_df) if compute_efficiency else None
    excel_path = v3_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_rows)
    return {'cohort': cohort_df, 'passenger_decisions': passenger_df, 'decision_share_summary': summary_df, 'llm_call_log': llm_log_df, 'train_outputs': train_outputs, 'operational_proxy': pd.DataFrame(proxy_rows), 'network_efficiency': efficiency_df, 'excel_path': excel_path, 'curve_path': curve_path, 'gif_path': gif_path, 'run_id': run_id, 'checkpoint_paths': checkpoint_paths}
