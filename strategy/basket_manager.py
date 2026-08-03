from typing import List, Optional
from utils.logger import Logger

MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1


class BasketManager:
    def __init__(self):
        self.logger = Logger()

    def get_buy_positions(self, positions: List[dict]) -> List[dict]:
        return [p for p in positions if p["type"] == MT5_ORDER_TYPE_BUY]

    def get_sell_positions(self, positions: List[dict]) -> List[dict]:
        return [p for p in positions if p["type"] == MT5_ORDER_TYPE_SELL]

    def get_total_buy_volume(self, positions: List[dict]) -> float:
        return sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_BUY)

    def get_total_sell_volume(self, positions: List[dict]) -> float:
        return sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_SELL)

    def get_net_volume(self, positions: List[dict]) -> float:
        return self.get_total_buy_volume(positions) - self.get_total_sell_volume(positions)

    def is_locked_exposure(self, positions: List[dict]) -> bool:
        if not positions:
            return False
        return self.get_net_volume(positions) == 0

    def select_trigger_position(self, positions: List[dict]) -> Optional[dict]:
        net_vol = self.get_net_volume(positions)
        if net_vol > 0:
            candidates = self.get_buy_positions(positions)
        elif net_vol < 0:
            candidates = self.get_sell_positions(positions)
        else:
            return None
        if not candidates:
            return None
        candidates.sort(key=lambda p: (p.get("time", 0), p.get("ticket", 0)))
        return candidates[0]

    def get_commission(self, positions: List[dict], commission_per_position: float) -> float:
        return len(positions) * commission_per_position

    def get_gross_profit(self, positions: List[dict]) -> float:
        return sum(p.get("profit", 0.0) for p in positions)

    def get_net_profit(self, positions: List[dict], commission_per_position: float) -> float:
        gross = self.get_gross_profit(positions)
        commission = self.get_commission(positions, commission_per_position)
        return gross - commission
