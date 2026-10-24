"""Summarize and plot Scenario A choices by passenger attributes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from dataclasses import dataclass
PALETTE = ['#0A6DAF', '#A72061', '#926AAD', '#059244', '#AC5326', '#848385', '#D4E5F4', '#FBB9BA', '#F5EBF4', '#C2E3D0', '#F6E4D0', '#C9C9C9']
CHOICES = ['Continue along the original route', 'Reroute to the shortest-time metro path', 'Forgo metro travel']
COLORS = ['#0A6DAF', '#059244', '#A72061']
CHOICE_MAP = {'continue_original_route': CHOICES[0], 'continue_current_shortest_route': CHOICES[0], 'reroute_to_shortest_time': CHOICES[1], 'abandon_trip': CHOICES[2]}
PURPOSE_MAP = {'商务/工作事务': 'Business/work-related\nactivities', '回家': 'Returning home', '就医/照护': 'Medical treatment/\ncaregiving', '通勤/上学': 'Commuting/education', '休闲/旅游': 'Leisure/tourism', '个人事务/其他': 'Personal/other'}
PURPOSE_ORDER = ['商务/工作事务', '通勤/上学', '回家', '就医/照护', '休闲/旅游', '个人事务/其他']
INPUT_COLUMNS = ['Run_Order', 'PID', 'Origin', 'Dest', 'OD_Sample_Group', 'Age', 'Gender', 'Trip_Purpose', 'OCEAN_O', 'OCEAN_C', 'OCEAN_E', 'OCEAN_A', 'OCEAN_N', 'Risk_Preference', 'Rule_Reachable', 'Rule_Estimated_Delay_Min', 'Rule_Action', 'LLM_Action', 'LLM_Selected', 'LLM_Valid']

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def boolean(series):
    import pandas as pd
    values = series.astype(str).str.lower().map({'true': True, 'false': False, '1': True, '0': False})
    if values.isna().any():
        raise AssertionError('An unexpected boolean value was found.')
    return values.astype(bool)

def read_data(source):
    import pandas as pd
    source = Path(source)
    if source.suffix.lower() == '.csv':
        frame = pd.read_csv(source)
    else:
        frame = pd.read_excel(source, sheet_name='Passenger_Stats_All')
    frame = frame[boolean(frame.LLM_Selected) & boolean(frame.LLM_Valid) & frame.OD_Sample_Group.astype(str).str.startswith('affected_')].copy()
    frame = frame[INPUT_COLUMNS].copy().reset_index(drop=True)
    frame['Rule_Reachable'] = boolean(frame.Rule_Reachable)
    frame['Choice'] = frame.LLM_Action.map(CHOICE_MAP)
    frame['Rule_Choice'] = frame.Rule_Action.map(CHOICE_MAP)
    assert frame.Choice.notna().all() and frame.Rule_Choice.notna().all()
    assert not frame.duplicated(['Run_Order', 'PID']).any()
    assert len(frame) == 1350 and frame.PID.nunique() == 450
    assert set(frame.Run_Order) == {1, 2, 3}
    assert frame.groupby('PID').Run_Order.nunique().eq(3).all()
    fixed = [c for c in INPUT_COLUMNS if c not in {'Run_Order', 'Rule_Action', 'LLM_Action', 'LLM_Selected', 'LLM_Valid'}]
    assert len(frame[fixed].drop_duplicates()) == 450
    assert frame.Rule_Reachable.sum() == 1200
    assert frame.loc[~frame.Rule_Reachable, 'Choice'].eq(CHOICES[2]).all()
    assert frame.loc[~frame.Rule_Reachable, 'Rule_Estimated_Delay_Min'].isna().all()
    assert frame.loc[frame.Rule_Reachable, 'Rule_Estimated_Delay_Min'].notna().all()
    assert frame.loc[frame.Rule_Reachable, 'Rule_Estimated_Delay_Min'].ge(0).all()
    for col in ['Age', 'Gender', 'Trip_Purpose', 'Risk_Preference', 'OCEAN_O', 'OCEAN_C', 'OCEAN_E', 'OCEAN_A', 'OCEAN_N']:
        assert frame[col].notna().all()
    return frame

@dataclass
class Dimension:
    key: str
    title: str
    column: str
    levels: list
    labels: list
    axis_label: str

def dimensions(frame):
    import pandas as pd
    import numpy as np
    frame['Age_Group'] = pd.cut(frame.Age, [11, 18, 30, 45, 60, 80], labels=['12–18', '19–30', '31–45', '46–60', '61–80'])
    frame['Delay_Group'] = pd.cut(frame.Rule_Estimated_Delay_Min, [-np.inf, 5, 15, 30, np.inf], labels=['≤5', '>5–15', '>15–30', '>30']).astype(object)
    frame.loc[~frame.Rule_Reachable, 'Delay_Group'] = 'Metro unavailable'
    assert frame.Age_Group.notna().all() and frame.Delay_Group.notna().all()
    age = ['12–18', '19–30', '31–45', '46–60', '61–80']
    delay = ['≤5', '>5–15', '>15–30', '>30', 'Metro unavailable']
    result = [Dimension('01_delay', 'Estimated delay', 'Delay_Group', delay, delay, 'Estimated delay (min)'), Dimension('02_age', 'Age', 'Age_Group', age, age, 'Age (years)')]
    for index, code, title in [(3, 'O', 'Openness'), (4, 'C', 'Conscientiousness'), (5, 'E', 'Extraversion'), (6, 'A', 'Agreeableness'), (7, 'N', 'Neuroticism')]:
        result.append(Dimension(f'{index:02}_ocean_{code.lower()}', title, f'OCEAN_{code}', list(range(1, 6)), [str(x) for x in range(1, 6)], f'{title} score'))
    result.extend([Dimension('08_risk_preference', 'Risk preference', 'Risk_Preference', list(range(1, 6)), [str(x) for x in range(1, 6)], 'Risk preference score'), Dimension('09_trip_purpose', 'Trip purpose', 'Trip_Purpose', PURPOSE_ORDER, [PURPOSE_MAP[x] for x in PURPOSE_ORDER], 'Trip purpose'), Dimension('10_gender', 'Gender', 'Gender', ['F', 'M'], ['Female', 'Male'], 'Gender')])
    return result

def summarize(frame, dims):
    import pandas as pd
    import numpy as np
    pooled, by_run = ([], [])
    for dim in dims:
        for level, label in zip(dim.levels, dim.labels):
            group = frame[frame[dim.column].eq(level)]
            reachable = group[group.Rule_Reachable]
            row = {'dimension': dim.key, 'group': label.replace('\n', ' '), 'n_decisions': len(group), 'u_profiles': group.PID.nunique(), 'n_reachable': len(reachable), 'u_reachable_profiles': reachable.PID.nunique(), 'n_active_forgo': int(reachable.Choice.eq(CHOICES[2]).sum())}
            row['active_forgo_percent'] = row['n_active_forgo'] / len(reachable) * 100 if len(reachable) else np.nan
            percentages = []
            for run in [1, 2, 3]:
                current = group[group.Run_Order.eq(run)]
                current_reachable = current[current.Rule_Reachable]
                n_forgo = int(current_reachable.Choice.eq(CHOICES[2]).sum())
                percent = n_forgo / len(current_reachable) * 100 if len(current_reachable) else np.nan
                percentages.append(percent)
                one = {'dimension': dim.key, 'group': row['group'], 'run': run, 'n_decisions': len(current), 'n_reachable': len(current_reachable), 'n_active_forgo': n_forgo, 'active_forgo_percent': percent}
                for k, action in enumerate(CHOICES):
                    count = int(current.Choice.eq(action).sum())
                    one[f'choice_{k + 1}_count'] = count
                    one[f'choice_{k + 1}_percent'] = count / len(current) * 100 if len(current) else np.nan
                by_run.append(one)
            row['run_min_percent'] = min(percentages) if len(reachable) else np.nan
            row['run_max_percent'] = max(percentages) if len(reachable) else np.nan
            for k, action in enumerate(CHOICES):
                count = int(group.Choice.eq(action).sum())
                row[f'choice_{k + 1}_count'] = count
                row[f'choice_{k + 1}_percent'] = count / len(group) * 100 if len(group) else np.nan
            if len(group):
                assert sum((row[f'choice_{k + 1}_count'] for k in range(3))) == len(group)
            pooled.append(row)
    return (pd.DataFrame(pooled), pd.DataFrame(by_run))

def configure_plotting(cache_dir):
    os.environ.setdefault('MPLCONFIGDIR', str(cache_dir))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    arial = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf'
    if arial.is_file():
        font_manager.fontManager.addfont(arial)
    font_manager.findfont('Arial', fallback_to_default=False)
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 12, 'axes.labelsize': 13, 'xtick.labelsize': 12, 'ytick.labelsize': 12, 'legend.fontsize': 11.5, 'text.color': 'black', 'axes.labelcolor': 'black', 'xtick.color': 'black', 'ytick.color': 'black', 'axes.edgecolor': '#848385', 'axes.linewidth': 0.8, 'axes.unicode_minus': False, 'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none', 'figure.facecolor': 'none', 'axes.facecolor': 'none', 'savefig.facecolor': 'none'})

def render_one(dim, pooled, by_run, out, dpi=900):
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    from matplotlib.transforms import blended_transform_factory
    n = len(dim.levels)
    height = 2.7 + 0.53 * n
    fig = plt.figure(figsize=(13.2, height))
    bottom, top = (1.12 / height, 1 - 1.08 / height)
    left = fig.add_axes([0.215, bottom, 0.345, top - bottom])
    right = fig.add_axes([0.655, bottom, 0.18, top - bottom], sharey=left)
    data = pooled[pooled.dimension.eq(dim.key)].reset_index(drop=True)
    runs = by_run[by_run.dimension.eq(dim.key)]
    y = np.arange(n)
    for ax in [left, right]:
        ax.spines[['top', 'right']].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='y', length=0)
        ax.tick_params(axis='x', color='#848385', length=3)
        ax.grid(axis='x', color='#C9C9C9', linewidth=0.5)
        ax.set_axisbelow(True)
        ax.set_ylim(n - 0.45, -0.65)
    labels = [f'{label}\n' + f'n = {int(r.n_decisions)}; u = {int(r.u_profiles)}' for label, (_, r) in zip(dim.labels, data.iterrows())]
    left.set_yticks(y, labels)
    left.set_ylabel(dim.axis_label, labelpad=12)
    left.set_xlim(0, 100)
    left.set_xticks([0, 25, 50, 75, 100])
    left.set_xlabel('Share of decisions (%)', labelpad=6)
    previous = np.zeros(n)
    for i, color in enumerate(COLORS):
        values = data[f'choice_{i + 1}_percent'].fillna(0).to_numpy()
        left.barh(y, values, left=previous, height=0.44, color=color, edgecolor='none')
        previous += values
    for j, row in data.iterrows():
        if row.n_decisions == 0:
            left.text(50, j, 'No observations', ha='center', va='center', fontsize=12)
    right.tick_params(labelleft=False)
    xmax = 100 if dim.column == 'Delay_Group' else 15
    right.set_xlim(0, xmax)
    right.set_xticks([0, 25, 50, 75, 100] if xmax == 100 else [0, 5, 10, 15])
    right.set_xlabel('Forgo metro travel when reachable (%)', labelpad=6)
    run_colors = ['#0A6DAF', '#926AAD', '#AC5326']
    markers = ['s', '^', 'D']
    for j, row in data.iterrows():
        if row.n_reachable == 0:
            message = 'No observations' if row.n_decisions == 0 else 'Not applicable'
            right.text(xmax / 2, j, message, va='center', ha='center', fontsize=11.5)
            continue
        right.hlines(j, row.run_min_percent, row.run_max_percent, color='#848385', linewidth=1.6, zorder=2, clip_on=False)
        right.vlines([row.run_min_percent, row.run_max_percent], j - 0.07, j + 0.07, color='#848385', linewidth=1, zorder=2, clip_on=False)
        one = runs[runs.group.eq(row.group)].sort_values('run')
        for offset, (_, run), color, marker in zip([-0.13, 0, 0.13], one.iterrows(), run_colors, markers):
            right.scatter(run.active_forgo_percent, j + offset, color=color, marker=marker, s=24, linewidths=0, zorder=3, clip_on=False)
        right.scatter(row.active_forgo_percent, j, color='#A72061', marker='o', s=53, linewidths=0, zorder=4, clip_on=False)
        if row.run_max_percent > xmax:
            raise AssertionError('A repeat-level proportion would be clipped by the common axis.')
        transform = blended_transform_factory(right.transAxes, right.transData)
        right.text(1.09, j, f'{int(row.n_active_forgo)}/{int(row.n_reachable)} ({row.active_forgo_percent:.1f}%)', transform=transform, va='center', ha='left', fontsize=12, clip_on=False)
    fig.legend([Patch(facecolor=c, edgecolor='none') for c in COLORS], ['Continue along the original route', 'Reroute to the shortest-time metro path', 'Forgo metro travel'], loc='upper left', bbox_to_anchor=(0.215, 0.985), frameon=False, ncol=1, borderaxespad=0, handlelength=1.3, handletextpad=0.7, labelspacing=0.4)
    right_handles = [Line2D([], [], color='#A72061', marker='o', ls='none', markersize=6.7), Line2D([], [], color='#848385', lw=1.5)]
    right_labels = ['Pooled proportion', 'Range across three runs']
    for color, marker, run in zip(run_colors, markers, [1, 2, 3]):
        right_handles.append(Line2D([], [], color=color, marker=marker, ls='none', markersize=4.8))
        right_labels.append(f'Run {run}')
    fig.legend(right_handles, right_labels, loc='upper left', bbox_to_anchor=(0.65, 0.985), ncol=2, frameon=False, borderaxespad=0, handlelength=1.3, columnspacing=1.2, labelspacing=0.4)
    fig.text(0.215, 0.035, 'n = decision records; u = unique passenger profiles.', fontsize=10.8, va='center')
    fig.text(0.655, 0.035, 'Reachable metro journeys only; ranges are not confidence intervals.', fontsize=10.5, va='center')
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for artist in fig.findobj():
        if hasattr(artist, 'get_text') and artist.get_visible() and artist.get_text():
            bbox = artist.get_window_extent(renderer)
            if bbox.x0 < -1 or bbox.x1 > fig.bbox.width + 1 or bbox.y0 < -1 or (bbox.y1 > fig.bbox.height + 1):
                raise AssertionError(f'Text falls outside the canvas in {dim.key}: {artist.get_text()!r}')
    preview = out / 'previews' / f'{dim.key}_preview.png'
    fig.savefig(preview, dpi=180, transparent=False, facecolor='white')
    fig.savefig(out / 'figures' / f'{dim.key}.svg', transparent=True)
    fig.savefig(out / 'figures' / f'{dim.key}.pdf', transparent=True)
    fig.savefig(out / 'figures' / f'{dim.key}_900dpi.png', dpi=dpi, transparent=True)
    plt.close(fig)
    return {'dimension': dim.key, 'title': dim.title, 'width_inches': 13.2, 'height_inches': height, 'dpi': dpi, 'right_axis_max_percent': xmax, 'preview': preview.name, 'png': f'{dim.key}_900dpi.png', 'svg': f'{dim.key}.svg', 'pdf': f'{dim.key}.pdf'}

def render_overview(dims, out):
    import matplotlib.pyplot as plt
    from PIL import Image
    fig, axes = plt.subplots(5, 2, figsize=(18, 20), facecolor='white')
    for ax, dim in zip(axes.flat, dims):
        with Image.open(out / 'previews' / f'{dim.key}_preview.png') as im:
            ax.imshow(im.convert('RGB'))
        ax.set_axis_off()
        ax.set_title(dim.title, fontsize=16, loc='left', pad=2, color='black', fontfamily='Arial')
    fig.subplots_adjust(left=0.025, right=0.985, top=0.98, bottom=0.02, wspace=0.035, hspace=0.13)
    fig.savefig(out / 'previews' / '00_all_candidates_overview.png', dpi=180, facecolor='white')
    fig.savefig(out / 'previews' / '00_all_candidates_overview.pdf', facecolor='white')
    plt.close(fig)
