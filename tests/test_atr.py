import pytest
from strategy.atr import ATRCalculator


class TestATR:
    def test_calculate_from_rates_valid(self):
        calc = ATRCalculator()
        rates = []
        for i in range(20):
            rates.append({
                "high": 100.0 + i * 0.1,
                "low": 99.0 + i * 0.1,
                "close": 99.5 + i * 0.1,
            })
        atr = calc.calculate_from_rates(rates, period=14)
        assert atr is not None
        assert atr > 0

    def test_calculate_from_rates_insufficient_data(self):
        calc = ATRCalculator()
        rates = [{"high": 100, "low": 99, "close": 99.5}]
        atr = calc.calculate_from_rates(rates, period=14)
        assert atr is None

    def test_calculate_from_rates_empty(self):
        calc = ATRCalculator()
        assert calc.calculate_from_rates([], period=14) is None

    def test_calculate_from_rates_uses_closed_candles(self):
        calc = ATRCalculator()
        rates = []
        for i in range(20):
            rates.append({
                "high": 100.0 + 0.5 * (i % 3),
                "low": 99.0 + 0.5 * (i % 3),
                "close": 99.5 + 0.5 * (i % 3),
            })
        atr = calc.calculate_from_rates(rates, period=14)
        assert atr is not None
        assert atr > 0
