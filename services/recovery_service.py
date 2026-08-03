from typing import Dict, List, Optional, Tuple
from models.symbol_context import SymbolContext
from models.enums import SymbolState
from strategy.grid_builder import GridBuilder
from strategy.basket_manager import BasketManager
from mt5_client.order_service import OrderService
from mt5_client.position_service import PositionService
from utils.logger import Logger


class RecoveryService:
    def __init__(
        self,
        grid_builder: GridBuilder,
        basket_manager: BasketManager,
        order_service: OrderService,
        position_service: PositionService,
    ):
        self.grid_builder = grid_builder
        self.basket_manager = basket_manager
        self.order_service = order_service
        self.position_service = position_service
        self.logger = Logger()

    def recover_contexts(self, contexts: List[SymbolContext]) -> List[SymbolContext]:
        recovered = []
        for ctx in contexts:
            result = self._recover_single(ctx)
            if result:
                recovered.append(result)
        return recovered

    def _recover_single(self, ctx: SymbolContext) -> Optional[SymbolContext]:
        orders = self.order_service.get_open_orders(ctx.name, ctx.magic_number)
        positions = self.position_service.get_open_positions(ctx.name, ctx.magic_number)
        if not orders and not positions:
            self.logger.info("No active cycle to recover", symbol=ctx.name)
            ctx.state = SymbolState.IDLE
            return ctx
        ctx.active_order_tickets = [o["ticket"] for o in orders]
        ctx.active_position_tickets = [p["ticket"] for p in positions]
        self._update_exposure_from_positions(ctx, positions)
        if positions:
            ctx.state = SymbolState.POSITIONS_ACTIVE
            self.logger.info("Recovered to POSITIONS_ACTIVE",
                             symbol=ctx.name,
                             positions=len(positions))
        else:
            ctx.state = SymbolState.GRID_ACTIVE
            self.logger.info("Recovered to GRID_ACTIVE",
                             symbol=ctx.name,
                             orders=len(orders))
        ctx.last_event = "Recovered from startup"
        self.logger.info("Cycle recovered", symbol=ctx.name, state=ctx.state.value)
        return ctx

    def _update_exposure_from_positions(self, ctx: SymbolContext, positions: List[dict]):
        buy_vol = sum(p["volume"] for p in positions if p["type"] == 0)
        sell_vol = sum(p["volume"] for p in positions if p["type"] == 1)
        ctx.buy_volume = buy_vol
        ctx.sell_volume = sell_vol
        ctx.buy_count = sum(1 for p in positions if p["type"] == 0)
        ctx.sell_count = sum(1 for p in positions if p["type"] == 1)
