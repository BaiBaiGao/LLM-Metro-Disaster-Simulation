from collections import defaultdict
from datetime import datetime as _dt, timedelta as _timedelta, timezone as _timezone
from pathlib import Path
import ast
CASE_VERSION = 'line11_intrusion_20241222_v4'
CASE_CHECKPOINT_DIR = CASE_OUTPUT_DIR / 'checkpoints_v4'
LLM_MODEL_POOL = ['Qwen/Qwen3.5-27B']
LLM_MAX_MODEL_RETRIES = 10
LLM_MODEL_COOLDOWN_SEC = 2
LLM_EMPTY_RESPONSE_COOLDOWN_SEC = 5
LLM_VALIDATION_FAILURE_COOLDOWN_SEC = 0
LLM_MAX_WAIT_FOR_SHORT_COOLDOWN_SEC = 20
LLM_CORRECTION_RETRY_ENABLED = True
LLM_SKIP_MODELS_IN_COOLDOWN = False
V4_BEIJING_TZ = _timezone(_timedelta(hours=8))
V4_DAILY_QUOTA_POLICY = 'save_and_stop'
V4_LLM_MODEL_STATUS = {}

def v4_resolve_data_root():
    return _sr.project_root()

def v4_resolve_output_dir(data_root):
    return SUBMISSION_OUTPUT_DIR

def v4_resolve_schedule_path(data_root, output_dir):
    return SUBMISSION_SCHEDULE_PATH
CASE_DATA_ROOT = _sr.project_root()
CASE_OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
CASE_LOCAL_SCHEDULE = SUBMISSION_SCHEDULE_PATH
CASE_SCHEDULE_PATH = SUBMISSION_SCHEDULE_PATH
CASE_CHECKPOINT_DIR = CASE_OUTPUT_DIR / 'checkpoints_v4'

class V4DailyQuotaExhausted(RuntimeError):
    """Represent an exhausted inference allowance."""

def v4_now_ts():
    return time.time()

def v4_beijing_now(ts=None):
    return _dt.fromtimestamp(v4_now_ts() if ts is None else float(ts), tz=V4_BEIJING_TZ)

def v4_next_beijing_midnight_ts(now_ts=None):
    now_bjt = v4_beijing_now(now_ts)
    next_midnight = (now_bjt + _timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
    return next_midnight.timestamp()

def v4_format_bjt(ts):
    if not ts or not np.isfinite(float(ts)):
        return ''
    return v4_beijing_now(float(ts)).strftime('%Y-%m-%d %H:%M:%S BJT')

def v4_is_daily_quota_error(text):
    text = str(text or '').lower()
    quota_markers = ["today's quota", 'daily quota', 'please try again tomorrow', 'try again tomorrow', 'quota']
    return '429' in text and 'quota' in text or any((marker in text for marker in quota_markers))

def v4_is_empty_response_error(text):
    text = str(text or '').lower()
    return '空内容' in text or 'empty' in text or 'no content' in text

def v4_error_category(text):
    text = str(text or '')
    lower = text.lower()
    if not text:
        return 'none'
    if v4_is_daily_quota_error(text):
        return 'daily_quota'
    if v4_is_empty_response_error(text):
        return 'empty_content'
    if 'json' in lower or 'expecting value' in lower:
        return 'json_parse'
    if 'action_choice' in lower or '动作' in text or 'allowed' in lower:
        return 'action_invalid'
    if 'reason' in lower or '理由' in text:
        return 'reason_invalid'
    if 'timeout' in lower:
        return 'timeout'
    if 'ratelimit' in lower or '429' in lower:
        return 'rate_limit'
    return 'other'

def v4_model_status(model):
    model = str(model or '')
    if model not in V4_LLM_MODEL_STATUS:
        V4_LLM_MODEL_STATUS[model] = {'Model': model, 'Attempts': 0, 'Valid': 0, 'Validation_Failures': 0, 'Parse_Failures': 0, 'Empty_Responses': 0, 'Quota_Errors': 0, 'API_Errors': 0, 'Correction_Attempts': 0, 'Local_Repairs': 0, 'Total_Elapsed_Sec': 0.0, 'Cooldown_Reason': '', 'Cooldown_Until_TS': 0.0}
    return V4_LLM_MODEL_STATUS[model]

def v4_update_model_status(model, event, elapsed_sec=0.0):
    status = v4_model_status(model)
    event_map = {'attempt': 'Attempts', 'valid': 'Valid', 'validation_failure': 'Validation_Failures', 'parse_failure': 'Parse_Failures', 'empty_response': 'Empty_Responses', 'quota_error': 'Quota_Errors', 'api_error': 'API_Errors', 'correction_attempt': 'Correction_Attempts', 'local_repair': 'Local_Repairs'}
    if event in event_map:
        status[event_map[event]] += 1
    status['Total_Elapsed_Sec'] += float(elapsed_sec or 0.0)

def v4_mark_model_cooldown(model, reason='short', seconds=None, until_ts=None):
    if not model:
        return 0.0
    if until_ts is None:
        until_ts = v4_now_ts() + max(0.0, float(seconds if seconds is not None else LLM_MODEL_COOLDOWN_SEC))
    llm_model_cooldown_until[str(model)] = float(until_ts)
    status = v4_model_status(model)
    status['Cooldown_Reason'] = str(reason)
    status['Cooldown_Until_TS'] = float(until_ts)
    return float(until_ts)

def mark_llm_passenger_model_cooldown(model_name, cooldown_sec=None):
    """Track transient request failures without changing the configured model."""
    return v4_mark_model_cooldown(model_name, reason='short', seconds=LLM_MODEL_COOLDOWN_SEC if cooldown_sec is None else cooldown_sec)

def llm_cooldown_seconds_for_exception(exc):
    text = f'{type(exc).__name__}: {exc}'
    if v4_is_daily_quota_error(text):
        return max(0.0, v4_next_beijing_midnight_ts() - v4_now_ts())
    if v4_is_empty_response_error(text):
        return LLM_EMPTY_RESPONSE_COOLDOWN_SEC
    return LLM_MODEL_COOLDOWN_SEC

def v4_available_models(excluded_models=None):
    excluded = {str(model) for model in excluded_models or []}
    return [model for model in LLM_MODEL_POOL if str(model) not in excluded]

def v4_select_model_for_call(excluded_models=None):
    return {'status': 'ready', 'model': 'Qwen/Qwen3.5-27B', 'wait_sec': 0.0, 'reason': 'single_model'}

def v4_extract_json_candidates(text):
    text = str(text or '').strip()
    if not text:
        return []
    text = re.sub('<think>.*?</think>', '', text, flags=re.IGNORECASE | re.DOTALL).strip()
    fenced = re.findall('```(?:json)?\\s*(.*?)\\s*```', text, flags=re.IGNORECASE | re.DOTALL)
    candidates = fenced + [text]
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != '{':
            continue
        try:
            obj, end = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                candidates.append(text[idx:idx + end])
        except _sr.SubmissionStop:
            raise
        except Exception:
            pass
    first, last = (text.find('{'), text.rfind('}'))
    if first >= 0 and last > first:
        candidates.append(text[first:last + 1])
    seen, unique = (set(), [])
    for item in candidates:
        item = str(item).strip()
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique

def v4_load_json_candidate(candidate):
    candidate = str(candidate or '').strip()
    candidate = re.sub(',\\s*([}\\]])', '\\1', candidate)
    try:
        return json.loads(candidate)
    except _sr.SubmissionStop:
        raise
    except Exception:
        pass
    try:
        obj = ast.literal_eval(candidate)
        if isinstance(obj, dict):
            return obj
    except _sr.SubmissionStop:
        raise
    except Exception:
        pass
    raise json.JSONDecodeError('无法从候选文本解析JSON', candidate, 0)

def case_parse_json_response(raw_response):
    """Parse model JSON with support for code fences, surrounding text and trailing commas."""
    errors = []
    for candidate in v4_extract_json_candidates(raw_response):
        try:
            obj = v4_load_json_candidate(candidate)
            if isinstance(obj, dict):
                return obj
        except _sr.SubmissionStop:
            raise
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
    raise json.JSONDecodeError('未找到可解析JSON对象；' + ' | '.join(errors[:3]), str(raw_response or ''), 0)
V4_ACTION_ALIAS = {'continue_metro': 'continue_metro', '继续乘坐地铁': 'continue_metro', '继续地铁': 'continue_metro', '乘地铁': 'continue_metro', '地铁': 'continue_metro', 'continue_original_route': 'continue_metro', 'continue_current_shortest_route': 'continue_metro', 'abandon_trip': 'abandon_trip', '放弃出行': 'abandon_trip', '取消出行': 'abandon_trip', '不出行': 'abandon_trip', '放弃': 'abandon_trip', 'take_shuttle_bus': 'take_shuttle_bus', '乘接驳车': 'take_shuttle_bus', '接驳车': 'take_shuttle_bus', '短驳': 'take_shuttle_bus', '官方短驳': 'take_shuttle_bus', 'shuttle': 'take_shuttle_bus', 'take_other_surface_bus': 'take_other_surface_bus', '地面公交': 'take_other_surface_bus', '常规公交': 'take_other_surface_bus', '其他公交': 'take_other_surface_bus', '公交': 'take_other_surface_bus', 'reroute_to_shortest_time': 'take_other_surface_bus', 'take_taxi': 'take_taxi', '打车': 'take_taxi', '出租车': 'take_taxi', '网约车': 'take_taxi', 'taxi': 'take_taxi', 'take_other_transport': 'take_other_transport', '其他交通方式': 'take_other_transport', '自驾': 'take_other_transport', '私家车': 'take_other_transport', '开车': 'take_other_transport', '骑行': 'take_other_transport', '步行': 'take_other_transport'}

def v4_normalize_action_choice(value, allowed_actions=None):
    allowed = set(allowed_actions or LLM_ALLOWED_ACTIONS)
    raw = str(value or '').strip().strip('"\'`，。；; ')
    raw_lower = raw.lower()
    candidates = [raw, raw_lower]
    repairs = []
    for key, action in V4_ACTION_ALIAS.items():
        key_lower = str(key).lower()
        if raw == key or raw_lower == key_lower or key_lower in raw_lower or (str(key) in raw):
            candidates.append(action)
    for candidate in candidates:
        mapped = V4_ACTION_ALIAS.get(candidate, candidate)
        if mapped in allowed:
            if mapped != raw:
                repairs.append(f'action_choice:{raw}->{mapped}')
            return (mapped, repairs)
    return (raw, repairs)

def v4_payload_aliases(parsed):
    aliases = {'action_choice': ['action_choice', 'action', 'choice', 'decision', '选择', '动作', '出行选择'], 'reason': ['reason', '理由', '原因', 'explanation', 'rationale'], 'risk_perception_level': ['risk_perception_level', 'risk_level', '风险感知', '风险等级'], 'delay_perception_level': ['delay_perception_level', 'delay_level', '延误感知', '延误等级'], 'feeling_score': ['feeling_score', 'feeling', 'score', '感受分', '情绪分', '满意度']}
    lowered = {str(k).lower(): k for k in parsed.keys()}
    out, repairs = ({}, [])
    for target, names in aliases.items():
        for name in names:
            key = name if name in parsed else lowered.get(str(name).lower())
            if key in parsed:
                out[target] = parsed[key]
                if key != target:
                    repairs.append(f'field:{key}->{target}')
                break
    return (out, repairs)

def v4_normalize_payload(parsed, context):
    normalized, repairs = v4_payload_aliases(parsed if isinstance(parsed, dict) else {})
    if 'action_choice' in normalized:
        action, action_repairs = v4_normalize_action_choice(normalized.get('action_choice'), context.get('allowed_actions', []))
        normalized['action_choice'] = action
        repairs.extend(action_repairs)
    if 'risk_perception_level' not in normalized:
        normalized['risk_perception_level'] = 'medium'
        repairs.append('default:risk_perception_level=medium')
    if 'delay_perception_level' not in normalized:
        normalized['delay_perception_level'] = 'medium'
        repairs.append('default:delay_perception_level=medium')
    if 'feeling_score' not in normalized:
        normalized['feeling_score'] = 3
        repairs.append('default:feeling_score=3')
    return (normalized, repairs)

def case_validate_llm_decision(parsed, context):
    """Validate normalized outputs while enforcing action feasibility."""
    if not isinstance(parsed, dict):
        return (False, 'LLM输出不是JSON对象。')
    required = {'action_choice', 'reason', 'risk_perception_level', 'delay_perception_level', 'feeling_score'}
    missing = required - set(parsed)
    if missing:
        return (False, 'LLM JSON缺失字段：' + ','.join(sorted(missing)))
    action = str(parsed.get('action_choice', '')).strip()
    allowed = set(context.get('allowed_actions', []))
    if action not in allowed:
        return (False, 'action_choice不在当前可行动作集合中。')
    if action == 'continue_metro' and (not bool(context.get('metro_available'))):
        return (False, '当前地铁不可达时不能选择continue_metro。')
    if action == 'take_shuttle_bus' and (not bool(context.get('shuttle_available'))):
        return (False, '当前没有可用短驳时不能选择take_shuttle_bus。')
    reason = str(parsed.get('reason', '')).strip()
    if not reason:
        return (False, 'reason为空。')
    if len(reason) > 220:
        return (False, 'reason过长，应控制在220字以内。')
    prohibited_terms = ['action_choice', 'allowed_actions', 'OCEAN', 'Risk_Preference', 'LLM_', 'JSON', '代码', '字段', '后台', '人格分数', '开放性', '尽责性', '外向性', '宜人性', '神经质', '风险偏好', 'continue_metro', 'abandon_trip', 'take_shuttle_bus', 'take_other_surface_bus', 'take_taxi', 'take_other_transport']
    lower_reason = reason.lower()
    for term in prohibited_terms:
        if term.lower() in lower_reason:
            return (False, f'reason出现禁止后台术语：{term}')
    risk_level = str(parsed.get('risk_perception_level', '')).strip()
    delay_level = str(parsed.get('delay_perception_level', '')).strip()
    if risk_level not in LLM_PERCEPTION_LEVELS:
        return (False, 'risk_perception_level不是标准枚举。')
    if delay_level not in LLM_PERCEPTION_LEVELS:
        return (False, 'delay_perception_level不是标准枚举。')
    _, _, feeling_error = normalize_llm_feeling_score(parsed.get('feeling_score'))
    if feeling_error:
        return (False, feeling_error)
    return (True, '')

def v4_transport_feasibility(context):
    surface = context.get('surface', {})
    profile = context.get('profile', {})
    age = int(profile.get('Age', 40) or 40)
    road_km = float(surface.get('Road_Distance_KM', np.nan))
    walking_min = float(surface.get('walking_min', np.nan))
    cycling_min = float(surface.get('cycling_min', np.nan))
    private_car_min = float(surface.get('private_car_min', np.nan))
    hints = []
    if np.isfinite(walking_min):
        if road_km <= 2.5:
            hints.append(f'步行距离较短，约{walking_min:.0f}分钟，可作为现实选项。')
        elif road_km <= 5:
            hints.append(f'步行约{walking_min:.0f}分钟，只适合不赶时间且愿意走路的乘客。')
        else:
            hints.append(f'步行约{walking_min:.0f}分钟，通常负担较大。')
    if np.isfinite(cycling_min):
        if age <= 65 and road_km <= 10:
            hints.append(f'骑行约{cycling_min:.0f}分钟，若能使用非机动车，可以作为替代。')
        elif age <= 65 and road_km <= 18:
            hints.append(f'骑行约{cycling_min:.0f}分钟，距离偏长，只适合体力和时间允许时。')
        else:
            hints.append(f'骑行约{cycling_min:.0f}分钟，对该年龄或距离通常不轻松。')
    if np.isfinite(private_car_min):
        hints.append(f'私家车按道路速度估算约{private_car_min:.0f}分钟；事实卡不假设一定有车，只作为个人交通方式时间参照。')
    other_bus_min = float(surface.get('Other_Surface_Bus_Min', np.nan))
    taxi_min = float(surface.get('Taxi_Min', np.nan))
    if np.isfinite(other_bus_min) and np.isfinite(taxi_min):
        if other_bus_min <= taxi_min * 1.35:
            hints.append('常规地面公交与出租车时间差距不大时，不应默认忽略公交。')
        elif other_bus_min <= 90:
            hints.append('常规地面公交时间可接受但更慢，适合不愿打车或能忍受绕行的乘客。')
        else:
            hints.append('常规地面公交明显较慢，通常只有成本敏感或不赶时间时才会接受。')
    return hints

def v4_order_allowed_actions(context):
    actions = list(context.get('allowed_actions', []))
    material = f'v4|{context.get('passenger_id')}|{context.get('scenario_key')}'
    seed = int(hashlib.sha256(material.encode('utf-8')).hexdigest()[:12], 16)
    rng = random.Random(seed)
    rng.shuffle(actions)
    return actions
V4_BASE_FACT_CARD = case_human_fact_card
V4_BASE_BUILD_CONTEXT = CasePassengerAgent.build_case_context
V4_BASE_CASE_RECORD = CasePassengerAgent.case_record

def case_system_prompt():
    return '你是一名真实的上海地铁乘客，需要在事故处置下选择一种出行方式。事实卡给出的OD、路线、时间、可达性、短驳和可选动作是唯一事实来源；不要编造站点、票价、服务、事故细节或个人条件。年龄、性别、出行目的、OCEAN人格和风险偏好会影响倾向与语气，但它们只是概率性倾向，不能覆盖可达性和安全边界。六类动作都是有效候选：不要默认短驳、出租车或继续地铁更正确；应比较时间、稳定性、换乘负担、目的紧迫性和个人差异。如果当前地铁不可达，绝不能选择 continue_metro，也不能把硬中断描述成可忍受的延误。如果选择 take_other_transport，可以理解为自驾、骑行或步行等个人交通方式；事实卡未声明一定有私家车，只提供时间参照。如果选择 abandon_trip，含义是取消本次去目的地的出行，不是改乘其他方式。action_choice 必须从事实卡 allowed_actions 中选择一个英文代码。reason 只需给出清楚的中文理由，可以不是第一人称，也不要求50字以上；但不能写后台字段、人格分数、动作代码或JSON术语。risk_perception_level 和 delay_perception_level 只能是 none、low、medium、high、critical；feeling_score为1至5整数。只返回一个JSON对象，字段为 action_choice, reason, risk_perception_level, delay_perception_level, feeling_score。'

def v4_case_human_fact_card(context):
    card = V4_BASE_FACT_CARD(context)
    ordered_actions = context.get('allowed_actions_ordered') or context.get('allowed_actions') or []
    card['allowed_actions'] = [{'action_choice': action, '含义': CASE_ACTION_MEANINGS[action]} for action in ordered_actions]
    card['动作选择提示'] = 'allowed_actions中的每个动作都是可考虑选项；请不要因为官方短驳存在就机械选择短驳，也不要因为出租车更快就忽略成本、稳定性和个人差异。常规公交、骑行/步行/私家车等也可在条件合适时选择。'
    card['其他交通方式可行性提示'] = context.get('transport_feasibility', [])
    return card
case_human_fact_card = v4_case_human_fact_card

def v4_build_case_context(self, normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=None, od_groups=None):
    context = V4_BASE_BUILD_CONTEXT(self, normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=operational_proxy, od_groups=od_groups)
    context['transport_feasibility'] = v4_transport_feasibility(context)
    context['allowed_actions_ordered'] = v4_order_allowed_actions(context)
    context['fact_card'] = case_human_fact_card(context)
    self.case_context = context
    return context

def case_llm_prompt(context):
    """Build the Chinese user fact card; behavioral instructions remain in the system prompt."""
    return json.dumps(context['fact_card'], ensure_ascii=False, separators=(',', ':'))

def v4_correction_prompt(context, raw_response, error_message):
    return json.dumps({'任务': '上一条回复无法被代码接受。请只根据事实卡重新输出一个JSON对象。', '错误': str(error_message), '硬约束': {'allowed_actions': context.get('allowed_actions', []), '地铁可达': bool(context.get('metro_available')), '短驳可用': bool(context.get('shuttle_available')), '字段': ['action_choice', 'reason', 'risk_perception_level', 'delay_perception_level', 'feeling_score']}, '上一条回复': str(raw_response or '')[:1000], '事实卡': context.get('fact_card', {})}, ensure_ascii=False, separators=(',', ':'))

def v4_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, parsed, valid, error_message, prompt_tokens, completion_tokens, attempt_elapsed, total_elapsed, attempt_type, repairs=None, quota_stop=False):
    repairs = repairs or []
    llm_call_log.append({'Passenger_ID': context['passenger_id'], 'Scenario': context['scenario_key'], 'Prompt_Fact_Card': json.dumps(context['fact_card'], ensure_ascii=False), 'Raw_Response': raw, 'Parsed_Action': parsed.get('action_choice', '') if isinstance(parsed, dict) else '', 'Valid': bool(valid), 'Fallback_Used': not bool(valid), 'Error_Message': str(error_message or ''), 'Failure_Category': v4_error_category(error_message), 'Model': model, 'Attempted_Models': ' | '.join(attempted_models), 'Attempt_Count': len(attempted_models), 'Attempt_Type': attempt_type, 'Model_Fallback_Used': False, 'Prompt_Tokens': int(prompt_tokens or 0), 'Completion_Tokens': int(completion_tokens or 0), 'Repair_Applied': bool(repairs), 'Repair_Details': ' | '.join(map(str, repairs)), 'Cooldown_Reason': v4_model_status(model).get('Cooldown_Reason', ''), 'Next_Available_BJT': v4_format_bjt(v4_model_status(model).get('Cooldown_Until_TS', 0.0)), 'Quota_Stop': bool(quota_stop), 'Attempt_Elapsed_Sec': round(float(attempt_elapsed or 0.0), 3), 'Total_Elapsed_Sec': round(float(total_elapsed or 0.0), 3)})

def v4_try_one_llm_call(system_prompt, user_prompt, context, model, attempted_models, llm_call_log, attempt_type='primary'):
    raw = ''
    prompt_tokens = completion_tokens = 0
    start = time.time()
    v4_update_model_status(model, 'attempt')
    if attempt_type == 'correction':
        v4_update_model_status(model, 'correction_attempt')
    try:
        raw, prompt_tokens, completion_tokens = call_llm_passenger_json(system_prompt, user_prompt, model, LLM_TEMPERATURE, LLM_TIMEOUT_SEC)
        parsed0 = case_parse_json_response(raw)
        parsed, repairs = v4_normalize_payload(parsed0, context)
        if repairs:
            v4_update_model_status(model, 'local_repair')
        valid, error_message = case_validate_llm_decision(parsed, context)
        elapsed = time.time() - start
        v4_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, parsed, valid, error_message, prompt_tokens, completion_tokens, elapsed, 0.0, attempt_type, repairs=repairs)
        v4_update_model_status(model, 'valid' if valid else 'validation_failure', elapsed)
        return {'ok': True, 'valid': valid, 'parsed': parsed, 'raw': raw, 'error': error_message, 'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'elapsed': elapsed, 'repairs': repairs}
    except _sr.SubmissionStop:
        raise
    except Exception as exc:
        elapsed = time.time() - start
        error_message = f'{type(exc).__name__}: {exc}'
        category = v4_error_category(error_message)
        if category == 'daily_quota':
            v4_mark_model_cooldown(model, reason='daily_quota', until_ts=v4_next_beijing_midnight_ts())
            v4_update_model_status(model, 'quota_error', elapsed)
        elif category == 'empty_content':
            v4_mark_model_cooldown(model, reason='empty_response', seconds=LLM_EMPTY_RESPONSE_COOLDOWN_SEC)
            v4_update_model_status(model, 'empty_response', elapsed)
        elif category == 'json_parse':
            v4_update_model_status(model, 'parse_failure', elapsed)
        else:
            v4_mark_model_cooldown(model, reason='api_error', seconds=LLM_MODEL_COOLDOWN_SEC)
            v4_update_model_status(model, 'api_error', elapsed)
        v4_log_llm_attempt(llm_call_log, context, model, attempted_models, raw, {}, False, error_message, prompt_tokens, completion_tokens, elapsed, 0.0, attempt_type, repairs=[], quota_stop=category == 'daily_quota')
        return {'ok': False, 'valid': False, 'parsed': {}, 'raw': raw, 'error': error_message, 'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'elapsed': elapsed, 'repairs': []}

def case_call_llm(context, llm_call_log):
    return _sr.case_call(globals(), context, llm_call_log)

def v4_purpose_urgency(purpose):
    text = str(purpose or '')
    if any((key in text for key in ['通勤', '上学', '商务', '工作', '就医', '照护'])):
        return 1.0
    if '回家' in text:
        return 0.45
    if any((key in text for key in ['休闲', '旅游'])):
        return 0.15
    return 0.35

def v4_action_time_min(context, action):
    surface = context.get('surface', {})
    if action == 'continue_metro':
        value = context.get('metro_current_min')
    elif action == 'take_shuttle_bus':
        value = (context.get('shuttle') or {}).get('Generalized_Min', np.nan)
    elif action == 'take_other_surface_bus':
        value = surface.get('Other_Surface_Bus_Min', np.nan)
    elif action == 'take_taxi':
        value = surface.get('Taxi_Min', np.nan)
    elif action == 'take_other_transport':
        candidates = [surface.get('walking_min', np.nan), surface.get('cycling_min', np.nan), surface.get('private_car_min', np.nan)]
        finite = [float(v) for v in candidates if np.isfinite(float(v))]
        value = min(finite) if finite else np.nan
    else:
        value = np.nan
    try:
        value = float(value)
        return value if np.isfinite(value) else np.nan
    except _sr.SubmissionStop:
        raise
    except Exception:
        return np.nan

def v4_utility_fallback_choice(context):
    allowed = list(context.get('allowed_actions', []))
    profile = context.get('profile', {})
    surface = context.get('surface', {})
    urgency = v4_purpose_urgency(profile.get('Trip_Purpose', ''))
    O = int(profile.get('OCEAN_O', 3))
    C = int(profile.get('OCEAN_C', 3))
    A = int(profile.get('OCEAN_A', 3))
    N = int(profile.get('OCEAN_N', 3))
    R = int(profile.get('Risk_Preference', 3))
    road_km = float(surface.get('Road_Distance_KM', np.nan))
    proxy = context.get('operational_proxy') or {}
    proxy_score = int(proxy.get('score', 0) or 0)
    material = f'fallback|{context.get('passenger_id')}|{context.get('scenario_key')}|{context.get('origin')}|{context.get('destination')}'
    rng = random.Random(int(hashlib.sha256(material.encode('utf-8')).hexdigest()[:12], 16))
    utilities = {}
    finite_times = [v4_action_time_min(context, action) for action in allowed if action != 'abandon_trip']
    finite_times = [value for value in finite_times if np.isfinite(value)]
    median_time = float(np.median(finite_times)) if finite_times else 60.0
    for action in allowed:
        if action == 'abandon_trip':
            worst_time = max(finite_times) if finite_times else 120.0
            utilities[action] = -1.0 + (1.0 - urgency) * 1.3 + max(0, worst_time - 90) / 60.0 + (N - 3) * 0.18 - (C - 3) * 0.18
        else:
            t = v4_action_time_min(context, action)
            utilities[action] = -(t / max(20.0, median_time) if np.isfinite(t) else 3.0)
        if action == 'continue_metro':
            utilities[action] += 0.45 + (R - 3) * 0.08 - proxy_score * 0.18
        elif action == 'take_shuttle_bus':
            utilities[action] += 0.25 + (A - 3) * 0.16 + (O - 3) * 0.1 - (N - 3) * 0.05
        elif action == 'take_other_surface_bus':
            bus_time = v4_action_time_min(context, action)
            utilities[action] += 0.1 + (1.0 - urgency) * 0.25 - max(0, (bus_time or 0) - 100) / 120.0
            if np.isfinite(bus_time) and bus_time <= 60:
                utilities[action] += 0.35
            elif np.isfinite(bus_time) and bus_time <= 90:
                utilities[action] += 0.15
        elif action == 'take_taxi':
            utilities[action] += urgency * 0.55 + (N - 3) * 0.15 - max(0, float(surface.get('Taxi_Min', 999)) - 90) / 100.0
        elif action == 'take_other_transport':
            utilities[action] += (O - 3) * 0.16 + (R - 3) * 0.12
            if np.isfinite(road_km) and road_km <= 10:
                utilities[action] += 0.45
            elif np.isfinite(road_km) and road_km <= 25:
                utilities[action] += 0.15
            private_car_time = float(surface.get('private_car_min', np.nan))
            taxi_time = float(surface.get('Taxi_Min', np.nan))
            cycling_time = float(surface.get('cycling_min', np.nan))
            if np.isfinite(private_car_time) and np.isfinite(taxi_time) and (private_car_time <= taxi_time + 5):
                utilities[action] += 0.35
            if np.isfinite(cycling_time) and cycling_time <= 60:
                utilities[action] += 0.2
            if int(profile.get('Age', 40)) > 65 and np.isfinite(road_km) and (road_km > 8):
                utilities[action] -= 0.35
        utilities[action] += rng.uniform(-0.22, 0.22)
    choice = max(utilities, key=utilities.get)
    return (choice, 'v4_utility_fallback:' + json.dumps({k: round(float(v), 3) for k, v in utilities.items()}, ensure_ascii=False))

def v4_technical_fallback(self, scenario_system, allowed_actions):
    """Construct a utility-based response."""
    return v4_utility_fallback_choice(self.case_context)
CasePassengerAgent.technical_fallback = v4_technical_fallback

def v4_decide_case(self, normal_system, scenario_system, scenario, at_min, affected_corridor, use_live_llm, llm_call_log, operational_proxy=None, od_groups=None):
    context = self.build_case_context(normal_system, scenario_system, scenario, at_min, affected_corridor, operational_proxy=operational_proxy, od_groups=od_groups)
    self.llm_selected = True
    self.decision_mode = 'llm'
    self.rule_action_raw = ''
    self.rule_action = ''
    if use_live_llm:
        outcome = case_call_llm(context, llm_call_log)
    else:
        outcome = {'valid': False, 'parsed': {}, 'raw': '', 'error': 'smoke_test_no_live_llm', 'model': '', 'attempted_models': [], 'attempt_count': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'repair_applied': False, 'repair_details': '', 'failure_category': 'smoke_test', 'total_elapsed_sec': 0.0, 'quota_stop': False}
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

def v4_case_record(self):
    record = V4_BASE_CASE_RECORD(self)
    record.update({'LLM_Repair_Applied': bool(getattr(self, 'llm_repair_applied', False)), 'LLM_Repair_Details': str(getattr(self, 'llm_repair_details', '')), 'LLM_Failure_Category': str(getattr(self, 'llm_failure_category', '')), 'LLM_Total_Elapsed_Sec': round(float(getattr(self, 'llm_total_elapsed_sec', 0.0) or 0.0), 3), 'LLM_Quota_Stop': bool(getattr(self, 'llm_quota_stop', False))})
    return record
CasePassengerAgent.build_case_context = v4_build_case_context
CasePassengerAgent.decide_case = v4_decide_case
CasePassengerAgent.case_record = v4_case_record

def v4_llm_model_status_df():
    rows = []
    for model in LLM_MODEL_POOL:
        status = dict(v4_model_status(model))
        status['Cooldown_Until_BJT'] = v4_format_bjt(status.get('Cooldown_Until_TS', 0.0))
        rows.append(status)
    return pd.DataFrame(rows)

def v4_llm_error_summary_df(llm_log_df):
    if llm_log_df is None or llm_log_df.empty:
        return pd.DataFrame(columns=['Scenario', 'Failure_Category', 'Model', 'Rows', 'Valid_N', 'Quota_Stop_N', 'Repair_Applied_N'])
    frame = llm_log_df.copy()
    for col in ['Failure_Category', 'Model', 'Scenario']:
        if col not in frame:
            frame[col] = ''
    if 'Quota_Stop' not in frame:
        frame['Quota_Stop'] = False
    if 'Repair_Applied' not in frame:
        frame['Repair_Applied'] = False
    grouped = frame.groupby(['Scenario', 'Failure_Category', 'Model'], dropna=False)
    return grouped.agg(Rows=('Passenger_ID', 'size'), Valid_N=('Valid', lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())), Quota_Stop_N=('Quota_Stop', lambda s: int(pd.Series(s).fillna(False).astype(bool).sum())), Repair_Applied_N=('Repair_Applied', lambda s: int(pd.Series(s).fillna(False).astype(bool).sum()))).reset_index().sort_values(['Scenario', 'Rows'], ascending=[True, False])

def v4_write_partial_excel(path, records, logs, cohort_df, run_id, quota_stop_message=''):
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        pd.DataFrame(records).to_excel(writer, sheet_name='Passenger_Decisions_Partial', index=False)
        log_df = pd.DataFrame(logs)
        log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        v4_llm_error_summary_df(log_df).to_excel(writer, sheet_name='LLM_Error_Summary', index=False)
        v4_llm_model_status_df().to_excel(writer, sheet_name='LLM_Model_Status', index=False)
        cohort_df.to_excel(writer, sheet_name='Cohort', index=False)
        pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Completed_Decisions': len(records), 'Quota_Stop_Message': quota_stop_message, 'Saved_At_BJT': v4_beijing_now().strftime('%Y-%m-%d %H:%M:%S BJT')}]).to_excel(writer, sheet_name='Checkpoint_Status', index=False)

def v4_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_df, output_dir=CASE_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'Line11_Incident_LLM_TrainSimulation_v4_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx'
    zero_attempt_fallback = int(((passenger_df.get('LLM_Attempt_Count', pd.Series(dtype=float)).fillna(0).astype(float) == 0) & (passenger_df.get('Decision_Source', pd.Series(dtype=str)) == 'Rule_Fallback')).sum()) if not passenger_df.empty else 0
    run_summary = pd.DataFrame([{'Run_ID': run_id, 'Case_Version': CASE_VERSION, 'Cohort_N': len(cohort_df), 'Affected_N': int(cohort_df['Affected_Corridor'].sum()), 'LLM_Valid_Rate': float(passenger_df['LLM_Valid'].mean()) if not passenger_df.empty else np.nan, 'LLM_Fallback_N': int(passenger_df['LLM_Fallback_Used'].sum()) if not passenger_df.empty else 0, 'LLM_Fallback_Rate': float(passenger_df['LLM_Fallback_Used'].mean()) if not passenger_df.empty else np.nan, 'Zero_Attempt_Fallback_N': zero_attempt_fallback, 'Daily_Quota_Stop': False, 'Train_Log_Step_Sec': V3_LOG_STEP_SEC, 'GIF_Frame_Sec': V3_GIF_FRAME_SEC, 'GIF_Path': str(gif_path or '')}])
    gif_manifest = pd.DataFrame([{'GIF_Path': str(gif_path or ''), 'Frame_Interval_Sec': V3_GIF_FRAME_SEC, 'Start': case_hhmm(V3_SIM_START_MIN), 'End': case_hhmm(V3_SIM_END_MIN), 'Scope': '全网列车，11号线工况高亮'}])
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Decision_Share_Summary', index=False)
        passenger_df.to_excel(writer, sheet_name='Passenger_Decisions', index=False)
        llm_log_df.to_excel(writer, sheet_name='LLM_Call_Log', index=False)
        v4_llm_error_summary_df(llm_log_df).to_excel(writer, sheet_name='LLM_Error_Summary', index=False)
        v4_llm_model_status_df().to_excel(writer, sheet_name='LLM_Model_Status', index=False)
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

def case_plot_efficiency_v4(efficiency_df, output_dir=CASE_OUTPUT_DIR):
    if efficiency_df is None or efficiency_df.empty:
        return None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / 'Network_Efficiency_Curve_v4.png'
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    fig, ax = plt.subplots(figsize=(12, 4.8), dpi=180)
    times = pd.to_datetime(efficiency_df['Time'], format='%H:%M')
    ax.step(times, efficiency_df['Relative_Network_Efficiency'], where='post', color='#b71c1c', linewidth=2.0)
    for t in ['08:31', '09:17', '11:19', '20:00', '22:50']:
        x = pd.to_datetime(t, format='%H:%M')
        ax.axvline(x, color='gray', linestyle='--', linewidth=0.8)
        ax.text(x, 1.001, t, rotation=90, va='top', ha='right', fontsize=8)
    ax.set_title('上海地铁11号线侵线施工事故相对时间网络效率')
    ax.set_xlabel('时间')
    ax.set_ylabel('相对时间网络效率 E_incident(t) / E_normal(t)')
    ax.set_ylim(max(0.94, float(efficiency_df['Relative_Network_Efficiency'].min()) - 0.01), 1.002)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path

def run_case_study_v4(use_live_llm=True, compute_efficiency=True, generate_gif=False, resume=False, run_label=None):
    _sr.require_run()
    case_require_inputs()
    cohort_df = sample_case_cohort()
    base_run_id = case_run_id(cohort_df)
    run_id = base_run_id if resume else f'{base_run_id}_{run_label or _dt.now().strftime('%Y%m%d_%H%M%S')}'
    checkpoint_paths = case_checkpoint_paths(run_id)
    resumed_records, resumed_logs = case_load_resume(checkpoint_paths['jsonl']) if resume else ({}, [])
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
                    v4_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id)
                    print(f'v4 checkpoint: {len(all_records)}/{CASE_SAMPLE_SIZE * 3}', flush=True)
    except V4DailyQuotaExhausted as exc:
        v4_write_partial_excel(checkpoint_paths['excel'], all_records, llm_call_log, cohort_df, run_id, quota_stop_message=str(exc))
        raise RuntimeError(f'v4已保存checkpoint并停止：{exc}') from exc
    passenger_df = pd.DataFrame(all_records).sort_values(['Scenario', 'PID']).reset_index(drop=True)
    if len(passenger_df) != CASE_SAMPLE_SIZE * 3:
        raise AssertionError('乘客决策记录数量应为500×3；如果因额度停止，请次日北京时间0点后用resume=True继续。')
    summary_df = case_summary_table(passenger_df)
    llm_log_df = pd.DataFrame(llm_call_log)
    shuttle_df = pd.DataFrame(shuttle_rows)
    efficiency_df = case_network_efficiency_curve() if compute_efficiency else pd.DataFrame()
    curve_path = case_plot_efficiency_v4(efficiency_df) if compute_efficiency else None
    excel_path = v4_export_workbook(summary_df, passenger_df, llm_log_df, shuttle_df, efficiency_df, cohort_df, run_id, train_outputs, gif_path, proxy_rows)
    return {'cohort': cohort_df, 'passenger_decisions': passenger_df, 'decision_share_summary': summary_df, 'llm_call_log': llm_log_df, 'train_outputs': train_outputs, 'operational_proxy': pd.DataFrame(proxy_rows), 'network_efficiency': efficiency_df, 'excel_path': excel_path, 'curve_path': curve_path, 'gif_path': gif_path, 'run_id': run_id, 'checkpoint_paths': checkpoint_paths, 'llm_model_status': v4_llm_model_status_df()}
