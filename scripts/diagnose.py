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
    SYMBOLS,
    UTC_OFFSET,
    KILLZONES,
    MIN_CONFLUENCE_SCORE,
    MIN_RISK,
    MAX_RISK,
    DATA_M15_COUNT,
    DATA_H4_COUNT,
    MA_FAST_PERIOD,
    MA_SLOW_PERIOD,
)
from src.analysis import (  # noqa: E402
    get_data,
    detect_robust_bias,
    detect_fvg_retest,
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
    print("=" * 60)
    print("  DIAGNOSA ARAH — Cek Jarak Support & Resistance (M15)")
    print("=" * 60)

    if not mt5.initialize():
        print(f"\nMT5 GAGAL: {mt5.last_error()}")
        sys.exit(1)
    print("\n[OK] MT5 connected")

    df = get_data(SYMBOLS[0], mt5.TIMEFRAME_M15, DATA_M15_COUNT)
    if df.empty:
        print("[GAGAL] Tidak dapat mengambil data M15")
        mt5.shutdown()
        sys.exit(1)

    # Hardcoded lookback since strategy changed
    lookback_window = 15
    df_lookback = df.iloc[-lookback_window:]

    prev_high_global = df_lookback["high"].max()
    prev_low_global = df_lookback["low"].min()

    harga = df["close"].iloc[-1]
    print(f"\nPrevHigh (resistance) = {prev_high_global:.2f}")
    print(f"PrevLow  (support)    = {prev_low_global:.2f}")
    print(f"Harga sekarang        = {harga:.2f}")
    print(f"\nJarak ke High: ${prev_high_global - df['high'].iloc[-1]:.2f}")
    print(f"Jarak ke Low:  ${abs(prev_low_global - df['low'].iloc[-1]):.2f}")

    print("\n--- PENJELASAN ---")
    print("Silver Bullet Strategy berfokus pada FVG Momentum, bukan Sweep.")
    print("Data Support/Resistance ini sekadar referensi visual untuk Anda.")
    mt5.shutdown()


def run_signal_diagnostic():
    print("=" * 60)
    print("  DIAGNOSA SINYAL — Cek filter Silver Bullet FVG")
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

    df_m15 = get_data(SYMBOLS[0], mt5.TIMEFRAME_M15, DATA_M15_COUNT)
    df_h4 = get_data(SYMBOLS[0], mt5.TIMEFRAME_H4, DATA_H4_COUNT)

    if df_m15.empty or df_h4.empty:
        print(f"\n[GAGAL] Data kosong! M15={len(df_m15)}, H4={len(df_h4)}")
        mt5.shutdown()
        sys.exit(1)

    print("\n--- DATA ---")
    print(f"  M15 candles: {len(df_m15)}")
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

    fvg_status, entry_price, fvg_idx = detect_fvg_retest(df_m15, bias)
    print(f"\n--- FVG RETEST (M15) ---")
    print(f"  Status   : {fvg_status}")
    if fvg_status != "Searching...":
        print(f"  Entry    : {entry_price:.2f}")
    
    side = None
    alignment_error = None
    if "BUY" in fvg_status:
        side = "BUY"
    elif "SELL" in fvg_status:
        side = "SELL"

    confluence = 0
    if side:
        # Panggil fungsi confluence sesuai pattern baru
        confluence = calculate_confluence(side, bias, fvg_status, kz_active)

    print("\n--- CONFLUENCE ---")
    print(f"  Trade Side : {side if side else 'None'}")
    print(f"  Killzone   : {'1' if kz_active else '0'}")
    if side:
        bias_aligned = (side == "BUY" and bias in ("BULLISH", "RANGING")) or (
            side == "SELL" and bias in ("BEARISH", "RANGING")
        )
        print(f"  Bias       : {'1' if bias_aligned else '0'} ({bias})")
        print(f"  FVG Status : 1 ({fvg_status})")
    else:
        print(f"  Bias       : 0 ({bias})")
        print(f"  FVG Status : 0 ({fvg_status})")
        
    print(f"  Total      : {confluence}/3 (minimum: {MIN_CONFLUENCE_SCORE})")
    print(
        f"  Lolos?     : {'YA' if side and confluence >= MIN_CONFLUENCE_SCORE else 'TIDAK'}"
    )

    print("\n--- ALIGNMENT DETAILS ---")
    if side:
        if side == "BUY":
            print("  Target: BUY")
            print(f"  Bias ({bias}) harus BULLISH/RANGING: ✅ OK")
        elif side == "SELL":
            print("  Target: SELL")
            print(f"  Bias ({bias}) harus BEARISH/RANGING: ✅ OK")
    else:
        print("  TIDAK ADA FVG yang terdeteksi dan di-retest.")

    if fvg_status != "Searching...":
        print("\n--- RISK ---")
        print("  SL & Target dihitung dinamis menggunakan ATR oleh Risk Manager.")

    print(f"\n{'=' * 60}")
    print("  RINGKASAN")
    print(f"{'=' * 60}")
    blockers = []
    if not kz_active:
        blockers.append("Di luar Killzone")
    if not side:
        blockers.append("Tidak ada FVG Retest terdeteksi")
    if side and confluence < MIN_CONFLUENCE_SCORE:
        blockers.append(f"Confluence {confluence}/3 < minimum {MIN_CONFLUENCE_SCORE}")

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
