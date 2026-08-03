from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from .enums import OrderStatus


@dataclass
class GridOrderRecord:
    ticket: int
    symbol: str
    magic_number: int
    cycle_number: int
    grid_number: int
    order_type: int
    requested_price: float
    executed_price: Optional[float] = None
    volume: float = 0.0
    comment: str = ""
    status: OrderStatus = OrderStatus.REQUESTED
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
