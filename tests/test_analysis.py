import pandas as pd
from src.analysis.analysis import detect_sweep, detect_ifvg, calculate_confluence


def create_synthetic_df(length=25) -> pd.DataFrame:
    """Helper untuk membuat dummy DataFrame sebanyak `length`."""
    data = []
    for i in range(length):
        data.append(
            {"time": i, "open": 2000.0, "high": 2005.0, "low": 1995.0, "close": 2000.0}
        )
    return pd.DataFrame(data)


def test_detect_sweep_buy_exact():
    df = create_synthetic_df(25)

    # Setup sweep BUY di candle terakhir (index 24)
    # Prev low = 1995.0
    # Wick tembus ke 1992.0, tapi close kembali di 1996.0 (> 1995.0)
    df.loc[24, "low"] = 1992.0
    df.loc[24, "close"] = 1996.0

    status, extreme = detect_sweep(df)
    assert status == "SWEEP BUY 💧"
    assert extreme == 1992.0


def test_detect_sweep_sell_exact():
    df = create_synthetic_df(25)

    # Setup sweep SELL di candle terakhir
    # Prev high = 2005.0
    # Wick tembus ke 2008.0, tapi close kembali di 2004.0 (< 2005.0)
    df.loc[24, "high"] = 2008.0
    df.loc[24, "close"] = 2004.0

    status, extreme = detect_sweep(df)
    assert status == "SWEEP SELL 💧"
    assert extreme == 2008.0


def test_detect_sweep_buy_near():
    df = create_synthetic_df(25)

    # Setup NEAR sweep BUY
    # Prev low = 1995.0
    # Wick mendekati (misal 1995.5) dan close di atas (1996.0)
    # Syarat near sweep: jarak < NEAR_SWEEP_THRESHOLD (default 1.0)
    # Jarak = 1995.5 - 1995.0 = 0.5 (Valid)
    df.loc[24, "low"] = 1995.5
    df.loc[24, "close"] = 1996.0

    status, extreme = detect_sweep(df)
    assert status == "SWEEP BUY 💧"
    assert extreme == 1995.5


def test_detect_ifvg_sell():
    df = create_synthetic_df(25)

    # Inversed FVG (IFVG SELL): Bullish FVG awal -> Harga turun menembus FVG
    # Bullish FVG di candle 10, 11, 12
    # C1 High (idx 10) < C3 Low (idx 12)
    df.loc[10, "high"] = 2000.0
    df.loc[12, "low"] = 2002.0  # Gap = 2.0

    # Inverse: di candle terakhir harga close menembus C1 High
    df.loc[24, "close"] = 1998.0  # 1998.0 < 2000.0

    is_ifvg, msg = detect_ifvg(df, "SWEEP SELL 💧")
    assert is_ifvg is True
    assert msg == "IFVG SELL 🧲"


def test_detect_ifvg_buy():
    df = create_synthetic_df(25)

    # Inversed FVG (IFVG BUY): Bearish FVG awal -> Harga naik menembus FVG
    # Bearish FVG di candle 10, 11, 12
    # C1 Low (idx 10) > C3 High (idx 12)
    df.loc[10, "low"] = 2000.0
    df.loc[12, "high"] = 1998.0  # Gap = 2.0

    # Inverse: di candle terakhir harga close menembus C1 Low
    df.loc[24, "close"] = 2002.0  # 2002.0 > 2000.0

    is_ifvg, msg = detect_ifvg(df, "SWEEP BUY 💧")
    assert is_ifvg is True
    assert msg == "IFVG BUY 🧲"


def test_calculate_confluence():
    # Skenario 1: Perfect Alignment (Score 4)
    # Killzone(1) + Bias Bullish(1) + Sweep Buy(1) + IFVG Buy(1) = 4
    score = calculate_confluence(
        "BUY 🟢", "BULLISH", "SWEEP BUY 💧", "IFVG BUY 🧲", True
    )
    assert score == 4

    # Skenario 2: Sell in Bearish, no IFVG (Score 3)
    # Killzone(1) + Bias Bearish(1) + Sweep Sell(1) + No IFVG(0) = 3
    score = calculate_confluence("SELL 🔴", "BEARISH", "SWEEP SELL 💧", "No IFVG", True)
    assert score == 3

    # Skenario 3: Trading against Bias, no Killzone (Score 1)
    # Killzone(0) + Bias Bullish untuk Sell(0) + Sweep Sell(1) + No IFVG(0) = 1
    score = calculate_confluence(
        "SELL 🔴", "BULLISH", "SWEEP SELL 💧", "No IFVG", False
    )
    assert score == 1
