from pathlib import Path
from typing import Optional
from .models import AppConfig, SymbolConfig
from .loader import load_config, save_config


DEFAULT_USER_DEFAULTS_PATH = "data/user_defaults.yaml"


class DefaultsManager:
    def __init__(self, defaults_path: str = DEFAULT_USER_DEFAULTS_PATH):
        self.defaults_path = defaults_path

    def exists(self) -> bool:
        return Path(self.defaults_path).exists()

    def load(self) -> Optional[AppConfig]:
        return load_config(self.defaults_path)

    def save(self, config: AppConfig):
        save_config(config, self.defaults_path)

    def delete(self):
        p = Path(self.defaults_path)
        if p.exists():
            p.unlink()

    def get_enabled_symbols(self, config: AppConfig) -> list:
        return [s for s in config.symbols if s.enabled]
