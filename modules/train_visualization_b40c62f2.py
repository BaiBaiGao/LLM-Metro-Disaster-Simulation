def generate_train_movement_gif(result=None, output_dir=OUTPUT_DIR):
    _sr.require_run()
    result = result or globals().get('LAST_RESULT')
    if not isinstance(result, dict):
        raise ValueError('请先运行主仿真单元，确保 LAST_RESULT 存在。')
    train_log = result.get('train_position_log')
    if train_log is None or train_log.empty:
        raise ValueError('Train_Position_Log 为空，无法生成 GIF。')
    import matplotlib.pyplot as plt
    from PIL import Image
    from io import BytesIO
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    gif_path = output_dir / f'Train_Movement_{OUTPUT_VERSION}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif'
    system = SubwayRuleSystem(BASE_PATH, sim_start_time=START_TIME_STR, real_flow_df=None)
    line_edges = []
    for u, v, k, attr in system.G.edges(keys=True, data=True):
        if attr.get('type') != 'riding':
            continue
        p1 = system.G.nodes[u]['pos']
        p2 = system.G.nodes[v]['pos']
        line_edges.append((p1[1], p1[0], p2[1], p2[0]))
    frames = []
    frame_times = sorted((int(t) for t in train_log['Time_Sec'].dropna().unique() if int(t) % GIF_FRAME_STEP_SEC == 0))
    if not frame_times:
        frame_times = sorted((int(t) for t in train_log['Time_Sec'].dropna().unique()))
    rng = np.random.default_rng(20260526)
    train_offsets = {}
    for tid in train_log['Train_ID'].dropna().unique():
        angle = rng.uniform(0, 2 * np.pi)
        radius = rng.uniform(0.0006, 0.0015)
        train_offsets[tid] = (math.cos(angle) * radius, math.sin(angle) * radius)
    for t in frame_times:
        frame_df = train_log[train_log['Time_Sec'] == t].copy()
        fig, ax = plt.subplots(figsize=(8, 7))
        for x1, y1, x2, y2 in line_edges:
            ax.plot([x1, x2], [y1, y2], color='#c9c9c9', linewidth=0.6, zorder=1)
        if not frame_df.empty:
            xs = []
            ys = []
            colors = []
            for _, row in frame_df.iterrows():
                dx, dy = train_offsets.get(row['Train_ID'], (0.0, 0.0))
                xs.append(float(row['Lon']) + dx)
                ys.append(float(row['Lat']) + dy)
                colors.append('#d62728' if row['Status'] == 'running' else '#1f77b4')
            ax.scatter(xs, ys, s=9, c=colors, alpha=0.85, edgecolors='none', zorder=3)
        active = int(frame_df['Train_ID'].nunique()) if not frame_df.empty else 0
        dwell = int(frame_df[frame_df['Status'].isin(['dwell', 'terminal_dwell'])]['Train_ID'].nunique()) if not frame_df.empty else 0
        ax.set_title(f'Rule Train Agents v0.0.5.1 | t={t // 60:02d}:{t % 60:02d} | active={active} | dwell={dwell}')
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.set_aspect('equal', adjustable='box')
        ax.grid(False)
        ax.set_facecolor('white')
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=130)
        plt.close(fig)
        buf.seek(0)
        frames.append(Image.open(buf).convert('P', palette=Image.ADAPTIVE))
    if len(frames) < 2:
        raise ValueError('GIF 帧数不足，无法生成动态图。')
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=220, loop=0)
    print(f'GIF 已生成: {gif_path}')
    return gif_path
