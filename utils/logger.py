import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class Logger:
    _instance = None
    _console_enabled = True

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, log_dir: str = "logs", level: str = "INFO", console_enabled: bool = True):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.text_log_path = self.log_dir / "grid_decisions.txt"
        self.logger = logging.getLogger("SmartGridBot")
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self.logger.handlers.clear()
        file_handler = RotatingFileHandler(
            self.log_dir / "trading.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        Logger._console_enabled = console_enabled

    def _format(self, **fields) -> str:
        parts = []
        for k, v in fields.items():
            if v is not None:
                parts.append(f"{k}={v}")
        return " | ".join(parts)

    def _compose(self, message: str, fields: dict) -> str:
        msg = self._format(**fields) if fields else message
        if fields and message:
            msg = f"{message} | {msg}"
        return msg

    def info(self, message: str = "", **fields):
        msg = self._compose(message, fields)
        self.logger.info(msg)
        if Logger._console_enabled:
            print(f"[INFO] {msg}")

    def warning(self, message: str = "", **fields):
        msg = self._compose(message, fields)
        self.logger.warning(msg)
        if Logger._console_enabled:
            print(f"[WARN] {msg}")

    def error(self, message: str = "", **fields):
        msg = self._compose(message, fields)
        self.logger.error(msg)
        if Logger._console_enabled:
            print(f"[ERROR] {msg}")

    def debug(self, message: str = "", **fields):
        msg = self._compose(message, fields)
        self.logger.debug(msg)

    def critical(self, message: str = "", **fields):
        msg = self._compose(message, fields)
        self.logger.critical(msg)
        if Logger._console_enabled:
            print(f"[CRITICAL] {msg}")

    def text(self, message: str = "", **fields):
        msg = self._format(**fields) if fields else message
        with self.text_log_path.open("a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
