"""
outcome_tracker.py — Outcome Tracking Module
Memantau trade PENDING dan mengupdate statusnya (WIN_TP1, WIN_TP2, LOSS, EXPIRED).
"""

from src.config import MAX_TRADE_DURATION_CANDLES
from src.database.db import get_pending_trades, update_trade_result_by_id

import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger("xauusd_bot")


def evaluate_outcomes(
    trades: list[dict],
    current_high: float,
    current_low: float,
    current_time: datetime | None = None,
) -> tuple[list[dict], bool]:
    """
    Fungsi evaluasi murni tanpa I/O file, agar dapat digunakan backtester secara in-memory.
    """
    updated_trades = []
    changes_made = False

    if current_time is None:
        current_time = datetime.now()

    for t in trades:
        if t.get("result", "") != "PENDING":
            continue

        side = t.get("side", "")
        sl = float(t.get("sl", 0))
        tp1 = float(t.get("tp1", 0))
        tp2 = float(t.get("tp2", 0))

        trade_time_str = t.get("time")
        try:
            trade_time = datetime.fromisoformat(trade_time_str)
            # Menghitung estimasi "candle umur" berdasarkan delta waktu.
            delta_mins = (current_time - trade_time).total_seconds() / 60.0
            age_candles = delta_mins / 5.0
        except Exception:
            age_candles = 0

        old_result = "PENDING"
        new_result = "PENDING"

        if "BUY" in side:
            if current_low <= sl:
                new_result = "LOSS"
            elif current_high >= tp2:
                new_result = "WIN_TP2"
            elif current_high >= tp1:
                new_result = "WIN_TP1"
        elif "SELL" in side:
            if current_high >= sl:
                new_result = "LOSS"
            elif current_low <= tp2:
                new_result = "WIN_TP2"
            elif current_low <= tp1:
                new_result = "WIN_TP1"

        # Expired check
        if new_result == "PENDING" and age_candles > MAX_TRADE_DURATION_CANDLES:
            new_result = "EXPIRED"

        if new_result != old_result:
            t["result"] = new_result
            updated_trades.append(t)
            changes_made = True
            logger.info(f"Outcome Tracker: Trade {side} updated to {new_result}")

    return updated_trades, changes_made


def update_outcomes(df_trigger: pd.DataFrame) -> list[dict]:
    """
    Mengevaluasi trade PENDING berdasarkan pergerakan harga terbaru (High/Low).
    Jika menyentuh SL -> LOSS, TP2 -> WIN_TP2, dsb.
    Returns: List of updated trades (dict) for notifications.
    """
    if df_trigger is None or df_trigger.empty:
        return []

    trades = get_pending_trades()
    if not trades:
        return []

    current_high = df_trigger["high"].iloc[-1]
    current_low = df_trigger["low"].iloc[-1]

    updated_trades, changes_made = evaluate_outcomes(
        trades, current_high, current_low, current_time=None
    )

    if changes_made:
        for t in updated_trades:
            # Hitung mock pnl
            pnl = 0.0
            if "WIN_TP1" in t["result"]:
                pnl = t.get("risk", 0) * 1.5
            elif "WIN_TP2" in t["result"]:
                pnl = t.get("risk", 0) * 4.0
            elif "LOSS" in t["result"]:
                pnl = -t.get("risk", 0)

            try:
                update_trade_result_by_id(t["id"], t["result"], pnl)
            except Exception as e:
                logger.error(
                    f"Failed to update trade outcome to DB for trade ID {t.get('id')}: {e}"
                )

    return updated_trades
