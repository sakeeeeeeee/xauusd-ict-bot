"""
debug_sinyal.py — Diagnosa kenapa sinyal tidak muncul
Menampilkan status setiap filter secara real-time
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta

from config import (
    SYMBOL, UTC_OFFSET, KILLZONES,
    MIN_CONFLUENCE_SCORE, MIN_RISK, MAX_RISK,
    DATA_M15_COUNT, DATA_H4_COUNT,
    MA_FAST_PERIOD, MA_SLOW_PERIOD,
    SWEEP_LOOKBACK, SWEEP_CANDLE_WINDOW, IFVG_LOOKBACK,
)
from analysis import (
    get_data, detect_robust_bias, detect_sweep, detect_ifvg, calculate_confluence,
)

print("=" * 60)
print("  DIAGNOSA SINYAL — Cek setiap filter")
print("=" * 60)

# 1. Init MT5
if not mt5.initialize():
    print(f"\nMT5 GAGAL: {mt5.last_error()}")
    sys.exit(1)
print("\n[OK] MT5 connected")

# 2. Time check
wib_now = datetime.now(timezone.utc) + timedelta(hours=UTC_OFFSET)
jam = wib_now.hour
print(f"\n--- WAKTU ---")
print(f"  Sekarang : {wib_now.strftime('%H:%M:%S WIB')} (jam={jam})")
print(f"  Weekend  : {'YA' if wib_now.weekday() in (5,6) else 'TIDAK'}")

kz_active = False
for start, end in KILLZONES:
    in_kz = start <= jam < end
    status = "<<< AKTIF" if in_kz else ""
    print(f"  KZ {start:02d}:00-{end:02d}:00 : {status}")
    if in_kz:
        kz_active = True
print(f"  Dalam Killzone: {'YA' if kz_active else 'TIDAK — sinyal DIBLOKIR di sini!'}")

# 3. Fetch data
df_m15 = get_data(SYMBOL, mt5.TIMEFRAME_M15, DATA_M15_COUNT)
df_h4 = get_data(SYMBOL, mt5.TIMEFRAME_H4, DATA_H4_COUNT)

if df_m15.empty or df_h4.empty:
    print(f"\n[GAGAL] Data kosong! M15={len(df_m15)}, H4={len(df_h4)}")
    mt5.shutdown()
    sys.exit(1)

print(f"\n--- DATA ---")
print(f"  M15 candles: {len(df_m15)} (butuh min {max(MA_SLOW_PERIOD+1, SWEEP_LOOKBACK+1)})")
print(f"  H4  candles: {len(df_h4)}")
print(f"  Harga saat ini: {df_m15['close'].iloc[-1]:.2f}")

# 4. BIAS
bias = detect_robust_bias(df_h4)
ma_fast = df_h4["close"].rolling(window=MA_FAST_PERIOD).mean().iloc[-1]
ma_slow = df_h4["close"].rolling(window=MA_SLOW_PERIOD).mean().iloc[-1]
close_h4 = df_h4["close"].iloc[-1]

print(f"\n--- BIAS (H4) ---")
print(f"  Close H4 : {close_h4:.2f}")
print(f"  MA{MA_FAST_PERIOD}    : {ma_fast:.2f}")
print(f"  MA{MA_SLOW_PERIOD}    : {ma_slow:.2f}")
print(f"  Bias     : {bias}", end="")
if bias == "RANGING":
    print(" — DIBLOKIR! Harga di antara kedua MA")
else:
    print(f" — OK")

# 5. SWEEP
sweep_status, extreme_price = detect_sweep(df_m15)
print(f"\n--- SWEEP (M15, window={SWEEP_CANDLE_WINDOW} candle) ---")
print(f"  Status   : {sweep_status}", end="")
if sweep_status == "Searching...":
    # Tampilkan kenapa sweep gagal
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
        
        print(f"  Candle -{1+offset}: H={candle['high']:.2f} L={candle['low']:.2f} C={candle['close']:.2f}")
        print(f"           PrevHigh={prev_high:.2f} PrevLow={prev_low:.2f}")
        print(f"           Tembus High? {'YA' if candle['high'] > prev_high else f'TIDAK (kurang {abs(high_diff):.2f})'}")
        print(f"           Tembus Low?  {'YA' if candle['low'] < prev_low else f'TIDAK (kurang {abs(low_diff):.2f})'}")
        if candle['high'] > prev_high:
            print(f"           Close < PrevHigh? {'YA — SWEEP SELL!' if candle['close'] < prev_high else 'TIDAK — bukan sweep (close masih di atas)'}")
        if candle['low'] < prev_low:
            print(f"           Close > PrevLow? {'YA — SWEEP BUY!' if candle['close'] > prev_low else 'TIDAK — bukan sweep (close masih di bawah)'}")
else:
    print(f" — OK! Extreme={extreme_price:.2f}")

# 6. IFVG
is_ifvg, ifvg_msg = detect_ifvg(df_m15, sweep_status)
print(f"\n--- IFVG (M15, lookback={IFVG_LOOKBACK}) ---")
print(f"  Status   : {ifvg_msg}", end="")
if not is_ifvg:
    print(" — TIDAK ADA IFVG" + (" (skip karena belum ada sweep)" if sweep_status == "Searching..." else ""))
else:
    print(" — OK!")

# Determine side from sweep & alignment check
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

# 7. CONFLUENCE & ALIGNMENT
confluence = 0
if side:
    confluence = calculate_confluence(side, bias, sweep_status, ifvg_msg, kz_active)

print(f"\n--- CONFLUENCE ---")
print(f"  Trade Side : {side if side else 'None'}")
print(f"  Killzone   : {'1' if kz_active else '0'}")
if side:
    bias_aligned = (side == "BUY 🟢" and bias in ("BULLISH", "RANGING")) or (side == "SELL 🔴" and bias in ("BEARISH", "RANGING"))
    sweep_aligned = (side == "BUY 🟢" and "BUY" in sweep_status) or (side == "SELL 🔴" and "SELL" in sweep_status)
    ifvg_aligned = (side == "BUY 🟢" and "BUY" in ifvg_msg) or (side == "SELL 🔴" and "SELL" in ifvg_msg)
    
    print(f"  Bias       : {'1' if bias_aligned else '0'} ({bias})")
    print(f"  Sweep      : {'1' if sweep_aligned else '0'} ({sweep_status})")
    print(f"  IFVG       : {'1' if ifvg_aligned else '0'} ({ifvg_msg})")
else:
    print(f"  Bias       : 0 ({bias})")
    print(f"  Sweep      : 0 ({sweep_status})")
    print(f"  IFVG       : 0 ({ifvg_msg})")
print(f"  Total      : {confluence}/4 (minimum: {MIN_CONFLUENCE_SCORE})")
print(f"  Lolos?     : {'YA' if side and confluence >= MIN_CONFLUENCE_SCORE else 'TIDAK'}")

# 8. Alignment check
print(f"\n--- ALIGNMENT DETAILS ---")
if side:
    if side == "BUY 🟢":
        print(f"  Target: BUY")
        print(f"  Bias ({bias}) harus BULLISH/RANGING: ✅ OK")
        print(f"  IFVG ({ifvg_msg}) harus IFVG BUY: ✅ OK")
    elif side == "SELL 🔴":
        print(f"  Target: SELL")
        print(f"  Bias ({bias}) harus BEARISH/RANGING: ✅ OK")
        print(f"  IFVG ({ifvg_msg}) harus IFVG SELL: ✅ OK")
elif alignment_error:
    print(f"  ❌ {alignment_error}")
else:
    print("  TIDAK ADA SWEEP yang terdeteksi.")

# 9. Risk check
if extreme_price > 0:
    raw_risk = abs(df_m15['close'].iloc[-1] - extreme_price)
    print(f"\n--- RISK ---")
    print(f"  Raw risk : ${raw_risk:.2f}")
    print(f"  Min/Max  : ${MIN_RISK} - ${MAX_RISK}")
    print(f"  Valid?   : {'YA' if MIN_RISK <= raw_risk <= MAX_RISK else 'TIDAK'}")

# SUMMARY
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
    print(f"\n  SEMUA FILTER LOLOS! Sinyal seharusnya terkirim.")

mt5.shutdown()
print(f"\n{'=' * 60}")
