"""
config.py — Konfigurasi & Konstanta Bot XAUUSD
Semua parameter yang bisa di-tune ada di sini.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# === CREDENTIALS (dari .env) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === TRADING SYMBOL ===
SYMBOL = "XAUUSD"

# === TIMEZONE ===
UTC_OFFSET = 7  # WIB (Jakarta/Medan)

# === KILLZONE SESSIONS (dalam jam WIB) ===
KILLZONES = [
    (8, 10),  # Asia Session (XAUUSD tetap aktif)
    (14, 17),  # London Session
    (19, 23),  # New York Session
]

# === RISK MANAGEMENT ===
MIN_RISK = 1.50  # Minimum SL distance ($1.50 = ~150 pips XAUUSD)
MAX_RISK = 15.0  # Maximum SL distance ($15 = ~1500 pips)
SL_BUFFER = 0.50  # Buffer tambahan di atas/bawah sweep point ($0.50)
TP1_MULTIPLIER = 2  # TP1 = 2R
TP2_MULTIPLIER = 4  # TP2 = 4R

# === BIAS DETECTION ===
MA_FAST_PERIOD = 10  # Fast MA untuk H4 bias
MA_SLOW_PERIOD = 50  # Slow MA untuk H4 bias

# === SWEEP & IFVG ===
SWEEP_LOOKBACK = 15  # Candle untuk cari swing high/low (lebih agresif)
SWEEP_CANDLE_WINDOW = 5  # Cek sweep di 5 candle terakhir (lebih agresif)
NEAR_SWEEP_THRESHOLD = 1.0  # Toleransi near-sweep ($1.0 = ~100 pips XAUUSD)
IFVG_LOOKBACK = 15  # Candle ke belakang untuk cari FVG
DATA_M15_COUNT = 60  # Jumlah candle M15 yang di-fetch (harus > MA_SLOW_PERIOD)
DATA_H4_COUNT = 60  # Jumlah candle H4 (butuh >= 50 untuk MA_SLOW)

# === CONFLUENCE ===
MIN_CONFLUENCE_SCORE = 2  # Minimum score untuk kirim sinyal (max 4) — agresif

# === TIMING ===
SCAN_INTERVAL = 30  # Detik antara setiap scan
SLEEP_OUTSIDE_KZ = 60  # Detik sleep di luar killzone
ERROR_SLEEP = 10  # Detik sleep setelah error
WEEKEND_SLEEP = 3600  # Detik sleep di weekend (1 jam)
