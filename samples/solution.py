def clamp(value, minimum, maximum):
    """Return value limited to the inclusive minimum and maximum."""
    if minimum > maximum:
        raise ValueError("minimum must not exceed maximum")
    return max(minimum, min(value, maximum))
