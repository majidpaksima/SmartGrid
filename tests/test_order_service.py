import sys
from mt5_client.order_service import OrderService, MT5_RETCODE_PLACED


class TestOrderService:
    def _patch_mt5(self, monkeypatch):
        sent = []

        class FakeResult:
            retcode = MT5_RETCODE_PLACED
            comment = "done"
            order = 123
            volume = 0.01
            price = 4005.0
            request_id = 1

        class FakeMT5:
            @staticmethod
            def order_send(request):
                sent.append(dict(request))
                return FakeResult()

        monkeypatch.setitem(sys.modules, "MetaTrader5", FakeMT5())
        return sent

    def test_send_pending_order_with_retry_forwards_tp(self, monkeypatch):
        sent = self._patch_mt5(monkeypatch)
        svc = OrderService()
        result = svc.send_pending_order_with_retry(
            symbol="XAUUSD",
            order_type=4,
            volume=0.01,
            price=4005.0,
            magic=1,
            comment="C1_1",
            tp=4006.0,
            sl=0.0,
        )
        assert result["retcode"] == MT5_RETCODE_PLACED
        assert len(sent) == 1
        assert sent[0]["tp"] == 4006.0
        assert sent[0]["sl"] == 0.0

    def test_send_pending_order_with_retry_defaults_zero(self, monkeypatch):
        sent = self._patch_mt5(monkeypatch)
        svc = OrderService()
        svc.send_pending_order_with_retry(
            symbol="XAUUSD",
            order_type=5,
            volume=0.01,
            price=3995.0,
            magic=1,
            comment="C1_1",
        )
        assert sent[0]["tp"] == 0.0
        assert sent[0]["sl"] == 0.0

    def test_send_pending_order_forwards_tp(self, monkeypatch):
        sent = self._patch_mt5(monkeypatch)
        svc = OrderService()
        svc.send_pending_order(
            symbol="XAUUSD",
            order_type=4,
            volume=0.01,
            price=4005.0,
            magic=1,
            comment="C1_1",
            tp=4006.0,
            sl=0.0,
        )
        assert sent[0]["tp"] == 4006.0
