import pandas as pd
from src.analysis.analysis import (
    calculate_confluence,
    get_atr,
    detect_h4_structure,
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
#  CONFLUENCE TESTS
# ============================================================

def test_calculate_confluence():
    # Skenario 1: Perfect Alignment (Score 3)
    score = calculate_confluence(
        "BUY", "BULLISH", "BUY RETEST", True
    )
    assert score == 3

    # Skenario 2: Trading against Bias (Score 2)
    score = calculate_confluence(
        "SELL", "BULLISH", "SELL RETEST", True
    )
    assert score == 2

    # Skenario 3: RANGING bias (Score 2)
    score = calculate_confluence(
        "BUY", "RANGING", "BUY RETEST", True
    )
    assert score == 2


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
