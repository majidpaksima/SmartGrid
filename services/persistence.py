import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from models.cycle import CycleRecord
from models.grid_order import GridOrderRecord
from models.enums import CycleStatus, OrderStatus


class Persistence:
    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS application_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT,
                end_time TEXT,
                mode TEXT,
                account_login INTEGER,
                server TEXT,
                selected_config_path TEXT,
                shutdown_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                magic_number INTEGER,
                cycle_number INTEGER,
                status TEXT,
                state TEXT,
                start_time TEXT,
                end_time TEXT,
                anchor_price REAL,
                atr REAL,
                calculated_grid_step REAL,
                effective_grid_step REAL,
                grid_count INTEGER,
                lot_size REAL,
                target_profit REAL,
                commission_per_position REAL,
                trigger_ticket INTEGER,
                target_price REAL,
                exit_reason TEXT,
                gross_profit REAL,
                estimated_commission REAL,
                realized_profit REAL,
                net_profit REAL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER,
                symbol TEXT,
                magic_number INTEGER,
                cycle_number INTEGER,
                grid_number INTEGER,
                order_type INTEGER,
                requested_price REAL,
                executed_price REAL,
                volume REAL,
                comment TEXT,
                status TEXT,
                created_at TEXT,
                filled_at TEXT,
                cancelled_at TEXT
            );

            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER,
                symbol TEXT,
                magic_number INTEGER,
                cycle_number INTEGER,
                grid_number INTEGER,
                position_type INTEGER,
                open_price REAL,
                close_price REAL,
                volume REAL,
                open_time TEXT,
                close_time TEXT,
                gross_profit REAL,
                estimated_commission REAL,
                net_profit REAL,
                close_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                cycle_number INTEGER,
                state TEXT,
                event_type TEXT,
                message TEXT,
                details_json TEXT
            );

            CREATE TABLE IF NOT EXISTS saved_configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                updated_at TEXT,
                config_path TEXT,
                config_hash TEXT,
                is_default INTEGER DEFAULT 0
            );
        """)
        self.conn.commit()

    def save_cycle(self, cycle: CycleRecord) -> int:
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO cycles (symbol, magic_number, cycle_number, status, state,
                start_time, end_time, anchor_price, atr, calculated_grid_step,
                effective_grid_step, grid_count, lot_size, target_profit,
                commission_per_position, trigger_ticket, target_price, exit_reason,
                gross_profit, estimated_commission, realized_profit, net_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cycle.symbol, cycle.magic_number, cycle.cycle_number, cycle.status.value,
            cycle.state, _dt_str(cycle.start_time), _dt_str(cycle.end_time),
            cycle.anchor_price, cycle.atr, cycle.calculated_grid_step,
            cycle.effective_grid_step, cycle.grid_count, cycle.lot_size,
            cycle.target_profit, cycle.commission_per_position, cycle.trigger_ticket,
            cycle.target_price, cycle.exit_reason, cycle.gross_profit,
            cycle.estimated_commission, cycle.realized_profit, cycle.net_profit,
        ))
        self.conn.commit()
        cycle.id = c.lastrowid
        return cycle.id

    def save_order(self, order: GridOrderRecord):
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO orders (ticket, symbol, magic_number, cycle_number, grid_number,
                order_type, requested_price, executed_price, volume, comment, status,
                created_at, filled_at, cancelled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order.ticket, order.symbol, order.magic_number, order.cycle_number,
            order.grid_number, order.order_type, order.requested_price,
            order.executed_price, order.volume, order.comment, order.status.value,
            _dt_str(order.created_at), _dt_str(order.filled_at), _dt_str(order.cancelled_at),
        ))
        self.conn.commit()

    def save_event(self, symbol: str, cycle_number: int, state: str,
                   event_type: str, message: str, details: dict = None):
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO events (timestamp, symbol, cycle_number, state, event_type, message, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(), symbol, cycle_number, state,
            event_type, message, json.dumps(details) if details else None,
        ))
        self.conn.commit()

    def get_last_cycle(self, symbol: str, magic: int) -> Optional[CycleRecord]:
        c = self.conn.cursor()
        c.execute("""
            SELECT * FROM cycles WHERE symbol = ? AND magic_number = ?
            ORDER BY cycle_number DESC LIMIT 1
        """, (symbol, magic))
        row = c.fetchone()
        if row:
            return _row_to_cycle(row)
        return None

    def get_all_cycles(self, symbol: str = "", magic: int = 0) -> List[CycleRecord]:
        c = self.conn.cursor()
        if symbol and magic:
            c.execute("SELECT * FROM cycles WHERE symbol = ? AND magic_number = ? ORDER BY id",
                      (symbol, magic))
        elif symbol:
            c.execute("SELECT * FROM cycles WHERE symbol = ? ORDER BY id", (symbol,))
        else:
            c.execute("SELECT * FROM cycles ORDER BY id")
        return [_row_to_cycle(row) for row in c.fetchall()]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


def _dt_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _row_to_cycle(row) -> CycleRecord:
    return CycleRecord(
        id=row["id"],
        symbol=row["symbol"],
        magic_number=row["magic_number"],
        cycle_number=row["cycle_number"],
        status=CycleStatus(row["status"]) if row["status"] else CycleStatus.PENDING,
        state=row["state"] or "IDLE",
        start_time=_parse_dt(row["start_time"]),
        end_time=_parse_dt(row["end_time"]),
        anchor_price=row["anchor_price"],
        atr=row["atr"],
        calculated_grid_step=row["calculated_grid_step"],
        effective_grid_step=row["effective_grid_step"],
        grid_count=row["grid_count"] or 5,
        lot_size=row["lot_size"] or 0.01,
        target_profit=row["target_profit"] or 10.0,
        commission_per_position=row["commission_per_position"] or 0.0,
        trigger_ticket=row["trigger_ticket"],
        target_price=row["target_price"],
        exit_reason=row["exit_reason"],
        gross_profit=row["gross_profit"],
        estimated_commission=row["estimated_commission"],
        realized_profit=row["realized_profit"],
        net_profit=row["net_profit"],
    )


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
