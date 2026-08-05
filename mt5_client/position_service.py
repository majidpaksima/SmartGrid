from typing import Optional, List
from utils.logger import Logger
from utils.retry import retry_with_backoff

MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1
MT5_TRADE_ACTION_DEAL = 1
MT5_TRADE_ACTION_SLTP = 6
MT5_ORDER_FILLING_FOK = 0
MT5_ORDER_FILLING_IOC = 1
MT5_ORDER_FILLING_RETURN = 2
MT5_RETCODE_INVALID_FILL = 10030
MT5_RETCODE_PLACED = 10008
MT5_RETCODE_DONE = 10009
MT5_RETCODE_DONE_PARTIAL = 10010


class PositionService:
    def __init__(self, deviation_points: int = 20):
        self.deviation_points = deviation_points
        self.logger = Logger()

    def get_open_positions(self, symbol: str = "", magic: int = 0) -> List[dict]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []
        try:
            positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
            if positions is None:
                return []
            result = []
            for p in positions:
                if magic and p.magic != magic:
                    continue
                vol_p = getattr(p, 'volume', getattr(p, 'volume_current', 0.0))
                result.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": p.type,
                    "volume": vol_p,
                    "price_open": p.price_open,
                    "sl": p.sl,
                    "tp": p.tp,
                    "magic": p.magic,
                    "comment": p.comment,
                    "profit": p.profit,
                    "swap": p.swap,
                    "commission": getattr(p, 'commission', 0.0),
                    "time": p.time,
                    "time_update": p.time_update,
                })
            return result
        except Exception as e:
            self.logger.error("get_open_positions failed", error=str(e))
            return []

    def close_position(self, ticket: int, symbol: str, position_type: int, volume: float, price: float) -> dict:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return {"retcode": -1, "error": "MetaTrader5 not installed"}
        close_type = MT5_ORDER_TYPE_SELL if position_type == MT5_ORDER_TYPE_BUY else MT5_ORDER_TYPE_BUY
        filling_modes = [None, MT5_ORDER_FILLING_IOC, MT5_ORDER_FILLING_FOK, MT5_ORDER_FILLING_RETURN]
        last_result = None
        for mode in filling_modes:
            request = {
                "action": MT5_TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": close_type,
                "position": ticket,
                "price": price,
                "deviation": self.deviation_points,
                "magic": 0,
                "type_time": 0,
            }
            if mode is not None:
                request["type_filling"] = mode
            try:
                result = mt5.order_send(request)
                if result is None:
                    last_result = {"retcode": -1, "error": str(mt5.last_error())}
                    continue
                response = {
                    "retcode": result.retcode,
                    "comment": result.comment,
                    "order": result.order,
                }
                if result.retcode in (MT5_RETCODE_DONE, MT5_RETCODE_DONE_PARTIAL):
                    return response
                last_result = response
                if result.retcode != MT5_RETCODE_INVALID_FILL:
                    break
            except Exception as e:
                last_result = {"retcode": -1, "error": str(e)}
                break
        return last_result

    def close_position_with_retry(self, ticket: int, symbol: str, position_type: int,
                                  volume: float, price: float, max_attempts: int = 3) -> dict:
        success, result, error = retry_with_backoff(
            self.close_position,
            args=(ticket, symbol, position_type, volume, price),
            max_attempts=max_attempts,
        )
        if success:
            return result
        return {"retcode": -1, "error": error}

    def modify_position_sl_tp(self, ticket: int, symbol: str, sl: float = 0.0, tp: float = 0.0) -> dict:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return {"retcode": -1, "error": "MetaTrader5 not installed"}
        request = {
            "action": MT5_TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": sl if sl else 0.0,
            "tp": tp if tp else 0.0,
            "magic": 0,
        }
        try:
            result = mt5.order_send(request)
            if result is None:
                return {"retcode": -1, "error": str(mt5.last_error())}
            return {
                "retcode": result.retcode,
                "comment": result.comment,
                "order": result.order,
            }
        except Exception as e:
            return {"retcode": -1, "error": str(e)}
