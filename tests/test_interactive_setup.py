import pytest
from unittest.mock import patch, MagicMock
from config.interactive_setup import InteractiveSetup
from config.defaults_manager import DefaultsManager
from config.models import AppConfig, SymbolConfig


class TestInteractiveSetup:
    @patch("builtins.input", side_effect=["Y", "1", "5", "0.01", "M5", "14", "n", "0.14", "10.00", "710001", "Y"])
    def test_first_run_wizard_creates_defaults(self, mock_input, tmp_path):
        dm = DefaultsManager(str(tmp_path / "user_defaults.yaml"))
        setup = InteractiveSetup()
        setup._get_available_symbols = MagicMock(return_value={
            "XAUUSD": {"digits": 5, "tick_size": 0.00001, "contract_size": 100,
                       "volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                       "trade_stops_level": 0},
        })
        result = setup.run_wizard(dm)
        assert result is not None
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "XAUUSD"
        assert dm.exists()

    def test_later_run_loads_saved_defaults(self, tmp_path):
        dm = DefaultsManager(str(tmp_path / "user_defaults.yaml"))
        config = AppConfig(symbols=[SymbolConfig(name="XAUUSD", magic_number=710001)])
        dm.save(config)
        assert dm.exists()
        loaded = dm.load()
        assert loaded is not None
        assert len(loaded.symbols) == 1
        assert loaded.symbols[0].name == "XAUUSD"

    def test_invalid_symbol_rejected(self):
        setup = InteractiveSetup()
        available = {"XAUUSD": {}, "EURUSD": {}}
        with patch("builtins.input", return_value="BADSYMBOL"):
            selected = setup._select_symbols(available)
            assert "BADSYMBOL" not in selected

    def test_duplicate_magic_rejected(self):
        from config.models import AppConfig, SymbolConfig
        with pytest.raises(ValueError) as exc:
            AppConfig(symbols=[
                SymbolConfig(name="XAUUSD", magic_number=710001),
                SymbolConfig(name="EURUSD", magic_number=710001),
            ])
        assert "duplicate magic number" in str(exc.value).lower()
