from typing import List, Tuple, Optional
from utils.logger import Logger
from utils.price import normalize_buy_stop_price, normalize_sell_stop_price


class GridBuilder:
    def __init__(self):
        self.logger = Logger()

    def build_grid_prices(
        self,
        anchor_price: float,
        atr: float,
        grid_count: int,
        tick_size: float,
        bid: float = 0.0,
        ask: float = 0.0,
        trade_stops_level: int = 0,
    ) -> Tuple[float, float, List[float], List[float]]:
        calculated_grid_step = atr / grid_count
        market_buffer = 0.0
        if tick_size > 0:
            market_buffer = tick_size
        if bid > 0 and ask > 0:
            spread_buffer = max(ask - bid, tick_size)
            market_buffer = max(market_buffer, spread_buffer)
        if trade_stops_level > 0 and tick_size > 0:
            min_stop_distance = trade_stops_level * tick_size
            effective_grid_step = max(calculated_grid_step, min_stop_distance + market_buffer)
        else:
            effective_grid_step = max(calculated_grid_step, market_buffer)
        buy_prices = []
        sell_prices = []
        for j in range(1, grid_count + 1):
            min_buy = ask + market_buffer if ask > 0 else anchor_price
            raw_buy = max(anchor_price + j * effective_grid_step, min_buy + (j - 1) * effective_grid_step)
            buy_price = normalize_buy_stop_price(raw_buy, tick_size)
            buy_prices.append(buy_price)
            max_sell = bid - market_buffer if bid > 0 else anchor_price
            raw_sell = min(anchor_price - j * effective_grid_step, max_sell - (j - 1) * effective_grid_step)
            sell_price = normalize_sell_stop_price(raw_sell, tick_size)
            sell_prices.append(sell_price)
        return calculated_grid_step, effective_grid_step, buy_prices, sell_prices

    def build_orders(
        self,
        symbol: str,
        magic: int,
        cycle_number: int,
        grid_count: int,
        lot_size: float,
        buy_prices: List[float],
        sell_prices: List[float],
    ) -> List[dict]:
        orders = []
        for j, price in enumerate(buy_prices, 1):
            comment = f"C{cycle_number}_{j}"
            orders.append({
                "symbol": symbol,
                "type": 4,
                "volume": lot_size,
                "price": price,
                "magic": magic,
                "comment": comment,
                "grid_number": j,
                "cycle_number": cycle_number,
                "direction": "BUY",
            })
        for j, price in enumerate(sell_prices, 1):
            comment = f"C{cycle_number}_{j}"
            orders.append({
                "symbol": symbol,
                "type": 5,
                "volume": lot_size,
                "price": price,
                "magic": magic,
                "comment": comment,
                "grid_number": j,
                "cycle_number": cycle_number,
                "direction": "SELL",
            })
        return orders

    def build_orders_for_depth(
        self,
        symbol: str,
        magic: int,
        cycle_number: int,
        lot_size: float,
        buy_prices: List[float],
        sell_prices: List[float],
        buy_depth: int,
        sell_depth: int,
        buy_start: int = 1,
        sell_start: int = 1,
    ) -> List[dict]:
        orders = []
        for j in range(max(1, buy_start), min(buy_depth, len(buy_prices)) + 1):
            price = buy_prices[j - 1]
            comment = f"C{cycle_number}_{j}"
            orders.append({
                "symbol": symbol,
                "type": 4,
                "volume": lot_size,
                "price": price,
                "magic": magic,
                "comment": comment,
                "grid_number": j,
                "cycle_number": cycle_number,
                "direction": "BUY",
            })
        for j in range(max(1, sell_start), min(sell_depth, len(sell_prices)) + 1):
            price = sell_prices[j - 1]
            comment = f"C{cycle_number}_{j}"
            orders.append({
                "symbol": symbol,
                "type": 5,
                "volume": lot_size,
                "price": price,
                "magic": magic,
                "comment": comment,
                "grid_number": j,
                "cycle_number": cycle_number,
                "direction": "SELL",
            })
        return orders

    def calculate_initial_depths(
        self,
        target_profit: float,
        commission_per_position: float,
        lot_size: float,
        grid_step: float,
        tick_size: float,
        max_grid_count: int,
        side_bias: int = 0,
    ) -> Tuple[int, int]:
        if max_grid_count <= 0:
            return (0, 0)
        if grid_step <= 0 or lot_size <= 0:
            return (1, 1)

        # Rough profit per one grid move for a single position.
        move_value = abs(grid_step) * lot_size * 100
        if move_value <= 0:
            return (1, 1)

        total_target = max(target_profit + commission_per_position, tick_size * 10)
        estimated_positions = int(total_target / move_value) + 1
        estimated_positions = max(1, min(max_grid_count, estimated_positions))

        if side_bias > 0:
            return (estimated_positions, 1)
        if side_bias < 0:
            return (1, estimated_positions)
        first_side = max(1, estimated_positions // 2)
        second_side = max(1, estimated_positions - first_side)
        return (first_side, second_side)

    def parse_comment(self, comment: str) -> Optional[Tuple[int, int]]:
        try:
            if not comment or not comment.startswith("C"):
                return None
            parts = comment[1:].split("_")
            if len(parts) != 2:
                return None
            cycle = int(parts[0])
            grid = int(parts[1])
            return (cycle, grid)
        except (ValueError, IndexError):
            return None

    def make_comment(self, cycle_number: int, grid_number: int) -> str:
        return f"C{cycle_number}_{grid_number}"
