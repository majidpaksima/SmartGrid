from typing import Optional, List, Tuple
from utils.logger import Logger

MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1


class TargetCalculator:
    def __init__(self):
        self.logger = Logger()

    def calculate_basket_target(
        self,
        positions: List[dict],
        commission_per_position: float,
        target_profit: float,
        symbol: str,
        tick_size: float,
        current_price: float,
    ) -> Optional[float]:
        if not positions:
            return None
        total_buy_volume = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_BUY)
        total_sell_volume = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_SELL)
        net_volume = total_buy_volume - total_sell_volume
        if net_volume == 0:
            return None
        total_commission = len(positions) * commission_per_position
        gross_target = target_profit + total_commission
        mt5_usable = self._check_mt5_usable()
        if mt5_usable:
            direction = 1 if net_volume > 0 else -1
            lower, upper = self._find_bracket(positions, gross_target, symbol, current_price, direction, tick_size)
            if lower is not None and upper is not None:
                target = self._bisect_target(positions, gross_target, symbol, lower, upper, tick_size)
                if target is not None:
                    return self._adjust_target(positions, gross_target, symbol, target, tick_size, direction)
        return self._estimate_target_simple(positions, gross_target, net_volume, current_price, tick_size)

    def _check_mt5_usable(self) -> bool:
        try:
            import MetaTrader5 as mt5
            info = mt5.terminal_info()
            return info is not None
        except Exception:
            return False

    def _profit_at_price(self, positions: List[dict], close_price: float, symbol: str) -> float:
        try:
            import MetaTrader5 as mt5
            total = 0.0
            for p in positions:
                profit = mt5.order_calc_profit(
                    p["type"], symbol, p["volume"], p["price_open"], close_price
                )
                if profit is not None:
                    total += profit
            if total == 0.0 and len(positions) > 0:
                return self._estimate_profit_simple(positions, close_price)
            return total
        except Exception:
            return self._estimate_profit_simple(positions, close_price)

    def _find_bracket(
        self,
        positions: List[dict],
        gross_target: float,
        symbol: str,
        start_price: float,
        direction: int,
        tick_size: float,
    ) -> Tuple[Optional[float], Optional[float]]:
        step = tick_size * 100
        max_steps = 100000
        low = start_price
        high = start_price
        for _ in range(max_steps):
            if direction > 0:
                high = start_price + step
            else:
                low = start_price - step
            profit_low = self._profit_at_price(positions, low, symbol)
            profit_high = self._profit_at_price(positions, high, symbol)
            f_low = profit_low - gross_target
            f_high = profit_high - gross_target
            if f_low * f_high <= 0:
                return (low, high)
            step *= 2
            if step > 1e12:
                break
        return (None, None)

    def _bisect_target(
        self,
        positions: List[dict],
        gross_target: float,
        symbol: str,
        lower: float,
        upper: float,
        tick_size: float,
        max_iter: int = 200,
    ) -> Optional[float]:
        for _ in range(max_iter):
            mid = (lower + upper) / 2.0
            profit_mid = self._profit_at_price(positions, mid, symbol)
            f_mid = profit_mid - gross_target
            if abs(f_mid) < 1e-10 or (upper - lower) < tick_size * 0.1:
                return mid
            profit_low = self._profit_at_price(positions, lower, symbol)
            f_low = profit_low - gross_target
            if f_low * f_mid <= 0:
                upper = mid
            else:
                lower = mid
        return (lower + upper) / 2.0

    def _adjust_target(
        self,
        positions: List[dict],
        gross_target: float,
        symbol: str,
        target: float,
        tick_size: float,
        direction: int,
    ) -> float:
        adj_target = round(target / tick_size) * tick_size
        profit = self._profit_at_price(positions, adj_target, symbol)
        if profit < gross_target:
            adj_target += tick_size * direction
        return adj_target

    def _estimate_profit_simple(self, positions: List[dict], close_price: float) -> float:
        total = 0.0
        for p in positions:
            if p["type"] == MT5_ORDER_TYPE_BUY:
                total += (close_price - p["price_open"]) * p["volume"] * 100
            else:
                total += (p["price_open"] - close_price) * p["volume"] * 100
        return total

    def _estimate_target_simple(
        self,
        positions: List[dict],
        gross_target: float,
        net_volume: float,
        current_price: float,
        tick_size: float,
    ) -> Optional[float]:
        if net_volume == 0:
            return None
        price_move = gross_target / abs(net_volume * 100)
        direction = 1 if net_volume > 0 else -1
        target = current_price + price_move * direction
        target = round(target / tick_size) * tick_size
        return target
