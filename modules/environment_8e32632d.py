import gc
import hashlib
import json
import math
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
import networkx as nx
import numpy as np
import pandas as pd
EXPERIMENT_VERSION = 'v0.0.12'
OUTPUT_VERSION = EXPERIMENT_VERSION
BASE_SEED = 20260526
SIM_DURATION = 30
START_TIME_STR = '09:50'
PASSENGER_SAMPLE_SIZE = 1000
PASSENGER_SAMPLE_MODE = 'disturbance_focused'
TARGET_AFFECTED_RATIO = 0.7
TARGET_UNAFFECTED_CONTROL_RATIO = 0.3
TARGET_UNREACHABLE_RATIO = 0.1
TARGET_REROUTE_RATIO = 0.3
OD_DELAY_THRESHOLD_MIN = 1.0
MAX_OD_RESAMPLE_ATTEMPTS = 20000
PASSENGER_DECISION_MODE = 'paired_compare'
LLM_PASSENGER_RATIO = 1.0
LLM_MAX_PASSENGER_CALLS = 500
LLM_MODEL = 'Qwen/Qwen3.5-27B'
LLM_BACKUP_MODELS = []
LLM_MODEL_POOL = ['Qwen/Qwen3.5-27B']
LLM_MAX_MODEL_RETRIES = 10
LLM_MODEL_COOLDOWN_SEC = 5
LLM_RATE_LIMIT_COOLDOWN_SEC = 1800
LLM_EMPTY_RESPONSE_COOLDOWN_SEC = 60
LLM_VALIDATION_FAILURE_COOLDOWN_SEC = 3
LLM_SELECTION_MODE = 'od_group_stratified'
LLM_OD_GROUP_SELECTION_WEIGHTS = {'affected_reroute_available': 0.45, 'affected_reachable_delay': 0.35, 'affected_unreachable': 0.1, 'unaffected_control': 0.1}
LLM_OD_GROUP_SELECTION_PRIORITY = ['affected_reroute_available', 'affected_reachable_delay', 'affected_unreachable', 'unaffected_control']
LLM_TEMPERATURE = 0.7
LLM_TIMEOUT_SEC = 180
LLM_RANDOM_SEED = 20260601
LLM_BASE_URL = 'https://api-inference.modelscope.cn/v1/'
LLM_API_KEY = os.environ.get('MODELSCOPE_API_KEY', '')
LLM_ALLOWED_ACTIONS = ['continue_original_route', 'continue_current_shortest_route', 'reroute_to_shortest_time', 'abandon_trip']
LLM_PERCEPTION_LEVELS = ['none', 'low', 'medium', 'high', 'critical']
LLM_PERCEPTION_LEVEL_CODE = {level: idx for idx, level in enumerate(LLM_PERCEPTION_LEVELS)}
LLM_CALL_LOG_COLUMNS = ['Passenger_ID', 'Prompt_Context', 'Raw_Response', 'Parsed_Action', 'Valid', 'Fallback_Used', 'Error_Message', 'Model', 'Attempted_Models', 'Attempt_Count', 'Model_Fallback_Used', 'Prompt_Tokens', 'Completion_Tokens']
LLM_SKIP_MODELS_IN_COOLDOWN = True
CHECKPOINT_ENABLED = True
CHECKPOINT_SAVE_JSONL = True
CHECKPOINT_EXCEL_ENABLED = True
CHECKPOINT_EXCEL_EVERY_PASSENGERS = 25
PROGRESS_PRINT_EVERY_PASSENGERS = 5
SIM_STEP_SEC = 10
TRAIN_LOG_STEP_SEC = 10
TRAIN_SPEED_KMH = 45.0
TRACK_DETOUR_FACTOR = 1.15
MIN_SEGMENT_RUNTIME_SEC = 60
DWELL_SEC = 30
TERMINAL_DWELL_SEC = 120
WARM_START_LOOKBACK_MIN = 90
GIF_FRAME_STEP_SEC = 30
DEFAULT_BRANCH_HEADWAY_SEC = 600
DEFAULT_MAGLEV_HEADWAY_SEC = 900
DEFAULT_SERVICE_RULES = [{'line_id': '11', 'from_st': '花桥', 'to_st': '嘉定新城', 'headway_sec': DEFAULT_BRANCH_HEADWAY_SEC, 'source': 'default_branch'}, {'line_id': '5', 'from_st': '东川路', 'to_st': '闵行开发区', 'headway_sec': DEFAULT_BRANCH_HEADWAY_SEC, 'source': 'default_branch'}, {'line_id': '10', 'from_st': '新江湾城', 'to_st': '基隆路', 'headway_sec': DEFAULT_BRANCH_HEADWAY_SEC, 'source': 'default_branch'}, {'line_id': '8', 'from_st': '东方体育中心', 'to_st': '沈杜公路', 'headway_sec': DEFAULT_BRANCH_HEADWAY_SEC, 'source': 'default_branch'}, {'line_id': 'Maglev', 'from_st': '龙阳路', 'to_st': '浦东国际机场', 'headway_sec': DEFAULT_MAGLEV_HEADWAY_SEC, 'source': 'default_maglev'}]
TARGET_OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
DISTURBANCE_EDGES = [{'edge_type': 'inter_layer', 'edge_name': '同济大学|10', 'intensity': 1.0}, {'edge_type': 'intra_layer', 'edge_name': '10|同济大学|四平路', 'intensity': 1.0}, {'edge_type': 'intra_layer', 'edge_name': '10|四平路|同济大学', 'intensity': 1.0}, {'edge_type': 'intra_layer', 'edge_name': '10|同济大学|国权路', 'intensity': 1.0}, {'edge_type': 'intra_layer', 'edge_name': '10|国权路|同济大学', 'intensity': 1.0}, {'edge_type': 'inter_layer', 'edge_name': '四平路|10', 'intensity': 0.9}, {'edge_type': 'inter_layer', 'edge_name': '四平路|8', 'intensity': 0.9}, {'edge_type': 'intra_layer', 'edge_name': '10|四平路|邮电新村', 'intensity': 0.8}, {'edge_type': 'intra_layer', 'edge_name': '10|邮电新村|四平路', 'intensity': 0.8}, {'edge_type': 'intra_layer', 'edge_name': '10|国权路|五角场', 'intensity': 0.8}, {'edge_type': 'intra_layer', 'edge_name': '10|五角场|国权路', 'intensity': 0.8}, {'edge_type': 'intra_layer', 'edge_name': '8|四平路|曲阳路', 'intensity': 0.7}, {'edge_type': 'intra_layer', 'edge_name': '8|曲阳路|四平路', 'intensity': 0.7}, {'edge_type': 'intra_layer', 'edge_name': '8|四平路|鞍山新村', 'intensity': 0.7}, {'edge_type': 'intra_layer', 'edge_name': '8|鞍山新村|四平路', 'intensity': 0.7}]
INPUT_AUDIT_FILES = ['subway.json', '上海地铁地上线归纳.txt', '线路id与名称对应-20251210.xlsx', 'line_schedule_detailed.xlsx', '进站客流.xlsx', 'shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv']

def resolve_data_root():
    return _sr.project_root()
BASE_PATH = _sr.project_root()
OUTPUT_DIR = SUBMISSION_OUTPUT_DIR
