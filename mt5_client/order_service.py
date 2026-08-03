from typing import Optional, List
from utils.logger import Logger
from utils.retry import retry_with_backoff

MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1
MT5_ORDER_TYPE_BUY_LIMIT = 2
MT5_ORDER_TYPE_SELL_LIMIT = 3
MT5_ORDER_TYPE_BUY_STOP = 4
MT5_ORDER_TYPE_SELL_STOP = 5
MT5_TRADE_ACTION_DEAL = 1
MT5_TRADE_ACTION_PENDING = 5
MT5_TRADE_ACTION_SLTP = 6
MT5_TRADE_ACTION_MODIFY = 7
MT5_TRADE_ACTION_REMOVE = 8
MT5_ORDER_TIME_GTC = 0
MT5_ORDER_FILLING_FOK = 0
MT5_ORDER_FILLING_IOC = 1
MT5_ORDER_FILLING_RETURN = 2
MT5_ORDER_STATE_STARTED = 0
MT5_ORDER_STATE_PLACED = 1
MT5_ORDER_STATE_CANCELLED = 2
MT5_ORDER_STATE_PARTIAL = 3
MT5_ORDER_STATE_FILLED = 4
MT5_ORDER_STATE_REJECTED = 5
MT5_ORDER_STATE_EXPIRED = 6
MT5_RETCODE_PLACED = 10008
MT5_RETCODE_DONE = 10009
MT5_RETCODE_DONE_PARTIAL = 10010


class OrderService:
    def __init__(self, deviation_points: int = 20):
        self.deviation_points = deviation_points
        self.logger = Logger()

    def send_pending_order(
        self,
        symbol: str,
        order_type: int,
        volume: float,
        price: float,
        magic: int,
        comment: str,
        sl: float = 0.0,
        tp: float = 0.0,
    ) -> dict:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return {"retcode": -1, "error": "MetaTrader5 not installed"}
        request = {
            "action": MT5_TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl if sl else 0.0,
            "tp": tp if tp else 0.0,
            "deviation": self.deviation_points,
            "magic": magic,
            "comment": comment,
            "type_time": MT5_ORDER_TIME_GTC,
        }
        try:
            result = mt5.order_send(request)
            if result is None:
                error = mt5.last_error()
                return {"retcode": -1, "error": str(error)}
            retcode = result.retcode
            response = {
                "retcode": retcode,
                "comment": result.comment,
                "order": result.order,
                "volume": result.volume,
                "price": result.price,
                "request_id": result.request_id,
            }
            if retcode in (MT5_RETCODE_PLACED, MT5_RETCODE_DONE, MT5_RETCODE_DONE_PARTIAL):
                self.logger.info("Order placed", symbol=symbol, ticket=result.order,
                                 type=order_type, price=price, volume=volume, magic=magic)
            else:
                self.logger.error("Order failed", symbol=symbol, retcode=retcode,
                                  type=order_type, price=price, error=result.comment)
            return response
        except Exception as e:
            return {"retcode": -1, "error": str(e)}

    def send_pending_order_with_retry(
        self,
        symbol: str,
        order_type: int,
        volume: float,
        price: float,
        magic: int,
        comment: str,
        max_attempts: int = 3,
    ) -> dict:
        filling_modes = [None, MT5_ORDER_FILLING_RETURN, MT5_ORDER_FILLING_FOK]
        for attempt in range(max_attempts):
            mode_index = attempt if attempt < len(filling_modes) else 1
            mode = filling_modes[mode_index]
            try:
                import MetaTrader5 as mt5
            except ImportError:
                return {"retcode": -1, "error": "MetaTrader5 not installed"}
            request = {
                "action": MT5_TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": 0.0,
                "tp": 0.0,
                "deviation": self.deviation_points,
                "magic": magic,
                "comment": comment,
                "type_time": MT5_ORDER_TIME_GTC,
            }
            if mode is not None:
                request["type_filling"] = mode
            try:
                result = mt5.order_send(request)
                if result is None:
                    error = mt5.last_error()
                    continue
                retcode = result.retcode
                if retcode in (MT5_RETCODE_PLACED, MT5_RETCODE_DONE, MT5_RETCODE_DONE_PARTIAL):
                    self.logger.info("Order placed", symbol=symbol, ticket=result.order,
                                     type=order_type, price=price, volume=volume, magic=magic)
                    return {
                        "retcode": retcode,
                        "comment": result.comment,
                        "order": result.order,
                        "volume": result.volume,
                        "price": result.price,
                        "request_id": result.request_id,
                    }
                if retcode == 10030:
                    continue
                self.logger.error("Order failed", symbol=symbol, retcode=retcode,
                                  type=order_type, price=price, error=result.comment)
                return {"retcode": retcode, "error": result.comment}
            except Exception as e:
                continue
        return {"retcode": -1, "error": "All filling modes rejected"}

    def modify_order_tp(self, ticket: int, symbol: str, price: float, tp_price: float) -> dict:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return {"retcode": -1, "error": "MetaTrader5 not installed"}
        request = {
            "action": MT5_TRADE_ACTION_MODIFY,
            "order": ticket,
            "symbol": symbol,
            "price": price,
            "tp": tp_price,
            "deviation": self.deviation_points,
            "magic": 0,
            "type_time": MT5_ORDER_TIME_GTC,
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

    def remove_pending_order(self, ticket: int) -> dict:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return {"retcode": -1, "error": "MetaTrader5 not installed"}
        order = mt5.orders_get(ticket=ticket)
        if order is None or len(order) == 0:
            return {"retcode": MT5_RETCODE_DONE, "order": ticket}
        o = order[0]
        request = {
            "action": MT5_TRADE_ACTION_REMOVE,
            "order": ticket,
            "symbol": o.symbol,
            "magic": o.magic,
            "type_time": MT5_ORDER_TIME_GTC,
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

    def get_open_orders(self, symbol: str = "", magic: int = 0) -> List[dict]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []
        try:
            orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
            if orders is None:
                return []
            result = []
            for o in orders:
                if magic and o.magic != magic:
                    continue
                vol = getattr(o, 'volume', getattr(o, 'volume_current', getattr(o, 'volume_initial', 0.0)))
                result.append({
                    "ticket": o.ticket,
                    "symbol": o.symbol,
                    "type": o.type,
                    "volume": vol,
                    "volume_current": getattr(o, 'volume_current', vol),
                    "volume_initial": getattr(o, 'volume_initial', vol),
                    "price_open": o.price_open,
                    "sl": o.sl,
                    "tp": o.tp,
                    "magic": o.magic,
                    "comment": o.comment,
                    "time_setup": o.time_setup,
                    "state": o.state,
                })
            return result
        except Exception as e:
            self.logger.error("get_open_orders failed", error=str(e))
            return []
