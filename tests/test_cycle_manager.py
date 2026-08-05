import sys
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
        sc.anchor_price = 4000.0
        sc.contract_size = 100
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0, 4004.0, 4005.0, 4006.0, 4007.0, 4008.0, 4009.0, 4010.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0, 3996.0, 3995.0, 3994.0, 3993.0, 3992.0, 3991.0, 3990.0]
        sc.placed_buy_depth = 2
        sc.placed_sell_depth = 2
        cycle_manager.grid_builder.estimate_needed_depths = MagicMock(return_value=(7, 2))
        cycle_manager.position_service.get_open_positions.return_value = [
            {"type": 0, "volume": 0.01, "ticket": 1, "time": 1, "price_open": 4001.0, "profit": 0.0},
            {"type": 0, "volume": 0.01, "ticket": 2, "time": 2, "price_open": 4002.0, "profit": 0.0},
            {"type": 1, "volume": 0.01, "ticket": 3, "time": 3, "price_open": 3999.0, "profit": 0.0},
        ]
        cycle_manager._grow_grid_depth_if_needed(ctx, sc, dry_run=True)
        # Only the dominant side should grow.
        assert sc.placed_buy_depth == 7
        assert sc.placed_sell_depth == 2
        assert sc.placed_buy_depth <= ctx.grid_count
        assert sc.placed_sell_depth <= ctx.grid_count

    def test_keep_target_on_grid_grows_buy_side(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0, 4004.0, 4005.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0, 3996.0, 3995.0]
        sc.placed_buy_depth = 2
        sc.placed_sell_depth = 2
        sc.buy_volume = 0.03
        sc.sell_volume = 0.01
        target = cycle_manager._keep_target_on_grid(ctx, sc, 4002.5, dry_run=True)
        # Buy grid grows to cover the level hosting the target (one beyond).
        assert sc.placed_buy_depth == 4
        assert sc.placed_sell_depth == 2
        assert target == 4002.5

    def test_keep_target_on_grid_clamps_beyond_grid(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=5)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0, 4004.0, 4005.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0, 3996.0, 3995.0]
        sc.placed_buy_depth = 2
        sc.placed_sell_depth = 2
        sc.buy_volume = 0.03
        sc.sell_volume = 0.01
        target = cycle_manager._keep_target_on_grid(ctx, sc, 4010.0, dry_run=True)
        # Target beyond the grid is clamped to the last planted buy level.
        assert target == 4005.0
        assert sc.placed_buy_depth == 5

    def _patch_mt5(self, monkeypatch):
        sent = []

        class FakeResult:
            retcode = 10009
            comment = "done"

        class FakeMT5:
            @staticmethod
            def order_send(request):
                sent.append(dict(request))
                return FakeResult()

        monkeypatch.setitem(sys.modules, "MetaTrader5", FakeMT5())
        return sent

    def test_set_basket_targets_local_tp_for_position_beyond_target(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sent = self._patch_mt5(monkeypatch)
        positions = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4005.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager._set_basket_targets(ctx, sc, positions, 4003.0)
        buy_tps = {r["position"]: r["tp"] for r in sent if "tp" in r}
        # Position beyond target (entry 4005 > target 4003) gets local TP entry+step.
        assert abs(buy_tps[1] - 4006.0) < 1e-9
        # Position within target keeps the shared basket TP.
        assert abs(buy_tps[2] - 4003.0) < 1e-9

    def test_set_basket_targets_sell_mirror(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sent = self._patch_mt5(monkeypatch)
        positions = [
            {"ticket": 1, "type": 1, "volume": 0.02, "price_open": 3995.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 1, "volume": 0.02, "price_open": 3999.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager._set_basket_targets(ctx, sc, positions, 3997.0)
        sell_tps = {r["position"]: r["tp"] for r in sent if "tp" in r}
        # Position beyond target (entry 3995 < target 3997) gets local TP entry-step.
        assert abs(sell_tps[1] - 3994.0) < 1e-9
        # Position within target keeps the shared basket TP.
        assert abs(sell_tps[2] - 3997.0) < 1e-9

    def test_set_basket_targets_opposite_sl_never_behind(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sent = self._patch_mt5(monkeypatch)
        # Sell-dominant basket; a buy hedge sits above the basket target.
        positions = [
            {"ticket": 1, "type": 1, "volume": 0.03, "price_open": 3998.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager._set_basket_targets(ctx, sc, positions, 3996.0)
        buy_sls = {r["position"]: r["sl"] for r in sent if "sl" in r}
        # Hedge SL must stay below its own entry (min(3996, 4001-1)=3996 is valid).
        assert abs(buy_sls[2] - 3996.0) < 1e-9

    def test_place_grid_depths_passes_tp(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.lot_size = 0.01
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0]
        sc.placed_buy_depth = 0
        sc.placed_sell_depth = 0
        cycle_manager.order_service.send_pending_order_with_retry = MagicMock(
            return_value={"retcode": 10008, "order": 1, "comment": ""}
        )
        cycle_manager.order_service.get_open_orders.return_value = []
        assert cycle_manager._place_grid_depths(ctx, sc, 2, 2)
        calls = cycle_manager.order_service.send_pending_order_with_retry.call_args_list
        assert len(calls) == 4
        for call in calls:
            kwargs = call.kwargs
            if kwargs["order_type"] == 4:
                assert abs(kwargs["tp"] - (kwargs["price"] + 1.0)) < 1e-9
            else:
                assert abs(kwargs["tp"] - (kwargs["price"] - 1.0)) < 1e-9
