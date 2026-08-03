import pytest
from strategy.target_calculator import TargetCalculator


class TestTargetCalculator:
    def setup_method(self):
        self.calc = TargetCalculator()

    def test_five_buy_target(self):
        positions = []
        for i in range(5):
            positions.append({
                "type": 0,
                "volume": 0.01,
                "price_open": 4001.0 + i,
                "ticket": 1000 + i,
                "time": 1000000 + i,
            })
        target = self.calc._estimate_target_simple(
            positions, 10.70, 0.05, 4005.0, 0.01
        )
        assert target is not None

    def test_five_sell_target(self):
        positions = []
        for i in range(5):
            positions.append({
                "type": 1,
                "volume": 0.01,
                "price_open": 3999.0 - i,
                "ticket": 2000 + i,
                "time": 1000000 + i,
            })
        target = self.calc._estimate_target_simple(
            positions, 10.70, -0.05, 3995.0, 0.01
        )
        assert target is not None

    def test_equal_volume_returns_none(self):
        positions = [
            {"type": 0, "volume": 0.05, "price_open": 4001.0, "ticket": 1, "time": 1},
            {"type": 1, "volume": 0.05, "price_open": 3999.0, "ticket": 2, "time": 1},
        ]
        target = self.calc.calculate_basket_target(
            positions, 0.14, 10.0, "XAUUSD", 0.01, 4000.0
        )
        assert target is None

    def test_five_buy_one_sell_target(self):
        positions = []
        for i in range(5):
            positions.append({
                "type": 0,
                "volume": 0.01,
                "price_open": 4001.0 + i,
                "ticket": 1000 + i,
                "time": 1000000 + i,
            })
        positions.append({
            "type": 1,
            "volume": 0.01,
            "price_open": 3999.0,
            "ticket": 2000,
            "time": 1000000,
        })
        target = self.calc.calculate_basket_target(
            positions, 0.14, 10.0, "XAUUSD", 0.01, 4005.0
        )
        assert target is not None

    def test_five_sell_one_buy_target(self):
        positions = []
        for i in range(5):
            positions.append({
                "type": 1,
                "volume": 0.01,
                "price_open": 3999.0 - i,
                "ticket": 2000 + i,
                "time": 1000000 + i,
            })
        positions.append({
            "type": 0,
            "volume": 0.01,
            "price_open": 4001.0,
            "ticket": 1000,
            "time": 1000000,
        })
        target = self.calc.calculate_basket_target(
            positions, 0.14, 10.0, "XAUUSD", 0.01, 3995.0
        )
        assert target is not None

    def test_empty_positions_returns_none(self):
        target = self.calc.calculate_basket_target([], 0.14, 10.0, "XAUUSD", 0.01, 4000.0)
        assert target is None
