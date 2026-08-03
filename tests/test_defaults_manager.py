import pytest
from config.defaults_manager import DefaultsManager
from config.models import AppConfig, SymbolConfig
from config.loader import load_config


class TestDefaultsManager:
    def test_save_and_load(self, tmp_path):
        dm = DefaultsManager(str(tmp_path / "user_defaults.yaml"))
        config = AppConfig(symbols=[SymbolConfig(name="XAUUSD", magic_number=710001)])
        dm.save(config)
        loaded = dm.load()
        assert loaded is not None
        assert loaded.symbols[0].name == "XAUUSD"
        assert loaded.symbols[0].magic_number == 710001

    def test_exists(self, tmp_path):
        dm = DefaultsManager(str(tmp_path / "user_defaults.yaml"))
        assert not dm.exists()
        config = AppConfig(symbols=[SymbolConfig(name="XAUUSD", magic_number=710001)])
        dm.save(config)
        assert dm.exists()

    def test_delete(self, tmp_path):
        dm = DefaultsManager(str(tmp_path / "user_defaults.yaml"))
        config = AppConfig(symbols=[SymbolConfig(name="XAUUSD", magic_number=710001)])
        dm.save(config)
        assert dm.exists()
        dm.delete()
        assert not dm.exists()

    def test_get_enabled_symbols(self, tmp_path):
        dm = DefaultsManager(str(tmp_path / "user_defaults.yaml"))
        config = AppConfig(symbols=[
            SymbolConfig(name="XAUUSD", magic_number=710001, enabled=True),
            SymbolConfig(name="EURUSD", magic_number=710002, enabled=False),
        ])
        enabled = dm.get_enabled_symbols(config)
        assert len(enabled) == 1
        assert enabled[0].name == "XAUUSD"
