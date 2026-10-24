"""Run AFC preprocessing and comparisons."""
import argparse
import json
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--line11-manifest', required=True)
    parser.add_argument('--bebinca-manifest', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        parser.error('No analysis started. --execute is required.')
    import validation_pipeline as pipeline
    from extract_sources import extract
    for key in ['afc_directory', 'station_file']:
        if not pipeline.CFG.get(key) or not Path(pipeline.CFG[key]).exists():
            raise ValueError(f'Set {key} in validation_config.json to an available input.')
    extract({'Line11': args.line11_manifest, 'Bebinca': args.bebinca_manifest})
    for directory in [pipeline.PROCESSED, pipeline.TABLES, pipeline.QA]:
        directory.mkdir(parents=True, exist_ok=True)
    pipeline.make_mapping()
    pipeline.preprocess_afc()
    pipeline.compare_matched_od()
    pipeline.observed_spatial()
    pipeline.compute_metrics()
    pipeline.observed_temporal_context()
    print('AFC tables calculated from the supplied Scenario B and C runs.')
if __name__ == '__main__':
    main()
