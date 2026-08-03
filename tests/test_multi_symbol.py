import pytest
from models.symbol_context import SymbolContext
from models.enums import SymbolState
from services.symbol_manager import SymbolManager
from config.models import AppConfig, SymbolConfig


class TestMultiSymbol:
    def test_multi_symbol_independence(self):
        config = AppConfig(symbols=[
            SymbolConfig(name="XAUUSD", magic_number=710001, enabled=True),
            SymbolConfig(name="EURUSD", magic_number=710002, enabled=True),
            SymbolConfig(name="GBPUSD", magic_number=710003, enabled=False),
        ])
        manager = SymbolManager()
        manager.initialize_from_config(config)
        contexts = manager.get_all_contexts()
        assert len(contexts) == 3
        xau = manager.get_context("XAUUSD")
        eur = manager.get_context("EURUSD")
        assert xau is not None
        assert eur is not None
        assert xau.magic_number == 710001
        assert eur.magic_number == 710002
        xau.state = SymbolState.ERROR
        assert eur.state == SymbolState.IDLE
        active = manager.get_active_contexts()
        assert len(active) == 2

    def test_symbol_independent_cycle_numbers(self):
        config = AppConfig(symbols=[
            SymbolConfig(name="XAUUSD", magic_number=710001),
            SymbolConfig(name="EURUSD", magic_number=710002),
        ])
        manager = SymbolManager()
        manager.initialize_from_config(config)
        xau = manager.get_context("XAUUSD")
        eur = manager.get_context("EURUSD")
        xau.cycle_number = 5
        eur.cycle_number = 12
        assert xau.cycle_number != eur.cycle_number

    def test_symbol_independent_magic_numbers(self):
        config = AppConfig(symbols=[
            SymbolConfig(name="XAUUSD", magic_number=710001),
            SymbolConfig(name="EURUSD", magic_number=710002),
        ])
        manager = SymbolManager()
        manager.initialize_from_config(config)
        xau = manager.get_context("XAUUSD")
        eur = manager.get_context("EURUSD")
        assert xau.magic_number != eur.magic_number
