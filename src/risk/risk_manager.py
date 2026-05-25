"""
risk_manager.py — Risk Management Module
SL/TP calculation, risk validation, dan trade logging.
"""

import json
import logging
from datetime import datetime
from src.config import (
    MIN_RISK,
    MAX_RISK,
    SL_BUFFER,
    TP1_MULTIPLIER,
    TP2_MULTIPLIER,
)

logger = logging.getLogger("xauusd_bot")
TRADE_LOG = "trade_history.json"


def validate_risk(risk: float) -> tuple[bool, str]:
    """
    Cek apakah jarak SL masuk range yang acceptable.
    Returns: (is_valid, reason)
    """
    if risk < MIN_RISK:
        return False, f"Risk terlalu kecil: ${risk:.2f} < ${MIN_RISK} (noise territory)"
    if risk > MAX_RISK:
        return (
            False,
            f"Risk terlalu besar: ${risk:.2f} > ${MAX_RISK} (sinyal terlalu jauh)",
        )
    return True, "OK"


def calculate_sl_tp(
    side: str,
    entry_price: float,
    extreme_price: float,
) -> dict:
    """
    Hitung SL (dengan buffer) dan TP (2R/4R).
    Pastikan SL selalu di sisi yang benar:
      - BUY  → SL harus DI BAWAH entry
      - SELL → SL harus DI ATAS entry
    Returns dict dengan sl, tp1, tp2, risk.
    """
    if "BUY" in side:
        # SL di bawah entry
        sl = round(extreme_price - SL_BUFFER, 2)
        # Safety: jika SL malah di atas entry (karena near-sweep), perbaiki
        if sl >= entry_price:
            sl = round(
                entry_price - SL_BUFFER - 1.0, 2
            )  # Fallback: $1.5 di bawah entry
            logger.warning(
                f"SL corrected for BUY: extreme={extreme_price}, new SL={sl}"
            )
        risk = abs(entry_price - sl)
        tp1 = round(entry_price + (TP1_MULTIPLIER * risk), 2)
        tp2 = round(entry_price + (TP2_MULTIPLIER * risk), 2)
    else:
        # SL di atas entry
        sl = round(extreme_price + SL_BUFFER, 2)
        # Safety: jika SL malah di bawah entry, perbaiki
        if sl <= entry_price:
            sl = round(entry_price + SL_BUFFER + 1.0, 2)  # Fallback: $1.5 di atas entry
            logger.warning(
                f"SL corrected for SELL: extreme={extreme_price}, new SL={sl}"
            )
        risk = abs(entry_price - sl)
        tp1 = round(entry_price - (TP1_MULTIPLIER * risk), 2)
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
):
    """
    Simpan detail trade ke JSON file untuk tracking performa.
    """
    trade = {
        "time": datetime.now().isoformat(),
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "confluence_score": confluence_score,
        "bias": bias,
        "result": "PENDING",
    }

    try:
        with open(TRADE_LOG, "r") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    history.append(trade)

    try:
        with open(TRADE_LOG, "w") as f:
            json.dump(history, f, indent=2)
        logger.info(f"Trade logged: {side} @ {entry}")
    except Exception as e:
        logger.error(f"Failed to log trade: {e}")
