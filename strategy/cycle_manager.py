import time
from datetime import datetime
from typing import Optional, List
from models.enums import SymbolState, ExitReason, EventType, CycleStatus
from models.symbol_context import SymbolContext
from config.models import SymbolConfig, ApplicationSettings
from strategy.atr import ATRCalculator
from strategy.grid_builder import GridBuilder
from strategy.target_calculator import TargetCalculator
from strategy.basket_manager import BasketManager
from strategy.state_machine import SymbolStateMachine
from mt5_client.market_data import MarketData
from mt5_client.order_service import OrderService, MT5_ORDER_TYPE_BUY_STOP, MT5_ORDER_TYPE_SELL_STOP, MT5_RETCODE_PLACED
from mt5_client.position_service import PositionService
from mt5_client.history_service import HistoryService
from utils.logger import Logger
from utils.price import normalize_price, normalize_buy_stop_price, normalize_sell_stop_price
from utils.volume import normalize_volume

MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1
MT5_RETCODE_PLACED = 10008
MT5_RETCODE_DONE = 10009
MT5_RETCODE_DONE_PARTIAL = 10010
MT5_RETCODE_POSITION_CLOSED = 10027


class CycleManager:
    def __init__(
        self,
        app_settings: ApplicationSettings,
        market_data: MarketData,
        order_service: OrderService,
        position_service: PositionService,
        history_service: HistoryService,
        atr_calc: ATRCalculator,
        grid_builder: GridBuilder,
        target_calc: TargetCalculator,
        basket_manager: BasketManager,
    ):
        self.app_settings = app_settings
        self.market_data = market_data
        self.order_service = order_service
        self.position_service = position_service
        self.history_service = history_service
        self.atr_calc = atr_calc
        self.grid_builder = grid_builder
        self.target_calc = target_calc
        self.basket_manager = basket_manager
        self.logger = Logger()
        self._symbol_state_machines = {}

    def get_state_machine(self, symbol: str) -> SymbolStateMachine:
        if symbol not in self._symbol_state_machines:
            self._symbol_state_machines[symbol] = SymbolStateMachine()
        return self._symbol_state_machines[symbol]

    def process_symbol(self, ctx: SymbolConfig, sc: SymbolContext, dry_run: bool = False):
        sm = self.get_state_machine(sc.name)
        state = sm.state
        self.logger.debug("Processing symbol", symbol=sc.name, state=state.value, cycle=sc.cycle_number)
        if state == SymbolState.STOPPED:
            return
        if state == SymbolState.ERROR:
            return

        if state == SymbolState.IDLE:
            sm.transition_to(SymbolState.PREPARING)
            sc.last_event = "Starting preparation"
            return

        if state == SymbolState.PREPARING:
            self._handle_preparing(ctx, sc, sm, dry_run)
            return

        if state == SymbolState.PLACING_GRID:
            self._handle_placing_grid(ctx, sc, sm, dry_run)
            return

        if state == SymbolState.GRID_ACTIVE:
            self._handle_grid_active(ctx, sc, sm, dry_run)
            return

        if state == SymbolState.POSITIONS_ACTIVE:
            self._handle_positions_active(ctx, sc, sm, dry_run)
            return

        if state == SymbolState.TARGET_ACTIVE:
            self._handle_target_active(ctx, sc, sm, dry_run)
            return

        if state == SymbolState.LOCKED_EXPOSURE:
            self._handle_locked_exposure(ctx, sc, sm, dry_run)
            return

        if state == SymbolState.CLOSING:
            self._handle_closing(ctx, sc, sm, dry_run)
            return

        if state == SymbolState.RESETTING:
            self._handle_resetting(ctx, sc, sm, dry_run)
            return

    def _handle_preparing(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        if sc.cycle_number == 0:
            sc.cycle_number = 1
        tick = self.market_data.get_symbol_tick(sc.name)
        if not tick:
            sc.last_error = "Cannot get tick data"
            sm.transition_to(SymbolState.ERROR)
            return
        bid = tick["bid"]
        ask = tick["ask"]
        anchor_price = (bid + ask) / 2.0
        sc.anchor_price = anchor_price
        atr_value = self.atr_calc.calculate(sc.name, ctx.atr_period, ctx.atr_timeframe)
        if atr_value is None or atr_value <= 0:
            sc.last_error = "ATR calculation failed or zero"
            sm.transition_to(SymbolState.ERROR)
            return
        sc.atr = atr_value
        if ctx.atr_filter_enabled:
            check = self.atr_calc.check_entry_condition(
                sc.name, ctx.atr_period, ctx.atr_timeframe,
                ctx.atr_lookback, ctx.atr_slope_period)
            sc.atr_ok = check["allowed"]
            self.logger.info("ATR filter status", symbol=sc.name,
                             allowed=check["allowed"],
                             current=f"{check['current']:.6f}",
                             avg=f"{check['avg']:.6f}",
                             slope=f"{check['slope']:.6f}",
                             lookback=ctx.atr_lookback,
                             slope_period=ctx.atr_slope_period)
            if not check["allowed"]:
                sc.last_event = (f"ATR filter: current={check['current']:.6f}, "
                                 f"avg={check['avg']:.6f}, slope={check['slope']:.6f}")
                return
        sm.transition_to(SymbolState.PLACING_GRID)
        sc.last_event = "Preparation complete"
        self.logger.info("Preparation complete", symbol=sc.name, anchor=f"{anchor_price:.5f}",
                         atr=f"{atr_value:.6f}", cycle=sc.cycle_number)

    def _handle_placing_grid(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        symbol_info = self.market_data.get_symbol_info(sc.name)
        if not symbol_info:
            sc.last_error = "Cannot get symbol info"
            sm.transition_to(SymbolState.ERROR)
            return
        tick = self.market_data.get_symbol_tick(sc.name)
        if not tick:
            sc.last_error = "Cannot get market tick"
            sm.transition_to(SymbolState.ERROR)
            return
        tick_size = symbol_info["trade_tick_size"]
        trade_stops_level = symbol_info["trade_stops_level"]
        volume_min = symbol_info["volume_min"]
        volume_max = symbol_info["volume_max"]
        volume_step = symbol_info["volume_step"]
        sc.tick_size = tick_size
        sc.volume_min = volume_min
        sc.volume_max = volume_max
        sc.volume_step = volume_step
        sc.contract_size = symbol_info.get("trade_contract_size") or 100
        lot = normalize_volume(ctx.lot_size, volume_min, volume_max, volume_step)
        sc.lot_size = lot
        cal_step, eff_step, buy_prices, sell_prices = self.grid_builder.build_grid_prices(
            sc.anchor_price, sc.atr, ctx.grid_count, tick_size, tick["bid"], tick["ask"], trade_stops_level
        )
        sc.calculated_grid_step = cal_step
        sc.effective_grid_step = eff_step
        sc.buy_grid_prices = buy_prices
        sc.sell_grid_prices = sell_prices
        initial_buy_depth, initial_sell_depth = self.grid_builder.calculate_initial_depths(
            ctx.target_profit,
            ctx.commission_per_position,
            lot,
            buy_prices,
            sell_prices,
            sc.anchor_price,
            sc.contract_size,
            ctx.grid_count,
        )
        sc.grid_base_depth = max(initial_buy_depth, initial_sell_depth)
        sc.planned_buy_depth = initial_buy_depth
        sc.planned_sell_depth = initial_sell_depth
        sc.placed_buy_depth = 0
        sc.placed_sell_depth = 0
        self.logger.text(
            "grid_initial_plan",
            symbol=sc.name,
            cycle=sc.cycle_number,
            buy_depth=initial_buy_depth,
            sell_depth=initial_sell_depth,
            grid_count=ctx.grid_count,
            target_profit=ctx.target_profit,
        )
        if dry_run:
            staged_orders = self.grid_builder.build_orders_for_depth(
                sc.name,
                ctx.magic_number,
                sc.cycle_number,
                lot,
                buy_prices,
                sell_prices,
                initial_buy_depth,
                initial_sell_depth,
                grid_step=eff_step or sc.tick_size,
            )
            self.logger.info("DRY RUN: Grid orders ready", symbol=sc.name, cycle=sc.cycle_number,
                             order_count=len(staged_orders), buy_depth=initial_buy_depth,
                             sell_depth=initial_sell_depth)
            for o in staged_orders:
                self.logger.info("DRY RUN order", symbol=sc.name, type=o["direction"],
                                 price=f"{o['price']:.5f}", tp=f"{o['tp']:.5f}" if o.get("tp") else None,
                                 comment=o["comment"])
            sc.placed_buy_depth = initial_buy_depth
            sc.placed_sell_depth = initial_sell_depth
            sm.transition_to(SymbolState.GRID_ACTIVE)
            sc.last_event = f"Grid built (dry run): buy={initial_buy_depth}, sell={initial_sell_depth}"
            return
        if not self._place_grid_depths(ctx, sc, initial_buy_depth, initial_sell_depth):
            time.sleep(self.app_settings.restart_delay_seconds)
            sm.transition_to(SymbolState.RESETTING)
            sc.last_error = "Grid placement failed"
            return
        sc.last_event = f"Grid placed: buy={initial_buy_depth}, sell={initial_sell_depth}"
        sm.transition_to(SymbolState.GRID_ACTIVE)
        self.logger.info("Grid placement complete", symbol=sc.name, cycle=sc.cycle_number,
                         buy_depth=initial_buy_depth, sell_depth=initial_sell_depth)

    def _place_grid_depths(
        self,
        ctx: SymbolConfig,
        sc: SymbolContext,
        buy_depth: int,
        sell_depth: int,
        dry_run: bool = False,
    ) -> bool:
        if buy_depth < sc.placed_buy_depth or sell_depth < sc.placed_sell_depth:
            return False
        buy_depth = min(buy_depth, len(sc.buy_grid_prices), ctx.grid_count)
        sell_depth = min(sell_depth, len(sc.sell_grid_prices), ctx.grid_count)

        if dry_run:
            sc.placed_buy_depth = max(sc.placed_buy_depth, buy_depth)
            sc.placed_sell_depth = max(sc.placed_sell_depth, sell_depth)
            return True

        buy_orders = self.grid_builder.build_orders_for_depth(
            sc.name,
            ctx.magic_number,
            sc.cycle_number,
            sc.lot_size,
            sc.buy_grid_prices,
            sc.sell_grid_prices,
            buy_depth,
            0,
            buy_start=sc.placed_buy_depth + 1,
            grid_step=sc.effective_grid_step or sc.tick_size,
        )
        sell_orders = self.grid_builder.build_orders_for_depth(
            sc.name,
            ctx.magic_number,
            sc.cycle_number,
            sc.lot_size,
            sc.buy_grid_prices,
            sc.sell_grid_prices,
            0,
            sell_depth,
            sell_start=sc.placed_sell_depth + 1,
            grid_step=sc.effective_grid_step or sc.tick_size,
        )
        orders = buy_orders + sell_orders
        placed_tickets = []
        fatal_error = False
        max_placed_buy = sc.placed_buy_depth
        max_placed_sell = sc.placed_sell_depth
        for o in orders:
            result = self.order_service.send_pending_order_with_retry(
                symbol=o["symbol"],
                order_type=o["type"],
                volume=o["volume"],
                price=o["price"],
                magic=o["magic"],
                comment=o["comment"],
                max_attempts=self.app_settings.order_retry_count,
                tp=o.get("tp", 0.0) or 0.0,
            )
            retcode = result.get("retcode")
            if retcode in (MT5_RETCODE_PLACED, MT5_RETCODE_DONE, MT5_RETCODE_DONE_PARTIAL):
                ticket = result.get("order", 0)
                placed_tickets.append(ticket)
                self.logger.info("Order placed", symbol=sc.name, ticket=ticket,
                                 retcode=retcode, comment=o["comment"],
                                 price=f"{o['price']:.5f}", tp=f"{o.get('tp', 0.0):.5f}" if o.get("tp") else None)
                if o["direction"] == "BUY":
                    max_placed_buy = max(max_placed_buy, o["grid_number"])
                else:
                    max_placed_sell = max(max_placed_sell, o["grid_number"])
            elif retcode in (10015, 10030):
                # Invalid price / invalid fill: the level is too close to the
                # current market. Skip it and keep planting the rest so a single
                # moving market never rolls back the whole grid.
                self.logger.warning("Order skipped", symbol=sc.name, comment=o["comment"],
                                    retcode=retcode, price=f"{o['price']:.5f}",
                                    error=result.get("error", ""))
            else:
                self.logger.error("Order placement failed", symbol=sc.name,
                                  comment=o["comment"], retcode=retcode,
                                  error=result.get("error", ""))
                fatal_error = True
                break

        if fatal_error:
            for t in placed_tickets:
                self.order_service.remove_pending_order(t)
            return False

        sc.placed_buy_depth = max_placed_buy
        sc.placed_sell_depth = max_placed_sell
        open_orders = self.order_service.get_open_orders(sc.name, ctx.magic_number)
        sc.active_order_tickets = [o["ticket"] for o in open_orders]
        return True

    def _handle_grid_active(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        filled_orders = self._check_filled_orders(ctx, sc)
        if filled_orders > 0:
            self._refresh_state_from_mt5(ctx, sc)
            self._update_exposure(ctx, sc)
            if sc.buy_count + sc.sell_count > 0:
                self._try_set_basket_target(ctx, sc, dry_run)
                self._grow_grid_depth_if_needed(ctx, sc, dry_run)
                sm.transition_to(SymbolState.POSITIONS_ACTIVE)
                sc.last_event = "Orders filling"
            return

    def _check_both_sides_full_and_close(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine) -> bool:
        """If both sides of the grid have fully opened as positions, trigger a
        manual close of ALL positions of this cycle. Returns True if CLOSING was
        entered, False otherwise. Guarded by sc.both_sides_full_closed so the
        transition happens only once per cycle."""
        if self._both_sides_positions_full(ctx, sc) and not sc.both_sides_full_closed:
            sc.both_sides_full_closed = True
            self.logger.info("Both grid sides full - closing all positions",
                             symbol=sc.name, cycle=sc.cycle_number)
            sm.transition_to(SymbolState.CLOSING)
            sc.last_event = "Both sides full - closing cycle"
            return True
        return False

    def _handle_positions_active(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        self._refresh_state_from_mt5(ctx, sc)
        self._update_exposure(ctx, sc)
        if self._check_all_positions_closed(ctx, sc):
            self.logger.info("All positions closed", symbol=sc.name, cycle=sc.cycle_number)
            sm.transition_to(SymbolState.CLOSING)
            sc.last_event = "All positions closed (TP hit)"
            return
        # New rule: when both sides of the grid are fully opened, close all
        # positions of this cycle (prevent indefinite locked exposure).
        if self._check_both_sides_full_and_close(ctx, sc, sm):
            return
        if self.basket_manager.is_locked_exposure(self._get_positions(ctx, sc)):
            sm.transition_to(SymbolState.LOCKED_EXPOSURE)
            sc.last_event = "Locked exposure"
            return
        self._try_set_basket_target(ctx, sc, dry_run)
        self._grow_grid_depth_if_needed(ctx, sc, dry_run)
        sm.transition_to(SymbolState.TARGET_ACTIVE)
        sc.last_event = "Setting target"

    def _handle_target_active(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        self._refresh_state_from_mt5(ctx, sc)
        self._update_exposure(ctx, sc)
        positions = self._get_positions(ctx, sc)
        if self._check_all_positions_closed(ctx, sc):
            self.logger.info("All positions closed", symbol=sc.name, cycle=sc.cycle_number)
            sm.transition_to(SymbolState.CLOSING)
            sc.last_event = "All positions closed (TP hit)"
            return
        # New rule: when both sides of the grid are fully opened, close all
        # positions of this cycle (prevent indefinite locked exposure).
        if self._check_both_sides_full_and_close(ctx, sc, sm):
            return
        if self.basket_manager.is_locked_exposure(positions):
            sm.transition_to(SymbolState.LOCKED_EXPOSURE)
            sc.last_event = "Locked exposure"
            return
        self._try_set_basket_target(ctx, sc, dry_run)
        self._grow_grid_depth_if_needed(ctx, sc, dry_run)

    def _handle_locked_exposure(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        self._refresh_state_from_mt5(ctx, sc)
        self._update_exposure(ctx, sc)
        if self._check_all_positions_closed(ctx, sc):
            self.logger.info("All positions closed", symbol=sc.name, cycle=sc.cycle_number)
            sm.transition_to(SymbolState.CLOSING)
            sc.last_event = "All positions closed (TP hit)"
            return
        # New rule: when both sides of the grid are fully opened, close all
        # positions of this cycle (prevent indefinite locked exposure).
        if self._check_both_sides_full_and_close(ctx, sc, sm):
            return
        positions = self._get_positions(ctx, sc)
        if not self.basket_manager.is_locked_exposure(positions):
            sm.transition_to(SymbolState.TARGET_ACTIVE)
            sc.last_event = "Exposure changed, recalculating target"
            return
        if sc.target_price is not None and not dry_run:
            self._set_basket_targets(ctx, sc, positions, sc.target_price)

    def _handle_closing(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        if dry_run:
            sm.transition_to(SymbolState.RESETTING)
            sc.last_event = "Cycle close (dry run)"
            return
        self._cancel_all_pending_orders(ctx, sc)
        self._close_all_positions(ctx, sc)
        positions = self._get_positions(ctx, sc)
        orders = self.order_service.get_open_orders(sc.name, ctx.magic_number)
        if not positions and not orders:
            sm.transition_to(SymbolState.RESETTING)
            sc.last_event = "Cycle closed"
            self.logger.info("Cycle closed", symbol=sc.name, cycle=sc.cycle_number)
        else:
            # If positions/orders remain after closing attempts, re-check if they may have been
            # closed server-side despite retcode errors; allow immediate RESET if they are gone.
            self.logger.warning("Cycle close incomplete, rechecking server state", symbol=sc.name,
                                cycle=sc.cycle_number, positions=len(positions), orders=len(orders))
            # If any positions are still present after attempting to close them all,
            # we'll re-enter the CLOSING state in the next loop iteration rather than
            # transitioning to RESETTING, ensuring the closing attempts are retried.
            sc.last_event = f"Cycle close in-progress ({len(positions)} positions, {len(orders)} orders)"

    def _handle_resetting(self, ctx: SymbolConfig, sc: SymbolContext, sm: SymbolStateMachine, dry_run: bool):
        sc.cycle_number += 1
        sc.anchor_price = None
        sc.atr = None
        sc.calculated_grid_step = None
        sc.effective_grid_step = None
        sc.active_order_tickets = []
        sc.active_position_tickets = []
        sc.position_tickets_seen.clear()
        sc.buy_grid_prices = []
        sc.sell_grid_prices = []
        sc.grid_base_depth = 1
        sc.planned_buy_depth = 0
        sc.planned_sell_depth = 0
        sc.placed_buy_depth = 0
        sc.placed_sell_depth = 0
        sc.buy_count = 0
        sc.sell_count = 0
        sc.buy_volume = 0.0
        sc.sell_volume = 0.0
        sc.target_price = None
        sc.trigger_ticket = None
        sc.basket_target_locked = False
        sc.basket_direction = None
        sc.locked_position_tickets.clear()
        sc.settled_position_tickets.clear()
        sc.both_sides_full_closed = False
        self.logger.info("Cycle realised P/L", symbol=sc.name, cycle=sc.cycle_number,
                         realized_net_profit=f"{sc.realized_net_profit:.5f}")
        sc.realized_net_profit = 0.0
        sc.last_error = None
        sc.atr_ok = True
        sc.last_event = "Cycle reset"
        time.sleep(self.app_settings.restart_delay_seconds)
        sm.transition_to(SymbolState.PREPARING)

    def _check_filled_orders(self, ctx: SymbolConfig, sc: SymbolContext) -> int:
        orders = self.order_service.get_open_orders(sc.name, ctx.magic_number)
        filled = 0
        for ticket in list(sc.active_order_tickets):
            still_open = any(o["ticket"] == ticket for o in orders)
            if not still_open:
                filled += 1
        return filled

    def _grow_grid_depth_if_needed(self, ctx: SymbolConfig, sc: SymbolContext, dry_run: bool):
        positions = self._get_positions(ctx, sc)
        if not positions:
            return
        buy_target, sell_target = self.grid_builder.estimate_needed_depths(
            positions,
            ctx.target_profit,
            ctx.commission_per_position,
            sc.lot_size,
            sc.buy_grid_prices,
            sc.sell_grid_prices,
            sc.anchor_price,
            sc.contract_size,
            ctx.grid_count,
            sc.placed_buy_depth,
            sc.placed_sell_depth,
        )
        buy_target = min(ctx.grid_count, max(buy_target, sc.placed_buy_depth))
        sell_target = min(ctx.grid_count, max(sell_target, sc.placed_sell_depth))
        self.logger.text(
            "grid_growth_decision",
            symbol=sc.name,
            cycle=sc.cycle_number,
            buy_count=sc.buy_count,
            sell_count=sc.sell_count,
            placed_buy_depth=sc.placed_buy_depth,
            placed_sell_depth=sc.placed_sell_depth,
            buy_target=buy_target,
            sell_target=sell_target,
            dominant_side="BUY" if sc.buy_count > sc.sell_count else "SELL" if sc.sell_count > sc.buy_count else "EQUAL",
        )
        if buy_target == sc.placed_buy_depth and sell_target == sc.placed_sell_depth:
            return
        self._place_grid_depths(ctx, sc, buy_target, sell_target, dry_run=dry_run)

    def _refresh_state_from_mt5(self, ctx: SymbolConfig, sc: SymbolContext):
        orders = self.order_service.get_open_orders(sc.name, ctx.magic_number)
        positions = self.position_service.get_open_positions(sc.name, ctx.magic_number)
        sc.active_order_tickets = [o["ticket"] for o in orders]
        sc.active_position_tickets = [p["ticket"] for p in positions]
        open_tickets = {p["ticket"] for p in positions}
        for closed in sorted(sc.position_tickets_seen - open_tickets):
            if closed in sc.settled_position_tickets:
                continue
            sc.realized_net_profit += self._realized_profit_of(closed)
            sc.settled_position_tickets.add(closed)
        for p in positions:
            sc.position_tickets_seen.add(p["ticket"])

    def _update_exposure(self, ctx: SymbolConfig, sc: SymbolContext):
        positions = self.position_service.get_open_positions(sc.name, ctx.magic_number)
        buy_vol = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_BUY)
        sell_vol = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_SELL)
        sc.buy_volume = buy_vol
        sc.sell_volume = sell_vol
        sc.buy_count = sum(1 for p in positions if p["type"] == MT5_ORDER_TYPE_BUY)
        sc.sell_count = sum(1 for p in positions if p["type"] == MT5_ORDER_TYPE_SELL)

    def _check_all_positions_closed(self, ctx: SymbolConfig, sc: SymbolContext) -> bool:
        """Return True only when every position opened during this cycle has
        been closed (all take-profit fills have happened), so the cycle can
        complete and any remaining pending orders get cancelled.

        A single incidental close (e.g. a tight plant-time TP) never completes
        the cycle while other positions are still open.
        """
        if not sc.position_tickets_seen:
            return False
        positions = self.position_service.get_open_positions(sc.name, ctx.magic_number)
        # Only complete when every ticket seen during this cycle has actually been
        # closed. An empty position list is NOT sufficient by itself: right after
        # planting the grid there may be no filled positions yet, and returning True
        # would incorrectly end the cycle before any position even opened.
        open_tickets = {p["ticket"] for p in positions}
        seen_open = [t for t in sc.position_tickets_seen if t in open_tickets]
        return len(seen_open) == 0

    def _both_sides_grid_full(self, ctx: SymbolConfig, sc: SymbolContext) -> bool:
        """Return True when the grid has been planted to its full depth on BOTH
        the buy and sell sides (placed depths reached grid_count on both)."""
        return sc.placed_buy_depth >= ctx.grid_count and sc.placed_sell_depth >= ctx.grid_count

    def _both_sides_positions_full(self, ctx: SymbolConfig, sc: SymbolContext) -> bool:
        """Return True when positions have actually OPENED to the max depth on
        BOTH sides: buy_count and sell_count both reached grid_count, meaning
        every planted level on both directions has been filled by the market.

        This is the rule the user asked for: "when all positions on both sides
        are open, close all positions of the cycle".
        """
        return (
            sc.buy_count >= ctx.grid_count
            and sc.sell_count >= ctx.grid_count
            and sc.buy_count > 0
            and sc.sell_count > 0
        )

    def _get_positions(self, ctx: SymbolConfig, sc: SymbolContext) -> List[dict]:
        return self.position_service.get_open_positions(sc.name, ctx.magic_number)

    def _cancel_all_pending_orders(self, ctx: SymbolConfig, sc: SymbolContext):
        orders = self.order_service.get_open_orders(sc.name, ctx.magic_number)
        for o in orders:
            self.order_service.remove_pending_order(o["ticket"])
            self.logger.info("Order cancelled", symbol=sc.name, ticket=o["ticket"],
                             comment=o.get("comment", ""))

    def _close_all_positions(self, ctx: SymbolConfig, sc: SymbolContext):
        positions = self.position_service.get_open_positions(sc.name, ctx.magic_number)
        success_codes = (MT5_RETCODE_DONE, MT5_RETCODE_DONE_PARTIAL, MT5_RETCODE_POSITION_CLOSED)
        for p in positions:
            retries = self.app_settings.close_retry_count
            closed = False
            for attempt in range(retries):
                tick = self.market_data.get_symbol_tick(sc.name)
                if not tick:
                    time.sleep(0.5)
                    continue
                close_price = tick["bid"] if p["type"] == MT5_ORDER_TYPE_BUY else tick["ask"]
                result = self.position_service.close_position(
                    p["ticket"], sc.name, p["type"], p["volume"], close_price
                )
                if result.get("retcode") in success_codes:
                    self.logger.info("Position closed", symbol=sc.name, ticket=p["ticket"],
                                     comment=p.get("comment", ""))
                    closed = True
                    break
                else:
                    self.logger.warning("Position close attempt failed",
                                        symbol=sc.name, ticket=p["ticket"],
                                        attempt=attempt + 1, retcode=result.get("retcode"),
                                        error=result.get("error", ""))
                    time.sleep(0.5)
            if not closed:
                # Re-check MT5: the position may have been closed server-side
                # even though the request retcode differed (e.g. already gone).
                still_open = any(
                    op["ticket"] == p["ticket"]
                    for op in self.position_service.get_open_positions(sc.name, ctx.magic_number)
                )
                if not still_open:
                    self.logger.info("Position closed (confirmed gone)", symbol=sc.name,
                                     ticket=p["ticket"], comment=p.get("comment", ""))

    def _realized_profit_of(self, position_ticket: int) -> float:
        try:
            deals = self.history_service.get_deals_for_position(position_ticket)
            total = 0.0
            for d in deals:
                if d.get("entry") != 1:
                    continue
                total += (d.get("profit") or 0.0) + (d.get("commission") or 0.0) + (d.get("swap") or 0.0)
            return total
        except Exception:
            return 0.0

    @staticmethod
    def _basket_direction(positions: List[dict]) -> int:
        buy_vol = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_BUY)
        sell_vol = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_SELL)
        return 1 if buy_vol >= sell_vol else -1

    def _should_recompute_target(self, sc: SymbolContext, positions: List[dict]) -> bool:
        new_tickets = {p["ticket"] for p in positions if p.get("ticket")} - sc.locked_position_tickets
        if not new_tickets:
            return False
        for p in positions:
            if p.get("ticket") in new_tickets:
                is_buy = p["type"] == MT5_ORDER_TYPE_BUY
                if (sc.basket_direction > 0 and not is_buy) or (sc.basket_direction < 0 and is_buy):
                    return True
        return self._basket_direction(positions) != sc.basket_direction

    def _try_set_basket_target(self, ctx: SymbolConfig, sc: SymbolContext, dry_run: bool):
        positions = self._get_positions(ctx, sc)
        if not positions:
            return
        if self.basket_manager.is_locked_exposure(positions):
            return
        if sc.basket_target_locked and sc.target_price is not None:
            if self._should_recompute_target(sc, positions):
                sc.basket_target_locked = False
                sc.basket_direction = None
            else:
                self._reanchor_to_grid_top(ctx, sc, positions)
                if not dry_run:
                    self._set_basket_targets(ctx, sc, positions, sc.target_price)
                return
        tick = self.market_data.get_symbol_tick(sc.name)
        current_price = (tick["bid"] + tick["ask"]) / 2.0 if tick else 0
        target = self.target_calc.calculate_basket_target(
            positions,
            ctx.commission_per_position,
            ctx.target_profit,
            sc.name,
            sc.tick_size,
            current_price,
            contract_size=sc.contract_size,
        )
        if target is None:
            return
        target = self._keep_target_on_grid(ctx, sc, target, dry_run)
        sc.basket_target_locked = True
        sc.basket_direction = self._basket_direction(positions)
        sc.locked_position_tickets = {p["ticket"] for p in positions if p.get("ticket")}
        sc.target_price = target
        self._reanchor_to_grid_top(ctx, sc, positions)
        trigger = self.basket_manager.select_trigger_position(positions)
        if trigger:
            sc.trigger_ticket = trigger["ticket"]
        if not dry_run:
            self._set_basket_targets(ctx, sc, positions, sc.target_price)
        sc.last_event = f"Target set: {sc.target_price:.5f}"

    def _keep_target_on_grid(self, ctx: SymbolConfig, sc: SymbolContext,
                             target: float, dry_run: bool) -> float:
        """Grow the planted grid toward the basket target without lowering it.

        The dynamically computed target price can fall far outside the planted
        grid when only a few positions are open. Here we extend the grid on the
        dominant side as far as grid_count allows (so pendings keep opening along
        the way) but we NEVER clamp the TP down to the planted grid. Clamping it
        to a level the basket has not yet broken even at would close the cycle at
        a guaranteed net loss (the exact bug that produced a negative realized
        P/L in history). The target stays at the true break-even level; the price
        simply has to travel that far for the cycle to complete profitably.
        """
        net_buy = sc.buy_volume > sc.sell_volume
        if net_buy and sc.buy_grid_prices:
            needed = len(sc.buy_grid_prices)
            for j, p in enumerate(sc.buy_grid_prices, 1):
                if p >= target:
                    needed = j
                    break
            want = min(ctx.grid_count, needed + 1)
            if want > sc.placed_buy_depth:
                self._place_grid_depths(ctx, sc, want, sc.placed_sell_depth, dry_run=dry_run)
        elif not net_buy and sc.sell_grid_prices:
            needed = len(sc.sell_grid_prices)
            for j, p in enumerate(sc.sell_grid_prices, 1):
                if p <= target:
                    needed = j
                    break
            want = min(ctx.grid_count, needed + 1)
            if want > sc.placed_sell_depth:
                self._place_grid_depths(ctx, sc, sc.placed_buy_depth, want, dry_run=dry_run)
        return target

    def _reanchor_to_grid_top(self, ctx: SymbolConfig, sc: SymbolContext, positions: List[dict]):
        """Keep the shared basket TP anchored beyond the deepest open position.

        The target is only raised/lowered enough to stay beyond the deepest
        SAME-DIRECTION position that is actually open (never behind its entry,
        so MT5 accepts the TP). It is NOT anchored to the top of the planted
        grid: the grid can be planted much deeper than the positions that have
        filled so far, and gluing the TP to the planted grid's top would push it
        far beyond the basket's true break-even + small target profit.
        """
        step = sc.effective_grid_step or sc.tick_size
        if sc.basket_direction is not None and sc.basket_direction > 0:
            buy_entries = [p.get("price_open", 0.0) or 0.0 for p in positions if p["type"] == MT5_ORDER_TYPE_BUY]
            if buy_entries:
                top_entry = max(buy_entries)
                anchor = max(sc.target_price, top_entry + step) if sc.target_price is not None else top_entry + step
                anchor = self._align_to_tick(anchor, sc.tick_size)
                if sc.target_price is None or abs(anchor - sc.target_price) >= sc.tick_size * 0.5:
                    sc.target_price = anchor
                    sc.last_event = f"Target re-anchored: {anchor:.5f}"
        elif sc.basket_direction is not None and sc.basket_direction < 0:
            sell_entries = [p.get("price_open", 0.0) or 0.0 for p in positions if p["type"] == MT5_ORDER_TYPE_SELL]
            if sell_entries:
                bottom_entry = min(sell_entries)
                anchor = min(sc.target_price, bottom_entry - step) if sc.target_price is not None else bottom_entry - step
                anchor = self._align_to_tick(anchor, sc.tick_size)
                if sc.target_price is None or abs(anchor - sc.target_price) >= sc.tick_size * 0.5:
                    sc.target_price = anchor
                    sc.last_event = f"Target re-anchored: {anchor:.5f}"

    def _set_basket_targets(self, ctx: SymbolConfig, sc: SymbolContext, positions: List[dict], target_price: float):
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return
        if sc.basket_target_locked and sc.basket_direction is not None:
            net_buy = sc.basket_direction > 0
        else:
            buy_vol = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_BUY)
            sell_vol = sum(p["volume"] for p in positions if p["type"] == MT5_ORDER_TYPE_SELL)
            net_buy = buy_vol > sell_vol
        eff_target = self._align_to_tick(target_price, sc.tick_size)
        step = sc.effective_grid_step or sc.tick_size
        for p in positions:
            is_buy = p["type"] == MT5_ORDER_TYPE_BUY
            same_dir = (is_buy and net_buy) or (not is_buy and not net_buy)
            entry = p.get("price_open", 0.0) or 0.0
            if same_dir:
                eff = eff_target
                current = p.get("tp", 0.0) or 0.0
                if abs(current - eff) >= sc.tick_size * 0.5:
                    request = {"action": 6, "position": p["ticket"], "symbol": sc.name,
                               "tp": eff, "sl": p.get("sl", 0.0) or 0.0, "magic": ctx.magic_number}
                    self._send_modify(request, p["ticket"], eff, "TP")
            else:
                # Opposite-side hedge gets the basket target as SL, but never
                # behind its own entry either.
                if is_buy:
                    eff = min(target_price, entry - step) if entry > 0 else target_price
                else:
                    eff = max(target_price, entry + step) if entry > 0 else target_price
                eff = self._align_to_tick(eff, sc.tick_size)
                current = p.get("sl", 0.0) or 0.0
                if abs(current - eff) >= sc.tick_size * 0.5:
                    request = {"action": 6, "position": p["ticket"], "symbol": sc.name,
                               "sl": eff, "tp": p.get("tp", 0.0) or 0.0, "magic": ctx.magic_number}
                    self._send_modify(request, p["ticket"], eff, "SL")

    @staticmethod
    def _align_to_tick(price: float, tick_size: float) -> float:
        if tick_size > 0:
            return round(price / tick_size) * tick_size
        return price

    def _send_modify(self, request: dict, ticket: int, price: float, label: str):
        try:
            import MetaTrader5 as mt5
            result = mt5.order_send(request)
            if result and result.retcode == MT5_RETCODE_DONE:
                self.logger.info(f"Basket {label} set", ticket=ticket, price=f"{price:.5f}")
            else:
                rc = result.retcode if result else -1
                self.logger.warning(f"Failed to set basket {label}", ticket=ticket, retcode=rc)
        except Exception as e:
            self.logger.error(f"Exception setting basket {label}", error=str(e))
