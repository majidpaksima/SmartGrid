from typing import List


class CommissionService:
    def calculate_total_commission(self, position_count: int, commission_per_position: float) -> float:
        return position_count * commission_per_position

    def calculate_estimated_net_profit(self, gross_profit: float, position_count: int, commission_per_position: float) -> float:
        return gross_profit - self.calculate_total_commission(position_count, commission_per_position)
