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
