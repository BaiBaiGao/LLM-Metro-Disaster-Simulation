# Historical project reference: https://doi.org/10.1016/j.ijcip.2020.100358
def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate great-circle distance between latitude/longitude coordinates in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

class SubwayRuleSystem:
    """Build the multilayer metro environment, operational rules, paths and weighted efficiency."""

    def __init__(self, base_path, sim_start_time='05:30', real_flow_df=None):
        
        self.base_path = str(base_path)
        self.real_flow_df = real_flow_df
        self.G = nx.MultiGraph()
        try:
            t_obj = datetime.strptime(sim_start_time, '%H:%M')
            self.sim_start_min = t_obj.hour * 60 + t_obj.minute
            self.sim_start_dt_obj = t_obj
        except _sr.SubmissionStop:
            raise
        except Exception:
            self.sim_start_min = 330
            self.sim_start_dt_obj = datetime(2000, 1, 1, 5, 30)
        self.id_map_long_to_short = {}
        self.line_stations_index = {}
        self.schedule_rules = []
        self.schedule_lookup = {}
        self.default_service_audit = []
        self.station_pos_cache = {}
        self.fast_edge_data = []
        self.node_idx_map = {}
        self.node_pos_list = []
        self.node_st_names = []
        self._route_graph_cache = {}
        self._load_id_mapping()
        self._load_json_topology()
        self._load_detailed_schedule()
        self._build_station_index()
        self._ensure_default_service_rules()
        self._build_graph_topology()
        self._apply_ground_elevation_status()
        self._load_passenger_flow_data()
        self._apply_real_flow_initial_snapshot()
        self._build_single_layer_network()
        self._init_edge_index()
        self._init_flow_weights()
        self._precompute_static_simulation_data()
        self.reset_rule_state()
        self.Ef0 = self.calculate_weighted_efficiency(self.sim_start_min, 'Weekday')

    def _load_id_mapping(self):
        """Map long topology line identifiers to schedule line identifiers."""
        path = os.path.join(self.base_path, '线路id与名称对应-20251210.xlsx')
        try:
            if os.path.exists(path):
                df = pd.read_excel(path)
            else:
                df = pd.read_csv(path + ' - Sheet1.csv')
            for _, row in df.iterrows():
                if pd.isna(row['Line ID']):
                    continue
                long_id = str(int(row['Line ID'])) if isinstance(row['Line ID'], float) else str(row['Line ID'])
                line_name = str(row['Line Name'])
                short_id = None
                if '浦江' in line_name:
                    short_id = 'PJ'
                elif '磁浮' in line_name:
                    short_id = 'Maglev'
                elif '号线' in line_name:
                    match = re.search('(\\d+)', line_name)
                    if match:
                        short_id = match.group(1)
                if short_id:
                    self.id_map_long_to_short[long_id] = short_id
        except _sr.SubmissionStop:
            raise
        except Exception:
            pass

    def _rule_is_active(self, rule, clock_min):
        """Check a service rule at the specified minute, including overnight windows."""
        start = int(rule.get('start_min', 0)) % 1440
        end = int(rule.get('end_min', 1440)) % 1440
        minute = int(clock_min) % 1440
        if start == end:
            return True
        if start < end:
            return start <= minute < end
        return minute >= start or minute < end

    def _active_rules_for_line(self, line_id, clock_min, day_type='Weekday'):
        """Return active service rules for a line and day type."""
        return [r for r in self.schedule_lookup.get((str(line_id), day_type), []) if self._rule_is_active(r, clock_min)]

    def _rule_covers_service(self, rule, line_id, from_st, to_st):
        """Check whether a service rule covers the requested branch section."""
        if str(rule.get('line_id')) != str(line_id):
            return False
        rule_from = clean_station_name(rule.get('from_st', ''))
        rule_to = clean_station_name(rule.get('to_st', ''))
        from_st = clean_station_name(from_st)
        to_st = clean_station_name(to_st)
        if {rule_from, rule_to} == {from_st, to_st}:
            return True
        return self._is_station_in_section(str(line_id), from_st, rule_from, rule_to) and self._is_station_in_section(str(line_id), to_st, rule_from, rule_to)

    def _append_schedule_rule(self, rule):
        """Add a rule to both schedule records and lookup indices."""
        self.schedule_rules.append(rule)
        key = (str(rule['line_id']), str(rule['day_type']))
        if key not in self.schedule_lookup:
            self.schedule_lookup[key] = []
        self.schedule_lookup[key].append(rule)

    def _ensure_default_service_rules(self):
        """Add audited service rules for branches absent from the input schedule."""
        sim_min = int(self.sim_start_min) % 1440
        for spec in DEFAULT_SERVICE_RULES:
            line_id = str(spec['line_id'])
            from_st = clean_station_name(spec['from_st'])
            to_st = clean_station_name(spec['to_st'])
            source = str(spec['source'])
            headway = int(spec['headway_sec'])
            audit = {'Line_ID': line_id, 'From_Station': from_st, 'To_Station': to_st, 'Source': source, 'Headway_Sec': headway, 'Enabled': False, 'Reason': '', 'Generated_Trains': 0}
            line_cache = self.station_pos_cache.get(line_id, {})
            if from_st not in line_cache or to_st not in line_cache:
                audit['Reason'] = 'target_station_missing_in_network'
                self.default_service_audit.append(audit)
                continue
            active_rules = self._active_rules_for_line(line_id, sim_min, 'Weekday')
            covering_rules = [r for r in active_rules if self._rule_covers_service(r, line_id, from_st, to_st)]
            if covering_rules:
                audit['Reason'] = f'active_schedule_exists_at_{START_TIME_STR}'
                self.default_service_audit.append(audit)
                continue
            rule = {'line_id': line_id, 'day_type': 'Weekday', 'start_min': 0, 'end_min': 1440, 'from_st': from_st, 'to_st': to_st, 'interval': float(headway), 'source': source, 'is_default_service': True, 'default_service_key': f'{source}|{line_id}|{from_st}|{to_st}'}
            self._append_schedule_rule(rule)
            audit['Enabled'] = True
            audit['Reason'] = f'no_active_schedule_covering_service_at_{START_TIME_STR}'
            self.default_service_audit.append(audit)

    def _load_json_topology(self):
        """Read the locally supplied Amap topology without modifying it."""
        path = os.path.join(self.base_path, 'subway.json')
        with open(path, 'r', encoding='utf-8') as f:
            self.raw_json = json.load(f)

    def _load_detailed_schedule(self):
        """Read the detailed service schedule and retain its source labels."""
        path = os.path.join(self.base_path, 'line_schedule_detailed.xlsx')
        try:
            df = pd.read_excel(path)
            df['LineID'] = df['LineID'].apply(lambda x: str(int(x)) if isinstance(x, float) else str(x).strip())
            for _, row in df.iterrows():
                s_dt = pd.to_datetime(str(row['Start_Time']), format='%H:%M:%S', errors='coerce')
                e_dt = pd.to_datetime(str(row['End_Time']), format='%H:%M:%S', errors='coerce')
                rule = {'line_id': row['LineID'], 'day_type': str(row['DayType']).strip(), 'start_min': s_dt.hour * 60 + s_dt.minute if pd.notnull(s_dt) else 0, 'end_min': e_dt.hour * 60 + e_dt.minute if pd.notnull(e_dt) else 1440, 'from_st': clean_station_name(row['From_Station']), 'to_st': clean_station_name(row['To_Station']), 'interval': float(row['Interval_Sec']), 'source': 'schedule', 'is_default_service': False, 'default_service_key': ''}
                self.schedule_rules.append(rule)
                key = (rule['line_id'], rule['day_type'])
                if key not in self.schedule_lookup:
                    self.schedule_lookup[key] = []
                self.schedule_lookup[key].append(rule)
        except _sr.SubmissionStop:
            raise
        except Exception:
            pass

    def _build_station_index(self):
        """Index station order by line for branch and section matching."""
        for line_info in self.raw_json['l']:
            short_id = self.id_map_long_to_short.get(str(line_info['ls']))
            if not short_id:
                continue
            st_names = [st['n'] for st in line_info['st']]
            if short_id not in self.line_stations_index:
                self.line_stations_index[short_id] = []
                self.station_pos_cache[short_id] = {}
            for st in st_names:
                if st not in self.line_stations_index[short_id]:
                    self.line_stations_index[short_id].append(st)
                    self.station_pos_cache[short_id][st] = len(self.line_stations_index[short_id]) - 1

    def _is_station_in_section(self, line_id, station_name, from_st, to_st):
        """Check whether a station lies within a line section."""
        line_cache = self.station_pos_cache.get(line_id)
        if not line_cache:
            return False
        idx_s = line_cache.get(station_name)
        idx_f = line_cache.get(from_st)
        idx_t = line_cache.get(to_st)
        if idx_s is None or idx_f is None or idx_t is None:
            return False
        return min(idx_f, idx_t) <= idx_s <= max(idx_f, idx_t)

    def _build_graph_topology(self):
        """Build station and line layers using the supplied metro topology."""
        for line_info in self.raw_json['l']:
            short_id = self.id_map_long_to_short.get(str(line_info['ls']))
            if not short_id:
                continue
            sts = line_info['st']
            for st in sts:
                pos = tuple(map(float, st['sl'].split(',')))[::-1]
                node_st = f'{st['n']}_车站层'
                node_ln = f'{st['n']}_线路层_{short_id}'
                if not self.G.has_node(node_st):
                    self.G.add_node(node_st, layer='station', pos=pos, flow=1000)
                self.G.add_node(node_ln, layer='line', pos=pos, line_id=short_id, station_name=st['n'])
                self.G.add_edge(node_st, node_ln, type='boarding', weight=0)
            for i in range(len(sts) - 1):
                u = f'{sts[i]['n']}_线路层_{short_id}'
                v = f'{sts[i + 1]['n']}_线路层_{short_id}'
                if self.G.has_node(u) and self.G.has_node(v):
                    self.G.add_edge(u, v, type='riding', weight=0, line_id=short_id)

    def _apply_ground_elevation_status(self):
        """Apply locally supplied above-ground section classifications."""
        file_path = os.path.join(self.base_path, '上海地铁地上线归纳.txt')
        above_set = set()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if '：' not in line:
                        continue
                    parts = line.strip().split('：')
                    match = re.search('(\\d+)', parts[0])
                    lid = match.group(1) if match else 'PJ' if '浦江' in parts[0] else None
                    if not lid:
                        continue
                    for group in parts[1].split('，'):
                        sts = group.strip().split('-')
                        for i in range(len(sts) - 1):
                            pair = tuple(sorted((sts[i].strip(), sts[i + 1].strip())))
                            above_set.add((lid, pair[0], pair[1]))
        except _sr.SubmissionStop:
            raise
        except Exception:
            pass
        for u, v, k, attr in self.G.edges(keys=True, data=True):
            if attr.get('type') == 'riding':
                lid = attr.get('line_id')
                stu = self.G.nodes[u].get('station_name')
                stv = self.G.nodes[v].get('station_name')
                pair = tuple(sorted((stu, stv))) if stu and stv else None
                attr['is_above_ground'] = 1 if pair and (lid, pair[0], pair[1]) in above_set else 0

    def _load_passenger_flow_data(self):
        """Initialize station flow weights from the historical static input; later platform snapshots may override them."""
        file_path = os.path.join(self.base_path, '进站客流.xlsx')
        p_flow = {}
        sum_f, num_f = (0, 0)
        try:
            for static_frame in _sr.static_flow_frames(self.base_path):
                for _, row in static_frame.iterrows():
                    val = ((row[1] or 0) + (row[2] or 0)) / 2
                    p_flow[f'{row[0]}_车站层'] = p_flow.get(f'{row[0]}_车站层', 0) + val
                    sum_f += val
                    num_f += 1
        except _sr.SubmissionStop:
            raise
        except Exception:
            pass
        avg_flow = sum_f / max(num_f, 1) or 1000
        avg_deg = np.mean([d for n, d in self.G.degree() if self.G.nodes[n].get('layer') == 'station']) or 1
        self.flow_source_used = _sr.static_flow_source(self.base_path) if p_flow else 'default_static_flow'
        for n, d in self.G.nodes(data=True):
            if d.get('layer') == 'station':
                d['flow'] = p_flow.get(n, avg_flow / avg_deg * self.G.degree(n))

    def _apply_real_flow_initial_snapshot(self):
        """Override initial station weights with the nearest available platform snapshot."""
        if self.real_flow_df is None or len(self.real_flow_df) == 0:
            return
        required_cols = {'time', 'station', 'inbound', 'outbound'}
        if not required_cols.issubset(set(self.real_flow_df.columns)):
            print(f'警告: 客流表缺少必要列 {required_cols}，保留静态客流来源。')
            return
        try:
            start_minute = self.sim_start_min % 1440
            flow_df = self.real_flow_df.copy()
            minute_of_day = flow_df['time'].dt.hour * 60 + flow_df['time'].dt.minute
            nearest_minute = minute_of_day.iloc[(minute_of_day - start_minute).abs().argsort().iloc[0]]
            batch = flow_df[minute_of_day == nearest_minute]
            updated = 0
            for _, row in batch.iterrows():
                st_name = str(row['station']).strip()
                node_st = f'{st_name}_车站层'
                if self.G.has_node(node_st):
                    self.G.nodes[node_st]['flow'] = (float(row['inbound']) + float(row['outbound'])) / 2.0
                    updated += 1
            if updated > 0:
                hour = int(nearest_minute // 60)
                minute = int(nearest_minute % 60)
                self.flow_source_used = f'CSV_hour_snapshot:{hour:02d}:{minute:02d}'
                print(f'{OUTPUT_VERSION}: 已用 CSV 小时客流覆盖初始 flow，共更新 {updated} 个车站。')
        except _sr.SubmissionStop:
            raise
        except Exception as exc:
            print(f'警告: CSV 起始客流覆盖失败，保留静态客流。原因: {exc}')

    def _build_single_layer_network(self):
        """Build the auxiliary station connectivity graph."""
        self.single_layer_net = nx.Graph()
        for u, v, attr in self.G.edges(data=True):
            if attr.get('type') == 'riding':
                n1 = self.G.nodes[u].get('station_name', u.split('_')[0])
                n2 = self.G.nodes[v].get('station_name', v.split('_')[0])
                if n1 != n2:
                    self.single_layer_net.add_edge(n1, n2)

    def _init_edge_index(self):
        """Assign stable edge indices for disturbance and output alignment."""
        self.edge_list = list(self.G.edges(keys=True))
        self.edge_idx = {e: i for i, e in enumerate(self.edge_list)}

    def _init_flow_weights(self):
        """Derive inter-layer and intra-layer weights from station flows."""
        ln_weights = {}
        for u, v, k, attr in self.G.edges(keys=True, data=True):
            if attr['type'] == 'boarding':
                st = u if self.G.nodes[u].get('layer') == 'station' else v
                ln = v if st == u else u
                w = self.G.nodes[st].get('flow', 1000) / max(1, self.G.degree[st])
                attr['flow_weight'] = w
                ln_weights[ln] = w
        for u, v, k, attr in self.G.edges(keys=True, data=True):
            if attr['type'] == 'riding':
                attr['flow_weight'] = (ln_weights.get(u, 100) + ln_weights.get(v, 100)) / 2

    def _precompute_static_simulation_data(self):
        """Cache edge, line, distance, travel-time and service-rule information."""
        nodes = list(self.G.nodes())
        self.node_idx_map = {n: i for i, n in enumerate(nodes)}
        for i, n in enumerate(nodes):
            self.node_pos_list.append(self.G.nodes[n]['pos'])
            self.node_st_names.append(self.G.nodes[n].get('station_name', n.split('_')[0]))
        target_day_type = 'Weekday'
        for edge_idx, (u, v, k) in enumerate(self.edge_list):
            attr = self.G.edges[u, v, k]
            u_idx, v_idx = (self.node_idx_map[u], self.node_idx_map[v])
            lid = attr.get('line_id') or self.G.nodes[u].get('line_id') or self.G.nodes[v].get('line_id')
            est = {'edge_idx': edge_idx, 'u_idx': u_idx, 'v_idx': v_idx, 'type': attr['type'], 'line_id': str(lid) if lid else None, 'is_above_ground': attr.get('is_above_ground', 0), 'flow_weight': attr.get('flow_weight', 1.0), 'boarding_dist': 0.0, 'boarding_node_flow': 1000.0, 'riding_pos_mid': None, 'riding_applicable_rules': [], 'agent_override': 'normal', 'speed_factor': 1.0, 'disturbance_intensity': 0.0, 'speed_loss_ratio': 0.0, 'decision_source': ''}
            if lid:
                rules = self.schedule_lookup.get((str(lid), target_day_type), [])
                st_u, st_v = (self.node_st_names[u_idx], self.node_st_names[v_idx])
                check_st = st_u if attr['type'] == 'boarding' else None
                for r in rules:
                    if check_st:
                        if self._is_station_in_section(str(lid), check_st, r['from_st'], r['to_st']):
                            est['riding_applicable_rules'].append(r)
                    elif self._is_station_in_section(str(lid), st_u, r['from_st'], r['to_st']) and self._is_station_in_section(str(lid), st_v, r['from_st'], r['to_st']):
                        est['riding_applicable_rules'].append(r)
            if attr['type'] == 'boarding':
                st = self.node_st_names[u_idx]
                deg = self.single_layer_net.degree[st] if st in self.single_layer_net else 1
                est['boarding_dist'] = deg * 100.0
                st_node = u if self.G.nodes[u]['layer'] == 'station' else v
                est['boarding_node_flow'] = self.G.nodes[st_node].get('flow', 1000)
            else:
                p1, p2 = (self.G.nodes[u]['pos'], self.G.nodes[v]['pos'])
                est['riding_pos_mid'] = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                dist_km = haversine_km(p1[0], p1[1], p2[0], p2[1])
                est['distance_km'] = dist_km
                est['base_runtime_sec'] = max(MIN_SEGMENT_RUNTIME_SEC, dist_km * TRACK_DETOUR_FACTOR / TRAIN_SPEED_KMH * 3600.0)
            self.fast_edge_data.append(est)

    def reset_rule_state(self):
        """Reset edge disturbance states before a new operational evaluation."""
        for i, (u, v, k) in enumerate(self.edge_list):
            sd = self.fast_edge_data[i]
            sd.update({'agent_override': 'normal', 'speed_factor': 1.0, 'disturbance_intensity': 0.0, 'speed_loss_ratio': 0.0, 'decision_source': ''})
            self.G.edges[u, v, k].update({'agent_override': 'normal', 'speed_factor': 1.0, 'disturbance_intensity': 0.0, 'speed_loss_ratio': 0.0, 'decision_source': ''})
        self._route_graph_cache = {}

    def station_name_from_node(self, node_name):
        """Resolve a station name from a multilayer node."""
        data = self.G.nodes.get(node_name, {})
        if data.get('station_name'):
            return str(data.get('station_name'))
        return str(node_name).split('_')[0]

    def line_display_name(self, line_id):
        """Resolve the display name of a line identifier."""
        if line_id is None:
            return '未知线路'
        line_id = str(line_id)
        if line_id == 'PJ':
            return '浦江线'
        if line_id == 'Maglev':
            return '磁悬浮'
        return f'{line_id}号线'

    def headway_seconds(self, line_id, clock_min, default_seconds=300.0, station_name=None):
        """Compute the minimum applicable headway in seconds."""
        rules = self._active_rules_for_line(str(line_id), clock_min, 'Weekday')
        if station_name:
            station_name = clean_station_name(station_name)
            station_rules = [r for r in rules if self._is_station_in_section(str(line_id), station_name, clean_station_name(r['from_st']), clean_station_name(r['to_st']))]
            if station_rules:
                rules = station_rules
        if rules:
            return float(min((float(r['interval']) for r in rules)))
        return float(default_seconds)

    def public_edge_key(self, edge_idx):
        """Convert an internal edge index to the external disturbance key."""
        u, v, k = self.edge_list[edge_idx]
        sd = self.fast_edge_data[edge_idx]
        if sd['type'] == 'boarding':
            station_node = u if self.G.nodes[u].get('layer') == 'station' else v
            line_node = v if station_node == u else u
            station = self.station_name_from_node(station_node)
            line_id = str(self.G.nodes[line_node].get('line_id') or sd.get('line_id'))
            return ('inter_layer', station, line_id)
        if sd['type'] == 'riding':
            a = self.station_name_from_node(u)
            b = self.station_name_from_node(v)
            a, b = sorted([a, b])
            return ('intra_layer', str(sd.get('line_id')), a, b)
        return ('unknown', edge_idx)

    def public_edge_name(self, edge_idx):
        """Return a readable edge name."""
        key = self.public_edge_key(edge_idx)
        if key[0] == 'inter_layer':
            return f'{key[1]}|{key[2]}'
        if key[0] == 'intra_layer':
            return f'{key[1]}|{key[2]}|{key[3]}'
        return str(key)

    def edge_indices_for_key(self, key):
        """Find internal edge indices for a normalized key."""
        return [i for i in range(len(self.fast_edge_data)) if self.public_edge_key(i) == key]

    def edge_indices_for_station(self, station_name, edge_type='boarding'):
        """Find inter-layer and adjacent line edges associated with a station."""
        out = []
        station_name = clean_station_name(station_name)
        for i, (u, v, k) in enumerate(self.edge_list):
            if self.fast_edge_data[i]['type'] != edge_type:
                continue
            if self.station_name_from_node(u) == station_name or self.station_name_from_node(v) == station_name:
                out.append(i)
        return out

    def edge_indices_for_line(self, line_id, edge_type='riding'):
        """Find edges of the requested type on a line."""
        return [i for i, sd in enumerate(self.fast_edge_data) if sd['type'] == edge_type and str(sd.get('line_id')) == str(line_id)]

    def apply_edge_decision(self, edge_idx, intensity, speed_factor, override, source):
        """Apply intensity, speed and closure decisions to edge state."""
        loss = clip01(intensity)
        factor = max(0.0, min(1.0, float(speed_factor)))
        u, v, k = self.edge_list[edge_idx]
        sd = self.fast_edge_data[edge_idx]
        sd['disturbance_intensity'] = max(float(sd.get('disturbance_intensity', 0.0)), loss)
        sd['speed_loss_ratio'] = max(float(sd.get('speed_loss_ratio', 0.0)), loss)
        sd['speed_factor'] = min(float(sd.get('speed_factor', 1.0)), factor)
        if override != 'normal':
            sd['agent_override'] = override
        sd['decision_source'] = source
        self.G.edges[u, v, k].update({'disturbance_intensity': sd['disturbance_intensity'], 'speed_loss_ratio': sd['speed_loss_ratio'], 'speed_factor': sd['speed_factor'], 'agent_override': sd['agent_override'], 'decision_source': sd['decision_source']})
        self._route_graph_cache = {}

    def base_edge_minutes(self, edge_idx, current_time_min):
        """Compute undisturbed edge travel time, including walking and waiting where applicable."""
        sd = self.fast_edge_data[edge_idx]
        if sd['type'] == 'riding':
            return float(sd.get('base_runtime_sec', 120.0)) / 60.0
        if sd['type'] == 'boarding':
            walk_dist = float(sd.get('boarding_dist', 0.0))
            walk_norm = walk_dist / 1.4 / 60.0
            line_id = sd.get('line_id')
            u, v, _ = self.edge_list[edge_idx]
            station_node = u if self.G.nodes[u].get('layer') == 'station' else v
            station_name = self.station_name_from_node(station_node)
            hw_norm = self.headway_seconds(line_id, current_time_min, station_name=station_name) / 60.0 if line_id else 5.0
            return walk_norm + 0.5 * hw_norm
        return 0.0

    def edge_minutes(self, edge_idx, current_time_min, weight_mode='current'):
        """Compute current edge travel time; closed edges return infinity."""
        base = self.base_edge_minutes(edge_idx, current_time_min)
        if weight_mode == 'baseline':
            return (base, base)
        sd = self.fast_edge_data[edge_idx]
        if sd.get('agent_override') in {'closed', 'suspended', 'train_blocked'}:
            return (float('inf'), base)
        factor = float(sd.get('speed_factor', 1.0))
        if factor <= 0.0:
            return (float('inf'), base)
        return (max(0.01, base / factor), base)

    def calculate_weighted_efficiency(self, current_time_min, day_type='Weekday'):
        """Compute normalized multilayer efficiency under the current operational state."""
        for i, (u, v, k) in enumerate(self.edge_list):
            curr_min, base_min = self.edge_minutes(i, current_time_min, weight_mode='current')
            flow_weight = max(1e-06, float(self.fast_edge_data[i].get('flow_weight', 1.0)))
            self.G.edges[u, v, k]['tau'] = curr_min / flow_weight if np.isfinite(curr_min) else float('inf')
            self.G.edges[u, v, k]['tau_baseline'] = base_min / flow_weight if np.isfinite(base_min) else float('inf')
        st_nodes = [n for n, d in self.G.nodes(data=True) if d.get('layer') == 'station']
        st_set = set(st_nodes)
        n_st = len(st_nodes)
        if n_st < 2:
            return 0.0
        sum_inv_curr = 0.0
        sum_inv_base = 0.0
        for src in st_nodes:
            try:
                lens_curr = nx.single_source_dijkstra_path_length(self.G, src, weight='tau')
            except _sr.SubmissionStop:
                raise
            except Exception:
                lens_curr = {}
            try:
                lens_base = nx.single_source_dijkstra_path_length(self.G, src, weight='tau_baseline')
            except _sr.SubmissionStop:
                raise
            except Exception:
                lens_base = {}
            for dst in st_set:
                if dst == src:
                    continue
                l_c = lens_curr.get(dst, float('inf'))
                l_b = lens_base.get(dst, float('inf'))
                if l_c > 0 and np.isfinite(l_c):
                    sum_inv_curr += 1.0 / l_c
                if l_b > 0 and np.isfinite(l_b):
                    sum_inv_base += 1.0 / l_b
        ef = 1 / (n_st * (n_st - 1)) * sum_inv_curr
        ef0 = 1 / (n_st * (n_st - 1)) * sum_inv_base
        return ef / ef0 if ef0 > 0 else 1.0

    def build_passenger_route_graph(self, sim_min, weight_mode='current'):
        """Collapse parallel edges to the best current travel-time edge for routing."""
        cache_key = (int(sim_min), weight_mode, tuple(((i, sd.get('agent_override'), round(float(sd.get('speed_factor', 1.0)), 6)) for i, sd in enumerate(self.fast_edge_data) if sd.get('agent_override') != 'normal' or float(sd.get('speed_factor', 1.0)) < 1.0)))
        if cache_key in self._route_graph_cache:
            return self._route_graph_cache[cache_key]
        route_graph = nx.DiGraph()
        for n, data in self.G.nodes(data=True):
            route_graph.add_node(n, **data)

        def add_best(a, b, payload):
            old = route_graph.get_edge_data(a, b)
            if old is None or payload['weight'] < old.get('weight', float('inf')):
                route_graph.add_edge(a, b, **payload)
        clock_min = self.sim_start_min + int(sim_min)
        for edge_idx, (u, v, k) in enumerate(self.edge_list):
            sd = self.fast_edge_data[edge_idx]
            curr_min, norm_min = self.edge_minutes(edge_idx, clock_min, weight_mode=weight_mode)
            if not np.isfinite(curr_min):
                continue
            attr = self.G.edges[u, v, k]
            if attr.get('type') == 'riding':
                a = self.station_name_from_node(u)
                b = self.station_name_from_node(v)
                lid = str(sd.get('line_id'))
                section_key = tuple(sorted((lid, a, b)))
                payload = {'weight': curr_min, 'current_min': curr_min, 'normal_min': norm_min, 'type': 'riding', 'line_id': lid, 'section_key': section_key, 'edge_idx': edge_idx}
                add_best(u, v, payload)
                add_best(v, u, payload)
            elif attr.get('type') == 'boarding':
                u_layer = self.G.nodes[u].get('layer')
                v_layer = self.G.nodes[v].get('layer')
                if u_layer == 'station':
                    station_node, line_node = (u, v)
                else:
                    station_node, line_node = (v, u)
                lid = str(self.G.nodes[line_node].get('line_id') or sd.get('line_id'))
                access_payload = {'weight': curr_min + 0.25, 'current_min': curr_min, 'normal_min': norm_min, 'type': 'boarding', 'line_id': lid, 'edge_idx': edge_idx}
                exit_payload = {'weight': max(0.1, min(curr_min, 2.0)), 'current_min': max(0.1, min(curr_min, 2.0)), 'normal_min': max(0.1, min(norm_min, 2.0)), 'type': 'alighting_or_transfer', 'line_id': lid, 'edge_idx': edge_idx}
                add_best(station_node, line_node, access_payload)
                add_best(line_node, station_node, exit_payload)
        self._route_graph_cache[cache_key] = route_graph
        return route_graph

    def route_station_path(self, node_path):
        """Extract a station sequence without consecutive duplicates."""
        stations = []
        for node in node_path or []:
            st = self.station_name_from_node(node)
            if st and (not stations or stations[-1] != st):
                stations.append(st)
        return stations

    def route_line_segments(self, node_path, route_graph):
        """Group the node path into line-specific journey segments."""
        segments = []
        current = None
        for u, v in zip(node_path[:-1], node_path[1:]):
            data = route_graph.get_edge_data(u, v) or {}
            if data.get('type') != 'riding':
                continue
            lid = str(data.get('line_id'))
            a = self.station_name_from_node(u)
            b = self.station_name_from_node(v)
            if current and current['line_id'] == lid and (current['stations'][-1] == a):
                current['stations'].append(b)
                current['end'] = b
            else:
                if current:
                    segments.append(current)
                current = {'line_id': lid, 'line_name': self.line_display_name(lid), 'start': a, 'end': b, 'stations': [a, b]}
        if current:
            segments.append(current)
        return segments

    def route_impacts_from_edges(self, edge_records):
        """Summarize affected lines, sections and stations on a path."""
        affected_lines = set()
        affected_sections = []
        affected_stations = set()
        reasons = []
        seen = set()
        for rec in edge_records:
            if rec['disturbance_intensity'] <= 0:
                continue
            if rec['type'] == 'boarding':
                affected_stations.add(rec['station'])
                reasons.append(f'{rec['station']}站层间连边强度{rec['disturbance_intensity']:.2f}')
            elif rec['type'] == 'riding':
                affected_lines.add(self.line_display_name(rec['line_id']))
                key = (rec['line_id'], rec['from_station'], rec['to_station'])
                if key not in seen:
                    seen.add(key)
                    affected_sections.append({'line': self.line_display_name(rec['line_id']), 'section': f'{rec['from_station']}->{rec['to_station']}', 'intensity': rec['disturbance_intensity'], 'speed_factor': rec['speed_factor']})
                    reasons.append(f'{self.line_display_name(rec['line_id'])} {rec['from_station']}->{rec['to_station']}强度{rec['disturbance_intensity']:.2f}')
        return {'affected_lines': sorted(affected_lines), 'affected_sections': affected_sections, 'affected_stations': sorted(affected_stations), 'summary': '；'.join(reasons[:8]) if reasons else '当前路线未经过受扰动连边'}

    def plan_passenger_route(self, origin_st, dest_st, sim_min, weight_mode='current'):
        """Return minimum-time routing, accessibility and disruption information."""
        origin_st = clean_station_name(origin_st)
        dest_st = clean_station_name(dest_st)
        origin_node = f'{origin_st}_车站层'
        dest_node = f'{dest_st}_车站层'
        plan = {'reachable': False, 'origin': origin_st, 'dest': dest_st, 'node_path': [], 'station_path': [], 'line_segments': [], 'transfer_stations': [], 'normal_duration_min': float('inf'), 'current_duration_min': float('inf'), 'estimated_delay_min': float('inf'), 'affected_lines': [], 'affected_sections': [], 'affected_stations': [], 'impact_summary': '路线不可达', 'edge_indices': [], 'edge_records': []}
        if not self.G.has_node(origin_node) or not self.G.has_node(dest_node):
            plan['impact_summary'] = '起点或终点不在网络中'
            return plan
        route_graph = self.build_passenger_route_graph(sim_min, weight_mode=weight_mode)
        try:
            node_path = nx.shortest_path(route_graph, origin_node, dest_node, weight='weight')
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return plan
        current_total = 0.0
        normal_total = 0.0
        edge_indices = []
        edge_records = []
        for u, v in zip(node_path[:-1], node_path[1:]):
            data = route_graph.get_edge_data(u, v) or {}
            current_total += float(data.get('current_min', 0.0))
            normal_total += float(data.get('normal_min', data.get('current_min', 0.0)))
            edge_idx = data.get('edge_idx')
            if edge_idx is None:
                continue
            edge_indices.append(int(edge_idx))
            sd = self.fast_edge_data[int(edge_idx)]
            rec = {'edge_idx': int(edge_idx), 'type': sd['type'], 'line_id': sd.get('line_id'), 'disturbance_intensity': float(sd.get('disturbance_intensity', 0.0)), 'speed_factor': float(sd.get('speed_factor', 1.0)), 'agent_override': sd.get('agent_override', 'normal'), 'edge_name': self.public_edge_name(int(edge_idx))}
            if sd['type'] == 'boarding':
                rec['station'] = self.station_name_from_node(u if self.G.nodes[u].get('layer') == 'station' else v)
            elif sd['type'] == 'riding':
                rec['from_station'] = self.station_name_from_node(u)
                rec['to_station'] = self.station_name_from_node(v)
            edge_records.append(rec)
        station_path = self.route_station_path(node_path)
        segments = self.route_line_segments(node_path, route_graph)
        transfer_stations = []
        for prev, nxt in zip(segments[:-1], segments[1:]):
            transfer_stations.append(prev.get('end') if prev.get('end') == nxt.get('start') else f'{prev.get('end')}->{nxt.get('start')}')
        impacts = self.route_impacts_from_edges(edge_records)
        plan.update({'reachable': True, 'node_path': node_path, 'station_path': station_path, 'line_segments': segments, 'transfer_stations': transfer_stations, 'normal_duration_min': float(normal_total), 'current_duration_min': float(current_total), 'estimated_delay_min': float(max(0.0, current_total - normal_total)), 'affected_lines': impacts['affected_lines'], 'affected_sections': impacts['affected_sections'], 'affected_stations': impacts['affected_stations'], 'impact_summary': impacts['summary'], 'edge_indices': edge_indices, 'edge_records': edge_records})
        return plan

    def route_plans_equivalent(self, a, b):
        """Compare station sequences and line segments of two route plans."""
        if not a or not b:
            return False
        return list(a.get('station_path', [])) == list(b.get('station_path', [])) and [s.get('line_id') for s in a.get('line_segments', [])] == [s.get('line_id') for s in b.get('line_segments', [])]

    def route_has_disturbance(self, plan):
        """Check whether a route uses affected or inaccessible edges."""
        return any((float(rec.get('disturbance_intensity', 0.0)) > 0 for rec in plan.get('edge_records', [])))

    def route_hard_disruption_records(self, plan):
        """Identify closures, suspensions and blocked edges on the route."""
        hard_overrides = {'closed', 'suspended', 'train_blocked'}
        records = []
        for rec in plan.get('edge_records', []):
            override = str(rec.get('agent_override', 'normal'))
            try:
                speed_factor = float(rec.get('speed_factor', 1.0))
            except _sr.SubmissionStop:
                raise
            except Exception:
                speed_factor = 1.0
            if override in hard_overrides or speed_factor <= 0.0:
                records.append(rec)
        return records

    def route_has_hard_disruption(self, plan):
        """Check for closure, suspension, blockage or zero-speed edges."""
        return bool(self.route_hard_disruption_records(plan))

    def route_hard_disruption_summary(self, plan):
        """Produce the Chinese disruption summary used in prompts and audit output."""
        records = self.route_hard_disruption_records(plan)
        if not records:
            return '路线当前没有硬中断边'
        status_map = {'closed': '关闭', 'suspended': '停运', 'train_blocked': '阻断', 'normal': '速度因子为0'}
        reasons = []
        seen = set()
        for rec in records:
            override = str(rec.get('agent_override', 'normal'))
            status = status_map.get(override, override or '不可通行')
            if rec.get('type') == 'boarding':
                line = self.line_display_name(rec.get('line_id'))
                station = rec.get('station', '')
                text = f'{station}站{line}进出站/换乘边{status}'
            elif rec.get('type') == 'riding':
                line = self.line_display_name(rec.get('line_id'))
                text = f'{line} {rec.get('from_station', '')}->{rec.get('to_station', '')}区间{status}'
            else:
                text = f'{rec.get('edge_name', '')}{status}'
            if text and text not in seen:
                seen.add(text)
                reasons.append(text)
        return '；'.join(reasons[:8]) if reasons else '路线当前存在硬中断边'

    def station_names(self):
        """Return station names in the network."""
        return [self.station_name_from_node(n) for n, d in self.G.nodes(data=True) if d.get('layer') == 'station']
