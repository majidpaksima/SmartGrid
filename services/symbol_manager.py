from typing import Dict, List, Optional
from models.symbol_context import SymbolContext
from config.models import SymbolConfig, AppConfig


class SymbolManager:
    def __init__(self):
        self._contexts: Dict[str, SymbolContext] = {}

    def initialize_from_config(self, config: AppConfig):
        for sc in config.symbols:
            self._contexts[sc.name] = SymbolContext(
                name=sc.name,
                magic_number=sc.magic_number,
                grid_count=sc.grid_count,
                lot_size=sc.lot_size,
                commission_per_position=sc.commission_per_position,
                target_profit=sc.target_profit,
                atr_timeframe=sc.atr_timeframe,
                atr_period=sc.atr_period,
                dry_run=config.application.dry_run,
                atr_ok=not sc.atr_filter_enabled,
            )

    def get_context(self, symbol: str) -> Optional[SymbolContext]:
        return self._contexts.get(symbol)

    def get_all_contexts(self) -> List[SymbolContext]:
        return list(self._contexts.values())

    def get_active_contexts(self) -> List[SymbolContext]:
        return [ctx for ctx in self._contexts.values()
                if ctx.state.value not in ("STOPPED", "ERROR")]

    def get_symbol_names(self) -> List[str]:
        return list(self._contexts.keys())

    def update_from_config(self, ctx: SymbolContext, cfg: SymbolConfig):
        ctx.magic_number = cfg.magic_number
        ctx.grid_count = cfg.grid_count
        ctx.lot_size = cfg.lot_size
        ctx.commission_per_position = cfg.commission_per_position
        ctx.target_profit = cfg.target_profit
        ctx.atr_timeframe = cfg.atr_timeframe
        ctx.atr_period = cfg.atr_period
