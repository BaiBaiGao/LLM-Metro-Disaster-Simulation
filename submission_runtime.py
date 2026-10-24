"""Model requests, run directories and checkpoints."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
MODEL = 'Qwen/Qwen3.5-27B'
TEMPERATURE = 0.7
VERSION = 'metro_agents_20261024'
PACKAGE = Path(__file__).resolve().parent
ACTIVE = False
CURRENT_RUN = None
NETWORK_REQUESTS = 0

class SubmissionStop(RuntimeError):
    """Stop the current simulation."""

class QuotaExhausted(SubmissionStop):
    pass

from release_inputs import local_root, static_flow_frames, static_flow_source, load_notice_rows, validate_inputs

def project_root():
    return local_root()


def output_root(scenario):
    configured = os.environ.get('METRO_OUTPUT_ROOT')
    if not configured:
        return PACKAGE / 'outputs_not_configured' / scenario
    result = Path(configured).expanduser().resolve()
    if result.drive.lower() == 'c:':
        raise ValueError('METRO_OUTPUT_ROOT must be outside the system drive.')
    return result / VERSION / scenario

def require_run():
    if not ACTIVE:
        raise SubmissionStop('Execution is disabled. Use run_submission(enable_run=True) explicitly.')

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

def notebook_code_hash(path):
    """Hash notebook code cells."""
    notebook = json.loads(Path(path).read_text(encoding='utf-8'))
    return canonical_hash([''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code'])

def is_quota_error(status, message):
    text = str(message).lower()
    return any((term in text for term in ('quota', 'insufficient', 'credit', 'balance', 'daily limit', 'daily_limit', '额度', '配额', '余额', '欠费', '次数已用完', 'tokens exhausted'))) or status == 402

def chat(system_prompt, user_prompt, model=MODEL, temperature=TEMPERATURE, timeout=180, transport=None):
    """Send a chat request through the configured transport."""
    global NETWORK_REQUESTS
    if model != MODEL or float(temperature) != TEMPERATURE:
        raise SubmissionStop('Model and temperature must match the single-model configuration.')
    payload = {'model': MODEL, 'temperature': TEMPERATURE, 'messages': [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]}
    if transport is None:
        require_run()
        credential = os.environ.get('MODELSCOPE_API_KEY', '').strip()
        if not credential:
            raise SubmissionStop('MODELSCOPE_API_KEY is not set.')
        import requests
        NETWORK_REQUESTS += 1
        response = requests.post('https://api-inference.modelscope.cn/v1/chat/completions', headers={'Authorization': 'Bearer ' + credential, 'Content-Type': 'application/json'}, json=payload, timeout=timeout)
    else:
        response = transport(payload)
    status = int(getattr(response, 'status_code', 200))
    try:
        data = response.json() if hasattr(response, 'json') else response
    except Exception:
        raise RuntimeError('The inference service returned a non-JSON response.') from None
    message = data.get('error', data) if isinstance(data, dict) else 'Invalid response'
    if is_quota_error(status, message) and (status >= 400 or (isinstance(data, dict) and 'error' in data)):
        raise QuotaExhausted('The selected model allowance is exhausted; progress is preserved.')
    if status >= 400 or not isinstance(data, dict) or 'error' in data:
        raise RuntimeError(f'Inference request failed (HTTP {status}); no alternative model was selected.')
    choices = data.get('choices') or []
    content = (choices[0].get('message') or {}).get('content', '') if choices else ''
    if not str(content).strip():
        raise RuntimeError('The selected model returned empty content.')
    usage = data.get('usage') or {}
    meta = {'model': MODEL, 'http_status': status}
    return (str(content), int(usage.get('prompt_tokens') or 0), int(usage.get('completion_tokens') or 0), meta)

def case_call(ns, context, logs):
    """Reuse the scenario's prompt, normalization, and validity/feasibility checks."""
    require_run()
    attempts = int(ns.get('SUBMISSION_MAX_RESPONSE_ATTEMPTS', 10))
    attempted, started = ([], time.time())
    total_prompt_tokens = total_completion_tokens = 0
    prompt = ns['case_llm_prompt'](context)
    for index in range(attempts):
        attempted.append(MODEL)
        raw, p_tokens, c_tokens, parsed, repairs = ('', 0, 0, {}, [])
        try:
            raw, p_tokens, c_tokens, _ = chat(ns['case_system_prompt'](), prompt)
            total_prompt_tokens += p_tokens
            total_completion_tokens += c_tokens
            parsed = ns['case_parse_json_response'](raw)
            parsed, repairs = ns['v4_normalize_payload'](parsed, context)
            valid, error, warnings = ns['v5_validate_llm_decision'](parsed, context)
        except SubmissionStop:
            logs.append({'Model': MODEL, 'Valid': False, 'Quota_Stop': True, 'Scenario': context.get('scenario_key', context.get('scenario', '')), 'Passenger_ID': context.get('passenger_id', context.get('pid', '')), 'Error_Message': 'Execution stopped; no substitute response was generated.'})
            raise
        except Exception as exc:
            valid, error, warnings = (False, type(exc).__name__, [])
        logs.append({'Model': MODEL, 'Valid': bool(valid), 'Raw_Response': raw, 'Parsed_Action': parsed.get('action_choice', ''), 'Error_Message': str(error), 'Attempt_Count': index + 1, 'Prompt_Tokens': p_tokens, 'Completion_Tokens': c_tokens, 'Model_Fallback_Used': False, 'Scenario': context.get('scenario_key', context.get('scenario', '')), 'Passenger_ID': context.get('passenger_id', context.get('pid', context.get('PID', ''))), 'Prompt_Fact_Card': json.dumps(context.get('fact_card', {}), ensure_ascii=False), 'Repair_Applied': bool(repairs), 'Reason_Warnings': str(warnings), 'Failure_Category': '' if valid else 'invalid_response', 'Fallback_Used': False, 'Quota_Stop': False, 'Passenger_Model_Exhausted': False})
        if valid:
            return {'valid': True, 'parsed': parsed, 'raw': raw, 'error': '', 'model': MODEL, 'attempted_models': attempted, 'attempt_count': index + 1, 'prompt_tokens': total_prompt_tokens, 'completion_tokens': total_completion_tokens, 'repair_applied': bool(repairs), 'repair_details': str(repairs), 'failure_category': '', 'total_elapsed_sec': time.time() - started, 'quota_stop': False, 'reason_warnings': str(warnings), 'stop_policy': 'single_model', 'passenger_model_exhausted': False}
        prompt = ns['v4_correction_prompt'](context, raw, error)
    raise SubmissionStop('The selected model did not produce a valid response within the retry limit.')

def file_fingerprint(ns):
    paths = {}
    root = project_root()
    for name in ns.get('INPUT_AUDIT_FILES', []):
        candidate = root / name
        if candidate.is_file():
            paths[name] = sha256(candidate)
    for key in ['CASE_SCHEDULE_PATH', 'V6_REFERENCE_COHORT_PATH', 'BEBINCA_GROUND_SEGMENT_PATH']:
        path = ns.get(key)
        if path and Path(path).is_file():
            paths[key] = sha256(path)
    for path in [PACKAGE / 'data/public/historical_station_weights.csv', root / 'official_notices.json']:
        if path.is_file():
            paths[path.name] = sha256(path)
    return paths

def configuration(ns, scenario):
    conditions = []
    for item in ns.get('CASE_SCENARIOS', []):
        conditions.append({key: getattr(item, key) for key in ('key', 'start_min', 'end_min', 'line_state', 'north_service', 'shuttle_active', 'decision_time_bjt') if hasattr(item, key)})
    controls = {key: ns[key] for key in ('BASE_SEED', 'CASE_SEED', 'PASSENGER_SAMPLE_SIZE', 'PASSENGER_SAMPLE_MODE', 'LLM_MAX_PASSENGER_CALLS', 'CASE_SAMPLE_SIZE', 'CASE_AFFECTED_COUNT', 'DISTURBANCE_EDGES', 'TARGET_AFFECTED_RATIO', 'TARGET_UNAFFECTED_CONTROL_RATIO', 'TARGET_UNREACHABLE_RATIO', 'TARGET_REROUTE_RATIO', 'LLM_OD_GROUP_SELECTION_WEIGHTS', 'START_TIME_STR', 'SIM_DURATION') if key in ns}
    code = {str(p.relative_to(PACKAGE)): sha256(p) for p in sorted(PACKAGE.glob('*.py'))}
    code.update({str(p.relative_to(PACKAGE)): sha256(p) for p in sorted((PACKAGE / 'modules').glob('*.py'))})
    code.update({p.name: notebook_code_hash(p) for p in sorted(PACKAGE.glob('*.ipynb'))})
    configuration_prefixes = ('LLM_', 'CASE_', 'BEBINCA_', 'DISTURBANCE_', 'SIM_', 'TRAIN_', 'TRACK_', 'DEFAULT_', 'WARM_', 'PASSENGER_', 'TARGET_', 'OD_', 'MAX_OD', 'BASE_SEED', 'START_', 'DWELL_', 'TERMINAL_', 'SUBMISSION_MAX_RESPONSE_ATTEMPTS')
    controls_hash = canonical_hash({k: v for k, v in ns.items() if k.isupper() and k.startswith(configuration_prefixes) and isinstance(v, (str, int, float, bool, list, dict, tuple)) and (not re.search('KEY|TOKEN|SECRET|PASSWORD|OUTPUT|CHECKPOINT|PATH|ROOT|DIR', k))})
    return {'version': VERSION, 'scenario': scenario, 'model': MODEL, 'temperature': TEMPERATURE, 'conditions': conditions, 'controls': controls, 'all_controls_hash': controls_hash, 'input_sha256': file_fingerprint(ns), 'code_sha256': code}

def check_manifest(existing, expected):
    if existing.get('configuration_hash') != canonical_hash(expected):
        raise SubmissionStop('Resume rejected: model, timings, inputs, or code differ from the saved run.')

def prepare_run(ns, scenario, resume_run=None):
    if not os.environ.get('METRO_OUTPUT_ROOT'):
        raise SubmissionStop('Set METRO_OUTPUT_ROOT to the project output directory before running.')
    if not os.environ.get('MODELSCOPE_API_KEY', '').strip():
        raise SubmissionStop('Set MODELSCOPE_API_KEY before running.')
    validate_inputs(scenario)
    if Path(ns.get('SOURCE_DIR', project_root())).resolve() != project_root():
        raise SubmissionStop('Input root changed after loading. Restart the kernel and reload the scenario.')
    if scenario == 'C':
        supplied = sorted(load_notice_rows('metro') + load_notice_rows('city'), key=lambda row: row['Publish_Time_BJT'])
        if ns.get('BEBINCA_OFFICIAL_NOTICE_TIMELINE') != supplied:
            raise SubmissionStop('Notice inputs changed after loading. Restart the kernel and reload the scenario / 通知输入已变化，请重启内核并重新加载场景。')
    config = configuration(ns, scenario)
    root = output_root(scenario)
    if resume_run:
        run_dir = Path(resume_run).resolve()
        if root.resolve() not in run_dir.parents:
            raise SubmissionStop('Resume directory must belong to this scenario and code version.')
        manifest = json.loads((run_dir / 'run_manifest.json').read_text(encoding='utf-8'))
        check_manifest(manifest, config)
    else:
        suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        run_dir = root / suffix
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = {'configuration': config, 'configuration_hash': canonical_hash(config), 'status': 'prepared', 'created_utc': suffix}
        (run_dir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    for key in ['TARGET_OUTPUT_DIR', 'OUTPUT_DIR', 'CASE_OUTPUT_DIR']:
        ns[key] = run_dir
    ns['SUBMISSION_OUTPUT_DIR'] = run_dir
    ns['CASE_CHECKPOINT_DIR'] = run_dir / 'checkpoints'
    ns['CASE_CHECKPOINT_DIR'].mkdir(exist_ok=True)
    return (run_dir, manifest)

def validate_checkpoint(path, expected_model=MODEL, conditions=None):
    """Check checkpoint model, conditions and record format."""
    path = Path(path)
    if not path.exists():
        return
    scenarios = {s.key: s for s in conditions or []}
    seen = set()
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        payload = json.loads(line)
        record = payload['record']
        if record.get('LLM_Model') != expected_model or record.get('LLM_Valid') is not True:
            raise SubmissionStop(f'Checkpoint record {number} is not a valid single-model response.')
        identity = (record.get('Scenario'), record.get('PID'))
        if identity in seen:
            raise SubmissionStop('Duplicate passenger/scenario record in checkpoint.')
        seen.add(identity)
        if scenarios:
            scenario = scenarios.get(record.get('Scenario'))
            if scenario is None:
                raise SubmissionStop('Unknown scenario in checkpoint.')
            expected = f'{int(scenario.start_min) % 1440 // 60:02}:{int(scenario.start_min) % 60:02}'
            if record.get('Scenario_Time') != expected:
                raise SubmissionStop('Checkpoint decision time differs from the configured snapshot.')
            if hasattr(scenario, 'decision_time_bjt') and record.get('Decision_Time_BJT') != scenario.decision_time_bjt:
                raise SubmissionStop('Checkpoint decision date/time differs from the configured snapshot.')

def run(ns, scenario, *, enable_run=False, resume_run=None, **kwargs):
    """Run the selected scenario and save its output manifest."""
    global ACTIVE, CURRENT_RUN
    if not enable_run:
        raise SubmissionStop('No simulation was started. Pass enable_run=True when ready.')
    if ACTIVE:
        raise SubmissionStop('A run is already active in this kernel.')
    run_dir, manifest = prepare_run(ns, scenario, resume_run)
    CURRENT_RUN, ACTIVE = (run_dir, True)
    try:
        if scenario == 'A':
            if resume_run:
                raise SubmissionStop("Scenario A's original runner has no resume reader; use its saved progress as an audit and start a fresh run.")
            result = ns['main']()
        else:
            entry = ns['run_case_study_v6'] if scenario == 'B' else ns['run_case_study_bebinca']
            kwargs.update({'use_live_llm': True, 'resume': bool(resume_run), 'quota_probe': False})
            if scenario == 'B':
                kwargs.setdefault('generate_gif', False)
            result = entry(**kwargs)
        manifest['status'] = 'completed'
        manifest['completed_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['outputs'] = {k: str(Path(v).relative_to(run_dir)) for k, v in result.items() if k.endswith('_path') and isinstance(v, (str, Path)) and Path(v).is_relative_to(run_dir)}
        return result
    except BaseException as exc:
        manifest['status'] = 'stopped'
        manifest['stop_type'] = type(exc).__name__
        raise
    finally:
        ACTIVE = False
        (run_dir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

def disabled_probe(*args, **kwargs):
    raise SubmissionStop('Quota probes are disabled; no API request was made.')
