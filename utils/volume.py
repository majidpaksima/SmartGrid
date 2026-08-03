from decimal import Decimal, ROUND_HALF_UP


def normalize_volume(volume: float, volume_min: float, volume_max: float, volume_step: float) -> float:
    if volume_step <= 0:
        return max(volume_min, min(volume, volume_max))
    step_dec = Decimal(str(volume_step))
    vol_dec = Decimal(str(volume))
    normalized = (vol_dec / step_dec).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step_dec
    result = float(normalized)
    if result < volume_min:
        return volume_min
    if result > volume_max:
        return volume_max
    vol_step_dec = Decimal(str(volume_step))
    result_dec = Decimal(str(result))
    remainder = (result_dec / vol_step_dec) % 1
    if remainder != 0:
        result = float((result_dec / vol_step_dec).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * vol_step_dec)
    return result
