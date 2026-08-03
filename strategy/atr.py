import math
from typing import Optional, List, Dict
from utils.logger import Logger


TIMEFRAME_MAP = {
    "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M6": 6,
    "M10": 10, "M12": 12, "M15": 15, "M20": 20, "M30": 30,
    "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360,
    "H8": 480, "H12": 720, "D1": 1440, "W1": 10080, "MN1": 43200,
}


class ATRCalculator:
    def __init__(self):
        self.logger = Logger()

    def calculate(self, symbol: str, period: int = 14, timeframe_str: str = "M5") -> Optional[float]:
        tf = TIMEFRAME_MAP.get(timeframe_str.upper())
        if tf is None:
            self.logger.error("Invalid timeframe", symbol=symbol, timeframe=timeframe_str)
            return None
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None
        bars_needed = period + 100
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars_needed)
        if rates is None or len(rates) < period + 1:
            self.logger.error("Not enough data for ATR", symbol=symbol,
                              available=len(rates) if rates is not None else 0,
                              needed=period + 1)
            return None
        tr_values = []
        high_arr = rates["high"]
        low_arr = rates["low"]
        close_arr = rates["close"]
        for i in range(1, len(rates)):
            h = float(high_arr[i])
            l = float(low_arr[i])
            pc = float(close_arr[i - 1])
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_values.append(tr)
        if len(tr_values) < period:
            return None
        last_tr_values = tr_values[-period:]
        atr = last_tr_values[0]
        for i in range(1, len(last_tr_values)):
            atr = (atr * (period - 1) + last_tr_values[i]) / period
        atr_value = float(atr)
        self.logger.info("ATR calculated", symbol=symbol, atr=f"{atr_value:.6f}",
                         timeframe=timeframe_str, period=period)
        return atr_value

    def check_entry_condition(self, symbol: str, period: int, timeframe_str: str,
                              lookback: int, slope_period: int) -> Dict:
        result = {"allowed": False, "current": 0.0, "avg": 0.0, "slope": 0.0}
        tf = TIMEFRAME_MAP.get(timeframe_str.upper())
        if tf is None:
            return result
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return result
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, lookback + period + 10)
        if rates is None or len(rates) < lookback + period:
            return result
        high_arr = rates["high"]
        low_arr = rates["low"]
        close_arr = rates["close"]
        tr_values = []
        for i in range(1, len(rates)):
            h = float(high_arr[i])
            l = float(low_arr[i])
            pc = float(close_arr[i - 1])
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_values.append(tr)
        if len(tr_values) < lookback + period:
            return result
        atr_values = []
        for i in range(lookback):
            segment = tr_values[i:i + period]
            if len(segment) < period:
                break
            atr = segment[0]
            for j in range(1, len(segment)):
                atr = (atr * (period - 1) + segment[j]) / period
            atr_values.append(atr)
        if len(atr_values) < max(slope_period, 2):
            return result
        current = atr_values[-1]
        highest = max(atr_values)
        lowest = min(atr_values)
        avg_level = (highest + lowest) / 2.0
        recent = atr_values[-slope_period:]
        n = len(recent)
        sum_x = n * (n - 1) / 2.0
        sum_y = sum(recent)
        sum_xy = sum(i * recent[i] for i in range(n))
        sum_xx = sum(i * i for i in range(n))
        denom = n * sum_xx - sum_x * sum_x
        slope = (n * sum_xy - sum_x * sum_y) / denom if denom != 0 else 0.0
        allowed = current > avg_level and slope > 0
        result["allowed"] = allowed
        result["current"] = current
        result["avg"] = avg_level
        result["slope"] = slope
        self.logger.info("ATR entry condition", symbol=symbol, allowed=allowed,
                         current=f"{current:.6f}", avg=f"{avg_level:.6f}",
                         slope=f"{slope:.6f}", lookback=lookback, slope_period=slope_period)
        return result

    def calculate_from_rates(self, rates: list, period: int = 14) -> Optional[float]:
        if not rates or len(rates) < period + 1:
            return None
        tr_values = []
        for i in range(1, len(rates)):
            high = rates[i]["high"]
            low = rates[i]["low"]
            prev_close = rates[i - 1]["close"]
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            tr_values.append(tr)
        if len(tr_values) < period:
            return None
        last_tr_values = tr_values[-period:]
        atr = last_tr_values[0]
        for i in range(1, len(last_tr_values)):
            atr = (atr * (period - 1) + last_tr_values[i]) / period
        return float(atr)
