"""Network geometry and service states."""
def normalize_station_name(name):
    name = str(name).strip()
    return re.sub('[（(][^）)]*[）)]', '', name).strip()

def load_metro_routes(subway_json_path):
    with subway_json_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    positions = {}
    node_names = {}
    routes = {}
    all_edges = set()
    for line in data['l']:
        line_name = line['ln']
        route = []
        for station in line['st']:
            station_id = station['si']
            lon, lat = map(float, station['sl'].split(','))
            positions[station_id] = (lon, lat)
            node_names[station_id] = normalize_station_name(station['n'])
            route.append(station_id)
        routes.setdefault(line_name, []).append(route)
        all_edges.update((frozenset((left, right)) for left, right in zip(route[:-1], route[1:])))
    return (positions, node_names, routes, all_edges)
positions, node_names, routes, all_edges = load_metro_routes(NETWORK_DATA)
plot_positions = {node: (lon * 0.8, lat) for node, (lon, lat) in positions.items()}
LIMITED_SEGMENTS_20240915 = [('2号线', '龙阳路', '张江高科'), ('2号线', '凌空路', '浦东国际机场'), ('5号线', '莘庄', '奉浦大道'), ('5号线', '东川路', '闵行开发区'), ('11号线', '嘉定北', '武威路'), ('11号线', '御桥', '迪士尼'), ('11号线', '花桥', '武威路'), ('16号线', '龙阳路', '惠南'), ('16号线', '惠南东', '临港大道'), ('浦江线', '汇臻路', '沈杜公路')]
PRE_STOPPED_FULL_LINES_20240915 = {'磁悬浮'}
STOPPED_FULL_LINES_INITIAL = {'3号线', '5号线', '16号线', '17号线', '浦江线', '磁悬浮'}
STOPPED_SEGMENTS_INITIAL = [('1号线', '莘庄', '徐家汇'), ('1号线', '上海火车站', '富锦路'), ('2号线', '龙阳路', '浦东国际机场'), ('4号线', '虹桥路', '宝山路'), ('6号线', '巨峰路', '港城路'), ('7号线', '美兰湖', '潘广路'), ('8号线', '东方体育中心', '沈杜公路'), ('9号线', '松江新城', '中春路'), ('10号线', '国帆路', '基隆路'), ('11号线', '嘉定北', '武威路'), ('11号线', '御桥', '迪士尼'), ('11号线', '花桥', '武威路')]
EVENT_TIMELINE = [{'time': '2024-09-15 21:30 起', 'state': '磁浮线提前结束，部分地面/高架段限速', 'topology_changed': True}, {'time': '2024-09-16 运营开始—14:00', 'state': '全网地面/高架限制及部分全线停运', 'topology_changed': True}, {'time': '2024-09-16 14:00—14:30', 'state': '8号线、磁浮线、浦江线恢复', 'topology_changed': True}, {'time': '2024-09-16 14:30—15:00', 'state': '2号线、7号线、9号线恢复', 'topology_changed': True}, {'time': '2024-09-16 15:00—15:15', 'state': '17号线恢复', 'topology_changed': True}, {'time': '2024-09-16 15:15—17:00', 'state': '16号线恢复，其余未恢复区段继续暂停', 'topology_changed': True}, {'time': '2024-09-16 17:00—18:20', 'state': '5号线恢复，6号线巨峰路—港城路继续暂停', 'topology_changed': True}, {'time': '2024-09-16 18:20 起', 'state': '全网正常运营', 'topology_changed': False}]
REMAINING_SEGMENTS_AFTER_1430 = [item for item in STOPPED_SEGMENTS_INITIAL if item[0] in {'1号线', '4号线', '6号线', '10号线', '11号线'}]
NETWORK_STATES = [{'interval': '2024年9月16日运营开始—14:00', 'full_lines': STOPPED_FULL_LINES_INITIAL, 'segments': STOPPED_SEGMENTS_INITIAL, 'output': '上海地铁网络_贝碧嘉时间线_20240916_0000-1400_停运.png'}, {'interval': '2024年9月16日14:00—14:30', 'full_lines': {'3号线', '5号线', '16号线', '17号线'}, 'segments': [item for item in STOPPED_SEGMENTS_INITIAL if item[0] in {'1号线', '2号线', '4号线', '6号线', '7号线', '9号线', '10号线', '11号线'}], 'output': '上海地铁网络_贝碧嘉时间线_20240916_1400-1430_第一批恢复.png'}, {'interval': '2024年9月16日14:30—15:00', 'full_lines': {'3号线', '5号线', '16号线', '17号线'}, 'segments': REMAINING_SEGMENTS_AFTER_1430, 'output': '上海地铁网络_贝碧嘉时间线_20240916_1430-1500_第二批恢复.png'}, {'interval': '2024年9月16日15:00—15:15', 'full_lines': {'3号线', '5号线', '16号线'}, 'segments': REMAINING_SEGMENTS_AFTER_1430, 'output': '上海地铁网络_贝碧嘉时间线_20240916_1500-1515_第三批恢复.png'}, {'interval': '2024年9月16日15:15—17:00', 'full_lines': {'3号线', '5号线'}, 'segments': REMAINING_SEGMENTS_AFTER_1430, 'output': '上海地铁网络_贝碧嘉时间线_20240916_1515-1700_第四批恢复.png'}, {'interval': '2024年9月16日17:00—18:20', 'full_lines': set(), 'segments': [('6号线', '巨峰路', '港城路')], 'output': '上海地铁网络_贝碧嘉时间线_20240916_1700-1820_第五批恢复.png'}, {'interval': '2024年9月16日18:20 起（全网正常）', 'full_lines': set(), 'segments': [], 'output': '上海地铁网络_贝碧嘉时间线_20240916_1820后_全网正常.png'}]

def edge_key(left, right):
    return frozenset((left, right))

def route_edges_between(line_name, start_name, end_name):
    start_name = normalize_station_name(start_name)
    end_name = normalize_station_name(end_name)
    if line_name not in routes:
        raise KeyError(f'subway.json 中没有 {line_name}')
    for route in routes[line_name]:
        station_names = [node_names[node] for node in route]
        if start_name in station_names and end_name in station_names:
            start_index = station_names.index(start_name)
            end_index = station_names.index(end_name)
            left_index, right_index = sorted((start_index, end_index))
            segment_nodes = route[left_index:right_index + 1]
            return {edge_key(left, right) for left, right in zip(segment_nodes[:-1], segment_nodes[1:])}
    raise ValueError(f'无法在 {line_name} 的同一分支中定位区段：{start_name}—{end_name}')

def edges_for_status(full_lines, segment_specs):
    status_edges = set()
    for line_name in full_lines:
        if line_name not in routes:
            raise KeyError(f'subway.json 中没有 {line_name}')
        for route in routes[line_name]:
            status_edges.update((edge_key(left, right) for left, right in zip(route[:-1], route[1:])))
    for line_name, start_name, end_name in segment_specs:
        status_edges.update(route_edges_between(line_name, start_name, end_name))
    return status_edges
limited_edges = edges_for_status(set(), LIMITED_SEGMENTS_20240915)
pre_stopped_edges = edges_for_status(PRE_STOPPED_FULL_LINES_20240915, [])
for state in NETWORK_STATES:
    state['edges'] = edges_for_status(state['full_lines'], state['segments'])
NET_NORMAL = '#059244'
NET_STOPPED = '#A72061'
NET_LIMITED = '#AC5326'
NET_NODE = '#848385'
NET_LABELS = ['15 Sep\n21:30 onward', '16 Sep\nService start–14:00', '16 Sep\n14:00–14:30', '16 Sep\n14:30–15:00', '16 Sep\n15:00–15:15', '16 Sep\n15:15–17:00', '16 Sep\n17:00–18:20', '16 Sep\n18:20 onward']
NET_STATES = [{'edges': pre_stopped_edges, 'limited': limited_edges}] + [{'edges': state['edges'], 'limited': set()} for state in NETWORK_STATES]
assert len(NET_STATES) == 8
assert all((state['edges'] <= all_edges and state['limited'] <= all_edges for state in NET_STATES))
assert not NET_STATES[-1]['edges']

def network_segments(edges):
    return [[plot_positions[a], plot_positions[b]] for a, b in (sorted(edge) for edge in sorted(edges, key=lambda v: sorted(v)))]

def network_row(fig, bottom_inches, map_height_inches, legend_y_inches):
    figheight = fig.get_figheight()
    xy = np.array(list(plot_positions.values()))
    xmin, ymin = xy.min(axis=0)
    xmax, ymax = xy.max(axis=0)
    dx = (xmax - xmin) * 0.015
    dy = (ymax - ymin) * 0.015
    panelgap = 0.006
    width = (0.9 - 7 * panelgap) / 8
    for i, state in enumerate(NET_STATES):
        left = 0.075 + i * (width + panelgap)
        ax = fig.add_axes([left, bottom_inches / figheight, width, map_height_inches / figheight])
        normal = all_edges - state['edges'] - state['limited']
        for edges, color, lw, z in [(normal, NET_NORMAL, 0.5, 1), (state['limited'] - state['edges'], NET_LIMITED, 0.95, 2), (state['edges'], NET_STOPPED, 0.95, 3)]:
            ax.add_collection(LineCollection(network_segments(edges), colors=color, linewidths=lw, alpha=1, capstyle='round', joinstyle='round', zorder=z))
        ax.scatter(xy[:, 0], xy[:, 1], s=0.12, c=NET_NODE, linewidths=0, alpha=1, zorder=4)
        ax.set_xlim(xmin - dx, xmax + dx)
        ax.set_ylim(ymin - dy, ymax + dy)
        ax.set_aspect('equal')
        ax.axis('off')
        fig.text(left + width / 2, (bottom_inches - 0.11) / figheight, NET_LABELS[i], ha='center', va='top', fontsize=10.1, color='black', linespacing=1.2)
        ax.set_gid('network_state_' + str(i + 1))
    legend = [Line2D([0], [0], color=NET_NORMAL, lw=1.8, label='Normal service'), Line2D([0], [0], color=NET_LIMITED, lw=1.8, label='Speed restriction'), Line2D([0], [0], color=NET_STOPPED, lw=1.8, label='Service suspension')]
    fig.legend(handles=legend, loc='center', bbox_to_anchor=(0.525, legend_y_inches / figheight), ncol=3, frameon=False, fontsize=11.5, columnspacing=2.5)
