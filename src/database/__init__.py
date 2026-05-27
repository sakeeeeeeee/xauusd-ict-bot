"""Database module for XAUUSD Bot."""

from src.database.db import (
    init_db,
    insert_trade,
    update_trade_result,
    update_trade_result_by_id,
    get_all_trades,
    get_pending_trades,
    get_trades_by_date,
    log_scan,
)

__all__ = [
    "init_db",
    "insert_trade",
    "update_trade_result",
    "update_trade_result_by_id",
    "get_all_trades",
    "get_pending_trades",
    "get_trades_by_date",
    "log_scan",
]
