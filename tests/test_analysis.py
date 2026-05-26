import pandas as pd
from src.analysis.analysis import (
    detect_sweep,
    detect_ifvg,
    calculate_confluence,
    detect_premium_discount,
    check_invalidation,
    get_atr,
)


def create_synthetic_df(length=25) -> pd.DataFrame:
    """Helper untuk membuat dummy DataFrame sebanyak `length`."""
    data = []
    for i in range(length):
        data.append(
            {"time": i, "open": 2000.0, "high": 2005.0, "low": 1995.0, "close": 2000.0}
        )
    return pd.DataFrame(data)


# ============================================================
#  SWEEP TESTS
# ============================================================


def test_detect_sweep_buy_exact():
    df = create_synthetic_df(25)
    df.loc[24, "low"] = 1992.0
    df.loc[24, "close"] = 1996.0

    status, extreme, idx = detect_sweep(df)
    assert status == "SWEEP BUY 💧"
    assert extreme == 1992.0
    assert idx == 24


def test_detect_sweep_sell_exact():
    df = create_synthetic_df(25)
    df.loc[24, "high"] = 2008.0
    df.loc[24, "close"] = 2004.0

    status, extreme, idx = detect_sweep(df)
    assert status == "SWEEP SELL 💧"
    assert extreme == 2008.0
    assert idx == 24


def test_detect_sweep_buy_near_disabled_by_default():
    """Near-sweep tidak aktif ketika NEAR_SWEEP_ENABLED=False (default)."""
    df = create_synthetic_df(25)
    df.loc[24, "low"] = 1995.5
    df.loc[24, "close"] = 1996.0

    status, extreme, idx = detect_sweep(df)
    assert status == "Searching..."
    assert extreme == 0.0
    assert idx == -1


def test_detect_sweep_buy_near_enabled(monkeypatch):
    """Near-sweep aktif jika NEAR_SWEEP_ENABLED=True + London/NY + bias BULLISH."""
    import src.analysis.analysis as analysis_mod

    monkeypatch.setattr(analysis_mod, "NEAR_SWEEP_ENABLED", True)

    df = create_synthetic_df(25)
    for i in range(20, 25):
        df.loc[i, "high"] = 2000.0
        df.loc[i, "close"] = 2006.0

    df.loc[24, "low"] = 1995.5
    df.loc[24, "close"] = 1996.0
    df.loc[24, "high"] = 2000.0

    status, extreme, idx = detect_sweep(df, bias="BULLISH", is_london_ny_kz=True)
    assert status == "SWEEP BUY 💧"
    assert extreme == 1995.5
    assert idx == 24

    status, extreme, idx = detect_sweep(df, bias="BEARISH", is_london_ny_kz=True)
    assert status == "Searching..."

    status, extreme, idx = detect_sweep(df, bias="BULLISH", is_london_ny_kz=False)
    assert status == "Searching..."


# ============================================================
#  IFVG TESTS (sweep-anchored)
# ============================================================


def test_detect_ifvg_no_sweep():
    """Tanpa sweep, IFVG harus gagal dengan alasan jelas."""
    df = create_synthetic_df(25)
    is_ifvg, msg = detect_ifvg(df, "Searching...", sweep_idx=-1)
    assert is_ifvg is False
    assert "belum ada sweep" in msg


def test_detect_ifvg_buy_within_window():
    """IFVG BUY terdeteksi jika bearish FVG terbentuk dalam 5 candle setelah sweep."""
    df = create_synthetic_df(25)

    # Sweep BUY di candle 18
    sweep_idx = 18

    # Bearish FVG di candle 19, 20, 21 (dalam window 5 setelah sweep)
    # C1_Low (idx 19) > C3_High (idx 21)
    df.loc[19, "low"] = 2000.0
    df.loc[21, "high"] = 1998.0

    # Close terakhir di atas C1_Low → inverse
    df.loc[24, "close"] = 2002.0

    is_ifvg, msg = detect_ifvg(df, "SWEEP BUY 💧", sweep_idx=sweep_idx)
    assert is_ifvg is True
    assert msg == "IFVG BUY 🧲"


def test_detect_ifvg_sell_within_window():
    """IFVG SELL terdeteksi jika bullish FVG terbentuk dalam 5 candle setelah sweep."""
    df = create_synthetic_df(25)

    sweep_idx = 18

    # Bullish FVG di candle 19, 20, 21
    # C1_High (idx 19) < C3_Low (idx 21)
    df.loc[19, "high"] = 2000.0
    df.loc[21, "low"] = 2002.0

    # Close terakhir di bawah C1_High → inverse
    df.loc[24, "close"] = 1998.0

    is_ifvg, msg = detect_ifvg(df, "SWEEP SELL 💧", sweep_idx=sweep_idx)
    assert is_ifvg is True
    assert msg == "IFVG SELL 🧲"


def test_detect_ifvg_outside_window():
    """IFVG di luar 5-candle window setelah sweep harus ditolak."""
    df = create_synthetic_df(25)

    # Sweep di candle 5
    sweep_idx = 5

    # FVG di candle 15, 16, 17 (jauh di luar window 5+5=10)
    df.loc[15, "low"] = 2000.0
    df.loc[17, "high"] = 1998.0
    df.loc[24, "close"] = 2002.0

    is_ifvg, msg = detect_ifvg(df, "SWEEP BUY 💧", sweep_idx=sweep_idx)
    assert is_ifvg is False
    assert "tidak ditemukan" in msg


def test_detect_ifvg_wrong_direction():
    """IFVG SELL tidak valid jika sweep adalah BUY."""
    df = create_synthetic_df(25)

    sweep_idx = 18

    # Bullish FVG di candle 19, 20, 21 → ini akan jadi IFVG SELL
    df.loc[19, "high"] = 2000.0
    df.loc[21, "low"] = 2002.0
    df.loc[24, "close"] = 1998.0

    # Tapi sweep adalah BUY → harus cari IFVG BUY, bukan SELL
    is_ifvg, msg = detect_ifvg(df, "SWEEP BUY 💧", sweep_idx=sweep_idx)
    assert is_ifvg is False
    assert "tidak ditemukan IFVG BUY" in msg


# ============================================================
#  CONFLUENCE TESTS
# ============================================================


def test_calculate_confluence():
    # Skenario 1: Perfect Alignment (Score 4)
    score = calculate_confluence(
        "BUY 🟢", "BULLISH", "SWEEP BUY 💧", "IFVG BUY 🧲", True
    )
    assert score == 4

    # Skenario 2: Sell in Bearish, no IFVG (Score 3)
    score = calculate_confluence("SELL 🔴", "BEARISH", "SWEEP SELL 💧", "No IFVG", True)
    assert score == 3

    # Skenario 3: Trading against Bias, no Killzone (Score 1)
    score = calculate_confluence(
        "SELL 🔴", "BULLISH", "SWEEP SELL 💧", "No IFVG", False
    )
    assert score == 1

    # Skenario 4: RANGING bias tidak dapat poin (tier SWING)
    score = calculate_confluence(
        "BUY 🟢", "RANGING", "SWEEP BUY 💧", "IFVG BUY 🧲", True
    )
    assert score == 3

    # Skenario 5: RANGING + no killzone + SELL
    score = calculate_confluence(
        "SELL 🔴", "RANGING", "SWEEP SELL 💧", "IFVG SELL 🧲", False
    )
    assert score == 2


# ============================================================
#  PREMIUM / DISCOUNT TESTS
# ============================================================


def test_detect_premium_discount():
    # Setup data
    df = create_synthetic_df(50)

    # Set range strict 1000 - 2000 (midpoint 1500)
    df["low"] = 1500.0  # reset all
    df["high"] = 1500.0

    df.loc[0, "low"] = 1000.0
    df.loc[10, "high"] = 2000.0

    # 1. Close = 1800 (>1500) -> PREMIUM
    df.loc[49, "close"] = 1800.0
    assert detect_premium_discount(df, period=50) == "PREMIUM"

    # 2. Close = 1200 (<1500) -> DISCOUNT
    df.loc[49, "close"] = 1200.0
    assert detect_premium_discount(df, period=50) == "DISCOUNT"

    # 3. Close = 1500 (==1500) -> EQUILIBRIUM
    df.loc[49, "close"] = 1500.0
    assert detect_premium_discount(df, period=50) == "EQUILIBRIUM"

    # 4. Data kurang dari period
    df_short = create_synthetic_df(10)
    assert detect_premium_discount(df_short, period=50) == "EQUILIBRIUM"


# ============================================================
#  INVALIDATION TESTS
# ============================================================


def test_check_invalidation():
    # 1. Setup BUY Invalidation (Close < Extreme)
    df = create_synthetic_df(5)
    extreme_price = 1995.0

    # Valid setup: close di atas extreme
    df.loc[4, "close"] = 1996.0
    is_invalid, msg = check_invalidation(df, "BUY 🟢", extreme_price)
    assert is_invalid is False
    assert msg == ""

    # Invalid setup: close di bawah extreme
    df.loc[4, "close"] = 1994.0
    is_invalid, msg = check_invalidation(df, "BUY 🟢", extreme_price)
    assert is_invalid is True
    assert "di bawah Sweep Low" in msg

    # 2. Setup SELL Invalidation (Close > Extreme)
    extreme_price = 2005.0

    # Valid setup: close di bawah extreme
    df.loc[4, "close"] = 2004.0
    is_invalid, msg = check_invalidation(df, "SELL 🔴", extreme_price)
    assert is_invalid is False
    assert msg == ""

    # Invalid setup: close di atas extreme
    df.loc[4, "close"] = 2006.0
    is_invalid, msg = check_invalidation(df, "SELL 🔴", extreme_price)
    assert is_invalid is True
    assert "di atas Sweep High" in msg


# ============================================================
#  ATR TESTS
# ============================================================


def test_get_atr():
    # Setup df with 20 rows
    df = create_synthetic_df(20)

    # tr = max(high-low, abs(high-prev_close), abs(low-prev_close))
    # our synthetic df: high=2005, low=1995, close=2000 for all rows
    # so high-low = 10 for all rows. ATR should be exactly 10.0
    atr = get_atr(df, period=14)
    assert atr == 10.0

    # Test fallback if data insufficient
    df_short = create_synthetic_df(10)
    assert get_atr(df_short, period=14) == 0.0


# ============================================================
#  H4 STRUCTURE TESTS
# ============================================================


def test_detect_h4_structure():
    from src.analysis.analysis import detect_h4_structure

    # Needs at least 20 bars
    df = create_synthetic_df(30)

    # Clear highs and lows to a baseline
    df["high"] = 100.0
    df["low"] = 80.0

    # 1. BULLISH (HH and HL)
    # Swing 1
    df.loc[5, "high"] = 120.0
    df.loc[10, "low"] = 60.0
    # Swing 2
    df.loc[15, "high"] = 140.0
    df.loc[20, "low"] = 70.0  # HL (70 > 60), but lower than baseline 80

    assert detect_h4_structure(df) == "BULLISH"

    # 2. BEARISH (LH and LL)
    df["high"] = 100.0
    df["low"] = 80.0

    # Swing 1
    df.loc[5, "high"] = 140.0
    df.loc[10, "low"] = 70.0
    # Swing 2
    df.loc[15, "high"] = 120.0
    df.loc[20, "low"] = 60.0

    assert detect_h4_structure(df) == "BEARISH"

    # 3. NEUTRAL (HH but LL, or LH but HL)
    df["high"] = 100.0
    df["low"] = 80.0

    # Swing 1
    df.loc[5, "high"] = 120.0
    df.loc[10, "low"] = 70.0
    # Swing 2
    df.loc[15, "high"] = 140.0  # HH
    df.loc[20, "low"] = 60.0  # LL

    assert detect_h4_structure(df) == "NEUTRAL"

    # 4. Insufficient data
    df_short = create_synthetic_df(10)
    assert detect_h4_structure(df_short) == "NEUTRAL"
