from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from .enums import SymbolState


@dataclass
class SymbolContext:
    name: str
    magic_number: int
    state: SymbolState = SymbolState.IDLE
    cycle_number: int = 0
    anchor_price: Optional[float] = None
    atr: Optional[float] = None
    calculated_grid_step: Optional[float] = None
    effective_grid_step: Optional[float] = None
    grid_count: int = 5
    lot_size: float = 0.01
    commission_per_position: float = 0.14
    target_profit: float = 10.0
    atr_timeframe: str = "M5"
    atr_period: int = 14
    active_order_tickets: list = field(default_factory=list)
    active_position_tickets: list = field(default_factory=list)
    buy_count: int = 0
    sell_count: int = 0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    target_price: Optional[float] = None
    trigger_ticket: Optional[int] = None
    cycle_start_time: Optional[datetime] = None
    last_error: Optional[str] = None
    last_event: str = ""
    digits: int = 5
    tick_size: float = 0.00001
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    contract_size: int = 100
    trade_stops_level: int = 0
    trade_freeze_level: int = 0
    dry_run: bool = False
    atr_ok: bool = True
