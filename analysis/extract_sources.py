"""Read simulation workbooks from their run manifests."""
from pathlib import Path
import json
import sys
import pandas as pd
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from submission_runtime import MODEL, VERSION, sha256

def extract(sources):
    """Map Line11 and Bebinca to their corresponding run manifests."""
    if set(sources) != {'Line11', 'Bebinca'}:
        raise ValueError('Provide both Line11 and Bebinca completed-run manifests explicitly.')
    out = ROOT / 'processed'
    staged, provenance = ([], [])
    for case, manifest_path in sources.items():
        path = Path(manifest_path).resolve()
        manifest = json.loads(path.read_text(encoding='utf-8'))
        cfg = manifest['configuration']
        if manifest.get('status') != 'completed' or cfg.get('version') != VERSION or cfg.get('model') != MODEL:
            raise ValueError('Analysis requires a completed run with the configured model and version.')
        if cfg.get('scenario') != ('B' if case == 'Line11' else 'C'):
            raise ValueError('The run manifest does not match the requested scenario.')
        relative = manifest.get('outputs', {}).get('excel_path')
        if not relative:
            raise ValueError('The completed run does not declare its workbook output.')
        workbook = (path.parent / relative).resolve()
        if path.parent not in workbook.parents:
            raise ValueError('Workbook output must belong to the declared run directory.')
        cohort = pd.read_excel(workbook, sheet_name='Cohort')
        decisions = pd.read_excel(workbook, sheet_name='Passenger_Decisions')
        expected = 1500 if case == 'Line11' else 1600
        if len(decisions) != expected or decisions.duplicated(['PID', 'Scenario']).any():
            raise ValueError('Decision records are incomplete or duplicated.')
        if not decisions.LLM_Model.eq(MODEL).all():
            raise ValueError('A response from another model is present.')
        valid = decisions.LLM_Valid.astype(str).str.lower().isin(['true', '1'])
        if not valid.all():
            raise ValueError('Invalid responses must not be analyzed as LLM decisions.')
        sheets = ['Scenario_Config'] if case == 'Line11' else ['Official_Notice_Timeline', 'Travel_Probability_Summary']
        if case == 'Line11':
            times = decisions.groupby('Scenario').Scenario_Time.unique().to_dict()
            for scenario, expected_time in [('condition_1', '08:31'), ('condition_2', '09:17'), ('condition_3', '11:19')]:
                if set(times.get(scenario, [])) != {expected_time}:
                    raise ValueError('Scenario B decision times must match the configured operating conditions.')
        staged.extend([(cohort, f'{case}_cohort.csv'), (decisions, f'{case}_decisions.csv')])
        staged.extend(((pd.read_excel(workbook, sheet_name=sheet), f'{case}_{sheet}.csv') for sheet in sheets))
        provenance.append({'case': case, 'workbook_sha256': sha256(workbook), 'configuration_hash': manifest['configuration_hash'], 'agent_n': len(cohort), 'decision_n': len(decisions), 'status': 'completed_single_model'})
    out.mkdir(parents=True, exist_ok=True)
    for frame, filename in staged:
        frame.to_csv(out / filename, index=False, encoding='utf-8-sig')
    (out / 'simulation_sources.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
if __name__ == '__main__':
    raise SystemExit('Import extract() and supply the completed run manifests.')
