from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AccountSnapshot:
    login: int = 0
    server: str = ""
    currency: str = "USD"
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    margin_level: Optional[float] = None
    total_floating_gross_pnl: float = 0.0
    estimated_total_commission: float = 0.0
    estimated_net_pnl: float = 0.0
    realized_pnl_since_start: float = 0.0
    active_symbol_count: int = 0
    open_position_count: int = 0
    pending_order_count: int = 0
    bot_start_time: Optional[datetime] = None
    runtime_seconds: float = 0.0
    mode: str = "DRY RUN"
    connected: bool = False
    is_hedging: bool = True
