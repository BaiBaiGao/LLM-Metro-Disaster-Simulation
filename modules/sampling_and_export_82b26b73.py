# Sampling uses separately normalized entry and exit weights from the platform batch.
# Historical static weights initialize network flow only and may be overridden.
def choose_nearest_flow_batch(flow_df, start_time_str, valid_stations):
    """Select the platform station-flow batch nearest the configured simulation start time."""
    if flow_df is None or flow_df.empty:
        return pd.DataFrame()
    try:
        t_obj = datetime.strptime(start_time_str, '%H:%M')
        target_min = t_obj.hour * 60 + t_obj.minute
        minute_of_day = flow_df['time'].dt.hour * 60 + flow_df['time'].dt.minute
        nearest_minute = minute_of_day.iloc[(minute_of_day - target_min).abs().argsort().iloc[0]]
        batch = flow_df[minute_of_day == nearest_minute].copy()
        batch = batch[batch['station'].isin(valid_stations)]
        return batch
    except _sr.SubmissionStop:
        raise
    except Exception:
        return pd.DataFrame()

def _make_weighted_od_sampler(system, flow_df, start_time_str, valid_stations, rng):
    batch = choose_nearest_flow_batch(flow_df, start_time_str, valid_stations)
    if not batch.empty and {'station', 'inbound', 'outbound'}.issubset(batch.columns):
        origins = batch['station'].to_numpy()
        origin_weights = np.maximum(pd.to_numeric(batch['inbound'], errors='coerce').fillna(0).to_numpy(dtype=float), 0.0)
        dest_weights = np.maximum(pd.to_numeric(batch['outbound'], errors='coerce').fillna(0).to_numpy(dtype=float), 0.0)
        if origin_weights.sum() <= 0:
            raise _sr.SubmissionStop('Origin sampling weights have no positive mass.')
        if dest_weights.sum() <= 0:
            raise _sr.SubmissionStop('Destination sampling weights have no positive mass.')
        origin_prob = origin_weights / origin_weights.sum()
        dest_prob = dest_weights / dest_weights.sum()

        def sample_od():
            origin = str(rng.choice(origins, p=origin_prob))
            dest = str(rng.choice(origins, p=dest_prob))
            guard = 0
            while dest == origin and guard < 10:
                dest = str(rng.choice(origins, p=dest_prob))
                guard += 1
            if dest == origin:
                dest = str(rng.choice([s for s in valid_stations if s != origin]))
            return (clean_station_name(origin), clean_station_name(dest))
        return sample_od

    raise _sr.SubmissionStop('No valid flow batch is available for OD sampling.')

    def sample_uniform_od():
        origin, dest = rng.choice(valid_stations, size=2, replace=False)
        return (clean_station_name(str(origin)), clean_station_name(str(dest)))
    return sample_uniform_od

def _finite_float(value, default=np.nan):
    try:
        value = float(value)
        return value if np.isfinite(value) else default
    except _sr.SubmissionStop:
        raise
    except Exception:
        return default

def classify_od_for_sampling(system, origin, dest, sim_min=0):
    """
    Classify one OD under the already-applied disturbance. This uses the same
    code-computed baseline/current route facts that later feed PassengerAgent.
    """
    origin = clean_station_name(origin)
    dest = clean_station_name(dest)
    initial_plan = system.plan_passenger_route(origin, dest, sim_min, weight_mode='baseline')
    current_plan = system.plan_passenger_route(origin, dest, sim_min, weight_mode='current')
    baseline_reachable = bool(initial_plan.get('reachable'))
    current_duration = _finite_float(current_plan.get('current_duration_min', np.nan))
    normal_duration = _finite_float(initial_plan.get('normal_duration_min', np.nan))
    current_reachable = bool(current_plan.get('reachable')) and np.isfinite(current_duration)
    original_disturbed = bool(baseline_reachable and system.route_has_disturbance(initial_plan))
    current_disturbed = bool(current_reachable and system.route_has_disturbance(current_plan))
    has_alternative = bool(baseline_reachable and current_reachable and (not system.route_plans_equivalent(initial_plan, current_plan)))
    if np.isfinite(current_duration) and np.isfinite(normal_duration):
        delay_min = max(0.0, current_duration - normal_duration)
    else:
        delay_min = np.nan
    if not baseline_reachable:
        group = 'baseline_unreachable'
    elif original_disturbed:
        if not current_reachable:
            group = 'affected_unreachable'
        elif has_alternative:
            group = 'affected_reroute_available'
        elif np.isfinite(delay_min) and delay_min >= float(OD_DELAY_THRESHOLD_MIN):
            group = 'affected_reachable_delay'
        else:
            group = 'affected_reachable_no_delay'
    else:
        group = 'unaffected_control'
    return {'origin': origin, 'dest': dest, 'group': group, 'baseline_reachable': baseline_reachable, 'current_reachable': current_reachable, 'original_disturbed': original_disturbed, 'current_disturbed': current_disturbed, 'has_alternative': has_alternative, 'delay_min': delay_min}

def od_sampling_target_counts(sample_size):
    sample_size = int(sample_size)
    affected_total = int(round(sample_size * max(0.0, min(1.0, float(TARGET_AFFECTED_RATIO)))))
    affected_total = max(0, min(sample_size, affected_total))
    control_count = sample_size - affected_total
    unreachable_count = min(affected_total, int(round(sample_size * max(0.0, float(TARGET_UNREACHABLE_RATIO)))))
    reroute_count = min(affected_total - unreachable_count, int(round(sample_size * max(0.0, float(TARGET_REROUTE_RATIO)))))
    delay_count = max(0, affected_total - unreachable_count - reroute_count)
    targets = {'affected_unreachable': unreachable_count, 'affected_reroute_available': reroute_count, 'affected_reachable_delay': delay_count, 'unaffected_control': control_count}
    diff = sample_size - sum(targets.values())
    if diff > 0:
        targets['unaffected_control'] += diff
    elif diff < 0:
        targets['unaffected_control'] = max(0, targets['unaffected_control'] + diff)
    return targets

def _passenger_from_od_record(pid, record, sample_mode):
    passenger = PassengerAgent(pid, record['origin'], record['dest'], 0)
    passenger.od_sample_mode = sample_mode
    passenger.od_sample_group = record.get('group', 'unknown')
    return passenger

def generate_flow_random_passengers(system, flow_df, sample_size, start_time_str, sample_mode='flow_random'):
    valid_stations = sorted(set(system.station_names()))
    rng = np.random.default_rng(BASE_SEED)
    sample_od = _make_weighted_od_sampler(system, flow_df, start_time_str, valid_stations, rng)
    passengers = []
    for pid in range(1, int(sample_size) + 1):
        origin, dest = sample_od()
        record = classify_od_for_sampling(system, origin, dest, sim_min=0)
        record['group'] = 'flow_random_' + record.get('group', 'unknown')
        passengers.append(_passenger_from_od_record(pid, record, sample_mode))
    return passengers

def generate_disturbance_focused_passengers(system, flow_df, sample_size, start_time_str):
    """
    Generate passengers with targeted OD composition:
    affected OD pairs first, plus an unaffected all-network control group.
    Route facts are only used for sampling labels; final rule/LLM decisions are
    still recomputed later by PassengerAgent.decide().
    """
    sample_size = int(sample_size)
    valid_stations = sorted(set(system.station_names()))
    rng = np.random.default_rng(BASE_SEED)
    sample_od = _make_weighted_od_sampler(system, flow_df, start_time_str, valid_stations, rng)
    targets = od_sampling_target_counts(sample_size)
    buckets = {group: [] for group in targets}
    overflow = []
    classify_cache = {}
    for _ in range(int(MAX_OD_RESAMPLE_ATTEMPTS)):
        if all((len(buckets[group]) >= target for group, target in targets.items())):
            break
        origin, dest = sample_od()
        key = (origin, dest)
        record = classify_cache.get(key)
        if record is None:
            record = classify_od_for_sampling(system, origin, dest, sim_min=0)
            classify_cache[key] = record
        record = dict(record)
        group = record['group']
        if group in targets and len(buckets[group]) < targets[group]:
            buckets[group].append(record)
        else:
            overflow.append(record)
    records = []
    for group, target in targets.items():
        records.extend(buckets[group][:target])
    if len(records) < sample_size:
        target_groups = set(targets)
        affected_groups = {group for group in target_groups if group.startswith('affected_')}
        for preferred_groups in [affected_groups, target_groups, None]:
            for record in overflow:
                if len(records) >= sample_size:
                    break
                group = record.get('group', '')
                if preferred_groups is not None and group not in preferred_groups:
                    continue
                records.append(dict(record))
            if len(records) >= sample_size:
                break
    guard = 0
    while len(records) < sample_size and guard < int(MAX_OD_RESAMPLE_ATTEMPTS):
        origin, dest = sample_od()
        records.append(classify_od_for_sampling(system, origin, dest, sim_min=0))
        guard += 1
    if len(records) < sample_size:
        raise RuntimeError(f'受扰动 OD 定向抽样失败：仅生成 {len(records)} / {sample_size} 个乘客。')
    records = records[:sample_size]
    rng.shuffle(records)
    passengers = [_passenger_from_od_record(pid, record, PASSENGER_SAMPLE_MODE) for pid, record in enumerate(records, start=1)]
    group_counts = pd.Series([p.od_sample_group for p in passengers]).value_counts().to_dict()
    print('OD 定向抽样完成:', group_counts)
    print('OD 定向抽样目标:', targets)
    return passengers

def generate_passengers(system, flow_df, sample_size, start_time_str):
    """
    Generate passengers using disturbance-focused or station-flow-weighted OD sampling.
    """
    mode = str(PASSENGER_SAMPLE_MODE)
    if mode == 'disturbance_focused':
        return generate_disturbance_focused_passengers(system, flow_df, sample_size, start_time_str)
    if mode == 'flow_random':
        return generate_flow_random_passengers(system, flow_df, sample_size, start_time_str, sample_mode=mode)
    raise ValueError(f'非法 PASSENGER_SAMPLE_MODE: {mode}')

def _effective_llm_selection_budget(passengers):
    ratio = max(0.0, min(1.0, float(LLM_PASSENGER_RATIO)))
    cap = max(0, int(LLM_MAX_PASSENGER_CALLS))
    if ratio <= 0.0 or cap <= 0:
        return 0
    return min(cap, int(round(len(passengers) * ratio)))

def _random_select_passenger_ids(passengers, budget, rng):
    if budget <= 0:
        return set()
    ids = [int(p.pid) for p in passengers]
    if len(ids) <= budget:
        return set(ids)
    return set((int(pid) for pid in rng.choice(np.array(ids, dtype=int), size=budget, replace=False)))

def _stratified_select_passenger_ids(passengers, budget, rng):
    if budget <= 0:
        return set()
    grouped = {}
    for passenger in passengers:
        group = str(getattr(passenger, 'od_sample_group', 'unknown'))
        grouped.setdefault(group, []).append(int(passenger.pid))
    active_groups = [group for group in LLM_OD_GROUP_SELECTION_PRIORITY if group in grouped]
    for group in grouped:
        if group not in active_groups:
            active_groups.append(group)
    if not active_groups:
        return set()
    weights = {group: float(LLM_OD_GROUP_SELECTION_WEIGHTS.get(group, 0.0)) for group in active_groups}
    if sum(weights.values()) <= 0:
        return _random_select_passenger_ids(passengers, budget, rng)
    raw_targets = {group: budget * weights[group] / sum(weights.values()) for group in active_groups}
    targets = {group: min(len(grouped[group]), int(np.floor(raw_targets[group]))) for group in active_groups}
    assigned = sum(targets.values())
    remainder_order = sorted(active_groups, key=lambda group: (raw_targets[group] - np.floor(raw_targets[group]), weights[group]), reverse=True)
    for group in remainder_order:
        if assigned >= budget:
            break
        if targets[group] < len(grouped[group]):
            targets[group] += 1
            assigned += 1
    fill_order = list(LLM_OD_GROUP_SELECTION_PRIORITY) + [group for group in active_groups if group not in LLM_OD_GROUP_SELECTION_PRIORITY]
    while assigned < budget:
        progressed = False
        for group in fill_order:
            if group not in grouped:
                continue
            if targets.get(group, 0) < len(grouped[group]):
                targets[group] = targets.get(group, 0) + 1
                assigned += 1
                progressed = True
                if assigned >= budget:
                    break
        if not progressed:
            break
    selected = []
    for group in fill_order:
        ids = grouped.get(group, [])
        take = min(targets.get(group, 0), len(ids))
        if take <= 0:
            continue
        selected.extend((int(pid) for pid in rng.choice(np.array(ids, dtype=int), size=take, replace=False)))
    return set(selected[:budget])

def select_llm_passenger_ids(passengers):
    """
    Select passengers for LLM evaluation using the configured OD-group sampling weights.
    """
    mode = str(PASSENGER_DECISION_MODE)
    if mode not in {'rule', 'llm', 'paired_compare'}:
        raise ValueError(f'非法 PASSENGER_DECISION_MODE: {mode}')
    budget = _effective_llm_selection_budget(passengers)
    if mode == 'rule' or budget <= 0:
        return set()
    rng = np.random.default_rng(int(LLM_RANDOM_SEED))
    if str(LLM_SELECTION_MODE) == 'od_group_stratified':
        return _stratified_select_passenger_ids(passengers, budget, rng)
    return _random_select_passenger_ids(passengers, budget, rng)
llm_model_rr_index = 0
llm_model_cooldown_until = {model_name: 0.0 for model_name in LLM_MODEL_POOL}

def select_llm_passenger_model(excluded_models=None):
    return 'Qwen/Qwen3.5-27B'

def mark_llm_passenger_model_cooldown(model_name, cooldown_sec=None):
    if not model_name:
        return
    cooldown = LLM_MODEL_COOLDOWN_SEC if cooldown_sec is None else cooldown_sec
    llm_model_cooldown_until[str(model_name)] = time.time() + max(0, float(cooldown))

def llm_cooldown_seconds_for_exception(exc):
    text = f'{type(exc).__name__}: {exc}'.lower()
    if 'ratelimit' in text or '429' in text or 'quota' in text:
        return LLM_RATE_LIMIT_COOLDOWN_SEC
    if '空内容' in text or 'empty' in text:
        return LLM_EMPTY_RESPONSE_COOLDOWN_SEC
    return LLM_MODEL_COOLDOWN_SEC

def call_llm_passenger_json(system_prompt, user_content, model, temperature, timeout_sec):
    return _sr.chat(system_prompt, user_content, model, temperature, timeout_sec)[:3]

def normalize_llm_feeling_score(value):
    """
    Convert common LLM score scales into the notebook's 1-5 feeling score.
    The raw value is kept in Passenger_Stats for audit.
    """
    raw = '' if value is None else str(value)
    try:
        score = float(value)
    except _sr.SubmissionStop:
        raise
    except Exception:
        return (np.nan, raw, 'feeling_score 不是数值。')
    if not np.isfinite(score):
        return (np.nan, raw, 'feeling_score 不是有限数值。')
    if 1.0 <= score <= 5.0:
        normalized = int(round(score))
    elif 5.0 < score <= 10.0:
        normalized = int(round(score / 2.0))
    elif 10.0 < score <= 100.0:
        normalized = int(np.ceil(score / 20.0))
    else:
        return (np.nan, raw, 'feeling_score 无法映射到 1-5。')
    normalized = int(min(5, max(1, normalized)))
    return (normalized, raw, '')

def validate_llm_passenger_decision(parsed, context):
    """Validate feasible actions and normalized perception fields in a model response."""
    if not isinstance(parsed, dict):
        return (False, 'LLM 输出不是 JSON 对象。')
    required = ['action_choice', 'reason', 'risk_perception_level', 'delay_perception_level', 'feeling_score']
    missing = [field for field in required if field not in parsed]
    if missing:
        return (False, 'LLM JSON 缺失字段: ' + ','.join(missing))
    prohibited_route_fields = [key for key in parsed if 'route' in str(key).lower() or 'station' in str(key).lower()]
    if prohibited_route_fields:
        return (False, 'LLM 返回了禁止的路线/车站字段: ' + ','.join(map(str, prohibited_route_fields)))
    action = str(parsed.get('action_choice', ''))
    allowed = set(context.get('allowed_actions_for_llm', LLM_ALLOWED_ACTIONS))
    if action not in set(LLM_ALLOWED_ACTIONS):
        return (False, f'LLM action_choice 越界: {action}')
    if action not in allowed:
        return (False, f'LLM action_choice 不符合当前可达性约束: {action}')
    if not context.get('current_route_reachable', False) and action != 'abandon_trip':
        return (False, '当前不可达时 LLM 只能选择 abandon_trip。')
    if not context.get('has_available_alternative_route', False) and action == 'reroute_to_shortest_time':
        return (False, '没有不同于原路线的可用替代路线时不能选择 reroute_to_shortest_time。')
    if not context.get('baseline_route_reachable', False) and action == 'continue_original_route':
        return (False, '原始基准路线不可达时不能选择 continue_original_route。')
    if context.get('original_route_current_feasible') is False and action == 'continue_original_route':
        return (False, '原路线当前硬不可通行时不能选择 continue_original_route。')
    reason = str(parsed.get('reason', '')).strip()
    prohibited_reason_terms = ['current_route_reachable', 'current_route_passes_disturbance', 'original_route_passes_disturbance', 'estimated_delay_min', 'has_available_alternative_route', 'baseline_route_reachable', 'allowed_actions_for_llm', 'rule_action', 'Rule_Action', 'OCEAN', 'Risk_Preference', 'LLM_', 'JSON']
    reason_lower = reason.lower()
    for term in prohibited_reason_terms:
        if term.lower() in reason_lower:
            return (False, f'reason 出现后台字段或代码术语: {term}')
    if len(reason) > 120:
        return (False, 'reason 过长，应控制在 120 字以内。')
    risk_level = str(parsed.get('risk_perception_level', '')).strip()
    delay_level = str(parsed.get('delay_perception_level', '')).strip()
    if risk_level not in LLM_PERCEPTION_LEVELS:
        return (False, f'risk_perception_level 非标准枚举: {risk_level}')
    if delay_level not in LLM_PERCEPTION_LEVELS:
        return (False, f'delay_perception_level 非标准枚举: {delay_level}')
    _, _, feeling_error = normalize_llm_feeling_score(parsed.get('feeling_score'))
    if feeling_error:
        return (False, feeling_error)
    return (True, '')

def _action_counts(df, action_col, prefix):
    actions = list(LLM_ALLOWED_ACTIONS)
    return {f'{prefix}_{action}': int((df[action_col] == action).sum()) if action_col in df else 0 for action in actions}

def build_decision_comparison_summary(passenger_df):
    """
    Build one auditable long-form summary sheet for rule-vs-LLM passenger decisions.
    """
    rows = []
    if passenger_df is None or passenger_df.empty:
        return pd.DataFrame(columns=['Section', 'Group', 'Metric', 'Action_Source', 'Action', 'Value'])
    selected = passenger_df[passenger_df['LLM_Selected'] == True].copy()
    valid = selected[selected['LLM_Valid'] == True].copy()
    fallback = selected[selected['LLM_Fallback_Used'] == True].copy()
    agreement_rate = float((valid['Rule_Action'] == valid['LLM_Action']).mean()) if not valid.empty else np.nan
    rows.extend([{'Section': 'Overview', 'Group': 'All', 'Metric': 'Total_Passengers', 'Action_Source': '', 'Action': '', 'Value': int(len(passenger_df))}, {'Section': 'Overview', 'Group': 'All', 'Metric': 'LLM_Selected_Count', 'Action_Source': '', 'Action': '', 'Value': int(len(selected))}, {'Section': 'Overview', 'Group': 'All', 'Metric': 'LLM_Success_Count', 'Action_Source': '', 'Action': '', 'Value': int(len(valid))}, {'Section': 'Overview', 'Group': 'All', 'Metric': 'LLM_Fallback_Count', 'Action_Source': '', 'Action': '', 'Value': int(len(fallback))}, {'Section': 'Overview', 'Group': 'All', 'Metric': 'Rule_LLM_Agreement_Rate', 'Action_Source': '', 'Action': '', 'Value': agreement_rate}])
    for action, count in passenger_df['Rule_Action'].value_counts(dropna=False).items():
        rows.append({'Section': 'Action_Counts', 'Group': 'All', 'Metric': 'Rule_Action_Count', 'Action_Source': 'Rule', 'Action': action, 'Value': int(count)})
    llm_action_df = valid if not valid.empty else selected
    if not llm_action_df.empty:
        for action, count in llm_action_df['LLM_Action'].value_counts(dropna=False).items():
            rows.append({'Section': 'Action_Counts', 'Group': 'All', 'Metric': 'LLM_Action_Count', 'Action_Source': 'LLM', 'Action': action, 'Value': int(count)})
    conservatism_rank = {'abandon_trip': 0, 'reroute_to_shortest_time': 1, 'continue_current_shortest_route': 2, 'continue_original_route': 3}
    if not valid.empty:
        rule_rank = valid['Rule_Action'].map(conservatism_rank)
        llm_rank = valid['LLM_Action'].map(conservatism_rank)
        rows.append({'Section': 'Action_Change', 'Group': 'Valid_LLM', 'Metric': 'LLM_More_Conservative_Count', 'Action_Source': '', 'Action': '', 'Value': int((llm_rank < rule_rank).sum())})
        rows.append({'Section': 'Action_Change', 'Group': 'Valid_LLM', 'Metric': 'LLM_More_Aggressive_Count', 'Action_Source': '', 'Action': '', 'Value': int((llm_rank > rule_rank).sum())})
    else:
        rows.append({'Section': 'Action_Change', 'Group': 'Valid_LLM', 'Metric': 'LLM_More_Conservative_Count', 'Action_Source': '', 'Action': '', 'Value': 0})
        rows.append({'Section': 'Action_Change', 'Group': 'Valid_LLM', 'Metric': 'LLM_More_Aggressive_Count', 'Action_Source': '', 'Action': '', 'Value': 0})
    grouped_df = passenger_df.copy()
    grouped_df['Age_Group'] = pd.cut(grouped_df['Age'], bins=[0, 18, 30, 45, 60, 200], labels=['<=18', '19-30', '31-45', '46-60', '60+'], right=True, include_lowest=True).astype(str)
    group_specs = ['OD_Sample_Group', 'Age_Group', 'Risk_Preference', 'OCEAN_O', 'OCEAN_C', 'OCEAN_E', 'OCEAN_A', 'OCEAN_N']
    group_specs = [col for col in group_specs if col in grouped_df.columns]
    for group_col in group_specs:
        for (group_value, action), count in grouped_df.groupby([group_col, 'Rule_Action']).size().items():
            rows.append({'Section': 'Group_Action_Distribution', 'Group': f'{group_col}={group_value}', 'Metric': 'Rule_Action_Count', 'Action_Source': 'Rule', 'Action': action, 'Value': int(count)})
        if not valid.empty:
            valid_grouped = valid.copy()
            if group_col == 'Age_Group':
                valid_grouped['Age_Group'] = pd.cut(valid_grouped['Age'], bins=[0, 18, 30, 45, 60, 200], labels=['<=18', '19-30', '31-45', '46-60', '60+'], right=True, include_lowest=True).astype(str)
            for (group_value, action), count in valid_grouped.groupby([group_col, 'LLM_Action']).size().items():
                rows.append({'Section': 'Group_Action_Distribution', 'Group': f'{group_col}={group_value}', 'Metric': 'LLM_Action_Count', 'Action_Source': 'LLM', 'Action': action, 'Value': int(count)})
    return pd.DataFrame(rows)

def llm_call_log_dataframe(llm_call_log):
    if not llm_call_log:
        return pd.DataFrame(columns=LLM_CALL_LOG_COLUMNS)
    df = pd.DataFrame(llm_call_log)
    for col in LLM_CALL_LOG_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[LLM_CALL_LOG_COLUMNS]

def network_state_rows(system, network_agent, efficiency_series, train_position_log):
    """Summarize efficiency, train counts and operational conditions by minute."""
    summary = network_agent.summary()
    train_counts = {}
    stopped_counts = {}
    if isinstance(train_position_log, pd.DataFrame) and (not train_position_log.empty):
        grouped = train_position_log.groupby('Time_Sec')
        train_counts = grouped['Train_ID'].nunique().to_dict()
        stopped_counts = train_position_log[train_position_log['Status'].isin(['dwell', 'terminal_dwell'])].groupby('Time_Sec')['Train_ID'].nunique().to_dict()
    rows = []
    for time_min, eff in efficiency_series:
        time_sec = int(time_min * 60)
        rows.append({'Time_Min': int(time_min), 'Time_Sec': time_sec, 'Efficiency': float(eff), 'Active_Trains': int(train_counts.get(time_sec, 0)), 'Dwell_Trains': int(stopped_counts.get(time_sec, 0)), 'Closed_Stations': summary['closed_stations'], 'Suspended_Lines': summary['suspended_lines'], 'Slowed_Edges': summary['slowed_edges'], 'Blocked_Edges': summary['blocked_edges'], 'Closed_Station_Names': summary['closed_station_names'], 'Suspended_Line_IDs': summary['suspended_line_ids']})
    return rows

def runtime_json_safe(value):
    """Convert numpy/pandas/path objects into JSONL-safe plain Python values."""
    if isinstance(value, dict):
        return {str(k): runtime_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [runtime_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return v if np.isfinite(v) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except _sr.SubmissionStop:
        raise
    except Exception:
        pass
    return value

def append_jsonl_record(path, record):
    """Append one recovery record. Failures are reported but do not stop simulation."""
    if not CHECKPOINT_ENABLED or not CHECKPOINT_SAVE_JSONL or path is None:
        return None
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(runtime_json_safe(record), ensure_ascii=False) + '\n')
        return path
    except _sr.SubmissionStop:
        raise
    except Exception as exc:
        print(f'[checkpoint-warning] JSONL append failed: {type(exc).__name__}: {exc}', flush=True)
        return None

def partial_progress_summary(completed_count, total_count, llm_call_log, checkpoint_dir, run_id, stage='passenger_loop', error_message=''):
    selected_logs = list(llm_call_log or [])
    valid_count = sum((1 for rec in selected_logs if bool(rec.get('Valid', False))))
    fallback_count = sum((1 for rec in selected_logs if bool(rec.get('Fallback_Used', False))))
    pct = float(completed_count) / float(total_count) * 100.0 if total_count else 0.0
    return {'Version': OUTPUT_VERSION, 'Run_ID': run_id, 'Stage': stage, 'Completed_Passengers': int(completed_count), 'Total_Passengers': int(total_count), 'Progress_Percent': round(pct, 2), 'LLM_Call_Log_Count': int(len(selected_logs)), 'LLM_Valid_Count': int(valid_count), 'LLM_Fallback_Count': int(fallback_count), 'Checkpoint_Dir': str(checkpoint_dir), 'Error_Message': str(error_message or ''), 'Updated_At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

def write_decision_checkpoint(checkpoint_dir, run_id, completed_passengers, llm_call_log, completed_count, total_count, stage='passenger_loop', error_message=''):
    """Write a recoverable partial Excel workbook with passenger decisions and LLM logs."""
    if not CHECKPOINT_ENABLED or not CHECKPOINT_EXCEL_ENABLED:
        return None
    try:
        checkpoint_dir = Path(checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        passenger_df_partial = pd.DataFrame([p.to_record() for p in completed_passengers])
        llm_call_log_df_partial = llm_call_log_dataframe(llm_call_log)
        if passenger_df_partial.empty:
            summary_df_partial = pd.DataFrame()
        else:
            summary_df_partial = build_decision_comparison_summary(passenger_df_partial)
        run_summary_partial = partial_progress_summary(completed_count=completed_count, total_count=total_count, llm_call_log=llm_call_log, checkpoint_dir=checkpoint_dir, run_id=run_id, stage=stage, error_message=error_message)
        suffix = datetime.now().strftime('%H%M%S')
        out_path = checkpoint_dir / f'Checkpoint_{OUTPUT_VERSION}_{run_id}_{int(completed_count):04d}_{suffix}.xlsx'
        with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
            passenger_df_partial.to_excel(writer, sheet_name='Passenger_Stats', index=False)
            llm_call_log_df_partial.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
            summary_df_partial.to_excel(writer, sheet_name='Decision_Comparison_Summary', index=False)
            pd.DataFrame([run_summary_partial]).to_excel(writer, sheet_name='Run_Summary', index=False)
        return out_path
    except _sr.SubmissionStop:
        raise
    except Exception as exc:
        print(f'[checkpoint-warning] Excel checkpoint failed: {type(exc).__name__}: {exc}', flush=True)
        return None

def print_decision_progress(completed_count, total_count, llm_call_log, start_ts, checkpoint_path=None, force=False):
    if not force and int(completed_count) % max(1, int(PROGRESS_PRINT_EVERY_PASSENGERS)) != 0:
        return
    elapsed_min = (time.time() - start_ts) / 60.0
    valid_count = sum((1 for rec in llm_call_log or [] if bool(rec.get('Valid', False))))
    fallback_count = sum((1 for rec in llm_call_log or [] if bool(rec.get('Fallback_Used', False))))
    pct = float(completed_count) / float(total_count) * 100.0 if total_count else 0.0
    msg = f'[{datetime.now().strftime('%H:%M:%S')}] passenger progress {int(completed_count)}/{int(total_count)} ({pct:.1f}%) | LLM logs={len(llm_call_log or [])}, valid={valid_count}, fallback={fallback_count} | elapsed={elapsed_min:.1f} min'
    if checkpoint_path:
        msg += f' | checkpoint={checkpoint_path}'
    print(msg, flush=True)

def export_result(output_dir, efficiency_df, network_state_df, decisions_df, passenger_df, service_patterns_df, train_timetable_df, train_position_df, edge_train_counts_df, default_service_audit_df, run_summary, input_audit, decision_comparison_summary_df=None, llm_call_log_df=None):
    """Export one simulation to a workbook with stable worksheet names."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f'Simulation_Result_{OUTPUT_VERSION}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx'
    out_path = output_dir / filename
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        efficiency_df.to_excel(writer, sheet_name='Efficiency', index=False)
        network_state_df.to_excel(writer, sheet_name='Network_State', index=False)
        decisions_df.to_excel(writer, sheet_name='Disturbance_Decisions', index=False)
        passenger_df.to_excel(writer, sheet_name='Passenger_Stats', index=False)
        (decision_comparison_summary_df if decision_comparison_summary_df is not None else pd.DataFrame()).to_excel(writer, sheet_name='Decision_Comparison_Summary', index=False)
        (llm_call_log_df if llm_call_log_df is not None else pd.DataFrame(columns=LLM_CALL_LOG_COLUMNS)).to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        pd.DataFrame([run_summary]).to_excel(writer, sheet_name='Run_Summary', index=False)
        pd.DataFrame(input_audit).to_excel(writer, sheet_name='Input_Audit', index=False)
        service_patterns_df.to_excel(writer, sheet_name='Service_Patterns', index=False)
        train_timetable_df.to_excel(writer, sheet_name='Train_Timetable', index=False)
        train_position_df.to_excel(writer, sheet_name='Train_Position_Log', index=False)
        edge_train_counts_df.to_excel(writer, sheet_name='Edge_Train_Counts', index=False)
        default_service_audit_df.to_excel(writer, sheet_name='Default_Service_Audit', index=False)
    return out_path

def run_single_simulation():
    _sr.require_run()
    random.seed(BASE_SEED)
    np.random.seed(BASE_SEED)
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_start_ts = time.time()
    checkpoint_dir = OUTPUT_DIR / f'Runtime_Checkpoints_{OUTPUT_VERSION}_{run_id}'
    passenger_jsonl_path = checkpoint_dir / f'Passenger_Stats_{OUTPUT_VERSION}_{run_id}.jsonl'
    llm_jsonl_path = checkpoint_dir / f'LLM_Call_Log_{OUTPUT_VERSION}_{run_id}.jsonl'
    progress_jsonl_path = checkpoint_dir / f'Progress_{OUTPUT_VERSION}_{run_id}.jsonl'
    if CHECKPOINT_ENABLED:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        globals()['LAST_RUNTIME_CHECKPOINT_DIR'] = checkpoint_dir
        globals()['LAST_PASSENGER_CHECKPOINT_JSONL'] = passenger_jsonl_path
        globals()['LAST_LLM_CHECKPOINT_JSONL'] = llm_jsonl_path
        print(f'Runtime checkpoint dir: {checkpoint_dir}', flush=True)
        append_jsonl_record(progress_jsonl_path, partial_progress_summary(0, PASSENGER_SAMPLE_SIZE, [], checkpoint_dir, run_id, stage='started'))
    input_audit = audit_input_files(BASE_PATH)
    flow_df = load_flow_data(BASE_PATH)
    system = SubwayRuleSystem(BASE_PATH, sim_start_time=START_TIME_STR, real_flow_df=flow_df)
    disturbance_function = SimpleDisturbanceFunction(DISTURBANCE_EDGES)
    network_agent = MetroNetworkAgent(system, disturbance_function)
    decisions = network_agent.evaluate_and_apply()
    decisions_df = pd.DataFrame(decisions)
    train_engine = TrainSimulationEngine(system, day_type='Weekday')
    train_outputs = train_engine.run(sim_duration_min=SIM_DURATION)
    service_patterns_df = train_outputs['service_patterns']
    train_timetable_df = train_outputs['train_timetable']
    train_position_df = train_outputs['train_position_log']
    edge_train_counts_df = train_outputs['edge_train_counts']
    default_service_audit_df = train_outputs['default_service_audit']
    efficiency_series = []
    for t in range(SIM_DURATION):
        clock_min = system.sim_start_min + t
        efficiency_series.append((t, system.calculate_weighted_efficiency(clock_min, 'Weekday')))
    efficiency_df = pd.DataFrame({'Time': [x[0] for x in efficiency_series], 'Rule_MAS_Run_1': [x[1] for x in efficiency_series]})
    network_state_df = pd.DataFrame(network_state_rows(system, network_agent, efficiency_series, train_position_df))
    passengers = generate_passengers(system, flow_df, PASSENGER_SAMPLE_SIZE, START_TIME_STR)
    llm_selected_ids = select_llm_passenger_ids(passengers)
    llm_selected_id_set = set(llm_selected_ids)
    llm_call_log = []
    completed_passengers = []
    last_llm_log_written = 0
    total_passengers = len(passengers)
    print(f'Passenger decision loop started: total={total_passengers}, llm_selected={len(llm_selected_id_set)}', flush=True)
    try:
        for idx, passenger in enumerate(passengers, start=1):
            passenger.decide(system, sim_min=0, use_llm=passenger.pid in llm_selected_id_set, decision_mode=PASSENGER_DECISION_MODE, llm_call_log=llm_call_log)
            completed_passengers.append(passenger)
            append_jsonl_record(passenger_jsonl_path, passenger.to_record())
            for log_record in llm_call_log[last_llm_log_written:]:
                append_jsonl_record(llm_jsonl_path, log_record)
            last_llm_log_written = len(llm_call_log)
            checkpoint_path = None
            if idx % max(1, int(CHECKPOINT_EXCEL_EVERY_PASSENGERS)) == 0 or idx == total_passengers:
                checkpoint_path = write_decision_checkpoint(checkpoint_dir, run_id, completed_passengers, llm_call_log, completed_count=idx, total_count=total_passengers, stage='passenger_loop')
            if idx % max(1, int(PROGRESS_PRINT_EVERY_PASSENGERS)) == 0 or idx == 1 or idx == total_passengers or checkpoint_path:
                append_jsonl_record(progress_jsonl_path, partial_progress_summary(idx, total_passengers, llm_call_log, checkpoint_dir, run_id, stage='passenger_loop'))
                print_decision_progress(idx, total_passengers, llm_call_log, run_start_ts, checkpoint_path=checkpoint_path, force=True)
    except KeyboardInterrupt:
        interrupted_path = write_decision_checkpoint(checkpoint_dir, run_id, completed_passengers, llm_call_log, completed_count=len(completed_passengers), total_count=total_passengers, stage='keyboard_interrupt', error_message='KeyboardInterrupt')
        append_jsonl_record(progress_jsonl_path, partial_progress_summary(len(completed_passengers), total_passengers, llm_call_log, checkpoint_dir, run_id, stage='keyboard_interrupt', error_message='KeyboardInterrupt'))
        print(f'Run interrupted. Partial checkpoint: {interrupted_path}', flush=True)
        raise
    except Exception as exc:
        error_path = write_decision_checkpoint(checkpoint_dir, run_id, completed_passengers, llm_call_log, completed_count=len(completed_passengers), total_count=total_passengers, stage='error', error_message=f'{type(exc).__name__}: {exc}')
        append_jsonl_record(progress_jsonl_path, partial_progress_summary(len(completed_passengers), total_passengers, llm_call_log, checkpoint_dir, run_id, stage='error', error_message=f'{type(exc).__name__}: {exc}'))
        print(f'Run failed after {len(completed_passengers)}/{total_passengers}. Partial checkpoint: {error_path}', flush=True)
        raise
    passenger_df = pd.DataFrame([p.to_record() for p in passengers])
    decision_comparison_summary_df = build_decision_comparison_summary(passenger_df)
    llm_call_log_df = llm_call_log_dataframe(llm_call_log)
    od_group_counts = passenger_df['OD_Sample_Group'].value_counts().to_dict() if 'OD_Sample_Group' in passenger_df else {}
    llm_selected_group_counts = passenger_df.loc[passenger_df['LLM_Selected'] == True, 'OD_Sample_Group'].value_counts().to_dict() if {'LLM_Selected', 'OD_Sample_Group'}.issubset(passenger_df.columns) else {}
    od_affected_count = int(sum((count for group, count in od_group_counts.items() if str(group).startswith('affected_'))))
    summary = network_agent.summary()
    max_same_direction = int(edge_train_counts_df['Train_Count'].max()) if not edge_train_counts_df.empty else 0
    default_enabled = default_service_audit_df[default_service_audit_df['Enabled'] == True] if not default_service_audit_df.empty else pd.DataFrame()
    default_branch_enabled = int((default_enabled['Source'] == 'default_branch').sum()) if not default_enabled.empty else 0
    default_maglev_enabled = int((default_enabled['Source'] == 'default_maglev').sum()) if not default_enabled.empty else 0
    default_service_trains = int(default_service_audit_df['Generated_Trains'].sum()) if not default_service_audit_df.empty else 0
    run_summary = {'Version': OUTPUT_VERSION, 'Seed': BASE_SEED, 'Sim_Duration_Min': SIM_DURATION, 'Sim_Step_Sec': SIM_STEP_SEC, 'Train_Speed_KMH': TRAIN_SPEED_KMH, 'Track_Detour_Factor': TRACK_DETOUR_FACTOR, 'Dwell_Sec': DWELL_SEC, 'Terminal_Dwell_Sec': TERMINAL_DWELL_SEC, 'Passenger_Sample_Size': PASSENGER_SAMPLE_SIZE, 'Passenger_Sample_Mode': PASSENGER_SAMPLE_MODE, 'Target_Affected_Ratio': float(TARGET_AFFECTED_RATIO), 'Target_Unaffected_Control_Ratio': float(TARGET_UNAFFECTED_CONTROL_RATIO), 'Target_Unreachable_Ratio': float(TARGET_UNREACHABLE_RATIO), 'Target_Reroute_Ratio': float(TARGET_REROUTE_RATIO), 'OD_Delay_Threshold_Min': float(OD_DELAY_THRESHOLD_MIN), 'Max_OD_Resample_Attempts': int(MAX_OD_RESAMPLE_ATTEMPTS), 'OD_Affected_Count': od_affected_count, 'OD_Unaffected_Control_Count': int(od_group_counts.get('unaffected_control', 0)), 'OD_Affected_Unreachable_Count': int(od_group_counts.get('affected_unreachable', 0)), 'OD_Affected_Reroute_Available_Count': int(od_group_counts.get('affected_reroute_available', 0)), 'OD_Affected_Reachable_Delay_Count': int(od_group_counts.get('affected_reachable_delay', 0)), 'OD_Affected_Reachable_No_Delay_Count': int(od_group_counts.get('affected_reachable_no_delay', 0)), 'OD_Sample_Group_Counts': json.dumps(od_group_counts, ensure_ascii=False), 'Flow_Source': getattr(system, 'flow_source_used', 'unknown'), 'Efficiency_Min': float(efficiency_df['Rule_MAS_Run_1'].min()), 'Efficiency_Mean': float(efficiency_df['Rule_MAS_Run_1'].mean()), 'Closed_Stations': summary['closed_stations'], 'Suspended_Lines': summary['suspended_lines'], 'Slowed_Edges': summary['slowed_edges'], 'Blocked_Edges': summary['blocked_edges'], 'Default_Branch_Services_Enabled': default_branch_enabled, 'Default_Maglev_Services_Enabled': default_maglev_enabled, 'Default_Service_Trains_Generated': default_service_trains, 'Service_Patterns': int(len(service_patterns_df)), 'Generated_Trains': int(len(train_timetable_df)), 'Logged_Train_Positions': int(len(train_position_df)), 'Max_Same_Direction_Trains_Per_Edge': max_same_direction, 'Finished_Passengers': int((passenger_df['Status'] == 'finished').sum()) if not passenger_df.empty else 0, 'Abandoned_Passengers': int((passenger_df['Status'] == 'abandoned').sum()) if not passenger_df.empty else 0, 'Rerouted_Passengers': int((passenger_df['Action'] == 'reroute_to_shortest_time').sum()) if not passenger_df.empty else 0, 'Input_Disturbance_Count': len(DISTURBANCE_EDGES), 'Passenger_Decision_Mode': PASSENGER_DECISION_MODE, 'LLM_Passenger_Ratio': float(LLM_PASSENGER_RATIO), 'LLM_Max_Passenger_Calls': int(LLM_MAX_PASSENGER_CALLS), 'LLM_Selection_Mode': LLM_SELECTION_MODE, 'LLM_OD_Group_Selection_Weights': json.dumps(LLM_OD_GROUP_SELECTION_WEIGHTS, ensure_ascii=False), 'LLM_OD_Group_Selection_Priority': ';'.join(LLM_OD_GROUP_SELECTION_PRIORITY), 'LLM_Selected_Group_Counts': json.dumps(llm_selected_group_counts, ensure_ascii=False), 'LLM_Primary_Model': LLM_MODEL, 'LLM_Model_Pool': ';'.join(LLM_MODEL_POOL), 'LLM_Max_Model_Retries': int(LLM_MAX_MODEL_RETRIES), 'Runtime_Checkpoint_Enabled': bool(CHECKPOINT_ENABLED), 'Runtime_Checkpoint_Dir': str(checkpoint_dir), 'Runtime_Passenger_JSONL': str(passenger_jsonl_path), 'Runtime_LLM_Call_JSONL': str(llm_jsonl_path), 'Runtime_Progress_JSONL': str(progress_jsonl_path), 'LLM_Model_Fallback_Log_Count': int((llm_call_log_df['Model_Fallback_Used'] == True).sum()) if 'Model_Fallback_Used' in llm_call_log_df else 0, 'LLM_Selected_Count': int(passenger_df['LLM_Selected'].sum()) if 'LLM_Selected' in passenger_df else 0, 'LLM_Success_Count': int(passenger_df['LLM_Valid'].sum()) if 'LLM_Valid' in passenger_df else 0, 'LLM_Fallback_Count': int(passenger_df['LLM_Fallback_Used'].sum()) if 'LLM_Fallback_Used' in passenger_df else 0, 'Rule_LLM_Agreement_Rate': float((passenger_df.loc[passenger_df['LLM_Valid'] == True, 'Rule_Action'] == passenger_df.loc[passenger_df['LLM_Valid'] == True, 'LLM_Action']).mean()) if 'LLM_Valid' in passenger_df and bool((passenger_df['LLM_Valid'] == True).any()) else np.nan}
    try:
        output_path = export_result(OUTPUT_DIR, efficiency_df, network_state_df, decisions_df, passenger_df, service_patterns_df, train_timetable_df, train_position_df, edge_train_counts_df, default_service_audit_df, run_summary, input_audit, decision_comparison_summary_df, llm_call_log_df)
    except Exception as exc:
        final_error_path = write_decision_checkpoint(checkpoint_dir, run_id, completed_passengers, llm_call_log, completed_count=len(completed_passengers), total_count=len(passengers), stage='final_export_failed', error_message=f'{type(exc).__name__}: {exc}')
        print(f'Final Excel export failed. Partial checkpoint is available: {final_error_path}', flush=True)
        raise
    gc.collect()
    print(f'仿真完成，结果文件: {output_path}')
    return {'output_path': output_path, 'efficiency': efficiency_df, 'network_state': network_state_df, 'decisions': decisions_df, 'passengers': passenger_df, 'service_patterns': service_patterns_df, 'train_timetable': train_timetable_df, 'train_position_log': train_position_df, 'edge_train_counts': edge_train_counts_df, 'default_service_audit': default_service_audit_df, 'decision_comparison_summary': decision_comparison_summary_df, 'llm_call_log': llm_call_log_df, 'summary': run_summary}

def main():
    _sr.require_run()
    return run_single_simulation()
