from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional
from models.enums import ConsoleMode, ShutdownMode


class SymbolConfig(BaseModel):
    name: str
    enabled: bool = True
    grid_count: int = Field(default=5, ge=1, le=100)
    lot_size: float = Field(default=0.01, gt=0)
    atr_timeframe: str = "M5"
    atr_period: int = Field(default=14, ge=2)
    commission_per_position: float = Field(default=0.0, ge=0)
    target_profit: float = Field(default=10.0, gt=0)
    magic_number: int = Field(default=710001, gt=0)
    atr_filter_enabled: bool = True
    atr_lookback: int = Field(default=200, ge=10, le=10000)
    atr_slope_period: int = Field(default=5, ge=2, le=100)

    @field_validator("atr_timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        valid = {"M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20", "M30",
                 "H1", "H2", "H3", "H4", "H6", "H8", "H12",
                 "D1", "W1", "MN1"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid timeframe: {v}. Must be one of {valid}")
        return v.upper()


class MT5Config(BaseModel):
    terminal_path: Optional[str] = None
    login: Optional[int] = None
    server: Optional[str] = None
    password: Optional[str] = None
    deviation_points: int = 20
    request_timeout_seconds: int = 10


class ApplicationSettings(BaseModel):
    polling_interval_seconds: float = 0.25
    dashboard_refresh_seconds: float = 1.0
    restart_delay_seconds: float = 2.0
    close_retry_count: int = 5
    order_retry_count: int = 3
    history_lookback_days: int = 7
    dry_run: bool = False
    console_mode: str = "rich"
    log_level: str = "INFO"
    shutdown_mode: str = "leave_open"


class AppConfig(BaseModel):
    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    mt5: MT5Config = Field(default_factory=MT5Config)
    symbols: List[SymbolConfig] = []

    @model_validator(mode="after")
    def validate_magic_numbers(self):
        magics = []
        for sym in self.symbols:
            if sym.enabled:
                if sym.magic_number in magics:
                    raise ValueError(
                        f"Duplicate magic number {sym.magic_number} "
                        f"found for symbol {sym.name}. "
                        f"Each enabled symbol must have a unique magic number."
                    )
                magics.append(sym.magic_number)
        return self

    @model_validator(mode="after")
    def validate_mt5_timeout(self):
        if self.mt5.request_timeout_seconds < 1:
            raise ValueError("MT5 request timeout must be at least 1 second.")
        return self
