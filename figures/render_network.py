"""Plot the eight network states during Typhoon Bebinca."""
from pathlib import Path
import argparse
import json
import re
import numpy as np
from render_results import setup, save


def render(topology, out, dpi=900):
    out = Path(out).resolve()
    if out.drive.lower() == 'c:':
        raise ValueError('Choose a project output directory outside C:.')
    out.mkdir(parents=True, exist_ok=True)
    plt = setup(out)
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    source = Path(__file__).with_name('network_components.py')
    namespace = dict(NETWORK_DATA=Path(topology), np=np, json=json, re=re,
                     LineCollection=LineCollection, Line2D=Line2D)
    exec(compile(source.read_text(encoding='utf-8'), source.name, 'exec'), namespace)
    fig = plt.figure(figsize=(16, 3.1))
    namespace['network_row'](fig, .65, 1.9, 2.85)
    save(fig, out, 'C_network_states', dpi)
    plt.close(fig)
    report = [{'label': label, 'suspended_edges': len(state['edges']),
               'restricted_edges': len(state['limited'])}
              for label, state in zip(namespace['NET_LABELS'], namespace['NET_STATES'])]
    (out/'network_counts.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--topology', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dpi', type=int, default=900)
    args = parser.parse_args()
    render(args.topology, args.out, args.dpi)
