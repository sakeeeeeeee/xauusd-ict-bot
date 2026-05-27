"""
risk_manager.py — Risk Management Module
SL/TP calculation, risk validation, dan trade logging.
"""

import logging
import pandas as pd
from datetime import datetime
from src.database.db import insert_trade
from src.config import (
    MIN_RISK,
    MAX_RISK,
    SL_BUFFER,
    TP1_MULTIPLIER,
    TP2_MULTIPLIER,
    ATR_MIN_RISK_MULT,
    ATR_MAX_RISK_MULT,
    ATR_SL_BUFFER_MULT,
)

logger = logging.getLogger("xauusd_bot")
# TRADE_LOG = "trade_history.json" # Di-deprecate, pindah ke DB


def validate_risk(risk: float, atr: float = 0.0) -> tuple[bool, str]:
    """
    Cek apakah jarak SL masuk range yang acceptable.
    Jika atr > 0, gunakan kelipatan ATR (fallback ke config dollar jika tidak).
    Returns: (is_valid, reason)
    """
    min_r = (atr * ATR_MIN_RISK_MULT) if atr > 0 else MIN_RISK
    max_r = (atr * ATR_MAX_RISK_MULT) if atr > 0 else MAX_RISK

    if risk < min_r:
        return (
            False,
            f"Risk terlalu kecil: ${risk:.2f} < ${min_r:.2f} (noise territory)",
        )
    if risk > max_r:
        return (
            False,
            f"Risk terlalu besar: ${risk:.2f} > ${max_r:.2f} (sinyal terlalu jauh)",
        )
    return True, "OK"


def calculate_tp_structural(
    df: pd.DataFrame, side: str, entry: float, sl: float
) -> float:
    """
    Hitung TP1 berdasarkan struktur terdekat (Swing High untuk BUY, Swing Low untuk SELL).
    Jika struktur terlalu dekat (< 2R), fallback ke 2R.
    """
    risk = abs(entry - sl)

    if "BUY" in side:
        fallback_tp1 = entry + (TP1_MULTIPLIER * risk)
        if df is not None and not df.empty:
            recent_high = df["high"].max()
            if recent_high > fallback_tp1:
                return round(recent_high, 2)
        return round(fallback_tp1, 2)
    else:
        fallback_tp1 = entry - (TP1_MULTIPLIER * risk)
        if df is not None and not df.empty:
            recent_low = df["low"].min()
            if recent_low < fallback_tp1:
                return round(recent_low, 2)
        return round(fallback_tp1, 2)


def calculate_sl_tp(
    side: str,
    entry_price: float,
    extreme_price: float,
    df: pd.DataFrame = None,
    atr: float = 0.0,
) -> dict:
    """
    Hitung SL (dengan buffer) dan TP.
    TP1 dihitung berdasarkan struktur jika df diberikan (fallback ke default multiplier).
    TP2 tetap menggunakan default multiplier (misal 4R).
    Buffer SL menggunakan kelipatan ATR jika atr > 0, sebaliknya fallback ke default.
    """
    current_sl_buffer = (atr * ATR_SL_BUFFER_MULT) if atr > 0 else SL_BUFFER

    if "BUY" in side:
        sl = round(extreme_price - current_sl_buffer, 2)
        if sl >= entry_price:
            sl = round(entry_price - current_sl_buffer - 1.0, 2)
            logger.warning(
                f"SL corrected for BUY: extreme={extreme_price}, new SL={sl}"
            )
        risk = abs(entry_price - sl)
        tp1 = calculate_tp_structural(df, side, entry_price, sl)
        tp2 = round(entry_price + (TP2_MULTIPLIER * risk), 2)
    else:
        sl = round(extreme_price + current_sl_buffer, 2)
        if sl <= entry_price:
            sl = round(entry_price + current_sl_buffer + 1.0, 2)
            logger.warning(
                f"SL corrected for SELL: extreme={extreme_price}, new SL={sl}"
            )
        risk = abs(entry_price - sl)
        tp1 = calculate_tp_structural(df, side, entry_price, sl)
        tp2 = round(entry_price - (TP2_MULTIPLIER * risk), 2)

    return {
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": round(risk, 2),
    }


def log_trade(
    side: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    risk: float,
    confluence_score: int,
    bias: str,
    tier: str = "UNKNOWN",
    session: str = "UNKNOWN",
    atr: float = 0.0,
    spread: float = 0.0,
    near_sweep: bool = False,
    ifvg_after_sweep: bool = False,
    ticket1: int = None,
    ticket2: int = None,
):
    """
    Simpan detail trade ke JSON file untuk tracking performa.
    Backward compatible v2 schema.
    """
    trade = {
        "version": "v2",
        "time": datetime.now().isoformat(),
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "confluence_score": confluence_score,
        "bias": bias,
        "tier": tier,
        "session": session,
        "atr": atr,
        "spread": spread,
        "near_sweep": near_sweep,
        "ifvg_after_sweep": ifvg_after_sweep,
        "ticket1": ticket1,
        "ticket2": ticket2,
        "result": "PENDING",
    }

    try:
        insert_trade(trade)
        logger.info(f"Trade logged to DB: {side} @ {entry}")
    except Exception as e:
        logger.error(f"Failed to log trade to DB: {e}")
