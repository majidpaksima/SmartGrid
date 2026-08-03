import pytest
from unittest.mock import MagicMock
from models.symbol_context import SymbolContext
from models.enums import SymbolState
from config.models import SymbolConfig, ApplicationSettings
from strategy.cycle_manager import CycleManager
from strategy.atr import ATRCalculator
from strategy.grid_builder import GridBuilder
from strategy.target_calculator import TargetCalculator
from strategy.basket_manager import BasketManager
from mt5_client.market_data import MarketData
from mt5_client.order_service import OrderService
from mt5_client.position_service import PositionService
from mt5_client.history_service import HistoryService


@pytest.fixture
def cycle_manager():
    return CycleManager(
        app_settings=ApplicationSettings(dry_run=True),
        market_data=MagicMock(spec=MarketData),
        order_service=MagicMock(spec=OrderService),
        position_service=MagicMock(spec=PositionService),
        history_service=MagicMock(spec=HistoryService),
        atr_calc=MagicMock(spec=ATRCalculator),
        grid_builder=GridBuilder(),
        target_calc=MagicMock(spec=TargetCalculator),
        basket_manager=BasketManager(),
    )


class TestCycleManager:
    def test_comment_generation_and_parsing(self):
        builder = GridBuilder()
        comment = builder.make_comment(1, 5)
        assert comment == "C1_5"
        parsed = builder.parse_comment(comment)
        assert parsed == (1, 5)

    def test_comment_parsing_roundtrip(self):
        builder = GridBuilder()
        for cycle in [1, 12, 100]:
            for grid in [1, 5, 10]:
                comment = builder.make_comment(cycle, grid)
                parsed = builder.parse_comment(comment)
                assert parsed == (cycle, grid)

    def test_state_transitions_to_preparing(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sm = cycle_manager.get_state_machine("XAUUSD")
        assert sm.state == SymbolState.IDLE
        cycle_manager.process_symbol(ctx, sc, dry_run=True)
        assert sm.state == SymbolState.PREPARING

    def test_all_grids_filled_detection(self):
        basket = BasketManager()
        positions = []
        for i in range(5):
            positions.append({"type": 0, "volume": 0.01, "comment": f"C1_{i+1}"})
        for i in range(5):
            positions.append({"type": 1, "volume": 0.01, "comment": f"C1_{i+1}"})
        assert basket.is_locked_exposure(positions) == True

    def test_locked_exposure_detection(self):
        basket = BasketManager()
        positions = [
            {"type": 0, "volume": 0.05},
            {"type": 1, "volume": 0.05},
        ]
        assert basket.is_locked_exposure(positions) == True
        positions2 = [
            {"type": 0, "volume": 0.05},
            {"type": 1, "volume": 0.03},
        ]
        assert basket.is_locked_exposure(positions2) == False

    def test_trigger_selection_buy(self):
        basket = BasketManager()
        positions = [
            {"type": 0, "volume": 0.01, "ticket": 1001, "time": 200},
            {"type": 0, "volume": 0.01, "ticket": 1002, "time": 100},
            {"type": 1, "volume": 0.01, "ticket": 2001, "time": 150},
        ]
        trigger = basket.select_trigger_position(positions)
        assert trigger is not None
        assert trigger["type"] == 0
        assert trigger["time"] == 100

    def test_trigger_selection_sell(self):
        basket = BasketManager()
        positions = [
            {"type": 0, "volume": 0.01, "ticket": 1001, "time": 100},
            {"type": 1, "volume": 0.01, "ticket": 2001, "time": 50},
            {"type": 1, "volume": 0.01, "ticket": 2002, "time": 75},
        ]
        trigger = basket.select_trigger_position(positions)
        assert trigger is not None
        assert trigger["type"] == 1

    def test_trigger_selection_equal_volume(self):
        basket = BasketManager()
        positions = [
            {"type": 0, "volume": 0.05, "ticket": 1001, "time": 100},
            {"type": 1, "volume": 0.05, "ticket": 2001, "time": 100},
        ]
        trigger = basket.select_trigger_position(positions)
        assert trigger is None

    def test_grow_grid_depth_uses_mixed_exposure(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.lot_size = 0.01
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.placed_buy_depth = 2
        sc.placed_sell_depth = 2
        cycle_manager.position_service.get_open_positions.return_value = [
            {"type": 0, "volume": 0.01, "ticket": 1, "time": 1, "price_open": 4001.0, "profit": 0.0},
            {"type": 0, "volume": 0.01, "ticket": 2, "time": 2, "price_open": 4002.0, "profit": 0.0},
            {"type": 1, "volume": 0.01, "ticket": 3, "time": 3, "price_open": 3999.0, "profit": 0.0},
        ]
        cycle_manager._grow_grid_depth_if_needed(ctx, sc, dry_run=True)
        # Mixed exposure (2 buy + 1 sell) must not shrink below what was placed,
        # and must stay within the final cap.
        assert sc.placed_buy_depth >= 2
        assert sc.placed_sell_depth >= 2
        assert sc.placed_buy_depth <= ctx.grid_count
        assert sc.placed_sell_depth <= ctx.grid_count
