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
    NEAR_SWEEP_ENABLED,
    IFVG_AFTER_SWEEP_WINDOW,
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
#  LIQUIDITY SWEEP DETECTION (with conditional Near-Sweep)
# ============================================================


def detect_sweep(
    df: pd.DataFrame,
    bias: str = "",
    is_london_ny_kz: bool = False,
) -> tuple[str, float, int]:
    """
    Deteksi sweep di N candle terakhir.

    PASS 1 (exact sweep): Selalu aktif — wick tembus level + close rejection.
    PASS 2 (near-sweep):  Hanya aktif jika NEAR_SWEEP_ENABLED=True,
                          sedang di killzone London/NY, dan bias H4 searah.

    Returns: (status_string, extreme_price, sweep_candle_index)
             sweep_candle_index = -1 jika tidak ada sweep.
    """
    if df.empty or len(df) < SWEEP_LOOKBACK + SWEEP_CANDLE_WINDOW:
        return "Searching...", 0.0, -1

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
            abs_idx = len(df) - 1 - offset
            logger.info(
                f"SWEEP BUY detected (candle -{1 + offset}, idx={abs_idx})! "
                f"Low={candle['low']:.2f}, PrevLow={prev_low:.2f}"
            )
            return "SWEEP BUY 💧", candle["low"], abs_idx

        # Exact Sweep Sell: Wick tembus high, close kembali di bawah
        if candle["high"] > prev_high and candle["close"] < prev_high:
            abs_idx = len(df) - 1 - offset
            logger.info(
                f"SWEEP SELL detected (candle -{1 + offset}, idx={abs_idx})! "
                f"High={candle['high']:.2f}, PrevHigh={prev_high:.2f}"
            )
            return "SWEEP SELL 💧", candle["high"], abs_idx

    # === PASS 2: Near-sweep (gated) ===
    # Syarat: NEAR_SWEEP_ENABLED + London/NY killzone + bias searah
    if not NEAR_SWEEP_ENABLED:
        return "Searching...", 0.0, -1

    if not is_london_ny_kz:
        logger.debug("Near-sweep skipped: bukan London/NY killzone.")
        return "Searching...", 0.0, -1

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

        # Near-Sweep Buy: hanya jika bias BULLISH
        low_distance = abs(prev_low - candle["low"])
        if (
            bias == "BULLISH"
            and low_distance <= NEAR_SWEEP_THRESHOLD
            and candle["close"] > prev_low
        ):
            abs_idx = len(df) - 1 - offset
            logger.info(
                f"NEAR-SWEEP BUY detected (candle -{1 + offset}, idx={abs_idx})! "
                f"Low={candle['low']:.2f}, PrevLow={prev_low:.2f}, "
                f"Distance={low_distance:.2f}"
            )
            return "SWEEP BUY 💧", candle["low"], abs_idx

        # Near-Sweep Sell: hanya jika bias BEARISH
        high_distance = abs(candle["high"] - prev_high)
        if (
            bias == "BEARISH"
            and high_distance <= NEAR_SWEEP_THRESHOLD
            and candle["close"] < prev_high
        ):
            abs_idx = len(df) - 1 - offset
            logger.info(
                f"NEAR-SWEEP SELL detected (candle -{1 + offset}, idx={abs_idx})! "
                f"High={candle['high']:.2f}, PrevHigh={prev_high:.2f}, "
                f"Distance={high_distance:.2f}"
            )
            return "SWEEP SELL 💧", candle["high"], abs_idx

    return "Searching...", 0.0, -1


# ============================================================
#  INVERSED FAIR VALUE GAP (IFVG) DETECTION — SWEEP-ANCHORED
# ============================================================


def detect_ifvg(
    df: pd.DataFrame,
    sweep_status: str,
    sweep_idx: int = -1,
) -> tuple[bool, str]:
    """
    Deteksi Inversed FVG yang terbentuk dalam IFVG_AFTER_SWEEP_WINDOW candle
    setelah candle sweep. IFVG harus searah sweep.

    Returns: (is_ifvg_found, message_or_reason)
    """
    # Gate 1: harus ada sweep terlebih dahulu
    if sweep_idx < 0 or sweep_status == "Searching...":
        return False, "No IFVG — belum ada sweep"

    # Gate 2: tentukan arah yang dicari berdasarkan sweep
    if "BUY" in sweep_status:
        target_direction = "BUY"
    elif "SELL" in sweep_status:
        target_direction = "SELL"
    else:
        return False, "No IFVG — arah sweep tidak dikenali"

    # Gate 3: data cukup?
    if len(df) < 5:
        return False, "No IFVG — data tidak cukup"

    last_close = df["close"].iloc[-1]

    # Window: scan FVG hanya di candle sweep_idx sampai sweep_idx + IFVG_AFTER_SWEEP_WINDOW
    scan_start = sweep_idx
    scan_end = min(
        sweep_idx + IFVG_AFTER_SWEEP_WINDOW, len(df) - 2
    )  # -2 karena butuh i+2

    if scan_start >= scan_end:
        return False, f"No IFVG — window kosong (sweep di candle {sweep_idx})"

    # Scan BACKWARDS (dari terbaru ke terlama) dalam window
    for i in range(scan_end - 1, scan_start - 1, -1):
        if i + 2 >= len(df):
            continue

        c1_low = df["low"].iloc[i]
        c1_high = df["high"].iloc[i]
        c3_low = df["low"].iloc[i + 2]
        c3_high = df["high"].iloc[i + 2]

        # Bearish FVG (gap down): C1_Low > C3_High
        # IFVG BUY = price inverse kembali ke ATAS melewati C1_Low
        if target_direction == "BUY" and c1_low > c3_high and last_close > c1_low:
            logger.info(
                f"IFVG BUY found at candle index {i} "
                f"(sweep@{sweep_idx}, window={IFVG_AFTER_SWEEP_WINDOW})"
            )
            return True, "IFVG BUY 🧲"

        # Bullish FVG (gap up): C1_High < C3_Low
        # IFVG SELL = price inverse kembali ke BAWAH melewati C1_High
        if target_direction == "SELL" and c1_high < c3_low and last_close < c1_high:
            logger.info(
                f"IFVG SELL found at candle index {i} "
                f"(sweep@{sweep_idx}, window={IFVG_AFTER_SWEEP_WINDOW})"
            )
            return True, "IFVG SELL 🧲"

    return (
        False,
        f"No IFVG — tidak ditemukan IFVG {target_direction} dalam "
        f"{IFVG_AFTER_SWEEP_WINDOW} candle setelah sweep (idx {sweep_idx})",
    )


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

    # Bias alignment (tier SWING: hanya exact match, RANGING = 0 poin)
    if side == "BUY 🟢" and bias == "BULLISH":
        score += 1
    elif side == "SELL 🔴" and bias == "BEARISH":
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

    if side == "BUY 🟢":
        if last_close < extreme_price:
            return (
                True,
                f"Close terakhir ({last_close:.2f}) di bawah Sweep Low ({extreme_price:.2f})",
            )
    elif side == "SELL 🔴":
        if last_close > extreme_price:
            return (
                True,
                f"Close terakhir ({last_close:.2f}) di atas Sweep High ({extreme_price:.2f})",
            )

    return False, ""
