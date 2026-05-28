from src.risk.risk_manager import validate_risk, calculate_sl_tp

def test_validate_risk():
    valid, msg = validate_risk(5.0, atr=0)
    assert valid is True

    valid, msg = validate_risk(0.1, atr=0) # Asumsi min_risk > 0.1
    assert valid is False
    assert "terlalu kecil" in msg

    valid, msg = validate_risk(500.0, atr=0) # Asumsi max_risk < 500
    assert valid is False
    assert "terlalu besar" in msg

def test_calculate_sl_tp_buy():
    res = calculate_sl_tp("BUY", entry_price=2000.0, extreme_price=1995.0)
    assert res["sl"] < 2000.0
    assert res["tp1"] > 2000.0
    assert res["tp2"] > res["tp1"]

def test_calculate_sl_tp_sell():
    res = calculate_sl_tp("SELL", entry_price=2000.0, extreme_price=2005.0)
    assert res["sl"] > 2000.0
    assert res["tp1"] < 2000.0
    assert res["tp2"] < res["tp1"]

def test_calculate_tp_structural_buy():
    import pandas as pd
    from src.risk.risk_manager import calculate_tp_structural

    data = []
    for i in range(10):
        data.append({"high": 2010.0, "low": 1990.0})
    df = pd.DataFrame(data)

    df.loc[5, "high"] = 2050.0 # Swing high jauh
    tp1 = calculate_tp_structural(df, "BUY", 2000.0, 1995.0)
    assert tp1 > 2000.0

def test_calculate_tp_structural_sell():
    import pandas as pd
    from src.risk.risk_manager import calculate_tp_structural

    data = []
    for i in range(10):
        data.append({"high": 2010.0, "low": 1990.0})
    df = pd.DataFrame(data)

    df.loc[5, "low"] = 1950.0 # Swing low jauh
    tp1 = calculate_tp_structural(df, "SELL", 2000.0, 2005.0)
    assert tp1 < 2000.0
