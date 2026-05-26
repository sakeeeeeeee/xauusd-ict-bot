from src.risk.risk_manager import validate_risk, calculate_sl_tp


def test_validate_risk():
    # Default configs: MIN_RISK = 1.5, MAX_RISK = 15.0
    valid, msg = validate_risk(5.0)
    assert valid is True

    valid, msg = validate_risk(1.0)
    assert valid is False
    assert "terlalu kecil" in msg

    valid, msg = validate_risk(20.0)
    assert valid is False
    assert "terlalu besar" in msg


def test_calculate_sl_tp_buy():
    # Default configs: SL_BUFFER = 0.5, TP1 = 2R, TP2 = 4R
    res = calculate_sl_tp("BUY 🟢", entry_price=2000.0, extreme_price=1995.0)
    assert res["sl"] == 1994.5  # 1995 - 0.5

    # Risk = 2000 - 1994.5 = 5.5
    assert res["risk"] == 5.5

    # TP1 = 2000 + 2*5.5 = 2011.0
    assert res["tp1"] == 2011.0
    # TP2 = 2000 + 4*5.5 = 2022.0
    assert res["tp2"] == 2022.0


def test_calculate_sl_tp_sell():
    res = calculate_sl_tp("SELL 🔴", entry_price=2000.0, extreme_price=2005.0)
    assert res["sl"] == 2005.5  # 2005 + 0.5

    # Risk = 2005.5 - 2000 = 5.5
    assert res["risk"] == 5.5

    # TP1 = 2000 - 2*5.5 = 1989.0
    assert res["tp1"] == 1989.0
    # TP2 = 2000 - 4*5.5 = 1978.0
    assert res["tp2"] == 1978.0


def test_calculate_sl_tp_near_sweep_fallback():
    # Jika entry dan extreme sangat dekat hingga sl buffer membuat sl berbalik (invalid).
    # Contoh BUY: entry 2000, extreme 1999.8 -> sl harusnya 1999.3. Tapi bayangkan buffer membuat SL > entry.
    # Logic fallback di risk manager akan trigger jika SL >= entry.
    res = calculate_sl_tp(
        "BUY 🟢", entry_price=2000.0, extreme_price=2000.1
    )  # Anehomaly extreme > entry di BUY
    # Di BUY, SL awal = extreme - 0.5 = 1999.6. Ini <= 2000. Jadi ga trigger fallback di current logic karena extreme - 0.5 = 1999.6.

    # Coba extreme_price = 2001.0
    res = calculate_sl_tp("BUY 🟢", entry_price=2000.0, extreme_price=2001.0)
    assert res["sl"] == 1998.5
    assert res["risk"] == 1.5


def test_calculate_tp_structural_buy():
    import pandas as pd
    from src.risk.risk_manager import calculate_tp_structural

    data = []
    for i in range(10):
        data.append({"high": 2010.0, "low": 1990.0})
    df = pd.DataFrame(data)

    # Entry = 2000, SL = 1995 -> Risk = 5. Fallback 2R = 2010
    # Jika swing high = 2015 (> 2010), ambil swing high
    df.loc[5, "high"] = 2015.0
    tp1 = calculate_tp_structural(df, "BUY 🟢", 2000.0, 1995.0)
    assert tp1 == 2015.0

    # Jika swing high = 2008 (< 2010), ambil fallback 2010
    df["high"] = 2008.0
    tp1 = calculate_tp_structural(df, "BUY 🟢", 2000.0, 1995.0)
    assert tp1 == 2010.0


def test_calculate_tp_structural_sell():
    import pandas as pd
    from src.risk.risk_manager import calculate_tp_structural

    data = []
    for i in range(10):
        data.append({"high": 2010.0, "low": 1990.0})
    df = pd.DataFrame(data)

    # Entry = 2000, SL = 2005 -> Risk = 5. Fallback 2R = 1990
    # Jika swing low = 1985 (< 1990), ambil swing low
    df.loc[5, "low"] = 1985.0
    tp1 = calculate_tp_structural(df, "SELL 🔴", 2000.0, 2005.0)
    assert tp1 == 1985.0

    # Jika swing low = 1992 (> 1990), ambil fallback 1990
    df["low"] = 1992.0
    tp1 = calculate_tp_structural(df, "SELL 🔴", 2000.0, 2005.0)
    assert tp1 == 1990.0
