def calc_oee_percent(availability: float, performance: float, quality: float) -> float:
    """availability/performance/quality in [0..1]"""
    return round(availability * performance * quality * 100.0, 1)
