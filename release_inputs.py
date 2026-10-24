"""Load and validate simulation inputs."""
from pathlib import Path
import json
import os

PACKAGE = Path(__file__).resolve().parent
PLATFORM_FILE = 'shanghai_metro_flow_with_code_final_20250802-20250831_v4.csv'
BASE_FILES = ['subway.json', 'line_schedule_detailed.xlsx',
              '上海地铁地上线归纳.txt', '线路id与名称对应-20251210.xlsx', PLATFORM_FILE]


def local_root():
    """Return the configured input directory."""
    return Path(os.environ.get('METRO_DATA_ROOT', str(PACKAGE / 'local_inputs'))).expanduser().resolve()


def static_flow_source(base_path):
    """Return the static-weight source filename."""
    return '进站客流.xlsx' if (Path(base_path) / '进站客流.xlsx').is_file() else 'historical_station_weights.csv'


def static_flow_frames(base_path):
    """Read station weights in worksheet and row order."""
    import pandas as pd
    workbook = Path(base_path) / '进站客流.xlsx'
    if workbook.is_file():
        with pd.ExcelFile(workbook) as book:
            return [book.parse(sheet, header=None) for sheet in book.sheet_names]
    path = PACKAGE / 'data/public/historical_station_weights.csv'
    frame = pd.read_csv(path)
    return [group[['station', 'value_1', 'value_2']].set_axis([0, 1, 2], axis=1)
            for _, group in frame.groupby('sheet', sort=False)]


def load_notice_rows(source):
    """Read the local notice file or its input template."""
    path = local_root() / 'official_notices.json'
    if not path.exists():
        path = PACKAGE / 'data/templates/official_notices.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    return [dict(row) for row in rows
            if ('上海地铁' in row.get('Account', '')) == (source == 'metro')]


def validate_inputs(scenario):
    """Check required files, columns and values."""
    import pandas as pd
    import numpy as np
    root = local_root()
    missing = [name for name in BASE_FILES if not (root / name).is_file()]
    if scenario == 'C' and not (root / 'official_notices.json').is_file():
        missing.append('official_notices.json')
    if missing:
        raise FileNotFoundError('Missing local inputs / 缺少本地输入: ' + ', '.join(missing)
                                + '. See docs/DATA_SOURCES.md.')
    flow = pd.read_csv(root / PLATFORM_FILE)
    required = {'time', 'inbound', 'outbound'}
    if not required.issubset(flow.columns) or not {'station_name_mapped', 'station'}.intersection(flow.columns):
        raise ValueError('Platform CSV requires time, inbound, outbound and station or station_name_mapped.')
    dates = pd.to_datetime(flow.time, errors='raise')
    selected = flow[dates.dt.date.eq(pd.Timestamp('2025-08-08').date())]
    if selected.empty:
        raise ValueError('Platform CSV has no records for 2025-08-08.')
    weights = selected[['inbound', 'outbound']].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(weights.to_numpy()).all() or (weights < 0).any().any() or (weights.sum() <= 0).any():
        raise ValueError('Platform sampling weights must be finite, nonnegative and nonzero.')
    topology = json.loads((root/'subway.json').read_text(encoding='utf-8'))
    if not topology.get('l'):
        raise ValueError('Topology contains no metro lines.')
    for line in topology['l']:
        if not {'ln', 'ls', 'st'}.issubset(line) or not line['st']:
            raise ValueError('Each topology line needs ln, ls and a nonempty st list.')
        for station in line['st']:
            if not {'si', 'sl', 'n'}.issubset(station):
                raise ValueError('Station requires si, sl and n.')
            coordinates = [float(v) for v in station['sl'].split(',')]
            if len(coordinates) != 2 or not np.isfinite(coordinates).all():
                raise ValueError('Station coordinates are invalid.')
    schedule = pd.read_excel(root/'line_schedule_detailed.xlsx')
    schedule_fields = {'LineID','DayType','Start_Time','End_Time','From_Station','To_Station','Interval_Sec'}
    if schedule.empty or not schedule_fields.issubset(schedule):
        raise ValueError('Schedule is empty or has missing required columns.')
    interval = pd.to_numeric(schedule.Interval_Sec, errors='raise')
    if not np.isfinite(interval).all() or not interval.gt(0).all():
        raise ValueError('Schedule intervals must be finite positive seconds.')
    mapping = pd.read_excel(root/'线路id与名称对应-20251210.xlsx')
    if mapping.empty or not {'Line ID','Line Name'}.issubset(mapping):
        raise ValueError('Line mapping requires Line ID and Line Name.')
    ground = (root/'上海地铁地上线归纳.txt').read_text(encoding='utf-8')
    if not any('：' in line and '-' in line for line in ground.splitlines()):
        raise ValueError('Ground sections require line-name：station-station chains.')
    if scenario == 'B':
        path = Path(os.environ.get('SCENARIO_B_COHORT_FILE', PACKAGE / 'inputs/scenario_b_cohort.csv'))
        if not path.is_file():
            raise FileNotFoundError('The fixed Scenario B cohort is missing.')
    if scenario == 'C':
        rows = json.loads((root / 'official_notices.json').read_text(encoding='utf-8'))
        expected = json.loads((PACKAGE / 'data/notice_sources.json').read_text(encoding='utf-8'))
        identity = lambda r: (r.get('Publish_Time_BJT'), r.get('Account'))
        if len(rows) != len(expected) or sorted(map(identity, rows)) != sorted(map(identity, expected)):
            raise ValueError('Notice source/time identities differ from the configured timeline.')
        if any(not str(r.get('Body', '')).strip() for r in rows):
            raise ValueError('Notice bodies must be supplied locally; metadata alone cannot run Scenario C.')
    return {'scenario': scenario, 'required_files': BASE_FILES,
            'platform_date': '2025-08-08', 'notice_text_required': scenario == 'C'}
