from typing import Optional, List
from datetime import datetime, timedelta
from utils.logger import Logger


class HistoryService:
    def __init__(self):
        self.logger = Logger()

    def get_deals(self, days_back: int = 7, symbol: str = "", magic: int = 0) -> List[dict]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []
        try:
            from datetime import datetime as dt
            now = dt.now()
            start = now - timedelta(days=days_back)
            deals = mt5.history_deals_get(start, now, group=symbol if symbol else "*")
            if deals is None:
                return []
            result = []
            for d in deals:
                if magic and d.magic != magic:
                    continue
                vol_d = getattr(d, 'volume', 0.0)
                result.append({
                    "ticket": d.ticket,
                    "order": d.order,
                    "position_id": d.position_id,
                    "symbol": d.symbol,
                    "type": d.type,
                    "entry": d.entry,
                    "volume": vol_d,
                    "price": d.price,
                    "profit": d.profit,
                    "commission": d.commission,
                    "swap": d.swap,
                    "magic": d.magic,
                    "comment": d.comment,
                    "time": d.time,
                })
            return result
        except Exception as e:
            self.logger.error("get_deals failed", error=str(e))
            return []

    def get_orders_history(self, days_back: int = 7, symbol: str = "") -> List[dict]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []
        try:
            from datetime import datetime as dt
            now = dt.now()
            start = now - timedelta(days=days_back)
            orders = mt5.history_orders_get(start, now, group=symbol if symbol else "*")
            if orders is None:
                return []
            result = []
            for o in orders:
                vol_o = getattr(o, 'volume', getattr(o, 'volume_current', getattr(o, 'volume_initial', 0.0)))
                result.append({
                    "ticket": o.ticket,
                    "symbol": o.symbol,
                    "type": o.type,
                    "state": o.state,
                    "volume": vol_o,
                    "price_open": o.price_open,
                    "magic": o.magic,
                    "comment": o.comment,
                    "time_setup": o.time_setup,
                    "time_done": o.time_done,
                })
            return result
        except Exception as e:
            self.logger.error("get_orders_history failed", error=str(e))
            return []

    def get_deals_for_position(self, position_id: int, days_back: int = 7) -> List[dict]:
        all_deals = self.get_deals(days_back=days_back)
        return [d for d in all_deals if d.get("position_id") == position_id]
