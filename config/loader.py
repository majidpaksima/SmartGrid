import yaml
from pathlib import Path
from typing import Optional
from .models import AppConfig


def load_config(path: str) -> Optional[AppConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return None
    return AppConfig(**data)


def save_config(config: AppConfig, path: str):
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump()
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=False)


def config_to_yaml(config: AppConfig) -> str:
    data = config.model_dump()
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=False)
