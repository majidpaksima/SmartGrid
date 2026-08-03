from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AccountTableData:
    server: str = ""
    login: int = 0
    currency: str = "USD"
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    margin_level: Optional[float] = None
    floating_gross_pnl: float = 0.0
    estimated_commission: float = 0.0
    estimated_net_pnl: float = 0.0
    realized_pnl: float = 0.0
    active_symbols: int = 0
    open_positions: int = 0
    pending_orders: int = 0
    runtime: str = "00:00:00"
    mode: str = "DRY RUN"
    connected: bool = False


@dataclass
class SymbolTableData:
    symbol: str = ""
    state: str = "IDLE"
    cycle: int = 0
    bid: str = "-"
    ask: str = "-"
    anchor: str = "-"
    atr: str = "-"
    grid_step: str = "-"
    buy_pos: int = 0
    sell_pos: int = 0
    pending_buy: int = 0
    pending_sell: int = 0
    gross_pnl: str = "-"
    commission: str = "-"
    net_pnl: str = "-"
    target_profit: str = "-"
    target_price: str = "-"
    trigger_ticket: str = "-"
    last_event: str = ""
    last_error: str = ""
