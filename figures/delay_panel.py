from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

def render(data, geometry, out, large_text=False, compact=False, dpi=900):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Patch
    arial = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf'
    if arial.is_file():
        font_manager.fontManager.addfont(arial)
    font_manager.findfont('Arial', fallback_to_default=False)
    colors = ['#0A6DAF', '#059244', '#A72061']
    labels = ['Continue along the original route', 'Reroute to the shortest-time metro path', 'Forgo metro travel']
    body_size = 17.5 if compact else 18.5 if large_text else 11.5
    axis_size = 18.5 if compact else 20.5 if large_text else 12.5
    footer_size = 14.5 if large_text else 10.5
    plt.rcParams.update({'font.family': 'Arial', 'font.size': body_size, 'text.color': 'black', 'axes.labelcolor': 'black', 'xtick.color': 'black', 'ytick.color': 'black', 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'figure.facecolor': 'none', 'axes.facecolor': 'none', 'axes.unicode_minus': False})
    width, height = (geometry['width_pt'] / 72, geometry['height_pt'] / 72)
    fig = plt.figure(figsize=(width, height))
    if compact:
        bottom, top = (0.68 / height, 1 - 0.5 / height)
        left, plot_width = (0.18, 0.79)
    else:
        bottom, top = (0.98 / height, 1 - 1.04 / height) if large_text else (0.85 / height, 1 - 0.82 / height)
        left, plot_width = (0.352, 0.455) if large_text else (0.27, 0.69)
    ax = fig.add_axes([left, bottom, plot_width, top - bottom])
    positions = np.arange(len(data))
    previous = np.zeros(len(data))
    for index, color in enumerate(colors):
        values = data[f'choice_{index + 1}_percent'].to_numpy()
        ax.barh(positions, values, left=previous, height=0.62 if compact else 0.6 if large_text else 0.43, color=color, edgecolor='none')
        previous += values
    group_labels = [row['group'] if large_text else f'{row['group']}\nn = {int(row.n_decisions)}; u = {int(row.u_profiles)}' for _, row in data.iterrows()]
    if compact:
        from matplotlib.transforms import blended_transform_factory
        ax.set_yticks(positions, [''] * len(positions))
        trans = blended_transform_factory(ax.transAxes, ax.transData)
        for index, row in data.iterrows():
            label = 'NMP' if row['group'] == 'Metro unavailable' else row['group']
            ax.text(-0.025, index - 0.21, label, transform=trans, fontsize=body_size, ha='right', va='center', clip_on=False)
            ax.text(-0.025, index + 0.28, f'{int(row.n_decisions)}/{int(row.u_profiles)}', transform=trans, fontsize=13.5, ha='right', va='center', clip_on=False)
    else:
        ax.set_yticks(positions, group_labels, fontsize=body_size)
    ax.set_ylim(len(data) - 0.5, -0.6)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.tick_params(axis='y', length=0, pad=5)
    ax.tick_params(axis='x', color='#848385', length=3, labelsize=body_size)
    ax.set_xlabel('Share of decisions (%)', fontsize=axis_size, labelpad=4)
    if compact:
        fig.text(0.095, 0.932, 'Delay (min)\nn/u', fontsize=15.5, ha='center', va='center', linespacing=1.05)
    else:
        ax.set_ylabel('Estimated delay (min)', fontsize=axis_size, labelpad=10)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.spines['bottom'].set_color('#848385')
    ax.spines['bottom'].set_linewidth(0.8)
    ax.grid(axis='x', color='#C9C9C9', linewidth=0.5)
    ax.set_axisbelow(True)
    fig.legend([Patch(facecolor=c, edgecolor='none') for c in colors], ['OR', 'RR', 'FM'] if compact else labels, loc='upper left', bbox_to_anchor=(left, 0.986), borderaxespad=0, frameon=False, ncol=3 if compact else 1, columnspacing=1.5, handlelength=1.1 if large_text or compact else 1.25, handletextpad=0.5 if large_text or compact else 0.6, labelspacing=0.15 if large_text else 0.3, fontsize=body_size)
    if large_text and (not compact):
        from matplotlib.transforms import blended_transform_factory
        trans = blended_transform_factory(fig.transFigure, ax.transData)
        for index, row in data.iterrows():
            fig.text(0.885, index, f'{int(row.n_decisions)}/{int(row.u_profiles)}', transform=trans, fontsize=body_size, va='center', ha='center')
        fig.text(0.885, top + 0.025, 'n/u', fontsize=body_size, va='bottom', ha='center')
    if not compact:
        fig.text(left, 0.038 if large_text else 0.028, 'n/u = decision records / unique profiles' if large_text else 'n = decision records; u = unique passenger profiles.', fontsize=footer_size, ha='left', va='center', color='black')
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []
    for item in fig.findobj():
        if hasattr(item, 'get_text') and item.get_visible() and item.get_text():
            bounds = item.get_window_extent(renderer)
            assert bounds.x0 >= -0.5 and bounds.y0 >= -0.5 and (bounds.x1 <= fig.bbox.width + 0.5) and (bounds.y1 <= fig.bbox.height + 0.5), item.get_text()
            boxes.append((item.get_text(), bounds))
    stem = 'A_delay_choice_composition'
    fig.savefig(out / (stem + f'_{dpi}dpi.png'), dpi=dpi, transparent=True)
    fig.savefig(out / (stem + '.svg'), transparent=True)
    fig.savefig(out / (stem + '.pdf'), transparent=True)
    fig.savefig(out / (stem + '_preview.png'), dpi=220, facecolor='white', transparent=False)
    plt.close(fig)
    return (stem, colors)
