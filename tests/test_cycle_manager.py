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

    def test_locked_exposure_full_grid(self):
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
        cycle_manager.grid_builder.estimate_needed_depths = MagicMock(return_value=(7, 7))
        cycle_manager.position_service.get_open_positions.return_value = [
            {"type": 0, "volume": 0.01, "ticket": 1, "time": 1, "price_open": 4001.0, "profit": 0.0},
            {"type": 0, "volume": 0.01, "ticket": 2, "time": 2, "price_open": 4002.0, "profit": 0.0},
            {"type": 1, "volume": 0.01, "ticket": 3, "time": 3, "price_open": 3999.0, "profit": 0.0},
        ]
        cycle_manager._grow_grid_depth_if_needed(ctx, sc, dry_run=True)
        # Both sides grow together to the same depth.
        assert sc.placed_buy_depth == 7
        assert sc.placed_sell_depth == 7
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

    def test_keep_target_on_grid_never_clamps_below_break_even(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=5)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0, 4004.0, 4005.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0, 3996.0, 3995.0]
        sc.placed_buy_depth = 2
        sc.placed_sell_depth = 2
        sc.buy_volume = 0.03
        sc.sell_volume = 0.01
        target = cycle_manager._keep_target_on_grid(ctx, sc, 4010.0, dry_run=True)
        # The target beyond the planted grid is kept at its true break-even
        # level; the grid just grows as far as grid_count allows. Clamping it
        # down to the grid top would close the basket at a guaranteed loss.
        assert target == 4010.0
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

    def test_set_basket_targets_identical_tp_for_all_buys(self, cycle_manager, monkeypatch):
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
        # Every same-direction buy shares one TP: the passed target, applied as-is.
        assert abs(buy_tps[1] - 4003.0) < 1e-9
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
        # Every same-direction sell shares one TP: the passed target, applied as-is.
        assert abs(sell_tps[1] - 3997.0) < 1e-9
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

    def _base_buy_basket(self, sc):
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_volume = 0.03
        sc.sell_volume = 0.0
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0, 4004.0, 4005.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0, 3996.0, 3995.0]
        sc.placed_buy_depth = 2
        sc.placed_sell_depth = 2
        return [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4002.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 3, "type": 0, "volume": 0.01, "price_open": 4003.0, "tp": 0.0, "sl": 0.0},
        ]

    def test_basket_target_anchored_to_deepest_open_buy_on_lock(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        positions = self._base_buy_basket(sc)
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4002.5
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=True)
        # Grid grows to cover the target and the TP anchors just beyond the
        # deepest OPEN buy (4003) + step, NOT to the top of the planted grid.
        assert sc.placed_buy_depth == 4
        assert sc.basket_target_locked is True
        assert abs(sc.target_price - 4004.0) < 1e-9

    def test_basket_target_not_anchored_to_deep_planted_grid(self, cycle_manager):
        # Reproduces the reported bug: the grid is planted much deeper than the
        # positions that have actually filled. The TP must stay near the basket's
        # true break-even (just beyond the deepest open buy), not fly to the top
        # of the deep planted grid.
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=20)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        positions = self._base_buy_basket(sc)
        sc.placed_buy_depth = 20
        sc.buy_grid_prices = [4001.0 + i for i in range(20)]  # planted up to 4020
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4002.5
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=True)
        # Deepest open buy is 4003 -> TP = 4004, not the planted grid top (4021).
        assert abs(sc.target_price - 4004.0) < 1e-9
        assert sc.target_price < 4010.0

    def test_basket_target_raises_when_deeper_open_position_fills(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        positions = self._base_buy_basket(sc)
        sc.placed_buy_depth = 20
        sc.buy_grid_prices = [4001.0 + i for i in range(20)]
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4002.5
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=True)
        assert abs(sc.target_price - 4004.0) < 1e-9
        # A real deeper buy now fills -> TP rises to stay above its entry.
        cycle_manager.position_service.get_open_positions.return_value = positions + [
            {"ticket": 4, "type": 0, "volume": 0.01, "price_open": 4004.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=True)
        assert abs(sc.target_price - 4005.0) < 1e-9
        assert cycle_manager.target_calc.calculate_basket_target.call_count == 1

    def test_basket_target_remaining_tp_identical_and_frozen_on_tp_out(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        positions = self._base_buy_basket(sc)
        sc.placed_buy_depth = 5
        sent = self._patch_mt5(monkeypatch)
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4004.0
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert abs(sc.target_price - 4004.0) < 1e-9
        # A same-direction position takes profit; the remaining ones keep the same TP.
        remaining = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 4004.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4002.0, "tp": 4004.0, "sl": 0.0},
        ]
        cycle_manager.position_service.get_open_positions.return_value = remaining
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert abs(sc.target_price - 4004.0) < 1e-9
        assert cycle_manager.target_calc.calculate_basket_target.call_count == 1
        buy_tps = {r["position"]: r["tp"] for r in sent if "tp" in r}
        assert abs(buy_tps[1] - 4004.0) < 1e-9
        assert abs(buy_tps[2] - 4004.0) < 1e-9

    def test_place_grid_depths_passes_no_tp(self, cycle_manager):
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
            assert kwargs["tp"] == 0.0

    def test_place_grid_depths_skips_invalid_price_and_continues(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.lot_size = 0.01
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0]
        sc.placed_buy_depth = 0
        sc.placed_sell_depth = 0
        # Buy level 2 (4002.0) is rejected by MT5 (10015 invalid price); the
        # rest must still be planted and the whole grid must NOT be rolled back.
        responses = [
            {"retcode": 10008, "order": 101, "comment": ""},   # buy 4001.0
            {"retcode": 10015, "order": 0, "comment": "Invalid price"},  # buy 4002.0
            {"retcode": 10008, "order": 103, "comment": ""},   # buy 4003.0
            {"retcode": 10008, "order": 201, "comment": ""},   # sell 3999.0
        ]
        cycle_manager.order_service.send_pending_order_with_retry = MagicMock(side_effect=responses)
        cycle_manager.order_service.get_open_orders.return_value = []
        assert cycle_manager._place_grid_depths(ctx, sc, 3, 1)
        calls = cycle_manager.order_service.send_pending_order_with_retry.call_args_list
        assert len(calls) == 4
        # Buy level 1 (grid_number 1) and level 3 (grid_number 3) placed -> depth 3.
        assert sc.placed_buy_depth == 3
        assert sc.placed_sell_depth == 1
        # No rollback: remove_pending_order must NOT be called for the skipped level.
        cycle_manager.order_service.remove_pending_order.assert_not_called()

    def test_place_grid_depths_fatal_error_rolls_back(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=10)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.lot_size = 0.01
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_grid_prices = [4001.0, 4002.0, 4003.0]
        sc.sell_grid_prices = [3999.0, 3998.0, 3997.0]
        sc.placed_buy_depth = 0
        sc.placed_sell_depth = 0
        # A non-price fatal error (retcode 10018 invalid trade) must roll back.
        responses = [
            {"retcode": 10008, "order": 101, "comment": ""},   # buy 4001.0
            {"retcode": 10018, "order": 0, "comment": "Trade timeout"},  # fatal
        ]
        cycle_manager.order_service.send_pending_order_with_retry = MagicMock(side_effect=responses)
        cycle_manager.order_service.get_open_orders.return_value = []
        assert cycle_manager._place_grid_depths(ctx, sc, 2, 2) is False
        cycle_manager.order_service.remove_pending_order.assert_called_once_with(101)

    def test_refresh_tracks_seen_position_tickets(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        cycle_manager.position_service.get_open_positions.return_value = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0},
            {"ticket": 2, "type": 1, "volume": 0.01, "price_open": 3999.0},
        ]
        cycle_manager.order_service.get_open_orders.return_value = []
        cycle_manager._refresh_state_from_mt5(ctx, sc)
        assert sc.position_tickets_seen == {1, 2}

    def test_check_all_positions_closed_detection(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.position_tickets_seen = {1001, 1002}
        cycle_manager.position_service.get_open_positions.return_value = []
        assert cycle_manager._check_all_positions_closed(ctx, sc) is True

    def test_check_all_positions_closed_with_open_positions(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.position_tickets_seen = {1001, 1002}
        cycle_manager.position_service.get_open_positions.return_value = [
            {"ticket": 1001, "type": 0, "volume": 0.01, "price_open": 4001.0},
            {"ticket": 1003, "type": 0, "volume": 0.01, "price_open": 4002.0},
        ]
        assert cycle_manager._check_all_positions_closed(ctx, sc) is False

    def test_check_all_positions_closed_none_seen(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        cycle_manager.position_service.get_open_positions.return_value = []
        assert cycle_manager._check_all_positions_closed(ctx, sc) is False

    def test_target_active_completes_only_when_all_positions_closed(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.position_tickets_seen = {1001, 1002}
        sm = cycle_manager.get_state_machine("XAUUSD")
        sm.state = SymbolState.TARGET_ACTIVE
        # Some positions still open -> cycle must NOT close early.
        cycle_manager.position_service.get_open_positions.return_value = [
            {"ticket": 1002, "type": 0, "volume": 0.01, "price_open": 4001.0},
        ]
        cycle_manager.order_service.get_open_orders.return_value = []
        cycle_manager.target_calc.calculate_basket_target.return_value = 4003.0
        cycle_manager._handle_target_active(ctx, sc, sm, dry_run=True)
        assert sm.state == SymbolState.TARGET_ACTIVE
        # All positions closed -> cycle completes (TP hit for everyone).
        cycle_manager.position_service.get_open_positions.return_value = []
        cycle_manager._handle_target_active(ctx, sc, sm, dry_run=True)
        assert sm.state == SymbolState.CLOSING

    def test_basket_target_frozen_when_same_direction_position_closes(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_volume = 0.03
        sc.sell_volume = 0.0
        sent = self._patch_mt5(monkeypatch)
        positions = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4002.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 3, "type": 0, "volume": 0.01, "price_open": 4003.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4004.0
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert sc.basket_target_locked is True
        assert sc.basket_direction == 1
        assert sc.locked_position_tickets == {1, 2, 3}
        assert sc.target_price == 4004.0
        # A same-direction position takes profit; the target must stay frozen.
        remaining = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4002.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager.position_service.get_open_positions.return_value = remaining
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert sc.basket_target_locked is True
        assert sc.target_price == 4004.0
        assert cycle_manager.target_calc.calculate_basket_target.call_count == 1

    def test_basket_target_frozen_with_new_same_direction_position(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_volume = 0.03
        sc.sell_volume = 0.0
        sent = self._patch_mt5(monkeypatch)
        positions = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4002.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 3, "type": 0, "volume": 0.01, "price_open": 4003.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4004.0
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        # A new same-direction (buy) fill must not recompute the frozen target.
        cycle_manager.position_service.get_open_positions.return_value = positions + [
            {"ticket": 4, "type": 0, "volume": 0.01, "price_open": 4004.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert sc.basket_target_locked is True
        # The deeper buy now fills, so the TP re-anchors just beyond its entry
        # (4004 + step = 4005). It is NOT recomputed from scratch (call_count 1).
        assert sc.target_price == 4005.0
        assert cycle_manager.target_calc.calculate_basket_target.call_count == 1

    def test_basket_target_recomputed_when_opposite_position_opens(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_volume = 0.03
        sc.sell_volume = 0.0
        sent = self._patch_mt5(monkeypatch)
        positions = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4002.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 3, "type": 0, "volume": 0.01, "price_open": 4003.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4004.0
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert sc.basket_target_locked is True
        # A new opposite-side (sell) hedge opens -> target must be recomputed.
        cycle_manager.target_calc.calculate_basket_target.return_value = 3998.0
        cycle_manager.position_service.get_open_positions.return_value = positions + [
            {"ticket": 4, "type": 1, "volume": 0.01, "price_open": 3998.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert sc.basket_target_locked is True
        assert sc.basket_direction == 1
        assert sc.locked_position_tickets == {1, 2, 3, 4}
        # Even though the mock hinted a 3998 target, the basket is still buy
        # dominant, so the TP re-anchors just beyond the deepest open buy (4003).
        assert sc.target_price == 4004.0
        assert cycle_manager.target_calc.calculate_basket_target.call_count == 2

    def test_basket_target_direction_flips_on_larger_opposite(self, cycle_manager, monkeypatch):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.tick_size = 0.01
        sc.effective_grid_step = 1.0
        sc.buy_volume = 0.03
        sc.sell_volume = 0.0
        sent = self._patch_mt5(monkeypatch)
        positions = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 2, "type": 0, "volume": 0.01, "price_open": 4002.0, "tp": 0.0, "sl": 0.0},
            {"ticket": 3, "type": 0, "volume": 0.01, "price_open": 4003.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4005.0, "ask": 4005.1}
        cycle_manager.target_calc.calculate_basket_target.return_value = 4004.0
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert sc.basket_direction == 1
        # A sell hedge bigger than the whole buy side flips the basket direction.
        cycle_manager.target_calc.calculate_basket_target.return_value = 3990.0
        cycle_manager.position_service.get_open_positions.return_value = positions + [
            {"ticket": 4, "type": 1, "volume": 0.05, "price_open": 3998.0, "tp": 0.0, "sl": 0.0},
        ]
        cycle_manager._try_set_basket_target(ctx, sc, dry_run=False)
        assert sc.basket_direction == -1
        assert sc.target_price == 3990.0

    def test_basket_lock_fields_cleared_on_reset(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.basket_target_locked = True
        sc.basket_direction = 1
        sc.locked_position_tickets = {1, 2}
        sc.realized_net_profit = 3.5
        cycle_manager.app_settings = ApplicationSettings(restart_delay_seconds=0)
        sm = cycle_manager.get_state_machine("XAUUSD")
        sm.state = SymbolState.RESETTING
        cycle_manager._handle_resetting(ctx, sc, sm, dry_run=True)
        assert sc.basket_target_locked is False
        assert sc.basket_direction is None
        assert sc.locked_position_tickets == set()
        assert sc.realized_net_profit == 0.0
        assert sm.state == SymbolState.PREPARING

    def test_close_all_positions_accepts_position_closed_retcode(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        sc.lot_size = 0.01
        cycle_manager.app_settings.close_retry_count = 1
        pos = {"ticket": 77, "type": 0, "volume": 0.01, "price_open": 4001.0, "comment": "C1_1"}
        # First call returns the open position; the still-open re-check returns [].
        cycle_manager.position_service.get_open_positions.side_effect = [[pos], []]
        cycle_manager.market_data.get_symbol_tick.return_value = {"bid": 4000.0, "ask": 4000.1}
        cycle_manager.position_service.close_position.return_value = {"retcode": 10027}
        cycle_manager._close_all_positions(ctx, sc)
        # 10027 (position closed server-side) is treated as a successful close.
        assert cycle_manager.position_service.close_position.called
        assert cycle_manager.position_service.close_position.call_args[0][0] == 77

    def test_all_positions_closed_requires_seen_tickets_to_be_gone(self, cycle_manager):
        """A cycle must NOT complete just because the position list is empty.
        Right after planting the grid there are no filled positions yet; the cycle
        must keep running until every ticket seen during the cycle is closed."""
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        # No tickets seen yet, no open positions -> not complete.
        cycle_manager.position_service.get_open_positions.return_value = []
        assert cycle_manager._check_all_positions_closed(ctx, sc) is False
        # A position opened during the cycle.
        sc.position_tickets_seen.add(101)
        cycle_manager.position_service.get_open_positions.return_value = [
            {"ticket": 101, "type": 0, "volume": 0.01, "price_open": 4001.0},
        ]
        assert cycle_manager._check_all_positions_closed(ctx, sc) is False
        # The seen ticket is now gone -> complete.
        cycle_manager.position_service.get_open_positions.return_value = []
        assert cycle_manager._check_all_positions_closed(ctx, sc) is True

    def test_realized_net_profit_accumulates_once_per_closed_position(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001)
        sc = SymbolContext(name="XAUUSD", magic_number=710001)
        cycle_manager.history_service.get_deals_for_position.return_value = [
            {"entry": 1, "profit": 5.0, "commission": -0.2, "swap": 0.0},
        ]
        cycle_manager.position_service.get_open_positions.return_value = [
            {"ticket": 5, "type": 0, "volume": 0.01, "price_open": 4001.0},
        ]
        cycle_manager._refresh_state_from_mt5(ctx, sc)
        assert sc.realized_net_profit == 0.0
        cycle_manager.position_service.get_open_positions.return_value = []
        cycle_manager._refresh_state_from_mt5(ctx, sc)
        assert abs(sc.realized_net_profit - 4.8) < 1e-9
        cycle_manager._refresh_state_from_mt5(ctx, sc)
        assert abs(sc.realized_net_profit - 4.8) < 1e-9

    def test_both_sides_grid_full_triggers_closing(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=20)
        sc = SymbolContext(name="XAUUSD", magic_number=710001, grid_count=20)
        sc.placed_buy_depth = 20
        sc.placed_sell_depth = 20
        sc.both_sides_full_closed = False
        positions = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0},
            {"ticket": 2, "type": 1, "volume": 0.01, "price_open": 4000.0},
        ]
        for i in range(19):
            positions.append({"ticket": 10 + i, "type": 0, "volume": 0.01, "price_open": 4001.0 + i})
        for i in range(19):
            positions.append({"ticket": 100 + i, "type": 1, "volume": 0.01, "price_open": 4000.0 - i})
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._handle_positions_active(ctx, sc, MagicMock(), dry_run=False)
        assert sc.both_sides_full_closed is True
        assert sc.last_event == "Both sides full - closing cycle"

    def test_both_sides_grid_full_not_triggered_when_one_side_short(self, cycle_manager):
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=20)
        sc = SymbolContext(name="XAUUSD", magic_number=710001, grid_count=20)
        sc.placed_buy_depth = 20
        sc.placed_sell_depth = 7
        sc.both_sides_full_closed = False
        positions = [
            {"ticket": 1, "type": 0, "volume": 0.01, "price_open": 4001.0},
            {"ticket": 2, "type": 1, "volume": 0.01, "price_open": 4000.0},
        ]
        cycle_manager.position_service.get_open_positions.return_value = positions
        cycle_manager._handle_positions_active(ctx, sc, MagicMock(), dry_run=False)
        assert sc.both_sides_full_closed is False

    def test_both_sides_grid_full_not_triggered_when_no_positions_open(self, cycle_manager):
        """The 'both sides full' rule only fires when positions are actually
        OPEN on both sides, not when the grid is merely planted with pending
        orders. This prevents closing an empty cycle right after planting."""
        ctx = SymbolConfig(name="XAUUSD", magic_number=710001, grid_count=20)
        sc = SymbolContext(name="XAUUSD", magic_number=710001, grid_count=20)
        sc.placed_buy_depth = 20
        sc.placed_sell_depth = 20
        sc.buy_count = 0
        sc.sell_count = 0
        sc.both_sides_full_closed = False
        # Grid fully planted but no filled positions yet.
        cycle_manager.position_service.get_open_positions.return_value = []
        cycle_manager._handle_positions_active(ctx, sc, MagicMock(), dry_run=False)
        assert sc.both_sides_full_closed is False
