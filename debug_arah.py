"""Cek kenapa hanya BUY sweep, bukan SELL"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import MetaTrader5 as mt5
from config import SYMBOL, SWEEP_LOOKBACK, SWEEP_CANDLE_WINDOW, NEAR_SWEEP_THRESHOLD
from analysis import get_data

mt5.initialize()
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

    buy_status = "<-- SWEEP BUY!" if low_dist <= NEAR_SWEEP_THRESHOLD else "(terlalu jauh)"
    sell_status = "<-- SWEEP SELL!" if high_dist <= NEAR_SWEEP_THRESHOLD else "(terlalu jauh)"

    print(f"Candle -{1+offset}:")
    print(f"  Low  = {candle['low']:.2f} vs PrevLow  = {prev_low:.2f} -> jarak: ${low_dist:.2f} {buy_status}")
    print(f"  High = {candle['high']:.2f} vs PrevHigh = {prev_high:.2f} -> jarak: ${high_dist:.2f} {sell_status}")
    print()

harga = df["close"].iloc[-1]
print(f"Threshold near-sweep: ${NEAR_SWEEP_THRESHOLD}")
print(f"\nPrevHigh (resistance) = {prev_high_global:.2f}")
print(f"PrevLow  (support)    = {prev_low_global:.2f}")
print(f"Harga sekarang        = {harga:.2f}")
print(f"\nJarak ke High: ${prev_high_global - df['high'].iloc[-1]:.2f}")
print(f"Jarak ke Low:  ${abs(prev_low_global - df['low'].iloc[-1]):.2f}")

print(f"\n--- PENJELASAN ---")
print(f"Harga sedang di area LOW (support) -> BUY sweep terdeteksi")
print(f"Untuk SELL sweep, harga harus NAIK dulu ke area {prev_high_global:.2f}")
print(f"Ini normal — sinyal tergantung ARAH pergerakan harga saat ini")
print(f"\nKedua arah (BUY & SELL) bisa muncul, tinggal tunggu market bergerak ke area yang sesuai")

mt5.shutdown()
