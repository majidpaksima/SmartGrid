from typing import List, Optional
from utils.console import Console
from config.models import AppConfig, SymbolConfig, MT5Config, ApplicationSettings
from config.defaults_manager import DefaultsManager

TIMEFRAME_OPTIONS = [
    "M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15",
    "M20", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12",
    "D1", "W1", "MN1",
]


class InteractiveSetup:
    def __init__(self, mt5_connection=None):
        self.mt5 = mt5_connection

    def run_wizard(self, defaults_manager: DefaultsManager) -> Optional[AppConfig]:
        Console.print_banner()
        print()
        print("No saved trading configuration was found.")
        if not Console.ask_yes_no("Would you like to create a new default configuration?", default=True):
            return None
        available_symbols = self._get_available_symbols()
        if not available_symbols:
            print("ERROR: No available symbols found in MetaTrader 5.")
            print("Please ensure MT5 is connected and symbols are visible.")
            return None
        symbol_configs = []
        used_magics = []
        configured_names = set()
        while True:
            choice = self._select_symbol_name(available_symbols, configured_names, "Select a symbol to configure")
            if choice is None:
                break
            sym_name, sym_info = choice
            if sym_name in configured_names:
                print(f"Symbol {sym_name} is already configured.")
                continue
            if sym_info is None:
                print(f"ERROR: Could not resolve symbol information for {sym_name}.")
                continue
            cfg = self._configure_symbol(sym_name, sym_info, used_magics)
            if cfg:
                symbol_configs.append(cfg)
                used_magics.append(cfg.magic_number)
                configured_names.add(sym_name)
            if len(configured_names) >= len(available_symbols):
                break
            if not Console.ask_yes_no("Do you want to activate another symbol?", default=True):
                break
        if not symbol_configs:
            print("No symbols configured. Exiting.")
            return None
        self._print_summary(symbol_configs)
        if not Console.ask_yes_no("Save this configuration as the default?", default=True):
            return None
        config = AppConfig(
            application=ApplicationSettings(),
            mt5=MT5Config(),
            symbols=symbol_configs,
        )
        defaults_manager.save(config)
        print(f"Configuration saved to {defaults_manager.defaults_path}")
        return config

    def edit_wizard(self, existing_config: AppConfig) -> AppConfig:
        print("Editing configuration...")
        print("Press Enter to keep existing values.")
        new_symbols = list(existing_config.symbols)
        used_magics = [sym.magic_number for sym in new_symbols]
        while True:
            print("\n--- Symbol Management ---")
            self._print_symbol_summary(new_symbols)
            option = Console.ask_option(
                "Select an action",
                [
                    "Edit an existing symbol",
                    "Add new symbol(s)",
                    "Remove a symbol",
                    "Finish editing",
                ],
                default=4,
            )
            if option == 4:
                break
            if option == 1:
                if not new_symbols:
                    print("No symbols available to edit.")
                    continue
                idx = self._select_symbol_index(new_symbols, "Select symbol to edit")
                if idx is None:
                    continue
                current = new_symbols[idx]
                print(f"\nConfiguring {current.name}")
                updated = self._edit_one_symbol(current, [m for i, m in enumerate(used_magics) if i != idx])
                new_symbols[idx] = updated
                used_magics[idx] = updated.magic_number
                continue
            if option == 2:
                remaining = self._remaining_symbols(existing_config.symbols, new_symbols)
                if not remaining:
                    print("No additional symbols available to add.")
                    continue
                selected = self._select_symbols(remaining)
                if not selected:
                    print("No symbols selected.")
                    continue
                for sym_name in selected:
                    sym_info = remaining.get(sym_name)
                    if not sym_info:
                        continue
                    cfg = self._configure_symbol(sym_name, sym_info, used_magics)
                    if cfg:
                        new_symbols.append(cfg)
                        used_magics.append(cfg.magic_number)
                continue
            if option == 3:
                if not new_symbols:
                    print("No symbols available to remove.")
                    continue
                idx = self._select_symbol_index(new_symbols, "Select symbol to remove")
                if idx is None:
                    continue
                removed = new_symbols.pop(idx)
                used_magics.pop(idx)
                print(f"Removed symbol {removed.name}.")
                continue
        config = AppConfig(
            application=existing_config.application,
            mt5=existing_config.mt5,
            symbols=new_symbols,
        )
        self._print_summary(new_symbols)
        return config

    def _edit_one_symbol(self, existing: SymbolConfig, used_magics: List[int]) -> SymbolConfig:
        grid_count = Console.ask_int("Grid count", existing.grid_count, 1, 100)
        lot_size = Console.ask_float("Lot size", existing.lot_size, 0.001, 1000)
        tf_index = TIMEFRAME_OPTIONS.index(existing.atr_timeframe) + 1 if existing.atr_timeframe in TIMEFRAME_OPTIONS else 1
        print(f"ATR timeframe options: {', '.join(TIMEFRAME_OPTIONS)}")
        atr_tf = Console.ask_input("ATR timeframe", existing.atr_timeframe)
        atr_tf = atr_tf.upper() if atr_tf else existing.atr_timeframe
        atr_period = Console.ask_int("ATR period", existing.atr_period, 2, 1000)
        atr_filter = Console.ask_yes_no("Enable ATR entry filter", existing.atr_filter_enabled)
        if atr_filter:
            atr_lookback = Console.ask_int("ATR lookback candles", existing.atr_lookback, 10, 10000)
            atr_slope = Console.ask_int("ATR slope period", existing.atr_slope_period, 2, 100)
        else:
            atr_lookback = existing.atr_lookback
            atr_slope = existing.atr_slope_period
        commission = Console.ask_float("Round-turn commission per position", existing.commission_per_position, 0, 1000)
        target = Console.ask_float("Net basket target profit", existing.target_profit, 0.01, 1e9)
        magic = Console.ask_int("Magic number", existing.magic_number, 1, 999999999)
        while magic in used_magics:
            print(f"Magic number {magic} is already in use. Please choose another.")
            magic = Console.ask_int("Magic number", existing.magic_number, 1, 999999999)
        return SymbolConfig(
            name=existing.name,
            grid_count=grid_count,
            lot_size=lot_size,
            atr_timeframe=atr_tf,
            atr_period=atr_period,
            atr_filter_enabled=atr_filter,
            atr_lookback=atr_lookback,
            atr_slope_period=atr_slope,
            commission_per_position=commission,
            target_profit=target,
            magic_number=magic,
        )

    def _print_symbol_summary(self, symbol_configs: List[SymbolConfig]):
        if not symbol_configs:
            print("No symbols configured.")
            return
        headers = ["#", "Symbol", "Grid", "Lot", "ATR TF", "ATR", "ATR Filt", "Magic"]
        rows = []
        for i, sc in enumerate(symbol_configs, 1):
            rows.append([
                str(i),
                sc.name,
                str(sc.grid_count),
                f"{sc.lot_size:.2f}",
                sc.atr_timeframe,
                str(sc.atr_period),
                "ON" if sc.atr_filter_enabled else "OFF",
                str(sc.magic_number),
            ])
        Console.print_table(headers, rows)

    def _select_symbol_index(self, symbol_configs: List[SymbolConfig], prompt: str) -> Optional[int]:
        if not symbol_configs:
            return None
        print()
        for i, sc in enumerate(symbol_configs, 1):
            print(f"  {i:3d}. {sc.name}")
        idx = Console.ask_int(prompt, 1, 1, len(symbol_configs))
        return idx - 1

    def _remaining_symbols(self, all_symbols: dict, configured_symbols: List[SymbolConfig]) -> dict:
        configured_names = {s.name for s in configured_symbols}
        return {name: info for name, info in all_symbols.items() if name not in configured_names}

    def _get_available_symbols(self) -> dict:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return self._mock_symbols()
        initialized_here = False
        if self.mt5 is None:
            try:
                initialized_here = bool(mt5.initialize())
            except Exception:
                initialized_here = False
        symbols = {}
        try:
            all_syms = mt5.symbols_get()
            if all_syms:
                for s in all_syms:
                    name = s.name
                    mt5.symbol_select(name, True)
                    info = mt5.symbol_info(name)
                    if info and info.trade_mode > 0:
                        symbols[name] = {
                            "digits": info.digits,
                            "tick_size": info.trade_tick_size or info.point,
                            "contract_size": info.trade_contract_size,
                            "volume_min": info.volume_min,
                            "volume_max": info.volume_max,
                            "volume_step": info.volume_step,
                            "trade_stops_level": info.trade_stops_level or 0,
                        }
        except Exception:
            pass
        if initialized_here:
            try:
                mt5.shutdown()
            except Exception:
                pass
        if not symbols:
            return self._mock_symbols()
        return symbols

    def _mock_symbols(self) -> dict:
        return {
            "XAUUSD": {"digits": 5, "tick_size": 0.00001, "contract_size": 100,
                       "volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                       "trade_stops_level": 0},
            "EURUSD": {"digits": 5, "tick_size": 0.00001, "contract_size": 100000,
                       "volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                       "trade_stops_level": 0},
            "GBPUSD": {"digits": 5, "tick_size": 0.00001, "contract_size": 100000,
                       "volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                       "trade_stops_level": 0},
        }

    def _select_symbols(self, available: dict) -> List[str]:
        names = list(available.keys())
        print("\nAvailable symbols:")
        for i, name in enumerate(names, 1):
            print(f"  {i:3d}. {name}")
        print()
        raw = Console.ask_input("Enter symbols separated by commas")
        if not raw.strip():
            return []
        selected = [s.strip().upper() for s in raw.split(",") if s.strip()]
        valid = []
        invalid = []
        for s in selected:
            if s in available:
                valid.append(s)
            else:
                upper_names = {n.upper(): n for n in names}
                if s in upper_names:
                    valid.append(upper_names[s])
                else:
                    invalid.append(s)
        if invalid:
            print(f"Warning: these symbols were not found and will be skipped: {', '.join(invalid)}")
        return valid

    def _select_single_symbol(self, available: dict, prompt: str) -> Optional[str]:
        names = list(available.keys())
        if not names:
            return None
        print("\nAvailable symbols:")
        for i, name in enumerate(names, 1):
            print(f"  {i:3d}. {name}")
        print()
        choice = Console.ask_option(prompt, names, default=1)
        return names[choice - 1]

    def _select_symbol_name(self, available: dict, configured_names: set, prompt: str) -> Optional[tuple]:
        names = [name for name in available.keys() if name not in configured_names]
        if not names:
            raw_name = Console.ask_input("Type a broker symbol manually (or press Enter to finish)")
            if not raw_name.strip():
                return None
            sym_name = raw_name.strip().upper()
            return sym_name, self._get_symbol_metadata(sym_name, available)
        print("\nAvailable symbols:")
        for i, name in enumerate(names, 1):
            print(f"  {i:3d}. {name}")
        print(f"  {len(names) + 1:3d}. Type symbol manually")
        choice = Console.ask_option(prompt, names + ["Type symbol manually"], default=1)
        if choice == len(names) + 1:
            raw_name = Console.ask_input("Enter broker symbol name")
            if not raw_name.strip():
                return None
            sym_name = raw_name.strip().upper()
            return sym_name, self._get_symbol_metadata(sym_name, available)
        sym_name = names[choice - 1]
        return sym_name, available.get(sym_name)

    def _get_symbol_metadata(self, symbol_name: str, available: dict) -> Optional[dict]:
        if symbol_name in available:
            return available[symbol_name]
        if not self.mt5:
            return None
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None
        try:
            mt5.symbol_select(symbol_name, True)
            info = mt5.symbol_info(symbol_name)
            if info and info.trade_mode > 0:
                return {
                    "digits": info.digits,
                    "tick_size": info.trade_tick_size or info.point,
                    "contract_size": info.trade_contract_size,
                    "volume_min": info.volume_min,
                    "volume_max": info.volume_max,
                    "volume_step": info.volume_step,
                    "trade_stops_level": info.trade_stops_level or 0,
                }
        except Exception:
            return None
        return None

    def _configure_symbol(self, name: str, info: dict, used_magics: List[int]) -> Optional[SymbolConfig]:
        print(f"\n--- Configuring {name} ---")
        grid_count = Console.ask_int("Grid count", 5, 1, 100)
        lot_size = Console.ask_float("Lot size", 0.01, 0.001, 1000)
        if info.get("volume_min") and lot_size < info["volume_min"]:
            print(f"Lot size {lot_size} is below minimum {info['volume_min']}. Setting to minimum.")
            lot_size = info["volume_min"]
        if info.get("volume_max") and lot_size > info["volume_max"]:
            print(f"Lot size {lot_size} exceeds maximum {info['volume_max']}. Setting to maximum.")
            lot_size = info["volume_max"]
        print(f"ATR timeframe options: {', '.join(TIMEFRAME_OPTIONS)}")
        atr_tf = Console.ask_input("ATR timeframe", "M5")
        atr_tf = atr_tf.upper() if atr_tf else "M5"
        atr_period = Console.ask_int("ATR period", 14, 2, 1000)
        atr_filter = Console.ask_yes_no("Enable ATR entry filter", True)
        if atr_filter:
            atr_lookback = Console.ask_int("ATR lookback candles", 200, 10, 10000)
            atr_slope = Console.ask_int("ATR slope period", 5, 2, 100)
        else:
            atr_lookback = 200
            atr_slope = 5
        commission = Console.ask_float("Round-turn commission per position", 0.14, 0, 1000)
        target = Console.ask_float("Net basket target profit", 10.00, 0.01, 1e9)
        default_magic = 710000 + len(used_magics)
        magic = Console.ask_int("Magic number", default_magic, 1, 999999999)
        while magic in used_magics:
            print(f"Magic number {magic} is already used by another symbol. Please choose another.")
            magic = Console.ask_int("Magic number", default_magic, 1, 999999999)
        return SymbolConfig(
            name=name,
            grid_count=grid_count,
            lot_size=lot_size,
            atr_timeframe=atr_tf,
            atr_period=atr_period,
            atr_filter_enabled=atr_filter,
            atr_lookback=atr_lookback,
            atr_slope_period=atr_slope,
            commission_per_position=commission,
            target_profit=target,
            magic_number=magic,
        )

    def _print_summary(self, symbol_configs: List[SymbolConfig]):
        print("\n--- Configuration Summary ---")
        headers = ["Symbol", "Grid Count", "Lot Size", "ATR TF", "ATR Period",
                   "ATR Filter", "Commission", "Target", "Magic"]
        rows = []
        for sc in symbol_configs:
            rows.append([
                sc.name,
                str(sc.grid_count),
                f"{sc.lot_size:.2f}",
                sc.atr_timeframe,
                str(sc.atr_period),
                "ON" if sc.atr_filter_enabled else "OFF",
                f"{sc.commission_per_position:.2f}",
                f"{sc.target_profit:.2f}",
                str(sc.magic_number),
            ])
        Console.print_table(headers, rows)
        print()
