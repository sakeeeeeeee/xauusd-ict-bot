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

    if rates is None or len(rates) < MA_SLOW_PERIOD + 1:
        logger.warning(
            f"Data tidak cukup untuk {symbol} TF={timeframe}. "
            f"Got {len(rates) if rates is not None else 0} candles, "
            f"butuh minimal {MA_SLOW_PERIOD + 1}."
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
    BULLISH = harga di atas kedua MA DAN fast MA > slow MA (trend confirmed).
    BEARISH = harga di bawah kedua MA DAN fast MA < slow MA (trend confirmed).
    Jika MA belum crossover (bouncing melawan tren), tetap RANGING.
    Returns: 'BULLISH', 'BEARISH', atau 'RANGING'
    """
    if df.empty or len(df) < MA_SLOW_PERIOD + 1:
        return "RANGING"

    ma_fast = df["close"].rolling(window=MA_FAST_PERIOD).mean()
    ma_slow = df["close"].rolling(window=MA_SLOW_PERIOD).mean()
    close = df["close"].iloc[-1]

    fast_val = ma_fast.iloc[-1]
    slow_val = ma_slow.iloc[-1]

    # BULLISH: Harga di atas KEDUA MA + MA crossover confirmed (fast > slow)
    if close > fast_val and close > slow_val and fast_val > slow_val:
        return "BULLISH"
    # BEARISH: Harga di bawah KEDUA MA + MA crossover confirmed (fast < slow)
    elif close < fast_val and close < slow_val and fast_val < slow_val:
        return "BEARISH"
    # Mixed / bouncing melawan tren = RANGING
    return "RANGING"


# ============================================================
#  ATR (AVERAGE TRUE RANGE)
# ============================================================


def get_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Hitung Average True Range (ATR) untuk manajemen risiko dinamis.
    Returns: Nilai ATR terakhir. Mengembalikan 0.0 jika data kurang.
    """
    if df.empty or len(df) <= period:
        return 0.0

    # Menghitung True Range
    high_low = df["high"] - df["low"]
    high_prev_close = (df["high"] - df["close"].shift(1)).abs()
    low_prev_close = (df["low"] - df["close"].shift(1)).abs()

    tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    # Menghitung ATR (Simple Moving Average dari TR)
    atr = tr.rolling(window=period).mean()

    return atr.iloc[-1]


# ============================================================
#  H4 MARKET STRUCTURE
# ============================================================


def detect_h4_structure(df: pd.DataFrame) -> str:
    """
    Deteksi struktur H4 (BULLISH, BEARISH, NEUTRAL).
    Menggunakan swing high/low dengan window +/- 2 candle.
    BULLISH = Higher High (HH) & Higher Low (HL)
    BEARISH = Lower High (LH) & Lower Low (LL)
    """
    if len(df) < 20:
        return "NEUTRAL"

    highs = []
    lows = []

    # Deteksi fraktal swing (2 kiri, 2 kanan)
    for i in range(2, len(df) - 2):
        is_high = True
        is_low = True

        for j in range(i - 2, i + 3):
            if i == j:
                continue
            if df["high"].iloc[i] <= df["high"].iloc[j]:
                is_high = False
            if df["low"].iloc[i] >= df["low"].iloc[j]:
                is_low = False

        if is_high:
            highs.append(df["high"].iloc[i])
        if is_low:
            lows.append(df["low"].iloc[i])

    if len(highs) >= 2 and len(lows) >= 2:
        last_h1, last_h2 = highs[-2], highs[-1]
        last_l1, last_l2 = lows[-2], lows[-1]

        if last_h2 > last_h1 and last_l2 > last_l1:
            return "BULLISH"
        elif last_h2 < last_h1 and last_l2 < last_l1:
            return "BEARISH"

    return "NEUTRAL"


# ============================================================
#  PREMIUM / DISCOUNT ZONE DETECTION
# ============================================================


def detect_premium_discount(df: pd.DataFrame, period: int = 50) -> str:
    """
    Hitung range harga selama `period` candle terakhir.
    Jika harga saat ini berada di atas 50% dari range, maka PREMIUM.
    Jika harga saat ini berada di bawah 50% dari range, maka DISCOUNT.

    Returns: 'PREMIUM', 'DISCOUNT', atau 'EQUILIBRIUM'
    """
    if df.empty or len(df) < period:
        return "EQUILIBRIUM"

    recent_data = df.tail(period)
    highest = recent_data["high"].max()
    lowest = recent_data["low"].min()

    if highest == lowest:
        return "EQUILIBRIUM"

    current_close = df["close"].iloc[-1]

    relative_position = (current_close - lowest) / (highest - lowest)

    if relative_position > 0.5:
        return "PREMIUM"
    elif relative_position < 0.5:
        return "DISCOUNT"
    else:
        return "EQUILIBRIUM"


# ============================================================
#  FAIR VALUE GAP (FVG) RETEST DETECTION (SILVER BULLET)
# ============================================================


def detect_fvg_retest(
    df: pd.DataFrame,
    bias: str = "",
) -> tuple[str, float, int]:
    """
    Mendeteksi FVG murni dan apakah harga saat ini sedang me-retest FVG tersebut.
    Hanya mengembalikan sinyal jika searah dengan bias H4.

    Returns: (status_string, extreme_price, fvg_candle_index)
             fvg_candle_index = -1 jika tidak ada.
    """
    if df.empty or len(df) < 15:
        return "Searching...", 0.0, -1

    last_idx = len(df) - 1

    # Kita mundur mencari FVG yang terbentuk maksimal 15 candle terakhir
    # i adalah index untuk candle ke-3 dari formasi FVG
    for i in range(last_idx - 1, max(2, last_idx - 15), -1):
        c1 = df.iloc[i - 2]
        # c2 = df.iloc[i - 1] # Unused
        c3 = df.iloc[i]

        # Bullish FVG: C3 Low > C1 High
        if c3["low"] > c1["high"]:
            gap_top = c3["low"]
            gap_bottom = c1["high"]

            # Cek apakah gap masih valid (belum diclose di bawah gap_bottom)
            is_valid = True
            retested = False
            for j in range(i + 1, len(df)):
                test_candle = df.iloc[j]
                if test_candle["close"] < gap_bottom:
                    is_valid = False
                    break
                # Cek apakah harga sudah masuk ke dalam gap (retest)
                if test_candle["low"] <= gap_top:
                    retested = True

            # Sinyal valid jika gap belum jebol, sudah diretest
            # Bias filtering dilakukan oleh confluence scoring (bukan hard gate)
            if is_valid and retested and bias in ("BULLISH", "RANGING"):
                logger.info(
                    f"FVG BUY Retest detected! Gap: {gap_bottom:.2f} - {gap_top:.2f}"
                )
                # SL diletakkan di bawah C1 (awal pergerakan impulsif)
                return "FVG BUY", c1["low"], i

        # Bearish FVG: C3 High < C1 Low
        if c3["high"] < c1["low"]:
            gap_top = c1["low"]
            gap_bottom = c3["high"]

            is_valid = True
            retested = False
            for j in range(i + 1, len(df)):
                test_candle = df.iloc[j]
                if test_candle["close"] > gap_top:
                    is_valid = False
                    break
                if test_candle["high"] >= gap_bottom:
                    retested = True

            # Bias filtering dilakukan oleh confluence scoring (bukan hard gate)
            if is_valid and retested and bias in ("BEARISH", "RANGING"):
                logger.info(
                    f"FVG SELL Retest detected! Gap: {gap_bottom:.2f} - {gap_top:.2f}"
                )
                # SL diletakkan di atas C1
                return "FVG SELL", c1["high"], i

    return "Searching...", 0.0, -1


# ============================================================
#  CONFLUENCE SCORING
# ============================================================


def calculate_confluence(
    side: str,
    bias: str,
    fvg_status: str,
    is_killzone_active: bool,
) -> int:
    """
    Hitung score konfluensi untuk Silver Bullet.
    Max score = 3 (Killzone + Bias + FVG).
    """
    score = 0
    if is_killzone_active:
        score += 1

    # Bias alignment
    if side == "BUY" and bias == "BULLISH":
        score += 1
    elif side == "SELL" and bias == "BEARISH":
        score += 1

    # FVG alignment
    if side == "BUY" and "BUY" in fvg_status:
        score += 1
    elif side == "SELL" and "SELL" in fvg_status:
        score += 1

    return score


# ============================================================
#  INVALIDATION CHECK
# ============================================================


def check_invalidation(
    df: pd.DataFrame, side: str, extreme_price: float
) -> tuple[bool, str]:
    """
    Cek apakah setup telah menjadi invalid berdasarkan harga close terakhir.
    - BUY Setup: Invalid jika close terakhir < extreme_price (sweep gagal, harga terus turun).
    - SELL Setup: Invalid jika close terakhir > extreme_price (sweep gagal, harga terus naik).

    Returns: (is_invalid, reason_string)
    """
    if df.empty or extreme_price == 0.0 or not side:
        return False, ""

    last_close = df["close"].iloc[-1]

    if side == "BUY":
        if last_close < extreme_price:
            return (
                True,
                f"Close terakhir ({last_close:.2f}) di bawah Sweep Low ({extreme_price:.2f})",
            )
    elif side == "SELL":
        if last_close > extreme_price:
            return (
                True,
                f"Close terakhir ({last_close:.2f}) di atas Sweep High ({extreme_price:.2f})",
            )

    return False, ""
