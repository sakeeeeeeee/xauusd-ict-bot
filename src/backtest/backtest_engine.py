"""
backtest_engine.py — Backtesting Engine Module
Load MT5 historical data, replay candle by candle, output trades.
"""

# ruff: noqa: E402

import argparse
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5
from pathlib import Path

# Add project root to sys.path so we can import src
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.config import (
    DATA_M5_COUNT,
    DATA_M15_COUNT,
    DATA_H4_COUNT,
    UTC_OFFSET,
    BROKER_UTC_OFFSET,
    KILLZONES,
    LONDON_NY_KILLZONES,
    SESSION_RULES,
    TREND_DAYS,
)
MIN_CONFLUENCE_SCALP = 1  # Fallback local constant
from src.analysis.analysis import (
    get_atr,
    detect_robust_bias,
    detect_premium_discount,
    detect_fvg_retest,
    calculate_confluence,
    detect_h4_structure,
    check_invalidation,
)


def get_current_session(current_time: datetime) -> str:
    jam = current_time.hour
    if 8 <= jam < 10:
        return "ASIA"
    elif 14 <= jam < 17:
        return "LONDON"
    elif 19 <= jam < 23:
        return "NY"
    return "UNKNOWN"


def is_killzone(current_time: datetime = None) -> bool:
    if not current_time:
        return False
    jam = current_time.hour
    for start, end in KILLZONES:
        if start <= jam < end:
            return True
    return False


def is_london_ny_killzone(current_time: datetime = None) -> bool:
    if not current_time:
        return False
    jam = current_time.hour
    for start, end in LONDON_NY_KILLZONES:
        if start <= jam < end:
            return True
    return False


def is_news_blackout(current_time: datetime = None) -> tuple:
    return False, ""


from src.risk.risk_manager import calculate_sl_tp, validate_risk
from src.risk.outcome_tracker import evaluate_outcomes
from src.backtest.report import generate_report

# Setup logger for backtest
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backtest")


def _mock_trade_dict(
    side,
    entry,
    sl,
    tp1,
    tp2,
    risk,
    confluence_score,
    bias,
    tier,
    session,
    atr,
    spread,
    near_sweep,
    ifvg_after_sweep,
    time,
):
    return {
        "version": "v2",
        "time": time.isoformat(),
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "confluence_score": confluence_score,
        "bias": bias,
        "tier": tier,
        "session": session,
        "atr": atr,
        "spread": spread,
        "near_sweep": near_sweep,
        "ifvg_after_sweep": ifvg_after_sweep,
        "result": "PENDING",
    }


def fetch_historical_data(symbol: str, start: datetime, end: datetime):
    if not mt5.initialize():
        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
        return None, None, None

    logger.info(f"Downloading data for {symbol} from {start} to {end}...")

    # Fetch main M5 data for loop
    rates_m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start, end)
    if rates_m5 is None or len(rates_m5) == 0:
        logger.error("No M5 data found!")
        return None, None, None
    df_m5 = pd.DataFrame(rates_m5)
    df_m5["time"] = pd.to_datetime(df_m5["time"], unit="s")

    # Convert times to match WIB offset since MT5 is usually UTC or broker time.
    # For backtest consistency with live bot, we align MT5 time to local WIB if necessary.
    # The simplest is just treat df['time'] as the time we pass to get_wib_now replacement.

    # Fetch extra historical for M15 and H4
    start_pad_m15 = start - timedelta(days=5)
    rates_m15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_pad_m15, end)
    df_m15 = pd.DataFrame(rates_m15)
    df_m15["time"] = pd.to_datetime(df_m15["time"], unit="s")

    start_pad_h4 = start - timedelta(days=60)
    rates_h4 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, start_pad_h4, end)
    df_h4 = pd.DataFrame(rates_h4)
    df_h4["time"] = pd.to_datetime(df_h4["time"], unit="s")

    logger.info(
        f"Loaded {len(df_m5)} M5 candles, {len(df_m15)} M15 candles, {len(df_h4)} H4 candles."
    )
    return df_m5, df_m15, df_h4


def run_backtest(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    output_file: str = "backtest_results.csv",
    df_m5: pd.DataFrame = None,
    df_m15_full: pd.DataFrame = None,
    df_h4_full: pd.DataFrame = None,
    quiet: bool = False,
):
    if quiet:
        logger.setLevel(logging.CRITICAL)
    else:
        logger.setLevel(logging.INFO)

    if df_m5 is None or df_m15_full is None or df_h4_full is None:
        df_m5, df_m15_full, df_h4_full = fetch_historical_data(
            symbol, start_date, end_date
        )
        if df_m5 is None:
            return None

    trades = []
    signal_trackers = {
        "BUY": {"last_time": None, "last_candle_time": None, "last_extreme": None},
        "SELL": {"last_time": None, "last_candle_time": None, "last_extreme": None},
    }

    logger.info("Starting replay loop...")

    # We need at least enough previous M5 candles for lookbacks
    min_m5_index = max(100, DATA_M5_COUNT)

    for i in range(min_m5_index, len(df_m5)):
        # Slices
        # Adding (UTC_OFFSET - BROKER_UTC_OFFSET) to map broker time to local WIB
        current_time = df_m5.iloc[i]["time"] + timedelta(
            hours=(UTC_OFFSET - BROKER_UTC_OFFSET)
        )

        df_trigger = df_m5.iloc[i - DATA_M5_COUNT + 1 : i + 1].copy()

        df_m15 = (
            df_m15_full[df_m15_full["time"] <= df_m5.iloc[i]["time"]]
            .tail(DATA_M15_COUNT)
            .copy()
        )

        df_h4 = (
            df_h4_full[df_h4_full["time"] <= df_m5.iloc[i]["time"]]
            .tail(DATA_H4_COUNT)
            .copy()
        )

        if df_h4.empty or df_m15.empty:
            continue

        harga_now = df_trigger["close"].iloc[-1]
        current_candle_time = df_trigger["time"].iloc[-1]
        current_high = df_trigger["high"].iloc[-1]
        current_low = df_trigger["low"].iloc[-1]
        current_spread = (
            df_trigger["spread"].iloc[-1] * 0.01  # Mock default points to dollars
        )

        # Outcome Tracker Eval
        _, _ = evaluate_outcomes(
            trades, current_high, current_low, current_time=current_time
        )

        # ------------------- ANALYSIS -------------------
        bias = detect_robust_bias(df_h4)
        pd_zone = detect_premium_discount(df_h4)
        h4_struct = detect_h4_structure(df_h4)
        atr = get_atr(df_m15)

        # 3. Cek FVG Retest
        fvg_status, extreme_price, fvg_idx = detect_fvg_retest(df_m15, bias=bias)

        side = None
        if "BUY" in fvg_status:
            side = "BUY"
        elif "SELL" in fvg_status:
            side = "SELL"

        kz_active = is_killzone(current_time=current_time)
        confluence = 0
        if side:
            confluence = calculate_confluence(side, bias, fvg_status, kz_active)

        # Spam Check & Tier
        tier = None
        is_spam = False
        if side:
            tracker = signal_trackers[side]
            if tracker["last_candle_time"] == current_candle_time:
                is_spam = True
            elif (
                tracker["last_extreme"] == extreme_price
                and tracker["last_time"] is not None
            ):
                time_diff = (current_time - tracker["last_time"]).total_seconds() / 60.0
                if time_diff < 15:
                    is_spam = True
        is_valid_entry = False
        if side and not is_spam:
            session = get_current_session(current_time)
            current_dow = current_time.weekday()
            
            # === ROBUST ANTI-OVERFITTING PROFILE ===
            is_valid_entry = False
            if session == "LONDON":
                # London: Great on Mon-Wed with score >= 2.
                if current_dow in TREND_DAYS and confluence >= 2:
                    is_valid_entry = True
            elif session == "NY":
                # NY: Highly profitable ONLY with perfect confluence (score 3) on ALL days.
                if confluence >= 3:
                    is_valid_entry = True
            
            if not is_valid_entry:
                continue
            
            # Assign tier just for reporting
            tier = "SWING" if confluence >= 3 else "SCALP"

        # Entry Logic
        if side and is_valid_entry:
            skip_reason = None
            # Validasi news blackout
            in_blackout, _ = is_news_blackout(current_time)
            if in_blackout:
                skip_reason = "News Blackout"

            if not skip_reason:
                if session not in SESSION_RULES or tier not in SESSION_RULES[session]:
                    skip_reason = "Tier not allowed in session"

            if not skip_reason:
                is_invalid, _ = check_invalidation(df_trigger, side, extreme_price)
                if is_invalid:
                    skip_reason = "Invalidated"

            if not skip_reason:
                # PREMIUM/DISCOUNT ZONE FILTER (parity with live bot)
                if side == "BUY" and pd_zone != "DISCOUNT":
                    skip_reason = "BUY not in Discount zone"
                elif side == "SELL" and pd_zone != "PREMIUM":
                    skip_reason = "SELL not in Premium zone"

            if not skip_reason:
                # H4 STRUCTURE FILTER (parity with live bot)
                if side == "BUY" and h4_struct == "BEARISH":
                    skip_reason = "H4 Structure Bearish (BUY rejected)"
                elif side == "SELL" and h4_struct == "BULLISH":
                    skip_reason = "H4 Structure Bullish (SELL rejected)"

            if not skip_reason:
                levels = calculate_sl_tp(
                    side, harga_now, extreme_price, df_trigger, atr, session
                )
                is_valid, _ = validate_risk(levels["risk"], atr)
                if not is_valid:
                    skip_reason = "Risk validation failed"

            if not skip_reason:
                # Execute Trade
                t = _mock_trade_dict(
                    side=side,
                    entry=harga_now,
                    sl=levels["sl"],
                    tp1=levels["tp1"],
                    tp2=levels["tp2"],
                    risk=levels["risk"],
                    confluence_score=confluence,
                    bias=bias,
                    tier=tier,
                    session=get_current_session(current_time) or "UNKNOWN",
                    atr=atr,
                    spread=current_spread,
                    near_sweep="FVG RETEST",
                    ifvg_after_sweep=fvg_status,
                    time=current_time,
                )
                trades.append(t)

                signal_trackers[side]["last_time"] = current_time
                signal_trackers[side]["last_candle_time"] = current_candle_time
                signal_trackers[side]["last_extreme"] = extreme_price

                logger.info(f"[{current_time}] EXECUTED {tier} {side} @ {harga_now}")

    # Generate Report
    df_trades = pd.DataFrame(trades)
    if not df_trades.empty:
        if not quiet:
            generate_report(df_trades)

        df_trades.to_csv(output_file, index=False)
        if not quiet:
            logger.info(f"Saved trades to {output_file}")
    else:
        if not quiet:
            logger.warning(
                "❌ Tidak ada trade yang memenuhi kriteria strategi selama periode ini. Hasil CSV tidak dibuat."
            )

    return df_trades


def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XAUUSD ICT Bot Backtest Engine")
    parser.add_argument("--symbol", type=str, default="XAUUSD")
    parser.add_argument("--train-start", type=str, help="YYYY-MM-DD")
    parser.add_argument("--train-end", type=str, help="YYYY-MM-DD")
    parser.add_argument("--test-start", type=str, help="YYYY-MM-DD")
    parser.add_argument("--test-end", type=str, help="YYYY-MM-DD")
    parser.add_argument(
        "--days", type=int, default=30, help="Jumlah hari untuk backtest (default: 30)"
    )
    args = parser.parse_args()

    if args.train_start and args.train_end and args.test_start and args.test_end:
        train_start = parse_date(args.train_start)
        train_end = parse_date(args.train_end)
        test_start = parse_date(args.test_start)
        test_end = parse_date(args.test_end)

        logger.info("\n" + "=" * 50)
        logger.info("=== WALK-FORWARD: TRAIN SET ===")
        logger.info(f"Period: {train_start} to {train_end}")
        logger.info("=" * 50)
        run_backtest(
            args.symbol, train_start, train_end, output_file="train_results.csv"
        )

        logger.info("\n" + "=" * 50)
        logger.info("=== WALK-FORWARD: TEST SET ===")
        logger.info(f"Period: {test_start} to {test_end}")
        logger.info("=" * 50)
        run_backtest(args.symbol, test_start, test_end, output_file="test_results.csv")
    else:
        end = datetime.now()
        start = end - timedelta(days=args.days)
        run_backtest(args.symbol, start, end)
