def clip01(value):
    """Clamp a disturbance intensity to the interval [0, 1]."""
    try:
        return max(0.0, min(1.0, float(value)))
    except _sr.SubmissionStop:
        raise
    except Exception:
        return 0.0

class SimpleDisturbanceFunction:
    """Map normalized disturbance keys and intensities to edge speed loss."""

    def __init__(self, disturbance_edges):
        
        self.raw_records = list(disturbance_edges or [])
        self.records = []
        self.by_key = {}
        for rec in self.raw_records:
            edge_type = str(rec.get('edge_type', '')).strip()
            edge_name = str(rec.get('edge_name', '')).strip()
            intensity = clip01(rec.get('intensity', 0.0))
            key = self.normalize_key(edge_type, edge_name)
            normalized = {'edge_type': edge_type, 'edge_name': edge_name, 'normalized_key': key, 'intensity': intensity}
            self.records.append(normalized)
            self.by_key[key] = intensity

    @staticmethod
    def normalize_key(edge_type, edge_name):
        """Convert an inter-layer or intra-layer edge label to a comparable tuple."""
        parts = [clean_station_name(p) for p in str(edge_name).split('|')]
        if edge_type == 'inter_layer' and len(parts) >= 2:
            return ('inter_layer', parts[0], str(parts[1]))
        if edge_type == 'intra_layer' and len(parts) >= 3:
            a, b = sorted([parts[1], parts[2]])
            return ('intra_layer', str(parts[0]), a, b)
        return (edge_type, edge_name)

    @staticmethod
    def evaluate(edge_name, intensity, edge_type, agent_context=None):
        """Convert disturbance intensity into speed loss and speed factors."""
        loss = clip01(intensity)
        factor = 0.0 if loss >= 1.0 else max(0.05, 1.0 - loss)
        return {'edge_name': edge_name, 'edge_type': edge_type, 'speed_loss_ratio': loss, 'speed_factor': factor, 'agent_context': agent_context or {}}

    def get_intensity_by_key(self, key):
        """Return the intensity for an edge key, or zero if absent."""
        return float(self.by_key.get(key, 0.0))
