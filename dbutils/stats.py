"""Small numeric helpers shared by ingest aggregations and read paths."""


def percentile(values: list[float | int], p: float) -> float:
    """Linear-interpolation percentile (same algorithm as frontend eval paths)."""
    if not values:
        return 0.0
    sorted_vals = sorted(float(v) for v in values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lower = int(k)
    upper = min(lower + 1, len(sorted_vals) - 1)
    if lower == upper:
        return sorted_vals[lower]
    return sorted_vals[lower] + (sorted_vals[upper] - sorted_vals[lower]) * (k - lower)
