import requests
CASE_VERSION = 'line11_intrusion_20241222_v5'

def v5_resolve_output_dir():
    return SUBMISSION_OUTPUT_DIR
CASE_OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
CASE_CHECKPOINT_DIR = CASE_OUTPUT_DIR / 'checkpoints_v5'
if (CASE_OUTPUT_DIR / 'line_schedule_detailed.xlsx').exists():
    CASE_SCHEDULE_PATH = SUBMISSION_SCHEDULE_PATH
LLM_MODEL_POOL = ['Qwen/Qwen3.5-27B']
LLM_MAX_MODEL_RETRIES = 10
LLM_MODEL_COOLDOWN_SEC = 2
LLM_EMPTY_RESPONSE_COOLDOWN_SEC = 5
LLM_VALIDATION_FAILURE_COOLDOWN_SEC = 0
LLM_MAX_WAIT_FOR_SHORT_COOLDOWN_SEC = 20
V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL = 0.0
V5_QUOTA_PROBE_ROWS = []
V5_RUN_STOP_POLICY = ''
V4_LLM_MODEL_STATUS = {}
llm_model_cooldown_until = {model_name: 0.0 for model_name in LLM_MODEL_POOL}

class V5AccountQuotaExhausted(Exception):
    """Stop on exhausted allowance after saving completed progress."""

class V5ModelScopeHTTPError(Exception):
    

    def __init__(self, message, meta=None):
        super().__init__(message)
        self.meta = meta or {}

class V5EmptyResponseError(Exception):
    

    def __init__(self, message, meta=None):
        super().__init__(message)
        self.meta = meta or {}

def v5_reset_model_runtime():
    """Reset per-run model state."""
    global V4_LLM_MODEL_STATUS, llm_model_cooldown_until, V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL, V5_QUOTA_PROBE_ROWS, V5_RUN_STOP_POLICY
    V4_LLM_MODEL_STATUS = {}
    llm_model_cooldown_until = {model_name: 0.0 for model_name in LLM_MODEL_POOL}
    V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL = 0.0
    V5_QUOTA_PROBE_ROWS = []
    V5_RUN_STOP_POLICY = ''

def v5_to_int_or_nan(value):
    try:
        if value is None or value == '':
            return np.nan
        return int(value)
    except _sr.SubmissionStop:
        raise
    except Exception:
        return np.nan

def v5_response_meta(resp=None, error_text='', model=''):
    """Extract response metadata."""
    headers = getattr(resp, 'headers', {}) or {}

    def h(name):
        try:
            return headers.get(name)
        except _sr.SubmissionStop:
            raise
        except Exception:
            return None
    meta = {'HTTP_Status': int(getattr(resp, 'status_code', 0) or 0) if resp is not None else 0, 'User_Limit': h('modelscope-ratelimit-requests-limit'), 'User_Remaining': h('modelscope-ratelimit-requests-remaining'), 'Model_Limit': h('modelscope-ratelimit-model-requests-limit'), 'Model_Remaining': h('modelscope-ratelimit-model-requests-remaining'), 'Quota_Scope': '', 'Response_Text': str(error_text or ''), 'Model': model}
    meta['Quota_Scope'] = v5_quota_scope(meta, error_text)
    return meta

def v5_quota_scope(meta=None, text=''):
    meta = meta or {}
    lower = str(text or meta.get('Response_Text', '') or '').lower()
    user_remaining = v5_to_int_or_nan(meta.get('User_Remaining'))
    model_remaining = v5_to_int_or_nan(meta.get('Model_Remaining'))
    http_status = int(meta.get('HTTP_Status', 0) or 0)
    if np.isfinite(user_remaining) and int(user_remaining) <= 0:
        return 'account_daily_quota'
    if np.isfinite(model_remaining) and int(model_remaining) <= 0 and (http_status == 429):
        return 'model_daily_quota'
    if "today's quota for model" in lower or ('please try again tomorrow' in lower and 'model' in lower):
        return 'model_daily_quota'
    if http_status == 429 and 'quota' in lower:
        return 'model_daily_quota'
    if http_status == 429:
        return 'rate_limit'
    return ''

def v4_model_status(model):
    model = str(model or '')
    if model not in V4_LLM_MODEL_STATUS:
        V4_LLM_MODEL_STATUS[model] = {'Model': model, 'Attempts': 0, 'Valid': 0, 'Validation_Failures': 0, 'Parse_Failures': 0, 'Empty_Responses': 0, 'Quota_Errors': 0, 'API_Errors': 0, 'Correction_Attempts': 0, 'Local_Repairs': 0, 'Total_Elapsed_Sec': 0.0, 'Cooldown_Reason': '', 'Cooldown_Until_TS': 0.0, 'Last_HTTP_Status': 0, 'User_Limit': '', 'User_Remaining': '', 'Model_Limit': '', 'Model_Remaining': '', 'Quota_Scope': ''}
    return V4_LLM_MODEL_STATUS[model]

def v5_update_model_quota_meta(model, meta):
    if not model:
        return
    status = v4_model_status(model)
    for key in ['HTTP_Status', 'User_Limit', 'User_Remaining', 'Model_Limit', 'Model_Remaining', 'Quota_Scope']:
        value = meta.get(key, '')
        status['Last_HTTP_Status' if key == 'HTTP_Status' else key] = value

def v5_mark_model_quota_from_meta(model, meta):
    return None

def v5_error_category(text='', meta=None):
    scope = v5_quota_scope(meta or {}, text)
    if scope == 'account_daily_quota':
        return 'account_daily_quota'
    if scope == 'model_daily_quota':
        return 'model_daily_quota'
    if scope == 'rate_limit':
        return 'rate_limit'
    return v4_error_category(text)

def v5_available_models(excluded_models=None):
    excluded = {str(model) for model in excluded_models or []}
    return [model for model in LLM_MODEL_POOL if str(model) not in excluded]

def v5_select_model_for_call(excluded_models=None):
    return {'status': 'ready', 'model': 'Qwen/Qwen3.5-27B', 'wait_sec': 0.0, 'reason': 'single_model'}

def v5_modelscope_chat(system_prompt, user_content, model, temperature, timeout_sec, max_tokens=None):
    return _sr.chat(system_prompt, user_prompt, model, temperature, timeout_sec)

def v5_probe_model_quotas(timeout_sec=20):
    return _sr.disabled_probe()

def v5_personal_transport_profile(context):
    profile = context.get('profile', {})
    surface = context.get('surface', {})
    pid = int(context.get('passenger_id', 0) or 0)
    material = f'v5_personal|{pid}|{context.get('origin')}|{context.get('destination')}'
    rng = random.Random(int(hashlib.sha256(material.encode('utf-8')).hexdigest()[:12], 16))
    age = int(profile.get('Age', 40) or 40)
    purpose = str(profile.get('Trip_Purpose', ''))
    O = int(profile.get('OCEAN_O', 3) or 3)
    C = int(profile.get('OCEAN_C', 3) or 3)
    A = int(profile.get('OCEAN_A', 3) or 3)
    N = int(profile.get('OCEAN_N', 3) or 3)
    R = int(profile.get('Risk_Preference', 3) or 3)
    road_km = float(surface.get('Road_Distance_KM', np.nan))
    purpose_urgency = v4_purpose_urgency(purpose)
    urgency = int(min(5, max(1, round(1 + 4 * purpose_urgency + 0.25 * (C - 3) + rng.uniform(-0.5, 0.5)))))
    cost = int(min(5, max(1, round(3 - 0.25 * (R - 3) - 0.15 * (O - 3) + (0.4 if '休闲' in purpose else 0) + rng.uniform(-0.8, 0.8)))))
    transfer = int(min(5, max(1, round(3 + 0.25 * (A - 3) + 0.2 * (R - 3) - 0.25 * (N - 3) + rng.uniform(-0.7, 0.7)))))
    ridehail = int(min(5, max(1, round(3 + 0.25 * urgency - 0.35 * cost + 0.25 * (N - 3) + rng.uniform(-0.7, 0.7)))))
    car_probability = 0.18 + (0.18 if 25 <= age <= 60 else -0.08) + 0.07 * (urgency >= 4) - 0.04 * cost + 0.03 * (R - 3)
    private_car_available = rng.random() < max(0.04, min(0.55, car_probability))
    cycling_acceptable = bool(age <= 60 and np.isfinite(road_km) and (road_km <= 15) and (rng.random() < max(0.08, min(0.65, 0.22 + 0.06 * (O - 3) + 0.05 * (R - 3) - 0.04 * max(0, road_km - 8)))))
    if np.isfinite(road_km):
        walking_tolerance = int(min(5, max(1, round(5 - road_km / 2.5 + 0.25 * (R - 3) + rng.uniform(-0.5, 0.5)))))
    else:
        walking_tolerance = 2
    return {'Time_Urgency': urgency, 'Cost_Sensitivity': cost, 'Transfer_Tolerance': transfer, 'Ridehail_Acceptance': ridehail, 'Private_Car_Available': bool(private_car_available), 'Cycling_Acceptable': bool(cycling_acceptable), 'Walking_Tolerance': walking_tolerance, 'Profile_Note': '这些是基于画像和固定随机种子生成的仿真属性，用于表达个人交通条件差异，不代表外部真实调查。'}

def v5_action_time_for_card(context, action):
    value = v4_action_time_min(context, action)
    return '' if not np.isfinite(value) else f'{float(value):.1f}分钟'

def v5_action_comparison(context):
    allowed = list(context.get('allowed_actions', []))
    prefs = context.get('personal_transport_profile') or v5_personal_transport_profile(context)
    proxy = context.get('operational_proxy') or {}
    surface = context.get('surface', {})
    rows = []
    for action in allowed:
        row = {'action_choice': action, '含义': CASE_ACTION_MEANINGS.get(action, action), '估计时间': v5_action_time_for_card(context, action)}
        if action == 'continue_metro':
            row.update({'稳定性': f'运营代理等级{proxy.get('level', 'unknown')}；当前地铁可达时可选', '成本/负担': '保持原交通方式，换乘认知负担较低', '个人适配': '适合不愿临时改方式、能接受当前延误的乘客'})
        elif action == 'take_shuttle_bus':
            row.update({'稳定性': '官方短驳，需站外换乘和等待', '成本/负担': '费用低但换乘负担较高', '个人适配': '较适合愿意配合官方组织、能接受换乘的乘客'})
        elif action == 'take_other_surface_bus':
            row.update({'稳定性': '常规地面公交，路径可能绕行但费用低', '成本/负担': '成本低，时间和换乘不确定性中等', '个人适配': f'成本敏感度{prefs['Cost_Sensitivity']}/5；不赶时间或不愿打车时可考虑'})
        elif action == 'take_taxi':
            row.update({'稳定性': '点到点较直接，但受道路和叫车等待影响', '成本/负担': '费用高，换乘负担低', '个人适配': f'网约车接受度{prefs['Ridehail_Acceptance']}/5；赶时间或焦虑时更可能选择'})
        elif action == 'take_other_transport':
            other_modes = []
            if prefs.get('Private_Car_Available'):
                other_modes.append(f'私家车约{surface.get('private_car_min', np.nan):.1f}分钟')
            if prefs.get('Cycling_Acceptable'):
                other_modes.append(f'骑行约{surface.get('cycling_min', np.nan):.1f}分钟')
            if int(prefs.get('Walking_Tolerance', 1)) >= 4:
                other_modes.append(f'步行约{surface.get('walking_min', np.nan):.1f}分钟')
            row.update({'稳定性': '取决于个人交通条件和道路环境', '成本/负担': '私家车/骑行/步行的成本和体力负担不同', '个人适配': '；'.join(other_modes) if other_modes else '个人交通条件支持较弱，但仍可在特殊偏好下选择'})
        elif action == 'abandon_trip':
            row.update({'稳定性': '取消本次出行，不再前往目的地', '成本/负担': '避免延误和不确定性，但损失本次出行目标', '个人适配': f'时间紧迫度{prefs['Time_Urgency']}/5；紧迫度低时更可能接受'})
        rows.append(row)
    return rows
V5_BASE_BUILD_CONTEXT = V4_BASE_BUILD_CONTEXT if 'V4_BASE_BUILD_CONTEXT' in globals() else CasePassengerAgent.build_case_context
V5_BASE_FACT_CARD = V4_BASE_FACT_CARD if 'V4_BASE_FACT_CARD' in globals() else case_human_fact_card
V5_BASE_CASE_RECORD = CasePassengerAgent.case_record

def case_system_prompt():
    return '你现在不是交通系统分析器，也不是规则分类器，而是一名真实的上海地铁乘客。请站在乘客本人的第一人称视角，在事故处置现场做一个当下决定。你可以犹豫、烦躁、赶时间、怕麻烦、担心换乘、担心迟到、嫌打车贵，也可以觉得还好、愿意等等、愿意跟着工作人员安排走。你的回答要像一个真实乘客在心里盘算后的选择，而不是像论文摘要、系统报告、心理测评或规则解释。\n\n你会收到一张由导航和代码计算出的事实卡。事实卡是唯一事实来源，里面的OD、路线、时间、事故状态、短驳信息、个人交通条件和 allowed_actions 都必须严格遵守。不得编造新路线、新车站、新区间、新事故、新票价、新等候时间、新公交服务、私家车条件或其他外部信息。如果事实卡没有说某个条件存在，就不要假设它存在。\n\n年龄、性别、出行目的、人格画像、风险偏好和个人交通属性必须真实影响你的选择和语气。例如：赶着上班、上学、就医的人会更在意迟到；休闲出行的人可能更容易接受等待或取消；年纪较大的人可能更在意换乘、步行和不确定性；成本敏感的人会更犹豫是否打车；愿意尝试新方案的人可能更容易接受短驳或替代交通；焦虑或风险规避的人可能更想选择可控方式。但这些都只是概率性倾向，不是机械规则，不能违反事实卡里的可达性和可选动作。\n\n人格与风险偏好是行为倾向，不是后台字段。你可以让这些倾向自然体现在理由里，比如怕折腾、想稳一点、想省钱、想快点到、愿意听工作人员安排；但不要直接写 OCEAN、开放性、尽责性、外向性、宜人性、神经质、风险偏好、人格分数、代码字段名或后台变量。\n五级人格与风险解释：\n' + personality_guidance_text() + "\n\n六类动作的含义必须严格区分：continue_metro 仅表示当前地铁路径确实可达时继续乘地铁；abandon_trip 仅表示取消这次去目的地的出行，不能表示改乘其他方式；take_shuttle_bus 是官方嘉定新城↔武威路站外短驳；take_other_surface_bus 是非短驳的常规地面公交；take_taxi 是出租车或网约车；take_other_transport 是自驾、骑行、步行等其他方式。\n\n硬约束：action_choice 必须且只能从事实卡 allowed_actions 里选择。如果当前地铁不可达，绝不能选择 continue_metro，也不能把硬中断说成只是可以忍受的延误。如果短驳不可用，绝不能选择 take_shuttle_bus。take_other_transport 只能在事实卡给出的私家车、骑行或步行等条件适配时选择，不能凭空假设有车、有电动车或有人接送。\n\nreason 必须是中文，尽量使用第一人称，写出这个乘客当下真实的想法。建议50到120字，重点写为什么这个选择对我来说更合适。可以有情绪和生活化表达，包括但不限于怕耽误、嫌麻烦、想稳一点、打车太贵、短驳至少有人组织、今天不想折腾等。不要把事实卡里的时间逐项机械复述一遍，也不要写成'根据成本敏感度和风险偏好综合评估'这种报告口吻。不得输出Markdown、解释过程、置信度或额外字段。\n\nrisk_perception_level 和 delay_perception_level 只能是 none、low、medium、high、critical。feeling_score 只能是1、2、3、4、5中的整数。只返回严格JSON对象，必须且只能包含：action_choice, reason, risk_perception_level, delay_perception_level, feeling_score。"

def v5_case_human_fact_card(context):
    card = V5_BASE_FACT_CARD(context)
    ordered_actions = context.get('allowed_actions_ordered') or context.get('allowed_actions') or []
    card['allowed_actions'] = [{'action_choice': action, '含义': CASE_ACTION_MEANINGS[action]} for action in ordered_actions]
    card['个人交通属性'] = context.get('personal_transport_profile', {})
    card['动作比较表'] = context.get('action_comparison', [])
    card['动作选择提示'] = '六类动作都是真实候选。请逐项比较时间、稳定性、成本、换乘/体力负担和个人交通条件；不要因为地铁仍可达就机械继续地铁，也不要因为出租车时间短就忽略成本和叫车不确定性。常规公交和个人交通方式在成本敏感、短距离、私家车/骑行条件适配或不赶时间时可以合理选择。'
    return card
case_human_fact_card = v5_case_human_fact_card

def v5_build_case_context(self, normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=None, od_groups=None):
    context = V5_BASE_BUILD_CONTEXT(self, normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=operational_proxy, od_groups=od_groups)
    context['personal_transport_profile'] = v5_personal_transport_profile(context)
    context['transport_feasibility'] = []
    context['action_comparison'] = v5_action_comparison(context)
    context['allowed_actions_ordered'] = v4_order_allowed_actions(context)
    context['fact_card'] = case_human_fact_card(context)
    self.case_context = context
    return context

def case_llm_prompt(context):
    """Build the Chinese user fact card; behavioral instructions remain in the system prompt."""
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
    if action == 'continue_metro' and (not bool(context.get('metro_available'))):
        return (False, '当前地铁不可达时不能选择continue_metro。', warnings)
    if action == 'take_shuttle_bus' and (not bool(context.get('shuttle_available'))):
        return (False, '当前没有可用短驳时不能选择take_shuttle_bus。', warnings)
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
            warnings.append(f'reason含研究术语但v5允许：{term}')
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

def v5_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, parsed, valid, error_message, prompt_tokens, completion_tokens, attempt_elapsed, total_elapsed, attempt_type, repairs=None, quota_stop=False, meta=None, reason_warnings=None, stop_policy='', passenger_model_exhausted=False):
    repairs = repairs or []
    meta = meta or {}
    reason_warnings = reason_warnings or []
    llm_call_log.append({'Passenger_ID': context['passenger_id'], 'Scenario': context['scenario_key'], 'Prompt_Fact_Card': json.dumps(context['fact_card'], ensure_ascii=False), 'Raw_Response': raw, 'Parsed_Action': parsed.get('action_choice', '') if isinstance(parsed, dict) else '', 'Valid': bool(valid), 'Fallback_Used': not bool(valid), 'Error_Message': str(error_message or ''), 'Failure_Category': v5_error_category(error_message, meta), 'Model': model, 'Attempted_Models': ' | '.join(attempted_models), 'Attempt_Count': len(attempted_models), 'Attempt_Type': attempt_type, 'Model_Fallback_Used': False, 'Prompt_Tokens': int(prompt_tokens or 0), 'Completion_Tokens': int(completion_tokens or 0), 'Repair_Applied': bool(repairs), 'Repair_Details': ' | '.join(map(str, repairs)), 'Reason_Warnings': ' | '.join(map(str, reason_warnings)), 'Cooldown_Reason': v4_model_status(model).get('Cooldown_Reason', '') if model else '', 'Next_Available_BJT': v4_format_bjt(v4_model_status(model).get('Cooldown_Until_TS', 0.0)) if model else '', 'Quota_Stop': bool(quota_stop), 'HTTP_Status': meta.get('HTTP_Status', ''), 'User_Limit': meta.get('User_Limit', ''), 'User_Remaining': meta.get('User_Remaining', ''), 'Model_Limit': meta.get('Model_Limit', ''), 'Model_Remaining': meta.get('Model_Remaining', ''), 'Quota_Scope': meta.get('Quota_Scope', ''), 'Stop_Policy': stop_policy, 'Passenger_Model_Exhausted': bool(passenger_model_exhausted), 'Attempt_Elapsed_Sec': round(float(attempt_elapsed or 0.0), 3), 'Total_Elapsed_Sec': round(float(total_elapsed or 0.0), 3)})

def v5_try_one_llm_call(system_prompt, user_prompt, context, model, attempted_models, llm_call_log, attempt_type='primary'):
    raw = ''
    prompt_tokens = completion_tokens = 0
    meta = {}
    start = time.time()
    v4_update_model_status(model, 'attempt')
    if attempt_type == 'correction':
        v4_update_model_status(model, 'correction_attempt')
    try:
        raw, prompt_tokens, completion_tokens, meta = v5_modelscope_chat(system_prompt, user_prompt, model, LLM_TEMPERATURE, LLM_TIMEOUT_SEC)
        v5_update_model_quota_meta(model, meta)
        v5_mark_model_quota_from_meta(model, meta)
        parsed0 = case_parse_json_response(raw)
        parsed, repairs = v4_normalize_payload(parsed0, context)
        if repairs:
            v4_update_model_status(model, 'local_repair')
        valid, error_message, reason_warnings = v5_validate_llm_decision(parsed, context)
        elapsed = time.time() - start
        v5_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, parsed, valid, error_message, prompt_tokens, completion_tokens, elapsed, 0.0, attempt_type, repairs=repairs, meta=meta, reason_warnings=reason_warnings)
        v4_update_model_status(model, 'valid' if valid else 'validation_failure', elapsed)
        return {'ok': True, 'valid': valid, 'parsed': parsed, 'raw': raw, 'error': error_message, 'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'elapsed': elapsed, 'repairs': repairs, 'meta': meta, 'reason_warnings': reason_warnings}
    except _sr.SubmissionStop:
        raise
    except Exception as exc:
        elapsed = time.time() - start
        meta = getattr(exc, 'meta', {}) or v5_response_meta(None, str(exc), model)
        v5_update_model_quota_meta(model, meta)
        category = v5_error_category(str(exc), meta)
        error_message = f'{type(exc).__name__}: {exc}'
        if category == 'account_daily_quota':
            global V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL
            V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL = v4_next_beijing_midnight_ts()
            v4_update_model_status(model, 'quota_error', elapsed)
            v5_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, {}, False, error_message, prompt_tokens, completion_tokens, elapsed, 0.0, attempt_type, repairs=[], quota_stop=True, meta=meta, stop_policy='account_quota_stop')
            raise V5AccountQuotaExhausted(f'ModelScope账号总额度耗尽；下一次可尝试时间约为 {v4_format_bjt(V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL)}。')
        if category == 'model_daily_quota':
            v4_mark_model_cooldown(model, reason='model_daily_quota', until_ts=v4_next_beijing_midnight_ts())
            v4_update_model_status(model, 'quota_error', elapsed)
        elif category == 'empty_content':
            v4_mark_model_cooldown(model, reason='empty_response', seconds=LLM_EMPTY_RESPONSE_COOLDOWN_SEC)
            v4_update_model_status(model, 'empty_response', elapsed)
        elif category == 'json_parse':
            v4_update_model_status(model, 'parse_failure', elapsed)
        else:
            v4_mark_model_cooldown(model, reason='api_error', seconds=LLM_MODEL_COOLDOWN_SEC)
            v4_update_model_status(model, 'api_error', elapsed)
        v5_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, {}, False, error_message, prompt_tokens, completion_tokens, elapsed, 0.0, attempt_type, repairs=[], quota_stop=False, meta=meta)
        return {'ok': False, 'valid': False, 'parsed': {}, 'raw': raw, 'error': error_message, 'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'elapsed': elapsed, 'repairs': [], 'meta': meta, 'reason_warnings': []}

def case_call_llm(context, llm_call_log):
    return _sr.case_call(globals(), context, llm_call_log)

def v5_action_time_min(context, action):
    if action != 'take_other_transport':
        return v4_action_time_min(context, action)
    prefs = context.get('personal_transport_profile', {})
    surface = context.get('surface', {})
    values = []
    if prefs.get('Private_Car_Available'):
        values.append(float(surface.get('private_car_min', np.nan)))
    if prefs.get('Cycling_Acceptable'):
        values.append(float(surface.get('cycling_min', np.nan)))
    if int(prefs.get('Walking_Tolerance', 1)) >= 4:
        values.append(float(surface.get('walking_min', np.nan)))
    values = [v for v in values if np.isfinite(v)]
    return min(values) if values else v4_action_time_min(context, action)

def v5_utility_fallback_choice(context):
    allowed = list(context.get('allowed_actions', []))
    profile = context.get('profile', {})
    prefs = context.get('personal_transport_profile') or {}
    surface = context.get('surface', {})
    urgency = int(prefs.get('Time_Urgency', 3))
    cost = int(prefs.get('Cost_Sensitivity', 3))
    transfer = int(prefs.get('Transfer_Tolerance', 3))
    ridehail = int(prefs.get('Ridehail_Acceptance', 3))
    O = int(profile.get('OCEAN_O', 3))
    A = int(profile.get('OCEAN_A', 3))
    N = int(profile.get('OCEAN_N', 3))
    R = int(profile.get('Risk_Preference', 3))
    proxy = context.get('operational_proxy') or {}
    proxy_score = int(proxy.get('score', 0) or 0)
    material = f'v5_fallback|{context.get('passenger_id')}|{context.get('scenario_key')}|{context.get('origin')}|{context.get('destination')}'
    rng = random.Random(int(hashlib.sha256(material.encode('utf-8')).hexdigest()[:12], 16))
    finite_times = [v5_action_time_min(context, action) for action in allowed if action != 'abandon_trip']
    finite_times = [value for value in finite_times if np.isfinite(value)]
    median_time = float(np.median(finite_times)) if finite_times else 60.0
    utilities = {}
    for action in allowed:
        if action == 'abandon_trip':
            utilities[action] = -1.4 + (3 - urgency) * 0.25 + (N - 3) * 0.1 - (int(profile.get('OCEAN_C', 3)) - 3) * 0.12
        else:
            t = v5_action_time_min(context, action)
            utilities[action] = -(t / max(20.0, median_time) if np.isfinite(t) else 2.5)
        if action == 'continue_metro':
            utilities[action] += 0.32 + (R - 3) * 0.06 - proxy_score * 0.16 - max(0, urgency - 3) * 0.05
        elif action == 'take_shuttle_bus':
            utilities[action] += 0.2 + (A - 3) * 0.12 + (transfer - 3) * 0.14 + (O - 3) * 0.06
        elif action == 'take_other_surface_bus':
            bus_time = v5_action_time_min(context, action)
            utilities[action] += 0.18 + (cost - 3) * 0.2 + (3 - urgency) * 0.14
            if np.isfinite(bus_time) and np.isfinite(median_time) and (bus_time <= median_time * 1.25):
                utilities[action] += 0.35
        elif action == 'take_taxi':
            utilities[action] += (urgency - 3) * 0.22 + (ridehail - 3) * 0.22 - (cost - 3) * 0.18 + (N - 3) * 0.1
        elif action == 'take_other_transport':
            utilities[action] += (O - 3) * 0.1 + (R - 3) * 0.08
            if prefs.get('Private_Car_Available'):
                utilities[action] += 0.42
            if prefs.get('Cycling_Acceptable'):
                utilities[action] += 0.25
            if int(prefs.get('Walking_Tolerance', 1)) >= 4:
                utilities[action] += 0.22
        utilities[action] += rng.uniform(-0.24, 0.24)
    choice = max(utilities, key=utilities.get)
    return (choice, 'v5_utility_fallback:' + json.dumps({k: round(float(v), 3) for k, v in utilities.items()}, ensure_ascii=False))

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
    self.final_route_plan = self.current_route_plan if self.final_action == 'continue_metro' else self.initial_route_plan
    self.reroute_count = int(self.final_action in {'take_shuttle_bus', 'take_other_surface_bus', 'take_taxi', 'take_other_transport'})
    return self

def v5_case_record(self):
    record = V5_BASE_CASE_RECORD(self)
    context = getattr(self, 'case_context', {}) or {}
    prefs = context.get('personal_transport_profile', {}) or {}
    record.update({'Personal_Time_Urgency': prefs.get('Time_Urgency', ''), 'Personal_Cost_Sensitivity': prefs.get('Cost_Sensitivity', ''), 'Personal_Transfer_Tolerance': prefs.get('Transfer_Tolerance', ''), 'Personal_Ridehail_Acceptance': prefs.get('Ridehail_Acceptance', ''), 'Personal_Private_Car_Available': prefs.get('Private_Car_Available', ''), 'Personal_Cycling_Acceptable': prefs.get('Cycling_Acceptable', ''), 'Personal_Walking_Tolerance': prefs.get('Walking_Tolerance', ''), 'Action_Comparison_Input': json.dumps(context.get('action_comparison', []), ensure_ascii=False), 'LLM_Reason_Warnings': str(getattr(self, 'llm_reason_warnings', '')), 'LLM_Stop_Policy': str(getattr(self, 'llm_stop_policy', '')), 'LLM_Passenger_Model_Exhausted': bool(getattr(self, 'llm_passenger_model_exhausted', False))})
    return record
CasePassengerAgent.build_case_context = v5_build_case_context
CasePassengerAgent.technical_fallback = v5_technical_fallback
CasePassengerAgent.decide_case = v5_decide_case
CasePassengerAgent.case_record = v5_case_record

def v5_llm_model_status_df():
    return pd.DataFrame([{'Model': LLM_MODEL, 'Execution_Mode': 'single_model'}])

def v5_llm_error_summary_df(llm_log_df):
    if llm_log_df is None or llm_log_df.empty:
        return pd.DataFrame(columns=['Scenario', 'Failure_Category', 'Quota_Scope', 'Model', 'Rows', 'Valid_N', 'Quota_Stop_N', 'Passenger_Model_Exhausted_N', 'Repair_Applied_N'])
    frame = llm_log_df.copy()
    for col in ['Failure_Category', 'Quota_Scope', 'Model', 'Scenario']:
        if col not in frame:
            frame[col] = ''
    for col in ['Quota_Stop', 'Repair_Applied', 'Passenger_Model_Exhausted']:
        if col not in frame:
            frame[col] = False
    grouped = frame.groupby(['Scenario', 'Failure_Category', 'Quota_Scope', 'Model'], dropna=False)
    return grouped.agg(Rows=('Passenger_ID', 'size'), Valid_N=('Valid', lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())), Quota_Stop_N=('Quota_Stop', lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())), Passenger_Model_Exhausted_N=('Passenger_Model_Exhausted', lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())), Repair_Applied_N=('Repair_Applied', lambda s: int(pd.Series(s).fillna(False).astype(bool).sum()))).reset_index().sort_values(['Scenario', 'Rows'], ascending=[True, False])

def v5_choice_coverage_diagnostics(passenger_df):
    if passenger_df is None or passenger_df.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in passenger_df.groupby(['Scenario', 'Scenario_Name'], dropna=False):
        scenario, name = keys
        total = len(group)
        present = set(group['Action'].dropna().astype(str))
        all_actions = list(LLM_ALLOWED_ACTIONS)
        for action in all_actions:
            n = int((group['Action'] == action).sum())
            rows.append({'Scenario': scenario, 'Scenario_Name': name, 'Population': 'All_Final', 'Action': action, 'N': n, 'Pct': round(n / total * 100, 3) if total else np.nan, 'Present': action in present})
        valid_group = group[group.get('LLM_Valid', False) == True]
        valid_total = len(valid_group)
        for action in all_actions:
            n = int((valid_group['Action'] == action).sum()) if valid_total else 0
            rows.append({'Scenario': scenario, 'Scenario_Name': name, 'Population': 'Valid_LLM_Only', 'Action': action, 'N': n, 'Pct': round(n / valid_total * 100, 3) if valid_total else np.nan, 'Present': n > 0})
    return pd.DataFrame(rows)

def v5_write_partial_excel(path, records, logs, cohort_df, run_id, quota_stop_message='', quota_probe_df=None):
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        record_df = pd.DataFrame(records)
        record_df.to_excel(writer, sheet_name='Passenger_Decisions_Partial', index=False)
        log_df = pd.DataFrame(logs)
        log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        v5_llm_error_summary_df(log_df).to_excel(writer, sheet_name='LLM_Error_Summary', index=False)
        v5_llm_model_status_df().to_excel(writer, sheet_name='LLM_Model_Status', index=False)
        pd.DataFrame(quota_probe_df if quota_probe_df is not None else V5_QUOTA_PROBE_ROWS).to_excel(writer, sheet_name='LLM_Quota_Probe', index=False)
        v5_choice_coverage_diagnostics(record_df).to_excel(writer, sheet_name='Choice_Coverage_Diagnostics', index=False)
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Completed_Decisions': len(records), 'Quota_Stop_Message': quota_stop_message, 'Stop_Policy': V5_RUN_STOP_POLICY, 'Saved_At_BJT': v4_beijing_now().strftime('%Y-%m-%d %H:%M:%S BJT')}]).to_excel(writer, sheet_name='Checkpoint_Status', index=False)

def v5_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_df, quota_probe_df=None, output_dir=CASE_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'Line11_Incident_LLM_TrainSimulation_v5_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx'
    zero_attempt_fallback = int(((passenger_df.get('LLM_Attempt_Count', pd.Series(dtype=float)).fillna(0).astype(float) == 0) & (passenger_df.get('Decision_Source', pd.Series(dtype=str)) == 'Rule_Fallback')).sum()) if not passenger_df.empty else 0
    passenger_model_exhausted_n = int(passenger_df.get('LLM_Passenger_Model_Exhausted', pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not passenger_df.empty else 0
    run_summary = pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Cohort_N': len(cohort_df), 'Affected_N': int(cohort_df['Affected_Corridor'].sum()), 'LLM_Valid_Rate': float(passenger_df['LLM_Valid'].mean()) if not passenger_df.empty else np.nan, 'LLM_Fallback_N': int(passenger_df['LLM_Fallback_Used'].sum()) if not passenger_df.empty else 0, 'LLM_Fallback_Rate': float(passenger_df['LLM_Fallback_Used'].mean()) if not passenger_df.empty else np.nan, 'Zero_Attempt_Fallback_N': zero_attempt_fallback, 'Passenger_Model_Exhausted_N': passenger_model_exhausted_n, 'Account_Daily_Quota_Stop': bool(V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL and V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL > v4_now_ts()), 'Train_Log_Step_Sec': V3_LOG_STEP_SEC, 'GIF_Frame_Sec': V3_GIF_FRAME_SEC, 'GIF_Path': str(gif_path or '')}])
    gif_manifest = pd.DataFrame([{'GIF_Path': str(gif_path or ''), 'Frame_Interval_Sec': V3_GIF_FRAME_SEC, 'Start': case_hhmm(V3_SIM_START_MIN), 'End': case_hhmm(V3_SIM_END_MIN), 'Scope': '全网列车，11号线工况高亮'}])
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Decision_Share_Summary', index=False)
        passenger_df.to_excel(writer, sheet_name='Passenger_Decisions', index=False)
        llm_log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        v5_llm_error_summary_df(llm_log_df).to_excel(writer, sheet_name='LLM_Error_Summary', index=False)
        v5_llm_model_status_df().to_excel(writer, sheet_name='LLM_Model_Status', index=False)
        pd.DataFrame(quota_probe_df if quota_probe_df is not None else V5_QUOTA_PROBE_ROWS).to_excel(writer, sheet_name='LLM_Quota_Probe', index=False)
        v5_choice_coverage_diagnostics(passenger_df).to_excel(writer, sheet_name='Choice_Coverage_Diagnostics', index=False)
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

def case_plot_efficiency_v5(efficiency_df, output_dir=CASE_OUTPUT_DIR):
    path = case_plot_efficiency_v4(efficiency_df, output_dir=output_dir)
    if path:
        new_path = Path(output_dir) / 'Network_Efficiency_Curve_v5.png'
        try:
            Path(path).replace(new_path)
            return new_path
        except _sr.SubmissionStop:
            raise
        except Exception:
            return path
    return None

def run_case_study_v5(use_live_llm=True, compute_efficiency=True, generate_gif=False, resume=False, run_label=None, quota_probe=False):
    _sr.require_run()
    global V5_RUN_STOP_POLICY
    v5_reset_model_runtime()
    case_require_inputs()
    cohort_df = sample_case_cohort()
    base_run_id = case_run_id(cohort_df)
    run_id = base_run_id if resume else f'{base_run_id}_{run_label or _dt.now().strftime('%Y%m%d_%H%M%S')}'
    checkpoint_paths = case_checkpoint_paths(run_id)
    resumed_records, resumed_logs = case_load_resume(checkpoint_paths['jsonl']) if resume else ({}, [])
    quota_probe_df = v5_probe_model_quotas() if use_live_llm and quota_probe else pd.DataFrame(V5_QUOTA_PROBE_ROWS)
    if V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL and V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL > v4_now_ts():
        V5_RUN_STOP_POLICY = 'account_quota_stop_before_decision'
        v5_write_partial_excel(checkpoint_paths['excel'], list(resumed_records.values()), resumed_logs, cohort_df, run_id, quota_stop_message=f'ModelScope账号总额度耗尽；下一次可尝试时间约为 {v4_format_bjt(V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL)}。', quota_probe_df=quota_probe_df)
        raise RuntimeError(f'v5已保存checkpoint并停止：ModelScope账号总额度耗尽；下一次可尝试时间约为 {v4_format_bjt(V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL)}。')
    dynamic_system = build_v3_dynamic_system()
    train_engine = ContinuousScenarioTrainSimulationEngine(dynamic_system, day_type=CASE_DAY_TYPE)
    train_outputs = train_engine.run_continuous()
    gif_path = generate_v3_train_gif(train_outputs['train_position_log'], dynamic_system) if generate_gif else None
    all_records, llm_call_log, proxy_rows = (list(resumed_records.values()), list(resumed_logs), [])
    shuttle_rows = []
    try:
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
                    v5_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id, quota_probe_df=quota_probe_df)
                    print(f'v5 checkpoint: {len(all_records)}/{CASE_SAMPLE_SIZE * 3}', flush=True)
    except (V5AccountQuotaExhausted, _sr.SubmissionStop) as exc:
        V5_RUN_STOP_POLICY = 'account_quota_stop_during_decision'
        v5_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id, quota_stop_message=str(exc), quota_probe_df=quota_probe_df)
        raise RuntimeError(f'v5已保存checkpoint并停止：{exc}') from exc
    passenger_df = pd.DataFrame(all_records).sort_values(['Scenario', 'PID']).reset_index(drop=True)
    if len(passenger_df) != CASE_SAMPLE_SIZE * 3:
        raise AssertionError('乘客决策记录数量应为500×3；v5只有账号总额度耗尽时才应提前停止。')
    summary_df = case_summary_table(passenger_df)
    llm_log_df = pd.DataFrame(llm_call_log)
    shuttle_df = pd.DataFrame(shuttle_rows)
    efficiency_df = case_network_efficiency_curve() if compute_efficiency else pd.DataFrame()
    curve_path = case_plot_efficiency_v5(efficiency_df) if compute_efficiency else None
    excel_path = v5_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_rows, quota_probe_df=quota_probe_df)
    return {'cohort': cohort_df, 'passenger_decisions': passenger_df, 'decision_share_summary': summary_df, 'llm_call_log': llm_log_df, 'quota_probe': quota_probe_df, 'train_outputs': train_outputs, 'operational_proxy': pd.DataFrame(proxy_rows), 'network_efficiency': efficiency_df, 'excel_path': excel_path, 'curve_path': curve_path, 'gif_path': gif_path, 'run_id': run_id, 'checkpoint_paths': checkpoint_paths, 'llm_model_status': v5_llm_model_status_df()}
CASE_VERSION = 'line11_intrusion_20241222_v6'

def v6_resolve_output_dir():
    return SUBMISSION_OUTPUT_DIR
CASE_OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
CASE_CHECKPOINT_DIR = CASE_OUTPUT_DIR / 'checkpoints_v6'
if (CASE_OUTPUT_DIR / 'line_schedule_detailed.xlsx').exists():
    CASE_SCHEDULE_PATH = SUBMISSION_SCHEDULE_PATH
V6_MODEL_IDS = ['Qwen/Qwen3.5-27B']
LLM_MODEL_POOL = ['Qwen/Qwen3.5-27B']
LLM_MAX_MODEL_RETRIES = 10
LLM_MODEL_COOLDOWN_SEC = 2
LLM_EMPTY_RESPONSE_COOLDOWN_SEC = 5
LLM_VALIDATION_FAILURE_COOLDOWN_SEC = 0
LLM_MAX_WAIT_FOR_SHORT_COOLDOWN_SEC = 20
V6_REFERENCE_COHORT_PATH = Path(os.environ.get('SCENARIO_B_COHORT_FILE', str(SUBMISSION_PACKAGE / 'inputs' / 'scenario_b_cohort.csv')))
V6_REFERENCE_COHORT_SOURCE = str(V6_REFERENCE_COHORT_PATH)
V6_SCENARIO_FILTER_FOR_RUN = ''
V6_EXPECTED_DECISIONS = None
V6_RUN_STOP_POLICY = ''
V6_QUOTA_PROBE_ROWS = []
V5_ACCOUNT_QUOTA_EXHAUSTED_UNTIL = 0.0
V5_QUOTA_PROBE_ROWS = []
V5_RUN_STOP_POLICY = ''
V4_LLM_MODEL_STATUS = {}
llm_model_cooldown_until = {pair: 0.0 for pair in LLM_MODEL_POOL}
_V6_ORIG_SELECT_MODEL = v5_select_model_for_call
_V6_ORIG_LOG_ATTEMPT = v5_log_llm_attempt
_V6_ORIG_CASE_CALL_LLM = case_call_llm

def v6_reset_model_runtime():
    v5_reset_model_runtime()
    globals()['V6_QUOTA_PROBE_ROWS'] = []
    globals()['V6_RUN_STOP_POLICY'] = ''

def v5_modelscope_chat(system_prompt, user_content, model, temperature, timeout_sec, max_tokens=None):
    return _sr.chat(system_prompt, user_prompt, model, temperature, timeout_sec)

def v5_mark_model_quota_from_meta(model, meta):
    return None

def v5_select_model_for_call(excluded_models=None):
    return {'status': 'ready', 'model': 'Qwen/Qwen3.5-27B', 'wait_sec': 0.0, 'reason': 'single_model'}

def v5_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, parsed, valid, error_message, prompt_tokens, completion_tokens, attempt_elapsed, total_elapsed, attempt_type, repairs=None, quota_stop=False, meta=None, reason_warnings=None, stop_policy='', passenger_model_exhausted=False):
    return _V6_ORIG_LOG_ATTEMPT(llm_call_log, context, model, attempted_models, raw, parsed, valid, error_message, prompt_tokens, completion_tokens, attempt_elapsed, total_elapsed, attempt_type, repairs=repairs, quota_stop=quota_stop, meta=meta, reason_warnings=reason_warnings, stop_policy=stop_policy, passenger_model_exhausted=passenger_model_exhausted)

def case_call_llm(context, llm_call_log):
    return _sr.case_call(globals(), context, llm_call_log)

def v5_llm_model_status_df():
    return pd.DataFrame([{'Model': LLM_MODEL, 'Execution_Mode': 'single_model'}])

def v6_probe_model_quotas(timeout_sec=20):
    return _sr.disabled_probe()

def v5_probe_model_quotas(timeout_sec=20):
    return _sr.disabled_probe()

def v6_bool_series(series):

    def convert(value):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {'true', '1', 'yes', 'y'}:
            return True
        if text in {'false', '0', 'no', 'n'}:
            return False
        raise ValueError(f'Cannot parse Affected_Corridor as bool: {value!r}')
    return series.map(convert)

def sample_case_cohort():
    path = V6_REFERENCE_COHORT_PATH
    if not path.exists():
        raise FileNotFoundError(f'v6 must read Cohort from v5 partial workbook; missing: {path}')
    cohort = pd.read_csv(path) if path.suffix.lower() == '.csv' else pd.read_excel(path, sheet_name='Cohort')
    required_cols = ['Origin', 'Dest', 'Affected_Corridor', 'OD_Sample_Group', 'OD_Sampling_Source', 'Baseline_Route', 'PID']
    missing = [col for col in required_cols if col not in cohort.columns]
    if missing:
        raise AssertionError(f'Reference Cohort is missing required columns: {missing}')
    cohort = cohort[required_cols].copy()
    cohort['PID'] = cohort['PID'].astype(int)
    cohort = cohort.sort_values('PID').reset_index(drop=True)
    cohort['Affected_Corridor'] = v6_bool_series(cohort['Affected_Corridor'])
    if len(cohort) != CASE_SAMPLE_SIZE:
        raise AssertionError(f'Reference Cohort must contain {CASE_SAMPLE_SIZE} passengers; got {len(cohort)}.')
    if cohort['PID'].nunique() != CASE_SAMPLE_SIZE or set(cohort['PID']) != set(range(1, CASE_SAMPLE_SIZE + 1)):
        raise AssertionError('Reference Cohort PID must be unique and cover 1-500.')
    affected_n = int(cohort['Affected_Corridor'].sum())
    if affected_n != CASE_AFFECTED_COUNT:
        raise AssertionError(f'Reference Cohort must contain {CASE_AFFECTED_COUNT} affected passengers; got {affected_n}.')
    group_counts = cohort['OD_Sample_Group'].value_counts().to_dict()
    if group_counts.get('affected_corridor', 0) != CASE_AFFECTED_COUNT:
        raise AssertionError(f'affected_corridor group count is invalid: {group_counts}')
    if group_counts.get('unaffected_line11_control', 0) != CASE_SAMPLE_SIZE - CASE_AFFECTED_COUNT:
        raise AssertionError(f'unaffected_line11_control group count is invalid: {group_counts}')
    return cohort

def v6_resolve_scenarios(scenario_keys=None):
    if scenario_keys is None:
        return list(CASE_SCENARIOS[:3])
    keys = list(scenario_keys)
    if not keys:
        raise ValueError('scenario_keys cannot be empty.')
    invalid = [key for key in keys if key not in CASE_SCENARIO_BY_KEY]
    if invalid:
        raise KeyError(f'Unknown scenario keys: {invalid}')
    return [CASE_SCENARIO_BY_KEY[key] for key in keys]

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
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Scenario_Filter': V6_SCENARIO_FILTER_FOR_RUN, 'Reference_Cohort_Source': V6_REFERENCE_COHORT_PATH.name, 'Expected_Decisions': V6_EXPECTED_DECISIONS, 'Completed_Decisions': len(records), 'Quota_Stop_Message': quota_stop_message, 'Stop_Policy': V6_RUN_STOP_POLICY, 'Saved_At_BJT': v4_beijing_now().strftime('%Y-%m-%d %H:%M:%S BJT')}]).to_excel(writer, sheet_name='Checkpoint_Status', index=False)

def v5_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_df, quota_probe_df=None, output_dir=CASE_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'Line11_Incident_LLM_TrainSimulation_v6_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx'
    log_df = pd.DataFrame(llm_log_df)
    zero_attempt_fallback = int(((passenger_df.get('LLM_Attempt_Count', pd.Series(dtype=float)).fillna(0).astype(float) == 0) & (passenger_df.get('Decision_Source', pd.Series(dtype=str)) == 'Rule_Fallback')).sum()) if not passenger_df.empty else 0
    passenger_model_exhausted_n = int(passenger_df.get('LLM_Passenger_Model_Exhausted', pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not passenger_df.empty else 0
    run_summary = pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Scenario_Filter': V6_SCENARIO_FILTER_FOR_RUN, 'Reference_Cohort_Source': V6_REFERENCE_COHORT_PATH.name, 'Expected_Decisions': V6_EXPECTED_DECISIONS, 'Cohort_N': len(cohort_df), 'Affected_N': int(cohort_df['Affected_Corridor'].sum()), 'LLM_Valid_Rate': float(passenger_df['LLM_Valid'].mean()) if not passenger_df.empty else np.nan, 'LLM_Fallback_N': int(passenger_df['LLM_Fallback_Used'].sum()) if not passenger_df.empty else 0, 'LLM_Fallback_Rate': float(passenger_df['LLM_Fallback_Used'].mean()) if not passenger_df.empty else np.nan, 'Zero_Attempt_Fallback_N': zero_attempt_fallback, 'Passenger_Model_Exhausted_N': passenger_model_exhausted_n, 'Train_Log_Step_Sec': V3_LOG_STEP_SEC, 'GIF_Frame_Sec': V3_GIF_FRAME_SEC, 'GIF_Path': str(gif_path or '')}])
    gif_manifest = pd.DataFrame([{'GIF_Path': str(gif_path or ''), 'Frame_Interval_Sec': V3_GIF_FRAME_SEC, 'Start': case_hhmm(V3_SIM_START_MIN), 'End': case_hhmm(V3_SIM_END_MIN), 'Scope': 'Full-network train simulation; Line 11 incident highlighted'}])
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Decision_Share_Summary', index=False)
        passenger_df.to_excel(writer, sheet_name='Passenger_Decisions', index=False)
        log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        v5_llm_error_summary_df(log_df).to_excel(writer, sheet_name='LLM_Error_Summary', index=False)
        v5_llm_model_status_df().to_excel(writer, sheet_name='LLM_Model_Status', index=False)
        pd.DataFrame(quota_probe_df if quota_probe_df is not None else V6_QUOTA_PROBE_ROWS).to_excel(writer, sheet_name='LLM_Quota_Probe', index=False)
        v5_choice_coverage_diagnostics(passenger_df).to_excel(writer, sheet_name='Choice_Coverage_Diagnostics', index=False)
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

def case_plot_efficiency_v5(efficiency_df, output_dir=CASE_OUTPUT_DIR):
    path = case_plot_efficiency_v4(efficiency_df, output_dir=output_dir)
    if path:
        new_path = Path(output_dir) / 'Network_Efficiency_Curve_v6.png'
        try:
            Path(path).replace(new_path)
            return new_path
        except _sr.SubmissionStop:
            raise
        except Exception:
            return path
    return None

def run_case_study_v6(use_live_llm=True, compute_efficiency=True, generate_gif=False, resume=False, run_label=None, quota_probe=False, scenario_keys=None):
    _sr.require_run()
    quota_probe = False
    global V6_RUN_STOP_POLICY, V6_SCENARIO_FILTER_FOR_RUN, V6_EXPECTED_DECISIONS
    v6_reset_model_runtime()
    case_require_inputs()
    cohort_df = sample_case_cohort()
    selected_scenarios = v6_resolve_scenarios(scenario_keys)
    V6_SCENARIO_FILTER_FOR_RUN = ','.join((scenario.key for scenario in selected_scenarios))
    V6_EXPECTED_DECISIONS = len(cohort_df) * len(selected_scenarios)
    base_run_id = case_run_id(cohort_df)
    run_id = base_run_id if resume else f'{base_run_id}_{run_label or _dt.now().strftime('%Y%m%d_%H%M%S')}'
    checkpoint_paths = case_checkpoint_paths(run_id)
    resumed_records, resumed_logs = case_load_resume(checkpoint_paths['jsonl']) if resume else ({}, [])
    quota_probe_df = v6_probe_model_quotas() if use_live_llm and quota_probe else pd.DataFrame(V6_QUOTA_PROBE_ROWS)
    dynamic_system = build_v3_dynamic_system()
    train_engine = ContinuousScenarioTrainSimulationEngine(dynamic_system, day_type=CASE_DAY_TYPE)
    train_outputs = train_engine.run_continuous()
    gif_path = generate_v3_train_gif(train_outputs['train_position_log'], dynamic_system) if generate_gif else None
    all_records, llm_call_log, proxy_rows = (list(resumed_records.values()), list(resumed_logs), [])
    shuttle_rows = []
    try:
        for scenario in selected_scenarios:
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
                    v5_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id, quota_probe_df=quota_probe_df)
                    print(f'v6 checkpoint: {len(all_records)}/{V6_EXPECTED_DECISIONS}', flush=True)
    except (V5AccountQuotaExhausted, _sr.SubmissionStop) as exc:
        V6_RUN_STOP_POLICY = 'all_account_quota_stop_during_decision'
        v5_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id, quota_stop_message=str(exc), quota_probe_df=quota_probe_df)
        raise RuntimeError(f'v6 saved checkpoint and stopped: {exc}') from exc
    passenger_df = pd.DataFrame(all_records).sort_values(['Scenario', 'PID']).reset_index(drop=True)
    if len(passenger_df) != V6_EXPECTED_DECISIONS:
        raise AssertionError(f'Passenger decision records should be {V6_EXPECTED_DECISIONS}; incomplete runs must be resumed before analysis.')
    summary_df = case_summary_table(passenger_df)
    llm_log_df = pd.DataFrame(llm_call_log)
    shuttle_df = pd.DataFrame(shuttle_rows)
    efficiency_df = case_network_efficiency_curve() if compute_efficiency else pd.DataFrame()
    curve_path = case_plot_efficiency_v5(efficiency_df) if compute_efficiency else None
    excel_path = v5_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_rows, quota_probe_df=quota_probe_df)
    return {'cohort': cohort_df, 'passenger_decisions': passenger_df, 'decision_share_summary': summary_df, 'llm_call_log': llm_log_df, 'quota_probe': quota_probe_df, 'train_outputs': train_outputs, 'operational_proxy': pd.DataFrame(proxy_rows), 'network_efficiency': efficiency_df, 'excel_path': excel_path, 'curve_path': curve_path, 'gif_path': gif_path, 'run_id': run_id, 'checkpoint_paths': checkpoint_paths, 'expected_decisions': V6_EXPECTED_DECISIONS, 'scenario_filter': V6_SCENARIO_FILTER_FOR_RUN, 'llm_model_status': v5_llm_model_status_df()}
