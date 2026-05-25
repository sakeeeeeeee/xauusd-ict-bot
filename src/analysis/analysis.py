"""
analysis.py — ICT Analysis Engine (AGGRESSIVE MODE)
Sweep detection, IFVG detection, dan HTF Bias detection.
Near-sweep dan independent IFVG untuk lebih banyak sinyal.
"""

import logging
import pandas as pd
import MetaTrader5 as mt5
from src.config import (
    MA_FAST_PERIOD,
    MA_SLOW_PERIOD,
    SWEEP_LOOKBACK,
    SWEEP_CANDLE_WINDOW,
    NEAR_SWEEP_THRESHOLD,
    IFVG_LOOKBACK,
)

logger = logging.getLogger("xauusd_bot")


# ============================================================
#  DATA FETCHER
# ============================================================


def get_data(symbol: str, timeframe: int, n: int = 100) -> pd.DataFrame:
    """
    Fetch candlestick data dari MT5.
    Returns DataFrame kosong jika data tidak cukup.
    CATATAN: mt5.initialize() harus sudah dipanggil sebelumnya.
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)

    if rates is None or len(rates) < max(MA_SLOW_PERIOD + 1, SWEEP_LOOKBACK + 1):
        logger.warning(
            f"Data tidak cukup untuk {symbol} TF={timeframe}. "
            f"Got {len(rates) if rates is not None else 0} candles, "
            f"butuh minimal {max(MA_SLOW_PERIOD + 1, SWEEP_LOOKBACK + 1)}."
        )
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


# ============================================================
#  HTF BIAS DETECTION (Multi-Layer MA)
# ============================================================


def detect_robust_bias(df: pd.DataFrame) -> str:
    """
    Deteksi bias menggunakan dual MA di H4.
    Returns: 'BULLISH', 'BEARISH', atau 'RANGING'
    """
    if df.empty or len(df) < MA_SLOW_PERIOD + 1:
        return "RANGING"

    ma_fast = df["close"].rolling(window=MA_FAST_PERIOD).mean()
    ma_slow = df["close"].rolling(window=MA_SLOW_PERIOD).mean()
    close = df["close"].iloc[-1]

    fast_val = ma_fast.iloc[-1]
    slow_val = ma_slow.iloc[-1]

    # Harga di atas KEDUA MA = BULLISH kuat
    if close > fast_val and close > slow_val:
        return "BULLISH"
    # Harga di bawah KEDUA MA = BEARISH kuat
    elif close < fast_val and close < slow_val:
        return "BEARISH"
    # Mixed = RANGING
    return "RANGING"


# ============================================================
#  LIQUIDITY SWEEP DETECTION (with Near-Sweep)
# ============================================================


def detect_sweep(df: pd.DataFrame) -> tuple[str, float]:
    """
    Deteksi sweep di N candle terakhir.
    Sekarang termasuk NEAR-SWEEP: jika wick mendekati high/low
    dalam threshold, dianggap sebagai sweep juga.
    Returns: (status_string, extreme_price)
    """
    if df.empty or len(df) < SWEEP_LOOKBACK + SWEEP_CANDLE_WINDOW:
        return "Searching...", 0.0

    # === PASS 1: Cari exact sweep dulu ===
    for offset in range(SWEEP_CANDLE_WINDOW):
        idx = -(1 + offset)
        candle = df.iloc[idx]

        lb_end = len(df) + idx
        lb_start = lb_end - SWEEP_LOOKBACK
        if lb_start < 0:
            continue
        lookback = df.iloc[lb_start:lb_end]

        prev_high = lookback["high"].max()
        prev_low = lookback["low"].min()

        # Exact Sweep Buy: Wick tembus low, close kembali di atas
        if candle["low"] < prev_low and candle["close"] > prev_low:
            logger.info(
                f"SWEEP BUY detected (candle -{1 + offset})! "
                f"Low={candle['low']:.2f}, PrevLow={prev_low:.2f}"
            )
            return "SWEEP BUY 💧", candle["low"]

        # Exact Sweep Sell: Wick tembus high, close kembali di bawah
        if candle["high"] > prev_high and candle["close"] < prev_high:
            logger.info(
                f"SWEEP SELL detected (candle -{1 + offset})! "
                f"High={candle['high']:.2f}, PrevHigh={prev_high:.2f}"
            )
            return "SWEEP SELL 💧", candle["high"]

    # === PASS 2: Cari near-sweep (wick mendekati/menyentuh level) ===
    for offset in range(SWEEP_CANDLE_WINDOW):
        idx = -(1 + offset)
        candle = df.iloc[idx]

        lb_end = len(df) + idx
        lb_start = lb_end - SWEEP_LOOKBACK
        if lb_start < 0:
            continue
        lookback = df.iloc[lb_start:lb_end]

        prev_high = lookback["high"].max()
        prev_low = lookback["low"].min()

        # Near-Sweep Buy: Low mendekati/menyentuh prev_low, close harus di atas prev_low
        low_distance = abs(prev_low - candle["low"])
        if low_distance <= NEAR_SWEEP_THRESHOLD and candle["close"] > prev_low:
            logger.info(
                f"NEAR-SWEEP BUY detected (candle -{1 + offset})! "
                f"Low={candle['low']:.2f}, PrevLow={prev_low:.2f}, "
                f"Distance={low_distance:.2f}"
            )
            return "SWEEP BUY 💧", candle["low"]

        # Near-Sweep Sell: High mendekati/menyentuh prev_high, close harus di bawah prev_high
        high_distance = abs(candle["high"] - prev_high)
        if high_distance <= NEAR_SWEEP_THRESHOLD and candle["close"] < prev_high:
            logger.info(
                f"NEAR-SWEEP SELL detected (candle -{1 + offset})! "
                f"High={candle['high']:.2f}, PrevHigh={prev_high:.2f}, "
                f"Distance={high_distance:.2f}"
            )
            return "SWEEP SELL 💧", candle["high"]

    return "Searching...", 0.0


# ============================================================
#  INVERSED FAIR VALUE GAP (IFVG) DETECTION — INDEPENDENT
# ============================================================


def detect_ifvg(df: pd.DataFrame, sweep_status: str) -> tuple[bool, str]:
    """
    Deteksi Inversed FVG — INDEPENDENT dari sweep.
    Scan bearish dan bullish FVG, cek apakah price sudah inverse.
    Returns: (is_ifvg_found, message)
    """
    if len(df) < IFVG_LOOKBACK + 2:
        return False, "No IFVG"

    last_close = df["close"].iloc[-1]

    # Scan FVG dari IFVG_LOOKBACK candle ke belakang
    start_idx = max(0, len(df) - IFVG_LOOKBACK - 2)
    end_idx = len(df) - 2

    # Scan BACKWARDS (dari terbaru ke terlama) untuk mencari IFVG yang paling fresh
    for i in range(end_idx - 1, start_idx - 1, -1):
        c1_low = df["low"].iloc[i]
        c1_high = df["high"].iloc[i]
        c3_low = df["low"].iloc[i + 2]
        c3_high = df["high"].iloc[i + 2]

        # Bearish FVG (gap down): C1_Low > C3_High
        # IFVG BUY = price inverse kembali ke ATAS melewati C1_Low
        if c1_low > c3_high and last_close > c1_low:
            logger.info(f"IFVG BUY found at candle index {i}")
            return True, "IFVG BUY 🧲"

        # Bullish FVG (gap up): C1_High < C3_Low
        # IFVG SELL = price inverse kembali ke BAWAH melewati C1_High
        if c1_high < c3_low and last_close < c1_high:
            logger.info(f"IFVG SELL found at candle index {i}")
            return True, "IFVG SELL 🧲"

    return False, "No IFVG"


# ============================================================
#  CONFLUENCE SCORING
# ============================================================


def calculate_confluence(
    side: str,
    bias: str,
    sweep_status: str,
    ifvg_msg: str,
    is_killzone_active: bool,
) -> int:
    """
    Hitung score konfluensi yang ter-align dengan arah trade.
    Max score = 4.
    Semakin tinggi, semakin kuat setup.
    """
    score = 0
    if is_killzone_active:
        score += 1

    # Bias alignment
    if side == "BUY 🟢":
        if bias == "BULLISH":
            score += 1
        elif bias == "RANGING":
            score += 1
    elif side == "SELL 🔴":
        if bias == "BEARISH":
            score += 1
        elif bias == "RANGING":
            score += 1

    # Sweep alignment
    if side == "BUY 🟢" and "BUY" in sweep_status:
        score += 1
    elif side == "SELL 🔴" and "SELL" in sweep_status:
        score += 1

    # IFVG alignment
    if side == "BUY 🟢" and "BUY" in ifvg_msg:
        score += 1
    elif side == "SELL 🔴" and "SELL" in ifvg_msg:
        score += 1

    return score
