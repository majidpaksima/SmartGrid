from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from .enums import CycleStatus


@dataclass
class CycleRecord:
    symbol: str
    magic_number: int
    cycle_number: int
    status: CycleStatus = CycleStatus.PENDING
    state: str = "IDLE"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    anchor_price: Optional[float] = None
    atr: Optional[float] = None
    calculated_grid_step: Optional[float] = None
    effective_grid_step: Optional[float] = None
    grid_count: int = 5
    lot_size: float = 0.01
    target_profit: float = 10.0
    commission_per_position: float = 0.14
    trigger_ticket: Optional[int] = None
    target_price: Optional[float] = None
    exit_reason: Optional[str] = None
    gross_profit: Optional[float] = None
    estimated_commission: Optional[float] = None
    realized_profit: Optional[float] = None
    net_profit: Optional[float] = None
    id: Optional[int] = None
