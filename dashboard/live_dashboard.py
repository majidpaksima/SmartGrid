import sys
from datetime import datetime, timedelta
from typing import List
from models.symbol_context import SymbolContext
from models.account_snapshot import AccountSnapshot
from config.models import SymbolConfig
from services.commission_service import CommissionService
from utils.logger import Logger


class LiveDashboard:
    def __init__(self, commission_service: CommissionService):
        self.commission_service = commission_service
        self.logger = Logger()
        self._first_render = True

    def render(
        self,
        account: AccountSnapshot,
        symbol_contexts: List[SymbolContext],
        symbol_configs: List[SymbolConfig],
        bot_start_time: datetime,
        mode: str,
        connected: bool,
    ):
        try:
            self._render(account, symbol_contexts, symbol_configs, bot_start_time, mode, connected)
        except Exception as e:
            self.logger.error("Dashboard render failed", error=str(e))

    def _render(
        self,
        account: AccountSnapshot,
        symbol_contexts: List[SymbolContext],
        symbol_configs: List[SymbolConfig],
        bot_start_time: datetime,
        mode: str,
        connected: bool,
    ):
        lines = self._build_lines(account, symbol_contexts, bot_start_time, mode, connected)
        output = "\n".join(lines)
        if self._first_render:
            self._first_render = False
            sys.stdout.write(output + "\n")
            sys.stdout.flush()
        else:
            sys.stdout.write("\033[1;1H")
            sys.stdout.write(output)
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _build_lines(
        self,
        account: AccountSnapshot,
        symbol_contexts: List[SymbolContext],
        bot_start_time: datetime,
        mode: str,
        connected: bool,
    ) -> List[str]:
        runtime = str(timedelta(seconds=int((datetime.now() - bot_start_time).total_seconds())))
        conn_status = "CONNECTED" if connected else "DISCONNECTED"
        lines = [f"SMART GRID BOT | {mode}"]
        lines.append(f"Login: {account.login} | Server: {account.server} | Currency: {account.currency}")
        lines.append(f"Balance: {account.balance:.2f} | Equity: {account.equity:.2f}")
        lines.append(f"Margin: {account.margin:.2f} | Free: {account.free_margin:.2f}")
        ml = f"{account.margin_level:.2f}%" if account.margin_level else "-"
        lines.append(f"Margin Level: {ml}")
        lines.append(f"Gross PnL: {account.total_floating_gross_pnl:.2f} | Commission: {account.estimated_total_commission:.2f} | Net PnL: {account.estimated_net_pnl:.2f}")
        lines.append(f"Realized PnL: {account.realized_pnl_since_start:.2f}")
        lines.append(f"Symbols: {account.active_symbol_count} | Positions: {account.open_position_count} | Orders: {account.pending_order_count}")
        lines.append(f"Runtime: {runtime} | {conn_status} | press Ctrl+C for emergency close")
        lines.append("-" * 120)
        header = (
            f"{'Symbol':10s} {'State':16s} {'Cycle':5s} {'Buy':4s} {'Sell':4s} "
            f"{'ATR':12s} {'Target':10s} {'TP':10s} {'Flt PnL':8s} {'Event':25s}"
        )
        lines.append(header)
        lines.append("-" * 120)
        for ctx in symbol_contexts:
            atr_str = f"{ctx.atr:.6f}" if ctx.atr is not None else "-"
            target_str = f"{ctx.target_price:.5f}" if ctx.target_price else "-"
            event_str = ctx.last_event[:25] if ctx.last_event else ""
            flt_pnl = "-"
            lines.append(
                f"{ctx.name:10s} {ctx.state.value:16s} {str(ctx.cycle_number):5s} "
                f"{str(ctx.buy_count):4s} {str(ctx.sell_count):4s} "
                f"{atr_str:12s} {target_str:10s} {'-':10s} {flt_pnl:8s} {event_str:25s}"
            )
        return lines
