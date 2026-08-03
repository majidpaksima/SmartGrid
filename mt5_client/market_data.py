from typing import Optional, List
from utils.logger import Logger


class MarketData:
    def __init__(self):
        self.logger = Logger()

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None
        try:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            return {
                "name": info.name,
                "digits": info.digits,
                "point": info.point,
                "trade_tick_size": info.trade_tick_size or info.point,
                "trade_contract_size": info.trade_contract_size,
                "volume_min": info.volume_min,
                "volume_max": info.volume_max,
                "volume_step": info.volume_step,
                "trade_stops_level": info.trade_stops_level or 0,
                "trade_freeze_level": info.trade_freeze_level or 0,
                "trade_mode": info.trade_mode,
                "bid": info.bid,
                "ask": info.ask,
                "spread": info.spread,
            }
        except Exception as e:
            self.logger.error("get_symbol_info failed", symbol=symbol, error=str(e))
            return None

    def get_symbol_tick(self, symbol: str) -> Optional[dict]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None
        try:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            return {
                "bid": tick.bid,
                "ask": tick.ask,
                "time": tick.time,
                "last": tick.last,
                "volume": tick.volume,
            }
        except Exception as e:
            self.logger.error("get_symbol_tick failed", symbol=symbol, error=str(e))
            return None

    def get_rates(self, symbol: str, timeframe: int, count: int) -> Optional[List[dict]]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None
        try:
            mt5.symbol_select(symbol, True)
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is None or len(rates) == 0:
                return None
            result = []
            for i in range(len(rates)):
                result.append({
                    "time": int(rates[i]["time"]),
                    "open": float(rates[i]["open"]),
                    "high": float(rates[i]["high"]),
                    "low": float(rates[i]["low"]),
                    "close": float(rates[i]["close"]),
                    "tick_volume": int(rates[i]["tick_volume"]),
                    "spread": int(rates[i]["spread"]),
                    "real_volume": int(rates[i]["real_volume"]),
                })
            return result
        except Exception as e:
            self.logger.error("get_rates failed", symbol=symbol, error=str(e))
            return None

    def select_symbol(self, symbol: str, enable: bool = True) -> bool:
        try:
            import MetaTrader5 as mt5
            return mt5.symbol_select(symbol, enable)
        except Exception:
            return False

    def calculate_profit(self, action: int, symbol: str, volume: float, price_open: float, price_close: float) -> Optional[float]:
        try:
            import MetaTrader5 as mt5
            return mt5.order_calc_profit(action, symbol, volume, price_open, price_close)
        except Exception:
            return None

    def calculate_margin(self, action: int, symbol: str, volume: float, price: float) -> Optional[float]:
        try:
            import MetaTrader5 as mt5
            return mt5.order_calc_margin(action, symbol, volume, price)
        except Exception:
            return None
