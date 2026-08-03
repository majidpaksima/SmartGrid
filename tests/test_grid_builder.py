import pytest
from strategy.grid_builder import GridBuilder


class TestGridBuilder:
    def setup_method(self):
        self.builder = GridBuilder()

    def test_grid_step_calculation(self):
        _, step, _, _ = self.builder.build_grid_prices(
            anchor_price=4000.0, atr=5.0, grid_count=5,
            tick_size=0.00001, trade_stops_level=0
        )
        assert abs(step - 1.0) < 0.01

    def test_buy_stop_generation(self):
        _, _, buy_prices, _ = self.builder.build_grid_prices(
            anchor_price=4000.0, atr=5.0, grid_count=5,
            tick_size=0.01, trade_stops_level=0
        )
        assert len(buy_prices) == 5
        expected = [4001.0, 4002.0, 4003.0, 4004.0, 4005.0]
        for j, (actual, exp) in enumerate(zip(buy_prices, expected), 1):
            assert abs(actual - exp) < 0.02, f"Buy {j}: expected {exp}, got {actual}"

    def test_sell_stop_generation(self):
        _, _, _, sell_prices = self.builder.build_grid_prices(
            anchor_price=4000.0, atr=5.0, grid_count=5,
            tick_size=0.01, trade_stops_level=0
        )
        assert len(sell_prices) == 5
        expected = [3999.0, 3998.0, 3997.0, 3996.0, 3995.0]
        for j, (actual, exp) in enumerate(zip(sell_prices, expected), 1):
            assert abs(actual - exp) < 0.02, f"Sell {j}: expected {exp}, got {actual}"

    def test_tick_size_normalization(self):
        _, _, buy_prices, sell_prices = self.builder.build_grid_prices(
            anchor_price=4000.0, atr=5.0, grid_count=5,
            tick_size=0.01, trade_stops_level=0
        )
        for price in buy_prices:
            assert abs(round(price / 0.01) * 0.01 - price) < 1e-10
        for price in sell_prices:
            assert abs(round(price / 0.01) * 0.01 - price) < 1e-10

    def test_broker_stop_distance_adjustment(self):
        _, step, _, _ = self.builder.build_grid_prices(
            anchor_price=4000.0, atr=5.0, grid_count=5,
            tick_size=0.01, trade_stops_level=200
        )
        assert step >= 2.01

    def test_comment_generation(self):
        comment = self.builder.make_comment(cycle_number=1, grid_number=3)
        assert comment == "C1_3"

    def test_comment_parsing(self):
        result = self.builder.parse_comment("C12_5")
        assert result is not None
        assert result[0] == 12
        assert result[1] == 5

    def test_comment_parsing_invalid(self):
        assert self.builder.parse_comment("") is None
        assert self.builder.parse_comment("INVALID") is None
        assert self.builder.parse_comment("C1") is None

    def test_grid_count_respected(self):
        for count in [1, 3, 10]:
            _, _, buy_prices, sell_prices = self.builder.build_grid_prices(
                anchor_price=4000.0, atr=5.0, grid_count=count,
                tick_size=0.01, trade_stops_level=0
            )
            assert len(buy_prices) == count
            assert len(sell_prices) == count

    def test_initial_depth_stays_within_cap(self):
        buy_depth, sell_depth = self.builder.calculate_initial_depths(
            target_profit=10.0,
            commission_per_position=0.14,
            lot_size=0.01,
            grid_step=1.0,
            tick_size=0.01,
            max_grid_count=10,
        )
        assert 1 <= buy_depth <= 10
        assert 1 <= sell_depth <= 10
        assert buy_depth == sell_depth

    def test_initial_depth_scales_with_target(self):
        low = self.builder.calculate_initial_depths(
            target_profit=2.0, commission_per_position=0.0, lot_size=0.01,
            grid_step=1.0, tick_size=0.01, max_grid_count=10,
        )
        high = self.builder.calculate_initial_depths(
            target_profit=50.0, commission_per_position=0.0, lot_size=0.01,
            grid_step=1.0, tick_size=0.01, max_grid_count=10,
        )
        assert high[0] >= low[0]

    def test_needed_depth_solves_quadratic(self):
        # For one-directional 0.01 lot on XAUUSD, grid step 1.0:
        # profit at level N after a move is sum_{k=1}^{N} k*1*0.01*100 = N(N+1)/2
        depth = self.builder._solve_needed_depth(
            target_profit=10.0, commission_per_position=0.0,
            lot_size=0.01, grid_step=1.0, tick_size=0.01, max_grid_count=10,
        )
        for k in range(1, depth):
            assert k * (k + 1) / 2.0 * 1.0 < 10.0 + 1e-9
        assert depth * (depth + 1) / 2.0 * 1.0 >= 10.0 - 1e-9
        assert 1 <= depth <= 10

    def test_needed_depth_uses_commission(self):
        with_comm = self.builder._solve_needed_depth(
            target_profit=10.0, commission_per_position=0.14,
            lot_size=0.01, grid_step=1.0, tick_size=0.01, max_grid_count=10,
        )
        without_comm = self.builder._solve_needed_depth(
            target_profit=10.0, commission_per_position=0.0,
            lot_size=0.01, grid_step=1.0, tick_size=0.01, max_grid_count=10,
        )
        assert with_comm >= without_comm

    def test_estimate_needed_depths_mixed_sides(self):
        positions = [
            {"type": 0, "volume": 0.01, "ticket": 1, "time": 1},
            {"type": 0, "volume": 0.01, "ticket": 2, "time": 2},
            {"type": 0, "volume": 0.01, "ticket": 3, "time": 3},
            {"type": 1, "volume": 0.01, "ticket": 4, "time": 4},
        ]
        buy_depth, sell_depth = self.builder.estimate_needed_depths(
            positions,
            target_profit=10.0,
            commission_per_position=0.14,
            lot_size=0.01,
            grid_step=1.0,
            tick_size=0.01,
            max_grid_count=10,
        )
        # 3 buy + 1 sell: buy side must carry more depth than sell side.
        assert buy_depth >= sell_depth
        assert buy_depth <= 10
        assert sell_depth <= 10

    def test_build_orders_for_depth_uses_range(self):
        buy_prices = [4001.0, 4002.0, 4003.0, 4004.0]
        sell_prices = [3999.0, 3998.0, 3997.0, 3996.0]
        orders = self.builder.build_orders_for_depth(
            symbol="XAUUSD",
            magic=710001,
            cycle_number=1,
            lot_size=0.01,
            buy_prices=buy_prices,
            sell_prices=sell_prices,
            buy_depth=3,
            sell_depth=2,
            buy_start=2,
            sell_start=1,
        )
        assert [o["grid_number"] for o in orders if o["direction"] == "BUY"] == [2, 3]
        assert [o["grid_number"] for o in orders if o["direction"] == "SELL"] == [1, 2]
