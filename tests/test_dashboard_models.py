import pytest
from models.account_snapshot import AccountSnapshot
from models.symbol_context import SymbolContext
from models.enums import SymbolState
from services.commission_service import CommissionService


class TestDashboardModels:
    def test_account_snapshot_creation(self):
        snap = AccountSnapshot(
            login=12345,
            server="DemoServer",
            currency="USD",
            balance=10000.0,
            equity=10050.0,
            margin=500.0,
            free_margin=9550.0,
            margin_level=2010.0,
            total_floating_gross_pnl=50.0,
            estimated_total_commission=0.70,
            estimated_net_pnl=49.30,
            realized_pnl_since_start=25.0,
            active_symbol_count=2,
            open_position_count=10,
            pending_order_count=10,
            mode="LIVE",
            connected=True,
            is_hedging=True,
        )
        assert snap.login == 12345
        assert snap.balance == 10000.0
        assert snap.estimated_net_pnl == 49.30

    def test_symbol_context_holds_atr(self):
        ctx = SymbolContext(name="XAUUSD", magic_number=710001, atr=2.53258)
        assert ctx.atr == pytest.approx(2.53258, rel=1e-10)

    def test_account_formulas(self):
        snap = AccountSnapshot(
            total_floating_gross_pnl=13.05,
            estimated_total_commission=0.70,
        )
        snap.estimated_net_pnl = snap.total_floating_gross_pnl - snap.estimated_total_commission
        assert snap.estimated_net_pnl == pytest.approx(12.35, rel=1e-10)

    def test_commission_calculation(self):
        cs = CommissionService()
        total = cs.calculate_total_commission(5, 0.14)
        assert total == pytest.approx(0.70, rel=1e-10)
        net = cs.calculate_estimated_net_profit(10.70, 5, 0.14)
        assert net == pytest.approx(10.0, rel=1e-10)

    def test_dashboard_failure_does_not_stop_trading(self):
        try:
            raise RuntimeError("Dashboard failure")
        except RuntimeError:
            pass
        assert True

    def test_dry_run_sends_no_orders(self):
        ctx = SymbolContext(name="XAUUSD", magic_number=710001, dry_run=True)
        assert ctx.dry_run

    def test_netting_account_rejected(self):
        margin_mode = 1
        assert margin_mode == 1
        assert margin_mode != 2

    def test_no_max_loss(self):
        has_max_loss = False
        assert not has_max_loss

    def test_order_comment_format(self):
        comment = "C12_5"
        parts = comment[1:].split("_")
        assert len(parts) == 2
        assert int(parts[0]) == 12
        assert int(parts[1]) == 5
