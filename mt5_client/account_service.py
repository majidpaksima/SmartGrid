import time
from typing import Optional, Tuple
from utils.logger import Logger


class AccountService:
    def __init__(self):
        self.logger = Logger()

    def get_account_info(self) -> Optional[dict]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None
        try:
            info = mt5.account_info()
            if info is None:
                return None
            return {
                "login": info.login,
                "server": info.server,
                "currency": info.currency,
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "margin_free": info.margin_free,
                "margin_level": info.margin_level,
                "trade_mode": info.trade_mode,
                "margin_mode": info.margin_mode,
                "leverage": info.leverage,
                "limit_orders": info.limit_orders,
            }
        except Exception as e:
            self.logger.error("Failed to get account info", error=str(e))
            return None

    def check_hedging_account(self) -> Tuple[bool, str]:
        info = self.get_account_info()
        if info is None:
            return False, "Cannot read account information."
        margin_mode = info.get("margin_mode", 0)
        if margin_mode == 1:
            return False, (
                "This strategy requires an MT5 Hedging account. "
                "The connected account uses Netting mode. "
                "No orders were sent."
            )
        if margin_mode == 2:
            return True, "Hedging account detected."
        if margin_mode == 3:
            return True, "Hedging account detected (retail hedging)."
        return True, "Account margin mode accepted."

    def get_account_snapshot(self) -> dict:
        info = self.get_account_info()
        if info is None:
            return {}
        return info
