from typing import Optional, Tuple
from config.models import MT5Config
from utils.logger import Logger


class MT5Connection:
    def __init__(self, config: Optional[MT5Config] = None):
        self.config = config
        self.logger = Logger()
        self._connected = False

    def initialize(self, config: Optional[MT5Config] = None) -> Tuple[bool, str]:
        if config:
            self.config = config
        if not self.config:
            return False, "No MT5 configuration provided."
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return False, "MetaTrader5 package is not installed. Run: pip install MetaTrader5"
        path = self.config.terminal_path
        login = self.config.login
        server = self.config.server
        password = self.config.password
        if path:
            initialized = mt5.initialize(path=path, timeout=self.config.request_timeout_seconds * 1000)
        else:
            initialized = mt5.initialize(timeout=self.config.request_timeout_seconds * 1000)
        if not initialized:
            error = mt5.last_error()
            return False, f"MT5 initialize failed: {error}"
        if login and server and password:
            authorized = mt5.login(login=login, server=server, password=password)
            if not authorized:
                error = mt5.last_error()
                mt5.shutdown()
                return False, f"MT5 login failed: {error}"
        self._connected = True
        self.logger.info("MT5 connected successfully")
        return True, "Connected"

    def is_connected(self) -> bool:
        if not self._connected:
            return False
        try:
            import MetaTrader5 as mt5
            return mt5.terminal_info() is not None
        except Exception:
            return False

    def shutdown(self):
        if self._connected:
            try:
                import MetaTrader5 as mt5
                mt5.shutdown()
            except Exception:
                pass
            self._connected = False
            self.logger.info("MT5 disconnected")

    def ensure_connected(self) -> bool:
        if self.is_connected():
            return True
        if self.config:
            success, _ = self.initialize()
            return success
        return False
