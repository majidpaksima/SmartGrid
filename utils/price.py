from decimal import Decimal, ROUND_HALF_UP, ROUND_UP, ROUND_DOWN


def normalize_price(raw_price: float, tick_size: float, digits: int = 5) -> float:
    if tick_size <= 0:
        return round(raw_price, digits)
    tick_dec = Decimal(str(tick_size))
    price_dec = Decimal(str(raw_price))
    normalized = (price_dec / tick_dec).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick_dec
    return float(normalized)


def normalize_buy_stop_price(raw_price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return raw_price
    tick_dec = Decimal(str(tick_size))
    price_dec = Decimal(str(raw_price))
    normalized = (price_dec / tick_dec).to_integral_value(rounding=ROUND_UP) * tick_dec
    return float(normalized)


def normalize_sell_stop_price(raw_price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return raw_price
    tick_dec = Decimal(str(tick_size))
    price_dec = Decimal(str(raw_price))
    normalized = (price_dec / tick_dec).to_integral_value(rounding=ROUND_DOWN) * tick_dec
    return float(normalized)


def price_to_ticks(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return 0.0
    return price / tick_size
