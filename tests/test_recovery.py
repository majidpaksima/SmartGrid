import pytest
from unittest.mock import MagicMock
from models.symbol_context import SymbolContext
from models.enums import SymbolState
from services.recovery_service import RecoveryService
from strategy.grid_builder import GridBuilder
from strategy.basket_manager import BasketManager
from mt5_client.order_service import OrderService
from mt5_client.position_service import PositionService


class TestRecovery:
    @pytest.fixture
    def recovery_service(self):
        return RecoveryService(
            grid_builder=GridBuilder(),
            basket_manager=BasketManager(),
            order_service=MagicMock(spec=OrderService),
            position_service=MagicMock(spec=PositionService),
        )

    def test_no_active_cycle(self, recovery_service):
        recovery_service.order_service.get_open_orders.return_value = []
        recovery_service.position_service.get_open_positions.return_value = []
        ctx = SymbolContext(name="XAUUSD", magic_number=710001)
        recovery_service._recover_single(ctx)
        assert ctx.state == SymbolState.IDLE

    def test_single_active_cycle(self, recovery_service):
        recovery_service.order_service.get_open_orders.return_value = [
            {"ticket": 1, "comment": "C1_1", "type": 2, "volume": 0.01, "price_open": 4001.0,
             "symbol": "XAUUSD", "magic": 710001, "state": 1},
        ]
        recovery_service.position_service.get_open_positions.return_value = []
        ctx = SymbolContext(name="XAUUSD", magic_number=710001)
        recovery_service._recover_single(ctx)
        assert ctx.state == SymbolState.GRID_ACTIVE
        assert ctx.active_order_tickets == [1]

    def test_duplicate_cycle_detected(self, recovery_service):
        recovery_service.order_service.get_open_orders.return_value = [
            {"ticket": 1, "comment": "C1_1", "type": 2, "volume": 0.01, "price_open": 4001.0,
             "symbol": "XAUUSD", "magic": 710001, "state": 1},
        ]
        recovery_service.position_service.get_open_positions.return_value = [
            {"ticket": 2, "comment": "C2_1", "type": 0, "volume": 0.01, "price_open": 4001.0,
             "symbol": "XAUUSD", "magic": 710001, "profit": 0.0, "time": 1},
        ]
        ctx = SymbolContext(name="XAUUSD", magic_number=710001)
        recovery_service._recover_single(ctx)
        assert ctx.state == SymbolState.POSITIONS_ACTIVE
        assert ctx.active_order_tickets == [1]
        assert ctx.active_position_tickets == [2]

    def test_startup_recovery_close(self, recovery_service):
        recovery_service.order_service.get_open_orders.return_value = []
        recovery_service.position_service.get_open_positions.return_value = [
            {"ticket": 1, "comment": "C1_3", "type": 0, "volume": 0.01, "price_open": 4003.0,
             "symbol": "XAUUSD", "magic": 710001, "profit": 0.0, "time": 1},
        ]
        ctx = SymbolContext(name="XAUUSD", magic_number=710001)
        recovery_service._recover_single(ctx)
        assert ctx.state == SymbolState.POSITIONS_ACTIVE
