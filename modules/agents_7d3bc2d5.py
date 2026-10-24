class StationAgent:
    """Determine station opening and entry/exit speed from inter-layer disturbances."""

    def __init__(self, station_name):
        
        self.station_name = station_name
        self.status = 'open'
        self.walking_speed_factor = 1.0
        self.max_inter_layer_intensity = 0.0

    def decide(self, records, disturbance_function):
        
        self.max_inter_layer_intensity = max([r['intensity'] for r in records], default=0.0)
        result = disturbance_function.evaluate(f'{self.station_name}|station', self.max_inter_layer_intensity, 'inter_layer', {'agent': 'StationAgent', 'station': self.station_name})
        if self.max_inter_layer_intensity >= 1.0:
            self.status = 'closed'
            self.walking_speed_factor = 0.0
        else:
            self.status = 'open'
            self.walking_speed_factor = result['speed_factor']
        return {'Agent': 'StationAgent', 'Object': self.station_name, 'Decision': self.status, 'Max_Intensity': self.max_inter_layer_intensity, 'Speed_Factor': self.walking_speed_factor}

class LineAgent:
    """Determine line operation and speed restrictions from section disturbances."""

    def __init__(self, line_id):
        
        self.line_id = str(line_id)
        self.status = 'operating'
        self.line_speed_factor = 1.0
        self.max_intra_layer_intensity = 0.0

    def decide(self, records, disturbance_function):
        
        self.max_intra_layer_intensity = max([r['intensity'] for r in records], default=0.0)
        result = disturbance_function.evaluate(f'{self.line_id}|line', self.max_intra_layer_intensity, 'intra_layer', {'agent': 'LineAgent', 'line_id': self.line_id})
        if self.max_intra_layer_intensity >= 1.0:
            self.status = 'suspended'
            self.line_speed_factor = 0.0
        else:
            self.status = 'operating'
            self.line_speed_factor = result['speed_factor']
        return {'Agent': 'LineAgent', 'Object': self.line_id, 'Decision': self.status, 'Max_Intensity': self.max_intra_layer_intensity, 'Speed_Factor': self.line_speed_factor}

class MetroNetworkAgent:
    """Coordinate station and line decisions and update the network state."""

    def __init__(self, system, disturbance_function):
        
        self.system = system
        self.disturbance_function = disturbance_function
        self.station_agents = {st: StationAgent(st) for st in sorted(set(system.station_names()))}
        line_ids = sorted(set((str(sd.get('line_id')) for sd in system.fast_edge_data if sd.get('line_id') and sd['type'] == 'riding')))
        self.line_agents = {lid: LineAgent(lid) for lid in line_ids}
        self.decisions = []
        self.unmatched_disturbances = []

    def _records_by_key(self):
        """Group disturbance records by normalized edge key."""
        out = {}
        for rec in self.disturbance_function.records:
            out.setdefault(rec['normalized_key'], []).append(rec)
        return out

    def evaluate_and_apply(self):
        """Match disturbances, evaluate agents and update edge speed factors."""
        self.system.reset_rule_state()
        by_key = self._records_by_key()
        station_records = {st: [] for st in self.station_agents}
        line_records = {lid: [] for lid in self.line_agents}
        for key, records in by_key.items():
            indices = self.system.edge_indices_for_key(key)
            if not indices:
                self.unmatched_disturbances.extend(records)
                continue
            for rec in records:
                for edge_idx in indices:
                    sd = self.system.fast_edge_data[edge_idx]
                    enriched = dict(rec)
                    enriched['edge_idx'] = edge_idx
                    enriched['public_edge_name'] = self.system.public_edge_name(edge_idx)
                    if sd['type'] == 'boarding':
                        station_records.setdefault(key[1], []).append(enriched)
                    elif sd['type'] == 'riding':
                        line_records.setdefault(str(sd.get('line_id')), []).append(enriched)
        for st, agent in self.station_agents.items():
            records = station_records.get(st, [])
            decision = agent.decide(records, self.disturbance_function)
            if records or agent.status == 'closed':
                self.decisions.append(decision)
            if agent.status == 'closed':
                for edge_idx in self.system.edge_indices_for_station(st, 'boarding'):
                    self.system.apply_edge_decision(edge_idx, agent.max_inter_layer_intensity, 0.0, 'closed', 'StationAgent')
            else:
                for rec in records:
                    result = self.disturbance_function.evaluate(rec['public_edge_name'], rec['intensity'], 'inter_layer', {'agent': 'StationAgent', 'station': st})
                    self.system.apply_edge_decision(rec['edge_idx'], rec['intensity'], result['speed_factor'], 'normal', 'StationAgent')
        for lid, agent in self.line_agents.items():
            records = line_records.get(lid, [])
            decision = agent.decide(records, self.disturbance_function)
            if records or agent.status == 'suspended':
                self.decisions.append(decision)
            if agent.status == 'suspended':
                for edge_idx in self.system.edge_indices_for_line(lid, 'riding'):
                    self.system.apply_edge_decision(edge_idx, agent.max_intra_layer_intensity, 0.0, 'suspended', 'LineAgent')
            else:
                sections = {}
                for rec in records:
                    sections.setdefault(rec['normalized_key'], []).append(rec)
                for section_records in sections.values():
                    intensity = max((float(rec['intensity']) for rec in section_records))
                    first = section_records[0]
                    result = self.disturbance_function.evaluate(first['public_edge_name'], intensity, 'intra_layer', {'agent': 'LineAgent', 'line_id': lid})
                    for rec in section_records:
                        self.system.apply_edge_decision(rec['edge_idx'], intensity, result['speed_factor'], 'normal', 'LineAgent')
        for rec in self.unmatched_disturbances:
            self.decisions.append({'Agent': 'MetroNetworkAgent', 'Object': rec['edge_name'], 'Decision': 'unmatched_disturbance_edge', 'Max_Intensity': rec['intensity'], 'Speed_Factor': np.nan})
        summary = self.summary()
        self.decisions.append({'Agent': 'MetroNetworkAgent', 'Object': 'network', 'Decision': 'summary', 'Closed_Stations': summary['closed_stations'], 'Suspended_Lines': summary['suspended_lines'], 'Slowed_Edges': summary['slowed_edges'], 'Blocked_Edges': summary['blocked_edges']})
        return self.decisions

    def summary(self):
        """Count station closures, line suspensions, slow edges and blocked edges."""
        closed_stations = [st for st, ag in self.station_agents.items() if ag.status == 'closed']
        suspended_lines = [lid for lid, ag in self.line_agents.items() if ag.status == 'suspended']
        slowed_edges = [self.system.public_edge_name(i) for i, sd in enumerate(self.system.fast_edge_data) if sd.get('agent_override') == 'normal' and float(sd.get('speed_factor', 1.0)) < 1.0]
        blocked_edges = [self.system.public_edge_name(i) for i, sd in enumerate(self.system.fast_edge_data) if sd.get('agent_override') != 'normal']
        return {'closed_stations': len(closed_stations), 'suspended_lines': len(suspended_lines), 'slowed_edges': len(slowed_edges), 'blocked_edges': len(blocked_edges), 'closed_station_names': '；'.join(closed_stations), 'suspended_line_ids': '；'.join(suspended_lines)}

class PassengerAgent:
    """Compare rule and LLM decisions using the same passenger and journey context."""
    PROFILE_PURPOSES = ['通勤/上学', '商务/工作事务', '就医/照护', '回家', '休闲/旅游', '个人事务/其他']

    def __init__(self, pid, origin_st, dest_st, start_time_min=0):
        self.pid = pid
        self.origin = clean_station_name(origin_st)
        self.dest = clean_station_name(dest_st)
        self.start_time_min = int(start_time_min)
        self.status = 'created'
        self.action = 'none'
        self.initial_route_plan = {}
        self.current_route_plan = {}
        self.final_route_plan = {}
        self.reroute_count = 0
        self.origin_access_intensity = 0.0
        self.origin_access_speed_factor = 1.0
        profile = self._generate_profile(pid)
        self.age = profile['Age']
        self.gender = profile['Gender']
        self.trip_purpose = profile['Trip_Purpose']
        self.ocean_O = profile['OCEAN_O']
        self.ocean_C = profile['OCEAN_C']
        self.ocean_E = profile['OCEAN_E']
        self.ocean_A = profile['OCEAN_A']
        self.ocean_N = profile['OCEAN_N']
        self.risk_preference = profile['Risk_Preference']
        self.decision_mode = PASSENGER_DECISION_MODE
        self.llm_selected = False
        self.rule_action = 'none'
        self.rule_action_raw = 'none'
        self.rule_status = 'created'
        self.rule_decision_context = {}
        self.llm_action = ''
        self.llm_valid = False
        self.llm_fallback_used = False
        self.llm_reason = ''
        self.llm_risk_perception = ''
        self.llm_delay_perception = ''
        self.llm_risk_perception_code = np.nan
        self.llm_delay_perception_code = np.nan
        self.llm_feeling_score = np.nan
        self.llm_feeling_score_raw = ''
        self.llm_raw_response = ''
        self.llm_error_message = ''
        self.final_action = 'none'
        self.action_diff = False
        self.od_sample_mode = globals().get('PASSENGER_SAMPLE_MODE', 'flow_random')
        self.od_sample_group = 'unassigned'

    @staticmethod
    def _generate_profile(pid):
        seed = int(LLM_RANDOM_SEED) + int(pid) * 1009
        rng = np.random.default_rng(seed)
        age = int(rng.integers(12, 81))
        gender = str(rng.choice(['M', 'F']))
        if age <= 24:
            purposes = ['通勤/上学', '回家', '休闲/旅游', '就医/照护', '个人事务/其他']
            probs = [0.45, 0.2, 0.25, 0.03, 0.07]
        elif age <= 60:
            purposes = ['通勤/上学', '商务/工作事务', '就医/照护', '回家', '休闲/旅游', '个人事务/其他']
            probs = [0.1, 0.43, 0.06, 0.18, 0.1, 0.13]
        else:
            purposes = ['商务/工作事务', '就医/照护', '回家', '休闲/旅游', '个人事务/其他']
            probs = [0.05, 0.2, 0.3, 0.2, 0.25]
        return {'Age': age, 'Gender': gender, 'Trip_Purpose': str(rng.choice(purposes, p=probs)), 'OCEAN_O': int(rng.integers(1, 6)), 'OCEAN_C': int(rng.integers(1, 6)), 'OCEAN_E': int(rng.integers(1, 6)), 'OCEAN_A': int(rng.integers(1, 6)), 'OCEAN_N': int(rng.integers(1, 6)), 'Risk_Preference': int(rng.integers(1, 6))}

    @staticmethod
    def _path_text(plan):
        if not isinstance(plan, dict) or not plan.get('reachable'):
            return ''
        return ' -> '.join(plan.get('station_path', []))

    @staticmethod
    def _duration_value(value):
        try:
            value = float(value)
            return value if np.isfinite(value) else np.nan
        except _sr.SubmissionStop:
            raise
        except Exception:
            return np.nan

    @staticmethod
    def _json_safe(value):
        if isinstance(value, dict):
            return {str(k): PassengerAgent._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [PassengerAgent._json_safe(v) for v in value]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating, float)):
            v = float(value)
            return v if np.isfinite(v) else None
        if isinstance(value, (np.bool_, bool)):
            return bool(value)
        return value

    @staticmethod
    def _normalize_action(action):
        action = str(action or '')
        if action.startswith('abandon'):
            return 'abandon_trip'
        if action in LLM_ALLOWED_ACTIONS:
            return action
        return 'abandon_trip'

    def _build_rule_context(self, system, sim_min):
        initial_plan = self.initial_route_plan or {}
        current_plan = self.current_route_plan or {}
        baseline_reachable = bool(initial_plan.get('reachable'))
        current_reachable = bool(current_plan.get('reachable')) and np.isfinite(self._duration_value(current_plan.get('current_duration_min', np.nan)))
        original_disturbed = bool(baseline_reachable and system.route_has_disturbance(initial_plan))
        current_disturbed = bool(current_reachable and system.route_has_disturbance(current_plan))
        original_hard_disrupted = bool(baseline_reachable and system.route_has_hard_disruption(initial_plan))
        current_hard_disrupted = bool(current_reachable and system.route_has_hard_disruption(current_plan))
        original_route_current_feasible = bool(baseline_reachable and (not original_hard_disrupted))
        current_route_current_feasible = bool(current_reachable and (not current_hard_disrupted))
        original_hard_disruption_summary = system.route_hard_disruption_summary(initial_plan) if baseline_reachable else '原路线不可达'
        current_hard_disruption_summary = system.route_hard_disruption_summary(current_plan) if current_reachable else '当前路线不可达'
        route_equivalent = bool(baseline_reachable and current_route_current_feasible and system.route_plans_equivalent(initial_plan, current_plan))
        has_alternative = bool(baseline_reachable and current_route_current_feasible and (not route_equivalent))
        canonical_continue_action = ''
        allowed_actions = ['abandon_trip']
        if current_route_current_feasible:
            if not baseline_reachable:
                canonical_continue_action = 'continue_current_shortest_route'
                allowed_actions = [canonical_continue_action, 'abandon_trip']
            elif has_alternative:
                if original_route_current_feasible:
                    allowed_actions = ['continue_original_route', 'reroute_to_shortest_time', 'abandon_trip']
                else:
                    allowed_actions = ['reroute_to_shortest_time', 'abandon_trip']
            else:
                if not original_route_current_feasible:
                    canonical_continue_action = 'continue_current_shortest_route'
                elif self.rule_action in {'continue_original_route', 'continue_current_shortest_route'}:
                    canonical_continue_action = self.rule_action
                elif original_disturbed or current_disturbed:
                    canonical_continue_action = 'continue_current_shortest_route'
                else:
                    canonical_continue_action = 'continue_original_route'
                allowed_actions = [canonical_continue_action, 'abandon_trip']
        normal_duration = self._duration_value(initial_plan.get('normal_duration_min', np.nan))
        current_duration = self._duration_value(current_plan.get('current_duration_min', np.nan))
        if np.isfinite(current_duration) and np.isfinite(normal_duration):
            estimated_delay = max(0.0, current_duration - normal_duration)
        else:
            estimated_delay = np.nan
        context = {'passenger_id': self.pid, 'sim_min': int(sim_min), 'origin': self.origin, 'destination': self.dest, 'profile': {'Age': self.age, 'Gender': self.gender, 'Trip_Purpose': self.trip_purpose, 'OCEAN_O': self.ocean_O, 'OCEAN_C': self.ocean_C, 'OCEAN_E': self.ocean_E, 'OCEAN_A': self.ocean_A, 'OCEAN_N': self.ocean_N, 'Risk_Preference': self.risk_preference}, 'baseline_route_reachable': baseline_reachable, 'current_route_reachable': current_route_current_feasible, 'original_route_passes_disturbance': original_disturbed, 'current_route_passes_disturbance': current_disturbed, 'original_route_current_feasible': original_route_current_feasible, 'original_route_hard_disrupted': original_hard_disrupted, 'current_route_current_feasible': current_route_current_feasible, 'current_route_hard_disrupted': current_hard_disrupted, 'original_hard_disruption_summary': original_hard_disruption_summary, 'current_hard_disruption_summary': current_hard_disruption_summary, 'route_plans_equivalent': route_equivalent, 'canonical_continue_action': canonical_continue_action, 'has_available_alternative_route': has_alternative, 'original_route': self._path_text(initial_plan), 'current_available_route': self._path_text(current_plan), 'normal_duration_min': normal_duration, 'current_duration_min': current_duration, 'estimated_delay_min': estimated_delay, 'original_affected_lines': initial_plan.get('affected_lines', []), 'original_affected_stations': initial_plan.get('affected_stations', []), 'original_affected_sections': initial_plan.get('affected_sections', []), 'current_affected_lines': current_plan.get('affected_lines', []), 'current_affected_stations': current_plan.get('affected_stations', []), 'current_affected_sections': current_plan.get('affected_sections', []), 'impact_summary': current_plan.get('impact_summary', initial_plan.get('impact_summary', '')), 'disturbance_inputs': DISTURBANCE_EDGES, 'rule_action_raw': self.rule_action_raw, 'rule_action': self.rule_action, 'rule_status': self.rule_status, 'allowed_actions_for_llm': allowed_actions, 'unreachable_notice': '' if current_reachable else '当前没有可达路线，LLM 只能选择 abandon_trip。'}
        return self._json_safe(context)

    def _run_original_rule_decision(self, system, sim_min):
        self.initial_route_plan = system.plan_passenger_route(self.origin, self.dest, sim_min, weight_mode='baseline')
        self.current_route_plan = system.plan_passenger_route(self.origin, self.dest, sim_min, weight_mode='current')
        if not self.initial_route_plan.get('reachable'):
            self.status = 'abandoned'
            self.action = 'abandon_no_baseline_route'
            self.final_route_plan = self.initial_route_plan
            return
        disturbed = system.route_has_disturbance(self.initial_route_plan)
        first_boarding = next((rec for rec in self.initial_route_plan.get('edge_records', []) if rec.get('type') == 'boarding'), None)
        if first_boarding:
            self.origin_access_intensity = float(first_boarding.get('disturbance_intensity', 0.0))
            self.origin_access_speed_factor = float(first_boarding.get('speed_factor', 1.0))
        if not disturbed:
            self.status = 'finished'
            self.action = 'continue_original_route'
            self.final_route_plan = self.initial_route_plan
            return
        candidate = self.current_route_plan
        if not candidate.get('reachable') or not np.isfinite(candidate.get('current_duration_min', float('inf'))):
            self.status = 'abandoned'
            self.action = 'abandon_no_available_route'
            self.final_route_plan = candidate
            return
        self.final_route_plan = candidate
        self.status = 'finished'
        if system.route_plans_equivalent(self.initial_route_plan, candidate):
            self.action = 'continue_current_shortest_route'
        else:
            self.action = 'reroute_to_shortest_time'
            self.reroute_count = 1

    def decide(self, system, sim_min, use_llm=False, decision_mode=None, llm_call_log=None):
        self.decision_mode = decision_mode or PASSENGER_DECISION_MODE
        self.llm_selected = bool(use_llm)
        self._run_original_rule_decision(system, sim_min)
        self.rule_action_raw = self.action
        self.rule_action = self._normalize_action(self.action)
        self.rule_status = self.status
        self.rule_decision_context = self._build_rule_context(system, sim_min)
        self.final_action = self.rule_action
        if self.llm_selected:
            llm_result = self.decide_with_llm(system, sim_min, self.rule_decision_context, llm_call_log=llm_call_log)
            self.llm_action = llm_result['action_choice']
            self.llm_valid = bool(llm_result['valid'])
            self.llm_fallback_used = bool(llm_result['fallback_used'])
            self.llm_reason = llm_result.get('reason', '')
            self.llm_risk_perception = llm_result.get('risk_perception_level', 'none')
            self.llm_delay_perception = llm_result.get('delay_perception_level', 'none')
            self.llm_risk_perception_code = LLM_PERCEPTION_LEVEL_CODE.get(self.llm_risk_perception, np.nan)
            self.llm_delay_perception_code = LLM_PERCEPTION_LEVEL_CODE.get(self.llm_delay_perception, np.nan)
            self.llm_feeling_score = llm_result.get('feeling_score', np.nan)
            self.llm_feeling_score_raw = llm_result.get('feeling_score_raw', '')
            self.llm_raw_response = llm_result.get('raw_response', '')
            self.llm_error_message = llm_result.get('error_message', '')
            self.action_diff = bool(self.llm_valid and self.llm_action != self.rule_action)
            if self.decision_mode == 'llm':
                self.final_action = self.llm_action
                self._apply_final_action_from_choice(system, self.final_action)
            else:
                self.final_action = self.rule_action
        else:
            self.llm_action = ''
            self.llm_valid = False
            self.llm_fallback_used = False
            self.llm_risk_perception = ''
            self.llm_delay_perception = ''
            self.llm_risk_perception_code = np.nan
            self.llm_delay_perception_code = np.nan
            self.action_diff = False

    def _apply_final_action_from_choice(self, system, action_choice):
        action_choice = self._normalize_action(action_choice)
        self.final_action = action_choice
        self.action = action_choice
        self.reroute_count = 1 if action_choice == 'reroute_to_shortest_time' else 0
        if action_choice == 'abandon_trip':
            self.status = 'abandoned'
            plan = dict(self.current_route_plan or self.initial_route_plan or {})
            plan['reachable'] = False
            plan['station_path'] = []
            plan['impact_summary'] = '乘客选择放弃行程'
            self.final_route_plan = plan
        elif action_choice == 'continue_original_route':
            self.status = 'finished'
            self.final_route_plan = self.initial_route_plan
        elif action_choice in {'continue_current_shortest_route', 'reroute_to_shortest_time'}:
            self.status = 'finished'
            self.final_route_plan = self.current_route_plan
        else:
            self.status = self.rule_status
            self.action = self.rule_action_raw
            self.final_route_plan = self.final_route_plan or self.current_route_plan or self.initial_route_plan

    def _persona_context(self):
        gender_text = {'F': '女性', 'M': '男性'}.get(str(self.gender), str(self.gender))
        if self.age <= 24:
            age_style = '年轻乘客，行动快，也更容易受当下情绪和赶时间影响'
        elif self.age <= 44:
            age_style = '中青年乘客，通常会在效率、稳定性和安全之间做取舍'
        elif self.age <= 64:
            age_style = '中年乘客，更在意行程可控和少折腾'
        else:
            age_style = '年长乘客，更在意安全、换乘负担和路线确定性'
        purpose_style_map = {'通勤/上学': '这趟是通勤或上学，我会在意迟到，也会担心路上失控', '商务/工作事务': '这趟涉及工作安排，我会更在意准时、体面和不出岔子', '就医/照护': '这趟和就医或照护有关，我会把安全和确定到达放在前面', '回家': '我只是想顺利回家，会更看重确定性和少折腾', '休闲/旅游': '这趟没那么赶，但我不想把时间和心情都耗在路上', '个人事务/其他': '这趟是个人事务，我会看事情紧不紧急，再权衡时间和安全'}
        purpose_style = purpose_style_map.get(str(self.trip_purpose), '我会按这趟出行的实际紧迫程度来权衡时间和安全')
        anxious_style = '很容易焦虑，会反复担心被困、绕远和耽误事' if self.ocean_N >= 4 else '情绪基本稳定，但风险摆在眼前时会明显紧张' if self.ocean_N >= 2 else '遇到突发情况也比较冷静'
        planning_style = '习惯先确认路线和官方信息，再做决定' if self.ocean_C >= 4 else '会大致权衡时间、安全和麻烦程度' if self.ocean_C >= 2 else '更容易凭直觉和当下感受马上行动'
        change_style = '能接受临时改道和多换乘，只要结果更稳' if self.ocean_O >= 4 else '可以接受必要调整，但不喜欢无谓折腾' if self.ocean_O >= 2 else '不喜欢临时改变原计划，容易觉得改道麻烦'
        social_style = '会留意周围乘客和工作人员反应' if self.ocean_A >= 4 or self.ocean_E >= 4 else '主要关注自己的安全、时间和能否顺利到达'
        risk_style = '我明显更看重安全和确定性，宁愿慢一点' if self.risk_preference <= 2 else '我会在安全和时间之间折中' if self.risk_preference == 3 else '我更能接受一点风险或不确定性来少绕路、少折腾'
        return f'{self.age}岁，{gender_text}，出行目的：{self.trip_purpose}。{age_style}；{purpose_style}。情绪特点：{anxious_style}；计划性：{planning_style}；改道态度：{change_style}；社会线索：{social_style}；风险偏好：{risk_style}。'

    def _human_readable_context(self, context):
        normal_min = context.get('normal_duration_min')
        current_min = context.get('current_duration_min')
        delay_min = context.get('estimated_delay_min')

        def fmt_min(value):
            try:
                value = float(value)
                if np.isfinite(value):
                    return f'{value:.1f}分钟'
            except _sr.SubmissionStop:
                raise
            except Exception:
                pass
            return '不可用'
        if context.get('current_route_reachable', False):
            reach_text = '当前仍有可达路线。'
        else:
            reach_text = '当前没有可达路线，只能选择放弃地铁：放弃前往目的地，或放弃使用地铁改乘其他交通工具。'
        if context.get('original_route_hard_disrupted', False):
            original_feasible_text = '原路线当前不可通行：' + str(context.get('original_hard_disruption_summary', ''))
        elif context.get('original_route_passes_disturbance', False):
            original_feasible_text = '原路线经过受扰动边，但代码没有判定为硬不可通行。'
        else:
            original_feasible_text = '原路线未经过受扰动边，当前仍可按原计划走。'
        alternative_text = '系统找到了不同于原路线的当前可用替代路线。' if context.get('has_available_alternative_route') else '系统没有找到不同于原路线的可用替代路线。'
        return {'passenger_profile': self._persona_context(), 'origin': self.origin, 'destination': self.dest, 'original_route': context.get('original_route', ''), 'current_available_route': context.get('current_available_route', ''), 'reachability_summary': reach_text, 'original_route_feasibility': original_feasible_text, 'current_route_feasibility': '当前可用路线可通行。' if context.get('current_route_current_feasible') else str(context.get('current_hard_disruption_summary', '当前路线不可达')), 'alternative_summary': alternative_text, 'normal_duration': fmt_min(normal_min), 'current_available_route_duration': fmt_min(current_min), 'estimated_delay_for_current_available_route': fmt_min(delay_min), 'duration_note': 'estimated_delay 只表示当前可用路线相对正常基准的延误，不代表硬中断原路线仍可继续走。', 'impact_summary': context.get('impact_summary', ''), 'affected_lines': context.get('current_affected_lines', []), 'affected_stations': context.get('current_affected_stations', []), 'affected_sections': context.get('current_affected_sections', []), 'allowed_actions_for_llm': context.get('allowed_actions_for_llm', []), 'action_meaning': {'continue_original_route': '仅当原路线当前可通行时，继续按原始路线走', 'continue_current_shortest_route': '接受当前已经可用的路线继续走', 'reroute_to_shortest_time': '切换到代码给出的当前最短可用替代路线', 'abandon_trip': '放弃地铁：可以是放弃前往目的地，也可以是放弃使用地铁、改用其他交通工具'}}

    def _prompt_context_summary(self, context):
        return f'PID={self.pid}; OD={self.origin}->{self.dest}; current_reachable={context.get('current_route_reachable')}; original_disturbed={context.get('original_route_passes_disturbance')}; current_disturbed={context.get('current_route_passes_disturbance')}; original_feasible={context.get('original_route_current_feasible')}; original_hard={context.get('original_route_hard_disrupted')}; rule_action={context.get('rule_action')}; allowed={','.join(context.get('allowed_actions_for_llm', []))}'

    def decide_with_llm(self, system, sim_min, rule_decision_context, llm_call_log=None):
        context = self._json_safe(rule_decision_context)
        human_context = self._human_readable_context(context)
        system_prompt = '你现在不是系统分析器，而是一名真实的上海地铁乘客。请站在乘客本人的第一人称视角做决定，可以犹豫、烦躁、怕麻烦、赶时间、担心安全，也可以很放松、不关心不在乎、无所谓，也可以临时改变主意。在 allowed_actions_for_llm 允许的动作内，必须让年龄、性别、出行目的、人格画像、风险偏好和当下处境真正影响选择。如果多个动作都可行，且有赶时间等紧迫出行目的，可以做出更激进的选择；如果时间不紧迫或需要安全，选择也可以保守但不能为了制造差异而违反可达性约束或编造事实。abandon_trip 表示“放弃地铁”，包括两种想法：放弃前往目的地；或放弃使用地铁、改乘出租车/网约车/公交/步行等其他交通方式。只要你有这两类想法，action_choice 都必须选 abandon_trip。你只能根据事实选择动作和解释感受；线路、车站、路线、耗时、扰动状态都已由手机导航和代码计算，不得编造新路线、新车站、新区间、新灾害或新耗时。如果用户事实说明当前没有可达路线，只能选择 abandon_trip。如果原路线当前不可通行，不能选择 continue_original_route，也不能说只是延误能接受。如果没有不同于原路线的可用替代路线，不能选择 reroute_to_shortest_time。estimated_delay 只对应当前可用路线相对正常基准的延误，不要把它说成硬中断原路线的可接受延误。action_choice 必须严格从用户输入的 allowed_actions_for_llm 列表中选择。reason 必须像乘客当下的内心 OS 或脱口而出的想法，使用第一人称视角，50到120字；语气和用词要符合年龄段、性别、性格、风险偏好、出行目的和当下压力，可以更口语、更有生活感。不要像心理医生分析自己，也不要机械复述规则。不要写后台变量名、代码字段名、人格分数或 JSON 字段名。risk_perception_level 和 delay_perception_level 只能从 none, low, medium, high, critical 中选择。feeling_score 只能是 1、2、3、4、5 中的一个整数，不是 10 分制或 100 分制，不要输出小数。只返回严格 JSON，不要 Markdown，不要代码块。必须包含字段：action_choice, reason, risk_perception_level, delay_perception_level, feeling_score。不要输出任何置信度字段或其他额外字段。'
        user_content = json.dumps(human_context, ensure_ascii=False, separators=(',', ':'))
        prompt_summary = self._prompt_context_summary(context)
        raw_response = ''
        parsed = {}
        parsed_action = ''
        valid = False
        fallback_used = False
        error_message = ''
        attempt_errors = []
        prompt_tokens = 0
        completion_tokens = 0
        attempted_models = []
        model_used = ''
        max_attempts = max(1, int(LLM_MAX_MODEL_RETRIES))
        for _ in range(max_attempts):
            candidate_model = select_llm_passenger_model(excluded_models=attempted_models)
            if not candidate_model:
                break
            attempted_models.append(candidate_model)
            try:
                candidate_raw, p_tok, c_tok = call_llm_passenger_json(system_prompt=system_prompt, user_content=user_content, model=candidate_model, temperature=LLM_TEMPERATURE, timeout_sec=LLM_TIMEOUT_SEC)
                raw_response = candidate_raw
                prompt_tokens += int(p_tok or 0)
                completion_tokens += int(c_tok or 0)
                candidate_parsed = json.loads(str(candidate_raw).strip())
                candidate_action = str(candidate_parsed.get('action_choice', ''))
                candidate_valid, candidate_error = validate_llm_passenger_decision(candidate_parsed, context)
                if candidate_valid:
                    parsed = candidate_parsed
                    parsed_action = candidate_action
                    valid = True
                    model_used = candidate_model
                    error_message = ''
                    break
                attempt_errors.append(f'{candidate_model}: {candidate_error}')
                mark_llm_passenger_model_cooldown(candidate_model, cooldown_sec=LLM_VALIDATION_FAILURE_COOLDOWN_SEC)
            except _sr.SubmissionStop:
                raise
            except Exception as exc:
                err = f'{type(exc).__name__}: {exc}'
                attempt_errors.append(f'{candidate_model}: {err}')
                mark_llm_passenger_model_cooldown(candidate_model, cooldown_sec=llm_cooldown_seconds_for_exception(exc))
        if not valid:
            fallback_used = True
            error_message = ' | '.join(attempt_errors) if attempt_errors else '没有可用模型返回合法 LLM 决策。'
            if not model_used:
                model_used = attempted_models[-1] if attempted_models else LLM_MODEL
        if fallback_used:
            result = {'action_choice': context.get('rule_action', 'abandon_trip'), 'reason': 'LLM 输出无效或调用失败，使用规则决策兜底。', 'risk_perception_level': 'none', 'delay_perception_level': 'none', 'feeling_score': np.nan, 'feeling_score_raw': str(parsed.get('feeling_score', '')) if isinstance(parsed, dict) else '', 'valid': False, 'fallback_used': True, 'raw_response': raw_response, 'error_message': error_message}
        else:
            normalized_feeling, feeling_raw, _ = normalize_llm_feeling_score(parsed.get('feeling_score'))
            result = {'action_choice': parsed_action, 'reason': str(parsed.get('reason', '')), 'risk_perception_level': str(parsed.get('risk_perception_level', '')), 'delay_perception_level': str(parsed.get('delay_perception_level', '')), 'feeling_score': normalized_feeling, 'feeling_score_raw': feeling_raw, 'valid': True, 'fallback_used': False, 'raw_response': raw_response, 'error_message': ''}
        if llm_call_log is not None:
            llm_call_log.append({'Passenger_ID': self.pid, 'Prompt_Context': prompt_summary, 'Raw_Response': raw_response, 'Parsed_Action': parsed_action, 'Valid': bool(valid), 'Fallback_Used': bool(fallback_used), 'Error_Message': error_message if fallback_used else ' | '.join(attempt_errors), 'Model': model_used or (attempted_models[-1] if attempted_models else LLM_MODEL), 'Attempted_Models': ';'.join(attempted_models), 'Attempt_Count': int(len(attempted_models)), 'Model_Fallback_Used': False, 'Prompt_Tokens': int(prompt_tokens or 0), 'Completion_Tokens': int(completion_tokens or 0)})
        if not result['valid']:
            raise _sr.SubmissionStop('No valid single-model response; progress has been saved.')
        return result

    def to_record(self):
        final_plan = self.final_route_plan or {}
        initial_plan = self.initial_route_plan or {}
        current_plan = self.current_route_plan or {}
        ctx = self.rule_decision_context or {}
        return {'PID': self.pid, 'Origin': self.origin, 'Dest': self.dest, 'Start_Time_Min': self.start_time_min, 'Status': self.status, 'Action': self.action, 'Reroute_Count': self.reroute_count, 'Origin_Access_Intensity': self.origin_access_intensity, 'Origin_Access_Speed_Factor': self.origin_access_speed_factor, 'Initial_Route': self._path_text(initial_plan), 'Current_Route': self._path_text(current_plan), 'Final_Route': self._path_text(final_plan), 'Initial_Normal_Min': self._duration_value(initial_plan.get('normal_duration_min', np.nan)), 'Current_Route_Current_Min': self._duration_value(current_plan.get('current_duration_min', np.nan)), 'Final_Current_Min': self._duration_value(final_plan.get('current_duration_min', np.nan)), 'Estimated_Delay_Min': ctx.get('estimated_delay_min', np.nan), 'Final_Impact_Summary': final_plan.get('impact_summary', ''), 'Rule_Reachable': bool(ctx.get('current_route_reachable', False)), 'Rule_Route_Disturbed': bool(ctx.get('original_route_passes_disturbance', False)), 'Rule_Current_Route_Disturbed': bool(ctx.get('current_route_passes_disturbance', False)), 'Original_Route_Current_Feasible': bool(ctx.get('original_route_current_feasible', False)), 'Original_Route_Hard_Disrupted': bool(ctx.get('original_route_hard_disrupted', False)), 'Original_Hard_Disruption_Summary': ctx.get('original_hard_disruption_summary', ''), 'Rule_Continue_Original': self.rule_action == 'continue_original_route', 'Rule_Continue_Current_Shortest': self.rule_action == 'continue_current_shortest_route', 'Rule_Reroute_To_Shortest': self.rule_action == 'reroute_to_shortest_time', 'Rule_Abandon': self.rule_action == 'abandon_trip', 'Rule_Normal_Min': ctx.get('normal_duration_min', np.nan), 'Rule_Current_Min': ctx.get('current_duration_min', np.nan), 'Rule_Estimated_Delay_Min': ctx.get('estimated_delay_min', np.nan), 'Rule_Impact_Summary': ctx.get('impact_summary', ''), 'OD_Sample_Mode': getattr(self, 'od_sample_mode', ''), 'OD_Sample_Group': getattr(self, 'od_sample_group', ''), 'Decision_Mode': self.decision_mode, 'LLM_Selected': self.llm_selected, 'Age': self.age, 'Gender': self.gender, 'Trip_Purpose': self.trip_purpose, 'OCEAN_O': self.ocean_O, 'OCEAN_C': self.ocean_C, 'OCEAN_E': self.ocean_E, 'OCEAN_A': self.ocean_A, 'OCEAN_N': self.ocean_N, 'Risk_Preference': self.risk_preference, 'Rule_Action': self.rule_action, 'Rule_Action_Raw': self.rule_action_raw, 'LLM_Action': self.llm_action, 'Final_Action': self.final_action, 'Action_Diff': self.action_diff, 'Rule_Status': self.rule_status, 'LLM_Valid': self.llm_valid, 'LLM_Fallback_Used': self.llm_fallback_used, 'LLM_Reason': self.llm_reason, 'LLM_Risk_Perception': self.llm_risk_perception, 'LLM_Delay_Perception': self.llm_delay_perception, 'LLM_Risk_Perception_Code': self.llm_risk_perception_code, 'LLM_Delay_Perception_Code': self.llm_delay_perception_code, 'LLM_Feeling_Score': self.llm_feeling_score, 'LLM_Feeling_Score_Raw': self.llm_feeling_score_raw}

class TrainAgent:
    """Represent a train's departure, dwelling, running, waiting and arrival state."""

    def __init__(self, train_id, service_id, line_id, direction, departure_abs_sec, route_segments):
        
        self.train_id = train_id
        self.service_id = service_id
        self.line_id = str(line_id)
        self.direction = direction
        self.departure_abs_sec = int(departure_abs_sec)
        self.route_segments = route_segments
        self.segment_idx = 0
        self.status = 'scheduled'
        self.wait_reason = ''
        self.progress = 0.0
        self.elapsed_on_segment = 0.0
        self.dwell_remaining_sec = 0
        self.current_station = route_segments[0]['from_station'] if route_segments else ''
        self.current_edge_name = ''
        self.current_edge_key = None
        self.current_segment = None
        self.x = route_segments[0]['from_pos'][1] if route_segments else np.nan
        self.y = route_segments[0]['from_pos'][0] if route_segments else np.nan

    def is_active(self, now_abs_sec):
        """Check whether a train has departed and has not yet completed its service."""
        return self.status not in {'finished', 'cancelled'} and now_abs_sec >= self.departure_abs_sec

    def _set_at_station(self, station_name, pos):
        """Set train position to the station platform coordinates."""
        self.current_station = station_name
        self.current_edge_name = ''
        self.current_edge_key = None
        self.current_segment = None
        self.progress = 0.0
        self.x = pos[1]
        self.y = pos[0]

    def _can_enter_segment(self, segment, occupied_directed_edges):
        """Check accessibility and same-direction occupancy before entering a section."""
        if segment['edge_status'] in {'suspended', 'closed', 'train_blocked'} or segment['speed_factor'] <= 0:
            return (False, 'blocked_by_rule_agent')
        if segment['directed_edge_key'] in occupied_directed_edges:
            return (False, 'safe_spacing_wait')
        return (True, '')

    def step(self, now_abs_sec, dt_sec, occupied_directed_edges):
        """Advance the train state by one simulation step, including dwell and turnaround waits."""
        if self.status == 'finished':
            return
        if now_abs_sec < self.departure_abs_sec:
            self.status = 'scheduled'
            return
        if not self.route_segments:
            self.status = 'cancelled'
            return
        if self.status == 'scheduled':
            self.status = 'dwell'
            self.dwell_remaining_sec = DWELL_SEC
            first = self.route_segments[0]
            self._set_at_station(first['from_station'], first['from_pos'])
        if self.status in {'dwell', 'terminal_dwell'}:
            self.dwell_remaining_sec = max(0, self.dwell_remaining_sec - dt_sec)
            if self.dwell_remaining_sec > 0:
                return
            if self.status == 'terminal_dwell':
                self.status = 'finished'
                return
            if self.segment_idx >= len(self.route_segments):
                self.status = 'terminal_dwell'
                self.dwell_remaining_sec = TERMINAL_DWELL_SEC
                return
            segment = self.route_segments[self.segment_idx]
            can_enter, reason = self._can_enter_segment(segment, occupied_directed_edges)
            if not can_enter:
                self.status = 'dwell'
                self.wait_reason = reason
                self._set_at_station(segment['from_station'], segment['from_pos'])
                return
            self.status = 'running'
            self.wait_reason = ''
            self.current_segment = segment
            self.current_edge_key = segment['directed_edge_key']
            self.current_edge_name = segment['edge_name']
            self.elapsed_on_segment = 0.0
            self.progress = 0.0
            occupied_directed_edges.add(segment['directed_edge_key'])
        if self.status == 'running':
            segment = self.current_segment
            if segment is None:
                self.status = 'dwell'
                return
            runtime = max(float(segment['runtime_sec']), 1.0)
            self.elapsed_on_segment += dt_sec
            self.progress = min(1.0, self.elapsed_on_segment / runtime)
            lat1, lon1 = segment['from_pos']
            lat2, lon2 = segment['to_pos']
            self.y = lat1 + (lat2 - lat1) * self.progress
            self.x = lon1 + (lon2 - lon1) * self.progress
            self.current_station = ''
            if self.progress >= 1.0:
                self.segment_idx += 1
                self._set_at_station(segment['to_station'], segment['to_pos'])
                if self.segment_idx >= len(self.route_segments):
                    self.status = 'terminal_dwell'
                    self.dwell_remaining_sec = TERMINAL_DWELL_SEC
                else:
                    self.status = 'dwell'
                    self.dwell_remaining_sec = DWELL_SEC

    def position_record(self, rel_sec):
        """Return train position, state and waiting reason."""
        return {'Time_Sec': int(rel_sec), 'Train_ID': self.train_id, 'Service_ID': self.service_id, 'Line_ID': self.line_id, 'Direction': self.direction, 'Status': self.status, 'Current_Station': self.current_station, 'Edge_Name': self.current_edge_name, 'Segment_Index': int(self.segment_idx), 'Progress': float(self.progress), 'Lon': float(self.x) if np.isfinite(self.x) else np.nan, 'Lat': float(self.y) if np.isfinite(self.y) else np.nan, 'Wait_Reason': self.wait_reason}

class TrainSimulationEngine:
    """Generate services, trains, positions and section occupancy from schedules."""

    def __init__(self, system, day_type='Weekday'):
        
        self.system = system
        self.day_type = day_type
        self.service_patterns = []
        self.trains = []
        self.timetable_rows = []
        self.position_rows = []
        self.edge_count_rows = []
        self.invalid_patterns = []
        self.segment_lookup = {}

    @staticmethod
    def _time_to_sec(value):
        """Convert a time value to seconds within a day."""
        if hasattr(value, 'hour'):
            return int(value.hour) * 3600 + int(value.minute) * 60 + int(getattr(value, 'second', 0))
        text = str(value)
        parts = text.split(':')
        if len(parts) < 2:
            return 0
        hour = int(float(parts[0]))
        minute = int(float(parts[1]))
        second = int(float(parts[2])) if len(parts) > 2 else 0
        return hour * 3600 + minute * 60 + second

    def _station_pos(self, station_name):
        """Look up station longitude and latitude."""
        node = f'{station_name}_车站层'
        if self.system.G.has_node(node):
            return tuple(self.system.G.nodes[node]['pos'])
        for n, data in self.system.G.nodes(data=True):
            if self.system.station_name_from_node(n) == station_name:
                return tuple(data['pos'])
        return (np.nan, np.nan)

    def _line_graph(self, line_id):
        """Build a line-layer subgraph for branch routing."""
        graph = nx.Graph()
        for edge_idx, (u, v, k) in enumerate(self.system.edge_list):
            sd = self.system.fast_edge_data[edge_idx]
            if sd['type'] != 'riding' or str(sd.get('line_id')) != str(line_id):
                continue
            runtime = float(sd.get('base_runtime_sec', self.system.base_edge_minutes(edge_idx, self.system.sim_start_min) * 60.0))
            graph.add_edge(u, v, weight=runtime, edge_idx=edge_idx)
        return graph

    def _segment_from_stations(self, line_id, from_station, to_station, edge_idx=None, virtual=False):
        """Construct an operational segment from adjacent or virtual stations."""
        from_pos = self._station_pos(from_station)
        to_pos = self._station_pos(to_station)
        distance = haversine_km(from_pos[0], from_pos[1], to_pos[0], to_pos[1]) if np.isfinite(from_pos[0]) and np.isfinite(to_pos[0]) else 0.0
        base_runtime = max(MIN_SEGMENT_RUNTIME_SEC, distance * TRACK_DETOUR_FACTOR / TRAIN_SPEED_KMH * 3600.0)
        speed_factor = 1.0
        edge_status = 'normal'
        intensity = 0.0
        if edge_idx is not None:
            sd = self.system.fast_edge_data[edge_idx]
            base_runtime = float(sd.get('base_runtime_sec', base_runtime))
            speed_factor = float(sd.get('speed_factor', 1.0))
            edge_status = sd.get('agent_override', 'normal')
            intensity = float(sd.get('disturbance_intensity', 0.0))
        runtime = float('inf') if speed_factor <= 0 or edge_status in {'suspended', 'closed', 'train_blocked'} else base_runtime / max(speed_factor, 1e-06)
        edge_name = f'{line_id}|{from_station}|{to_station}'
        directed_edge_key = (str(line_id), from_station, to_station)
        undirected_edge_key = (str(line_id), tuple(sorted((from_station, to_station))))
        return {'line_id': str(line_id), 'from_station': from_station, 'to_station': to_station, 'from_pos': from_pos, 'to_pos': to_pos, 'edge_idx': edge_idx, 'edge_name': edge_name, 'directed_edge_key': directed_edge_key, 'undirected_edge_key': undirected_edge_key, 'distance_km': distance, 'base_runtime_sec': base_runtime, 'runtime_sec': runtime, 'speed_factor': speed_factor, 'edge_status': edge_status, 'disturbance_intensity': intensity, 'virtual': bool(virtual)}

    def _segments_from_node_path(self, line_id, node_path, graph):
        """Convert a line-layer path to operational train segments."""
        segments = []
        for u, v in zip(node_path[:-1], node_path[1:]):
            data = graph.get_edge_data(u, v) or {}
            edge_idx = data.get('edge_idx')
            from_station = self.system.station_name_from_node(u)
            to_station = self.system.station_name_from_node(v)
            segments.append(self._segment_from_stations(line_id, from_station, to_station, edge_idx=edge_idx, virtual=False))
        return segments

    def _ring_segments(self, line_id, reverse=False):
        """Construct clockwise or anticlockwise ring services, including a virtual closure if required."""
        stations = list(self.system.line_stations_index.get(str(line_id), []))
        if not stations:
            return []
        if reverse:
            stations = list(reversed(stations))
        graph = self._line_graph(line_id)
        segments = []
        for a, b in zip(stations[:-1], stations[1:]):
            node_a = f'{a}_线路层_{line_id}'
            node_b = f'{b}_线路层_{line_id}'
            edge_idx = None
            if graph.has_edge(node_a, node_b):
                edge_idx = graph.get_edge_data(node_a, node_b).get('edge_idx')
            segments.append(self._segment_from_stations(line_id, a, b, edge_idx=edge_idx, virtual=edge_idx is None))
        a = stations[-1]
        b = stations[0]
        node_a = f'{a}_线路层_{line_id}'
        node_b = f'{b}_线路层_{line_id}'
        edge_idx = graph.get_edge_data(node_a, node_b).get('edge_idx') if graph.has_edge(node_a, node_b) else None
        segments.append(self._segment_from_stations(line_id, a, b, edge_idx=edge_idx, virtual=edge_idx is None))
        return segments

    def _build_segments_for_rule(self, line_id, from_station, to_station, reverse=False):
        """Create the train path for a service rule, including branches and rings."""
        if from_station == to_station:
            return self._ring_segments(line_id, reverse=reverse)
        graph = self._line_graph(line_id)
        start = f'{from_station}_线路层_{line_id}'
        end = f'{to_station}_线路层_{line_id}'
        if not graph.has_node(start) or not graph.has_node(end):
            return []
        try:
            node_path = nx.shortest_path(graph, start, end, weight='weight')
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
        if reverse:
            node_path = list(reversed(node_path))
        return self._segments_from_node_path(line_id, node_path, graph)

    def build_service_patterns(self):
        """Convert scheduled and additional rules into directional services."""
        rows = []
        schedule = pd.DataFrame(self.system.schedule_rules)
        if schedule.empty:
            self.service_patterns = []
            return []
        schedule = schedule[schedule['day_type'] == self.day_type].copy()
        for ridx, row in schedule.iterrows():
            line_id = str(row['line_id'])
            from_station = clean_station_name(row['from_st'])
            to_station = clean_station_name(row['to_st'])
            start_sec = int(row['start_min']) * 60
            end_sec = int(row['end_min']) * 60
            interval_sec = int(row['interval'])
            source = str(row.get('source', 'schedule'))
            is_default_service = bool(row.get('is_default_service', False))
            default_service_key = str(row.get('default_service_key', ''))
            for direction, reverse in [('forward', False), ('reverse', True)]:
                segments = self._build_segments_for_rule(line_id, from_station, to_station, reverse=reverse)
                service_id = f'{source}_{line_id}_{ridx}_{direction}'
                if not segments:
                    self.invalid_patterns.append({'Service_ID': service_id, 'Line_ID': line_id, 'From_Station': from_station, 'To_Station': to_station, 'Direction': direction, 'Source': source, 'Is_Default_Service': is_default_service, 'Reason': 'empty_route'})
                    continue
                route_runtime = sum((float(seg['runtime_sec']) for seg in segments if np.isfinite(seg['runtime_sec'])))
                pattern = {'service_id': service_id, 'line_id': line_id, 'from_station': segments[0]['from_station'], 'to_station': segments[-1]['to_station'], 'direction': direction, 'start_sec': start_sec, 'end_sec': end_sec, 'interval_sec': interval_sec, 'segments': segments, 'station_count': len(segments) + 1, 'route_runtime_sec': route_runtime, 'is_ring': from_station == to_station, 'source_from_station': from_station, 'source_to_station': to_station, 'source': source, 'is_default_service': is_default_service, 'default_service_key': default_service_key}
                rows.append(pattern)
        self.service_patterns = rows
        return rows

    def _departure_times(self, pattern, warm_start_abs_sec, sim_end_abs_sec):
        """Generate departures within service and warm-up windows."""
        start = max(int(pattern['start_sec']), int(warm_start_abs_sec))
        end = min(int(pattern['end_sec']), int(sim_end_abs_sec))
        if end < start:
            return []
        interval = max(1, int(pattern['interval_sec']))
        first = int(pattern['start_sec'])
        if first < start:
            first += int(math.ceil((start - first) / interval) * interval)
        return list(range(first, end + 1, interval))

    def build_trains(self, sim_start_abs_sec, sim_end_abs_sec):
        """Instantiate trains and timetable records."""
        if not self.service_patterns:
            self.build_service_patterns()
        max_runtime = max([p['route_runtime_sec'] for p in self.service_patterns], default=0.0)
        warm_start = sim_start_abs_sec - int(max(WARM_START_LOOKBACK_MIN * 60, max_runtime + TERMINAL_DWELL_SEC))
        train_id = 1
        for pattern in self.service_patterns:
            for dep in self._departure_times(pattern, warm_start, sim_end_abs_sec):
                t = TrainAgent(f'TR{train_id:05d}', pattern['service_id'], pattern['line_id'], pattern['direction'], dep, pattern['segments'])
                self.trains.append(t)
                self.timetable_rows.append({'Train_ID': t.train_id, 'Service_ID': pattern['service_id'], 'Line_ID': pattern['line_id'], 'Direction': pattern['direction'], 'Departure_Abs_Sec': int(dep), 'Departure_Rel_Sec': int(dep - sim_start_abs_sec), 'From_Station': pattern['from_station'], 'To_Station': pattern['to_station'], 'Interval_Sec': pattern['interval_sec'], 'Station_Count': pattern['station_count'], 'Route_Runtime_Sec': pattern['route_runtime_sec'], 'Is_Ring': pattern['is_ring'], 'Source': pattern['source'], 'Is_Default_Service': pattern['is_default_service'], 'Default_Service_Key': pattern['default_service_key'], 'Source_From_Station': pattern['source_from_station'], 'Source_To_Station': pattern['source_to_station']})
                train_id += 1
        self._update_default_service_generated_counts()
        return self.trains

    def _update_default_service_generated_counts(self):
        """Record how many trains each additional service rule generated."""
        if not hasattr(self.system, 'default_service_audit'):
            return
        counts = {}
        for row in self.timetable_rows:
            if not row.get('Is_Default_Service', False):
                continue
            key = (str(row.get('Source')), str(row.get('Line_ID')), clean_station_name(row.get('Source_From_Station', '')), clean_station_name(row.get('Source_To_Station', '')))
            counts[key] = counts.get(key, 0) + 1
        for audit in self.system.default_service_audit:
            key = (str(audit.get('Source')), str(audit.get('Line_ID')), clean_station_name(audit.get('From_Station', '')), clean_station_name(audit.get('To_Station', '')))
            audit['Generated_Trains'] = int(counts.get(key, 0))

    def _active_running_occupancy(self):
        """Collect occupied same-direction sections for spacing constraints."""
        occ = set()
        for train in self.trains:
            if train.status == 'running' and train.current_edge_key is not None:
                occ.add(train.current_edge_key)
        return occ

    def _log_positions_and_counts(self, rel_sec):
        """Record train positions and section occupancy counts."""
        active = [t for t in self.trains if t.status not in {'scheduled', 'finished', 'cancelled'}]
        for train in active:
            self.position_rows.append(train.position_record(rel_sec))
        counts = {}
        for train in active:
            if train.status != 'running' or train.current_segment is None:
                continue
            seg = train.current_segment
            key = (seg['line_id'], seg['edge_name'], train.direction)
            counts[key] = counts.get(key, 0) + 1
        for (line_id, edge_name, direction), cnt in counts.items():
            self.edge_count_rows.append({'Time_Sec': int(rel_sec), 'Line_ID': line_id, 'Edge_Name': edge_name, 'Direction': direction, 'Train_Count': int(cnt)})

    def run(self, sim_duration_min=SIM_DURATION):
        """Execute the train-state loop and return output tables."""
        sim_start_abs_sec = int(self.system.sim_start_min * 60)
        sim_end_abs_sec = sim_start_abs_sec + int(sim_duration_min * 60)
        self.build_service_patterns()
        self.build_trains(sim_start_abs_sec, sim_end_abs_sec)
        if not self.trains:
            return self.to_dataframes()
        warm_start_abs_sec = min((t.departure_abs_sec for t in self.trains))
        now = warm_start_abs_sec
        while now <= sim_end_abs_sec:
            occupied = self._active_running_occupancy()
            for train in self.trains:
                train.step(now, SIM_STEP_SEC, occupied)
            if now >= sim_start_abs_sec and (now - sim_start_abs_sec) % TRAIN_LOG_STEP_SEC == 0:
                self._log_positions_and_counts(now - sim_start_abs_sec)
            now += SIM_STEP_SEC
        return self.to_dataframes()

    def to_dataframes(self):
        """Convert simulation records to data frames for workbook export."""
        service_rows = []
        for p in self.service_patterns:
            service_rows.append({'Service_ID': p['service_id'], 'Line_ID': p['line_id'], 'Source_From_Station': p['source_from_station'], 'Source_To_Station': p['source_to_station'], 'Actual_From_Station': p['from_station'], 'Actual_To_Station': p['to_station'], 'Direction': p['direction'], 'Start_Sec': p['start_sec'], 'End_Sec': p['end_sec'], 'Interval_Sec': p['interval_sec'], 'Station_Count': p['station_count'], 'Route_Runtime_Sec': p['route_runtime_sec'], 'Is_Ring': p['is_ring'], 'Source': p['source'], 'Is_Default_Service': p['is_default_service'], 'Default_Service_Key': p['default_service_key']})
        if self.invalid_patterns:
            service_rows.extend(self.invalid_patterns)
        self._update_default_service_generated_counts()
        return {'service_patterns': pd.DataFrame(service_rows), 'train_timetable': pd.DataFrame(self.timetable_rows), 'train_position_log': pd.DataFrame(self.position_rows), 'edge_train_counts': pd.DataFrame(self.edge_count_rows), 'default_service_audit': pd.DataFrame(getattr(self.system, 'default_service_audit', []))}
