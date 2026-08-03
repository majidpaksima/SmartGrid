#!/usr/bin/env python3
"""Multi-Symbol Smart ATR Grid Trading Bot with Dynamic Basket TP."""

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from config.models import AppConfig, SymbolConfig, ApplicationSettings, MT5Config
from config.loader import load_config, save_config
from config.defaults_manager import DefaultsManager
from config.interactive_setup import InteractiveSetup
from utils.logger import Logger
from utils.console import Console
from mt5_client.connection import MT5Connection
from mt5_client.account_service import AccountService
from mt5_client.market_data import MarketData
from mt5_client.order_service import OrderService
from mt5_client.position_service import PositionService
from mt5_client.history_service import HistoryService
from strategy.atr import ATRCalculator
from strategy.grid_builder import GridBuilder
from strategy.target_calculator import TargetCalculator
from strategy.basket_manager import BasketManager
from strategy.cycle_manager import CycleManager
from services.symbol_manager import SymbolManager
from services.commission_service import CommissionService
from services.persistence import Persistence, CycleRecord
from services.recovery_service import RecoveryService
from models.enums import SymbolState, ExitReason, EventType, CycleStatus, ShutdownMode
from models.account_snapshot import AccountSnapshot
from dashboard.live_dashboard import LiveDashboard

load_dotenv()

SHUTDOWN_REQUESTED = False
EMERGENCY_CLOSE_REQUESTED = False
_CLOSE_ATTEMPTED = False
SHUTDOWN_MODE = ShutdownMode.LEAVE_OPEN


def signal_handler(sig, frame):
    global SHUTDOWN_REQUESTED, EMERGENCY_CLOSE_REQUESTED, _CLOSE_ATTEMPTED
    if not _CLOSE_ATTEMPTED:
        EMERGENCY_CLOSE_REQUESTED = True
        _CLOSE_ATTEMPTED = True
        print("\nEmergency close requested. Press Ctrl+C again to force shutdown.")
    else:
        SHUTDOWN_REQUESTED = True
        print("\nForce shutdown requested.")


class SmartGridBot:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.logger = Logger()
        self.defaults_manager = DefaultsManager()
        self.config: Optional[AppConfig] = None
        self.mt5_connection: Optional[MT5Connection] = None
        self.account_service = AccountService()
        self.market_data = MarketData()
        self.order_service = OrderService()
        self.position_service = PositionService()
        self.history_service = HistoryService()
        self.atr_calc = ATRCalculator()
        self.grid_builder = GridBuilder()
        self.target_calc = TargetCalculator()
        self.basket_manager = BasketManager()
        self.commission_service = CommissionService()
        self.symbol_manager = SymbolManager()
        self.persistence = Persistence()
        self.dashboard = LiveDashboard(self.commission_service)
        self.cycle_manager = None
        self.bot_start_time = datetime.now()
        self._last_dashboard_render = 0.0

    def run(self):
        global SHUTDOWN_REQUESTED, SHUTDOWN_MODE
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        Console.print_banner()
        self.persistence.initialize()
        config = self._resolve_config()
        if config is None:
            print("No configuration available. Exiting.")
            return
        self.config = config
        mt5_cfg = self._build_mt5_config(config)
        self.mt5_connection = MT5Connection(mt5_cfg)
        success, msg = self.mt5_connection.initialize()
        if not success:
            self.logger.error(f"MT5 connection failed: {msg}")
            print(f"ERROR: {msg}")
            return
        is_hedging, hedge_msg = self.account_service.check_hedging_account()
        if not is_hedging:
            self.logger.error(hedge_msg)
            print(f"ERROR: {hedge_msg}")
            self.mt5_connection.shutdown()
            return
        self.cycle_manager = CycleManager(
            app_settings=config.application,
            market_data=self.market_data,
            order_service=self.order_service,
            position_service=self.position_service,
            history_service=self.history_service,
            atr_calc=self.atr_calc,
            grid_builder=self.grid_builder,
            target_calc=self.target_calc,
            basket_manager=self.basket_manager,
        )
        self.symbol_manager.initialize_from_config(config)
        recovery = RecoveryService(
            grid_builder=self.grid_builder,
            basket_manager=self.basket_manager,
            order_service=self.order_service,
            position_service=self.position_service,
        )
        contexts = self.symbol_manager.get_all_contexts()
        recovery.recover_contexts(contexts)
        if config.application.dry_run:
            print("\nDRY RUN mode enabled. No real orders will be placed.\n")
        else:
            if not self.args.yes:
                if not Console.ask_yes_no("Start live trading with the selected configuration?", default=False):
                    print("Trading not started. Exiting.")
                    self.mt5_connection.shutdown()
                    return
            print("\nStarting live trading...\n")
        self.logger.info("Bot started", mode="DRY RUN" if config.application.dry_run else "LIVE")
        try:
            self._event_loop()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _resolve_config(self) -> Optional[AppConfig]:
        if self.args.config:
            cfg = load_config(self.args.config)
            if cfg:
                return cfg
            print(f"ERROR: Config file not found: {self.args.config}")
            return None
        if self.args.yes:
            if self.defaults_manager.exists():
                cfg = self.defaults_manager.load()
                if cfg:
                    return cfg
                print("ERROR: --yes specified but saved defaults are invalid.")
                return None
            print("ERROR: --yes specified but no saved defaults found.")
            return None
        if self.args.dry_run:
            if self.defaults_manager.exists():
                cfg = self.defaults_manager.load()
                if cfg:
                    cfg.application.dry_run = True
                    return cfg
        if not self.defaults_manager.exists():
            setup = InteractiveSetup(mt5_connection=self.mt5_connection)
            cfg = setup.run_wizard(self.defaults_manager)
            return cfg
        return self._handle_later_run()

    def _handle_later_run(self) -> Optional[AppConfig]:
        cfg = self.defaults_manager.load()
        if cfg is None:
            print("ERROR: Saved configuration is invalid. Starting fresh setup.")
            setup = InteractiveSetup(mt5_connection=self.mt5_connection)
            return setup.run_wizard(self.defaults_manager)
        Console.print_banner()
        print("\nSaved default configuration found.\n")
        headers = ["Symbol", "Grid Count", "Lot Size", "ATR TF", "Commission", "Target", "Magic"]
        rows = []
        for sc in cfg.symbols:
            if sc.enabled:
                rows.append([sc.name, str(sc.grid_count), f"{sc.lot_size:.2f}",
                            sc.atr_timeframe, f"{sc.commission_per_position:.2f}",
                            f"{sc.target_profit:.2f}", str(sc.magic_number)])
        Console.print_table(headers, rows)
        print()
        option = Console.ask_option(
            "Select an option",
            [
                "Run with saved settings",
                "Edit settings for this run only",
                "Edit and save as new defaults",
                "Create a completely new configuration",
                "Exit",
            ],
            default=1,
        )
        if option == 5:
            print("Exiting. No orders were sent.")
            sys.exit(0)
        if option == 4:
            setup = InteractiveSetup(mt5_connection=self.mt5_connection)
            new_cfg = setup.run_wizard(self.defaults_manager)
            return new_cfg
        if option == 3:
            setup = InteractiveSetup()
            edited = setup.edit_wizard(cfg)
            print()
            if Console.ask_yes_no("Save edited configuration as the new default?", default=True):
                self.defaults_manager.save(edited)
                print("Defaults updated.")
            return edited
        if option == 2:
            setup = InteractiveSetup()
            edited = setup.edit_wizard(cfg)
            return edited
        if option == 1:
            return cfg
        return cfg

    def _build_mt5_config(self, config: AppConfig) -> MT5Config:
        mt5_cfg = config.mt5
        if mt5_cfg.login is None:
            login_str = os.getenv("MT5_LOGIN")
            mt5_cfg.login = int(login_str) if login_str else None
        if mt5_cfg.server is None:
            mt5_cfg.server = os.getenv("MT5_SERVER")
        if mt5_cfg.password is None:
            mt5_cfg.password = os.getenv("MT5_PASSWORD")
        if mt5_cfg.terminal_path is None:
            mt5_cfg.terminal_path = os.getenv("MT5_TERMINAL_PATH")
        return mt5_cfg

    def _event_loop(self):
        global SHUTDOWN_REQUESTED, EMERGENCY_CLOSE_REQUESTED
        config = self.config
        while not SHUTDOWN_REQUESTED:
            try:
                if self._check_emergency_close():
                    self.logger.info("EMERGENCY CLOSE: closing all positions and cancelling all orders")
                    for ctx_cfg in config.symbols:
                        if not ctx_cfg.enabled:
                            continue
                        sc = self.symbol_manager.get_context(ctx_cfg.name)
                        if sc is None:
                            continue
                        sm = self.cycle_manager.get_state_machine(sc.name)
                        if sm.state in (SymbolState.STOPPED, SymbolState.ERROR):
                            continue
                        sm.transition_to(SymbolState.CLOSING)
                        sc.last_event = "Emergency close"
                    EMERGENCY_CLOSE_REQUESTED = False
                connected = self.mt5_connection.ensure_connected()
                if not connected:
                    self.logger.warning("MT5 connection lost, retrying...")
                    time.sleep(1)
                    continue
                for ctx_cfg in config.symbols:
                    if not ctx_cfg.enabled:
                        continue
                    sc = self.symbol_manager.get_context(ctx_cfg.name)
                    if sc is None:
                        continue
                    if sc.state in (SymbolState.STOPPED, SymbolState.ERROR):
                        continue
                    self.cycle_manager.process_symbol(ctx_cfg, sc, config.application.dry_run)
                now = time.time()
                if now - self._last_dashboard_render >= config.application.dashboard_refresh_seconds:
                    self._render_dashboard()
                    self._last_dashboard_render = now
                time.sleep(config.application.polling_interval_seconds)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error("Event loop error", error=str(e))
                time.sleep(1)

    def _render_dashboard(self):
        config = self.config
        contexts = self.symbol_manager.get_all_contexts()
        account_info = self.account_service.get_account_info() or {}
        snapshot = AccountSnapshot(
            login=account_info.get("login", 0),
            server=account_info.get("server", ""),
            currency=account_info.get("currency", "USD"),
            balance=account_info.get("balance", 0.0),
            equity=account_info.get("equity", 0.0),
            margin=account_info.get("margin", 0.0),
            free_margin=account_info.get("margin_free", 0.0),
            margin_level=account_info.get("margin_level"),
            connected=self.mt5_connection.is_connected(),
            mode="DRY RUN" if config.application.dry_run else "LIVE",
            bot_start_time=self.bot_start_time,
            runtime_seconds=(datetime.now() - self.bot_start_time).total_seconds(),
        )
        total_gross = 0.0
        total_commission = 0.0
        total_positions = 0
        total_orders = 0
        for ctx in contexts:
            positions = self.position_service.get_open_positions(ctx.name, ctx.magic_number)
            for p in positions:
                total_gross += p.get("profit", 0.0)
                total_commission += ctx.commission_per_position
                total_positions += 1
            pending = self.order_service.get_open_orders(ctx.name, ctx.magic_number)
            total_orders += len(pending)
        snapshot.total_floating_gross_pnl = total_gross
        snapshot.estimated_total_commission = total_commission
        snapshot.estimated_net_pnl = total_gross - total_commission
        snapshot.active_symbol_count = len([c for c in contexts if c.state != SymbolState.STOPPED])
        snapshot.open_position_count = total_positions
        snapshot.pending_order_count = total_orders
        enabled_configs = [s for s in config.symbols if s.enabled]
        self.dashboard.render(
            account=snapshot,
            symbol_contexts=contexts,
            symbol_configs=enabled_configs,
            bot_start_time=self.bot_start_time,
            mode=snapshot.mode,
            connected=snapshot.connected,
        )

    def _check_emergency_close(self) -> bool:
        global EMERGENCY_CLOSE_REQUESTED
        try:
            import msvcrt
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key.lower() == b'c':
                    self.logger.info("Emergency close triggered via keyboard")
                    return True
        except ImportError:
            pass
        return EMERGENCY_CLOSE_REQUESTED

    def _shutdown(self):
        self.logger.info("Bot shutting down")
        try:
            results = self.persistence.get_all_cycle_records() if hasattr(self, 'persistence') else []
            if results:
                total_gross = sum(r.gross_profit or 0.0 for r in results)
                total_net = sum(r.net_profit or 0.0 for r in results)
                total_commission = sum(r.estimated_commission or 0.0 for r in results)
                closed = sum(1 for r in results if r.exit_reason and r.exit_reason != "UNKNOWN")
                self.logger.info("=== FINAL REPORT ===", cycles=len(results), closed=closed,
                                 gross=f"{total_gross:.2f}", commission=f"{total_commission:.2f}",
                                 net=f"{total_net:.2f}")
                print(f"\n=== FINAL REPORT ===")
                print(f"Cycles completed: {closed} / {len(results)}")
                print(f"Total gross profit: {total_gross:.2f}")
                print(f"Total net profit: {total_net:.2f}")
        except Exception as e:
            self.logger.error("Failed to generate final report", error=str(e))
        if self.mt5_connection:
            self.mt5_connection.shutdown()
        self.persistence.close()
        print("\nBot stopped. Existing positions have been left unchanged.")
        print("State saved.")


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-Symbol Smart ATR Grid Trading Bot")
    parser.add_argument("--yes", action="store_true", help="Skip final confirmation")
    parser.add_argument("--config", type=str, help="Path to custom configuration file")
    parser.add_argument("--dry-run", action="store_true", help="Calculate and display without sending orders")
    return parser.parse_args()


def main():
    args = parse_args()
    bot = SmartGridBot(args)
    bot.run()


if __name__ == "__main__":
    main()
