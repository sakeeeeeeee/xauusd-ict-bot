import pytest
import pandas as pd
from datetime import datetime, timedelta

from src.risk.outcome_tracker import update_outcomes
from src.config import MAX_TRADE_DURATION_CANDLES
import src.database.db as db


@pytest.fixture
def mock_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_bot_database.db"
    monkeypatch.setattr(db, "DB_FILE", str(test_db))
    db.init_db()
    return test_db


def create_df(high, low):
    return pd.DataFrame({"high": [high], "low": [low]})


def test_update_outcomes_buy_win_tp1(mock_db):
    trade = {
        "time": datetime.now().isoformat(),
        "side": "BUY 🟢",
        "entry": 2000.0,
        "sl": 1990.0,
        "tp1": 2020.0,
        "tp2": 2040.0,
        "result": "PENDING",
        "risk": 10.0,
    }
    db.insert_trade(trade)

    df = create_df(high=2025.0, low=2000.0)
    updated = update_outcomes(df)

    assert len(updated) == 1
    assert updated[0]["result"] == "WIN_TP1"

    trades = db.get_all_trades()
    assert trades[0]["result"] == "WIN_TP1"


def test_update_outcomes_sell_loss(mock_db):
    trade = {
        "time": datetime.now().isoformat(),
        "side": "SELL 🔴",
        "entry": 2000.0,
        "sl": 2010.0,
        "tp1": 1980.0,
        "tp2": 1960.0,
        "result": "PENDING",
        "risk": 10.0,
    }
    db.insert_trade(trade)

    df = create_df(high=2015.0, low=2000.0)
    updated = update_outcomes(df)

    assert len(updated) == 1
    assert updated[0]["result"] == "LOSS"
    trades = db.get_all_trades()
    assert trades[0]["result"] == "LOSS"


def test_update_outcomes_expired(mock_db):
    old_time = datetime.now() - timedelta(minutes=(MAX_TRADE_DURATION_CANDLES * 5 + 10))
    trade = {
        "time": old_time.isoformat(),
        "side": "BUY 🟢",
        "entry": 2000.0,
        "sl": 1990.0,
        "tp1": 2020.0,
        "tp2": 2040.0,
        "result": "PENDING",
        "risk": 10.0,
    }
    db.insert_trade(trade)

    df = create_df(high=2010.0, low=1995.0)
    updated = update_outcomes(df)

    assert len(updated) == 1
    assert updated[0]["result"] == "EXPIRED"


def test_update_outcomes_no_pending(mock_db):
    trade = {
        "time": datetime.now().isoformat(),
        "side": "BUY 🟢",
        "entry": 2000.0,
        "sl": 1990.0,
        "tp1": 2020.0,
        "tp2": 2040.0,
        "result": "WIN_TP2",
        "risk": 10.0,
    }
    db.insert_trade(trade)

    df = create_df(high=2050.0, low=2000.0)
    updated = update_outcomes(df)

    assert len(updated) == 0
