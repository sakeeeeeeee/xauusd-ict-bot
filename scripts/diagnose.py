"""
diagnose.py — Unified Diagnostic CLI
====================================
Jalankan dengan: python -m scripts.diagnose [OPTIONS]
Opsi:
  --mt5     Diagnostik koneksi MetaTrader 5
  --arah    Diagnostik jarak Support & Resistance (Swing H/L)
  --signal  Diagnostik filter sinyal secara menyeluruh
"""

import sys
import os
import struct
import argparse
from datetime import datetime, timezone, timedelta

# Tambahkan project root ke sys.path agar bisa import dari src.*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import MetaTrader5 as mt5  # noqa: E402
from src.config import (  # noqa: E402
    SYMBOL,
    UTC_OFFSET,
    KILLZONES,
    MIN_CONFLUENCE_SCORE,
    MIN_RISK,
    MAX_RISK,
    DATA_M15_COUNT,
    DATA_H4_COUNT,
    MA_FAST_PERIOD,
    MA_SLOW_PERIOD,
    SWEEP_LOOKBACK,
    SWEEP_CANDLE_WINDOW,
    IFVG_LOOKBACK,
    NEAR_SWEEP_THRESHOLD,
)
from src.analysis import (  # noqa: E402
    get_data,
    detect_robust_bias,
    detect_sweep,
    detect_ifvg,
    calculate_confluence,
)

sys.stdout.reconfigure(encoding="utf-8")


def run_mt5_diagnostic():
    print("=" * 50)
    print("🔍 MT5 DEBUG DIAGNOSTIC")
    print("=" * 50)

    print(f"\n[1] Python Version : {sys.version}")
    print(f"    Python Arch    : {struct.calcsize('P') * 8}-bit")
    print(f"    Python Path    : {sys.executable}")

    if struct.calcsize("P") * 8 != 64:
        print("    ⚠️  WARNING: MetaTrader5 butuh Python 64-bit!")

    print("\n[2] Checking MetaTrader5 library...")
    print(f"    ✅ MetaTrader5 version: {mt5.__version__}")

    print("\n[3] Attempting mt5.initialize()...")
    result = mt5.initialize()
    print(f"    Default initialize: {result}")

    if not result:
        error = mt5.last_error()
        print(f"    ❌ Error code : {error[0]}")
        print(f"    ❌ Error msg  : {error[1]}")

        common_paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
            os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal"),
            r"C:\Program Files\RoboForex - MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
            r"C:\Program Files\FBS MetaTrader 5\terminal64.exe",
        ]

        print("\n[4] Scanning MT5 terminal paths...")
        found_any = False
        for path in common_paths:
            exists = os.path.exists(path)
            status = "✅ FOUND" if exists else "  not found"
            print(f"    {status}: {path}")
            if exists and path.endswith(".exe"):
                found_any = True
                print(f"\n    → Trying initialize with: {path}")
                result2 = mt5.initialize(path)
                print(f"      Result: {result2}")
                if result2:
                    info = mt5.terminal_info()
                    if info:
                        print(f"      ✅ Terminal: {info.name}")
                        print(f"      ✅ Company:  {info.company}")
                        print(f"      ✅ Path:     {info.path}")
                        print(f"      ✅ Connected: {info.connected}")
                    mt5.shutdown()
                    break
                else:
                    err2 = mt5.last_error()
                    print(f"      ❌ Error: {err2}")

        if not found_any:
            print("\n    ⚠️  Tidak ditemukan terminal64.exe di lokasi umum.")
    else:
        print("    ✅ MT5 initialized successfully!")
        info = mt5.terminal_info()
        if info:
            print("\n[4] Terminal Info:")
            print(f"    Name      : {info.name}")
            print(f"    Company   : {info.company}")
            print(f"    Path      : {info.path}")
            print(f"    Connected : {info.connected}")
            print(f"    Trade OK  : {info.trade_allowed}")

        account = mt5.account_info()
        if account:
            print("\n[5] Account Info:")
            print(f"    Login   : {account.login}")
            print(f"    Server  : {account.server}")
            print(f"    Balance : {account.balance}")
        else:
            print("\n[5] Account: Belum login ke akun trading")

        mt5.shutdown()

    print("\n" + "=" * 50)
    print("🏁 DEBUG SELESAI")
    print("=" * 50)


def run_arah_diagnostic():
    if not mt5.initialize():
        print(f"MT5 GAGAL: {mt5.last_error()}")
        return

    df = get_data(SYMBOL, mt5.TIMEFRAME_M15, 60)
    print("=== Kenapa hanya BUY, bukan SELL? ===\n")

    prev_high_global = 0
    prev_low_global = 0

    for offset in range(SWEEP_CANDLE_WINDOW):
        idx = -(1 + offset)
        candle = df.iloc[idx]
        lb_end = len(df) + idx
        lb_start = lb_end - SWEEP_LOOKBACK
        lookback = df.iloc[lb_start:lb_end]
        prev_high = lookback["high"].max()
        prev_low = lookback["low"].min()
        prev_high_global = prev_high
        prev_low_global = prev_low

        low_dist = abs(prev_low - candle["low"])
        high_dist = abs(candle["high"] - prev_high)

        buy_status = (
            "<-- SWEEP BUY!" if low_dist <= NEAR_SWEEP_THRESHOLD else "(terlalu jauh)"
        )
        sell_status = (
            "<-- SWEEP SELL!" if high_dist <= NEAR_SWEEP_THRESHOLD else "(terlalu jauh)"
        )

        print(f"Candle -{1 + offset}:")
        print(
            f"  Low  = {candle['low']:.2f} vs PrevLow  = {prev_low:.2f} -> jarak: ${low_dist:.2f} {buy_status}"
        )
        print(
            f"  High = {candle['high']:.2f} vs PrevHigh = {prev_high:.2f} -> jarak: ${high_dist:.2f} {sell_status}"
        )
        print()

    harga = df["close"].iloc[-1]
    print(f"Threshold near-sweep: ${NEAR_SWEEP_THRESHOLD}")
    print(f"\nPrevHigh (resistance) = {prev_high_global:.2f}")
    print(f"PrevLow  (support)    = {prev_low_global:.2f}")
    print(f"Harga sekarang        = {harga:.2f}")
    print(f"\nJarak ke High: ${prev_high_global - df['high'].iloc[-1]:.2f}")
    print(f"Jarak ke Low:  ${abs(prev_low_global - df['low'].iloc[-1]):.2f}")

    print("\n--- PENJELASAN ---")
    print("Harga sedang di area LOW (support) -> BUY sweep terdeteksi")
    print(f"Untuk SELL sweep, harga harus NAIK dulu ke area {prev_high_global:.2f}")
    print("Ini normal — sinyal tergantung ARAH pergerakan harga saat ini")
    print(
        "\nKedua arah (BUY & SELL) bisa muncul, tinggal tunggu market bergerak ke area yang sesuai"
    )
    mt5.shutdown()


def run_signal_diagnostic():
    print("=" * 60)
    print("  DIAGNOSA SINYAL — Cek setiap filter")
    print("=" * 60)

    if not mt5.initialize():
        print(f"\nMT5 GAGAL: {mt5.last_error()}")
        sys.exit(1)
    print("\n[OK] MT5 connected")

    wib_now = datetime.now(timezone.utc) + timedelta(hours=UTC_OFFSET)
    jam = wib_now.hour
    print("\n--- WAKTU ---")
    print(f"  Sekarang : {wib_now.strftime('%H:%M:%S WIB')} (jam={jam})")
    print(f"  Weekend  : {'YA' if wib_now.weekday() in (5, 6) else 'TIDAK'}")

    kz_active = False
    for start, end in KILLZONES:
        in_kz = start <= jam < end
        status = "<<< AKTIF" if in_kz else ""
        print(f"  KZ {start:02d}:00-{end:02d}:00 : {status}")
        if in_kz:
            kz_active = True
    print(f"  Dalam Killzone: {'YA' if kz_active else 'TIDAK — sinyal DIBLOKIR!'}")

    df_m15 = get_data(SYMBOL, mt5.TIMEFRAME_M15, DATA_M15_COUNT)
    df_h4 = get_data(SYMBOL, mt5.TIMEFRAME_H4, DATA_H4_COUNT)

    if df_m15.empty or df_h4.empty:
        print(f"\n[GAGAL] Data kosong! M15={len(df_m15)}, H4={len(df_h4)}")
        mt5.shutdown()
        sys.exit(1)

    print("\n--- DATA ---")
    print(
        f"  M15 candles: {len(df_m15)} (butuh min {max(MA_SLOW_PERIOD + 1, SWEEP_LOOKBACK + 1)})"
    )
    print(f"  H4  candles: {len(df_h4)}")
    print(f"  Harga saat ini: {df_m15['close'].iloc[-1]:.2f}")

    bias = detect_robust_bias(df_h4)
    ma_fast = df_h4["close"].rolling(window=MA_FAST_PERIOD).mean().iloc[-1]
    ma_slow = df_h4["close"].rolling(window=MA_SLOW_PERIOD).mean().iloc[-1]
    close_h4 = df_h4["close"].iloc[-1]

    print("\n--- BIAS (H4) ---")
    print(f"  Close H4 : {close_h4:.2f}")
    print(f"  MA{MA_FAST_PERIOD}    : {ma_fast:.2f}")
    print(f"  MA{MA_SLOW_PERIOD}    : {ma_slow:.2f}")
    print(f"  Bias     : {bias}", end="")
    if bias == "RANGING":
        print(" — DIBLOKIR! Harga di antara kedua MA")
    else:
        print(" — OK")

    sweep_status, extreme_price = detect_sweep(df_m15)
    print(f"\n--- SWEEP (M15, window={SWEEP_CANDLE_WINDOW} candle) ---")
    print(f"  Status   : {sweep_status}", end="")
    if sweep_status == "Searching...":
        print(" — TIDAK ADA sweep terdeteksi!")
        print(f"\n  Detail candle terakhir {SWEEP_CANDLE_WINDOW}:")
        for offset in range(SWEEP_CANDLE_WINDOW):
            idx = -(1 + offset)
            candle = df_m15.iloc[idx]
            lb_end = len(df_m15) + idx
            lb_start = lb_end - SWEEP_LOOKBACK
            if lb_start < 0:
                continue
            lookback = df_m15.iloc[lb_start:lb_end]
            prev_high = lookback["high"].max()
            prev_low = lookback["low"].min()
            high_diff = candle["high"] - prev_high
            low_diff = prev_low - candle["low"]

            print(
                f"  Candle -{1 + offset}: H={candle['high']:.2f} L={candle['low']:.2f} C={candle['close']:.2f}"
            )
            print(f"           PrevHigh={prev_high:.2f} PrevLow={prev_low:.2f}")
            print(
                f"           Tembus High? {'YA' if candle['high'] > prev_high else f'TIDAK (kurang {abs(high_diff):.2f})'}"
            )
            print(
                f"           Tembus Low?  {'YA' if candle['low'] < prev_low else f'TIDAK (kurang {abs(low_diff):.2f})'}"
            )
            if candle["high"] > prev_high:
                print(
                    f"           Close < PrevHigh? {'YA — SWEEP SELL!' if candle['close'] < prev_high else 'TIDAK'}"
                )
            if candle["low"] < prev_low:
                print(
                    f"           Close > PrevLow? {'YA — SWEEP BUY!' if candle['close'] > prev_low else 'TIDAK'}"
                )
    else:
        print(f" — OK! Extreme={extreme_price:.2f}")

    is_ifvg, ifvg_msg = detect_ifvg(df_m15, sweep_status)
    print(f"\n--- IFVG (M15, lookback={IFVG_LOOKBACK}) ---")
    print(f"  Status   : {ifvg_msg}", end="")
    if not is_ifvg:
        print(
            " — TIDAK ADA IFVG"
            + (
                " (skip karena belum ada sweep)"
                if sweep_status == "Searching..."
                else ""
            )
        )
    else:
        print(" — OK!")

    side = None
    alignment_error = None
    if sweep_status == "SWEEP BUY 💧":
        if ifvg_msg == "IFVG BUY 🧲":
            side = "BUY 🟢"
        else:
            alignment_error = f"BUY Setup Mismatched: Sweep=SWEEP BUY, IFVG={ifvg_msg} (Need IFVG BUY 🧲)"
    elif sweep_status == "SWEEP SELL 💧":
        if ifvg_msg == "IFVG SELL 🧲":
            side = "SELL 🔴"
        else:
            alignment_error = f"SELL Setup Mismatched: Sweep=SWEEP SELL, IFVG={ifvg_msg} (Need IFVG SELL 🧲)"

    confluence = 0
    if side:
        confluence = calculate_confluence(side, bias, sweep_status, ifvg_msg, kz_active)

    print("\n--- CONFLUENCE ---")
    print(f"  Trade Side : {side if side else 'None'}")
    print(f"  Killzone   : {'1' if kz_active else '0'}")
    if side:
        bias_aligned = (side == "BUY 🟢" and bias in ("BULLISH", "RANGING")) or (
            side == "SELL 🔴" and bias in ("BEARISH", "RANGING")
        )
        sweep_aligned = (side == "BUY 🟢" and "BUY" in sweep_status) or (
            side == "SELL 🔴" and "SELL" in sweep_status
        )
        ifvg_aligned = (side == "BUY 🟢" and "BUY" in ifvg_msg) or (
            side == "SELL 🔴" and "SELL" in ifvg_msg
        )
        print(f"  Bias       : {'1' if bias_aligned else '0'} ({bias})")
        print(f"  Sweep      : {'1' if sweep_aligned else '0'} ({sweep_status})")
        print(f"  IFVG       : {'1' if ifvg_aligned else '0'} ({ifvg_msg})")
    else:
        print(f"  Bias       : 0 ({bias})")
        print(f"  Sweep      : 0 ({sweep_status})")
        print(f"  IFVG       : 0 ({ifvg_msg})")
    print(f"  Total      : {confluence}/4 (minimum: {MIN_CONFLUENCE_SCORE})")
    print(
        f"  Lolos?     : {'YA' if side and confluence >= MIN_CONFLUENCE_SCORE else 'TIDAK'}"
    )

    print("\n--- ALIGNMENT DETAILS ---")
    if side:
        if side == "BUY 🟢":
            print("  Target: BUY")
            print(f"  Bias ({bias}) harus BULLISH/RANGING: ✅ OK")
            print(f"  IFVG ({ifvg_msg}) harus IFVG BUY: ✅ OK")
        elif side == "SELL 🔴":
            print("  Target: SELL")
            print(f"  Bias ({bias}) harus BEARISH/RANGING: ✅ OK")
            print(f"  IFVG ({ifvg_msg}) harus IFVG SELL: ✅ OK")
    elif alignment_error:
        print(f"  ❌ {alignment_error}")
    else:
        print("  TIDAK ADA SWEEP yang terdeteksi.")

    if extreme_price > 0:
        raw_risk = abs(df_m15["close"].iloc[-1] - extreme_price)
        print("\n--- RISK ---")
        print(f"  Raw risk : ${raw_risk:.2f}")
        print(f"  Min/Max  : ${MIN_RISK} - ${MAX_RISK}")
        print(f"  Valid?   : {'YA' if MIN_RISK <= raw_risk <= MAX_RISK else 'TIDAK'}")

    print(f"\n{'=' * 60}")
    print("  RINGKASAN")
    print(f"{'=' * 60}")
    blockers = []
    if not kz_active:
        blockers.append("Di luar Killzone")
    if not side:
        if sweep_status == "Searching...":
            blockers.append("Tidak ada Sweep terdeteksi")
        elif alignment_error:
            blockers.append(f"Arah tidak align ({alignment_error})")
    if side and confluence < MIN_CONFLUENCE_SCORE:
        blockers.append(f"Confluence {confluence}/4 < minimum {MIN_CONFLUENCE_SCORE}")

    if blockers:
        print(f"\n  SINYAL DIBLOKIR oleh {len(blockers)} filter:")
        for i, b in enumerate(blockers, 1):
            print(f"    {i}. {b}")
    else:
        print("\n  SEMUA FILTER LOLOS! Sinyal seharusnya terkirim.")

    mt5.shutdown()
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="XAUUSD ICT Bot - Diagnostic Tools",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Contoh penggunaan:
  python -m scripts.diagnose --mt5
  python -m scripts.diagnose --signal
  python -m scripts.diagnose --arah
  python -m scripts.diagnose --mt5 --signal""",
    )
    parser.add_argument(
        "--mt5", action="store_true", help="Jalankan diagnostic koneksi MetaTrader 5"
    )
    parser.add_argument(
        "--signal", action="store_true", help="Jalankan diagnostic sinyal & filter"
    )
    parser.add_argument(
        "--arah", action="store_true", help="Jalankan diagnostic support/resistance"
    )

    args = parser.parse_args()

    if not any([args.mt5, args.signal, args.arah]):
        parser.print_help()
        sys.exit(0)

    if args.mt5:
        run_mt5_diagnostic()

    if args.arah:
        run_arah_diagnostic()

    if args.signal:
        run_signal_diagnostic()
