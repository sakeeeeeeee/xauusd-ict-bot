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
# Subset killzone London/NY — digunakan untuk gating near-sweep
LONDON_NY_KILLZONES = [
    (14, 17),  # London Session
    (19, 23),  # New York Session
]

# === RISK & MONEY MANAGEMENT ===
MIN_RISK = 1.5  # Minimal SL distance (dalam dollar)
MAX_RISK = 15.0  # Maksimal SL distance (dalam dollar)
SL_BUFFER = 0.5  # Buffer di bawah swing low / di atas swing high
TP1_MULTIPLIER = 2.0  # Target Profit 1 (default 2R)
TP2_MULTIPLIER = 4.0  # Target Profit 2 (4R)
MIN_RR = 1.5  # Minimal Risk to Reward ratio untuk TP1

# === ATR DYNAMIC RISK ===
ATR_PERIOD = 14
ATR_MIN_RISK_MULT = 0.5
ATR_MAX_RISK_MULT = 2.0
ATR_SL_BUFFER_MULT = 0.2

# === EXECUTION CONFIG ===
MAX_SPREAD = (
    0.50  # Maksimal spread yang diizinkan (dalam dollar, e.g. 50 pips di XAUUSD)
)

# === NEWS BLACKOUT CONFIG ===
NEWS_BLACKOUT_MINUTES = 30  # Window (sebelum & sesudah) dalam menit untuk skip trade
NEWS_SCHEDULE_FILE = "news_blackout.json"  # File JSON berisi array string jam news (WIB), e.g. ["19:30", "21:00"]

# === BIAS DETECTION ===
MA_FAST_PERIOD = 10  # Fast MA untuk H4 bias
MA_SLOW_PERIOD = 50  # Slow MA untuk H4 bias

# === SWEEP & IFVG ===
SWEEP_LOOKBACK = 15  # Candle untuk cari swing high/low (lebih agresif)
SWEEP_CANDLE_WINDOW = 5  # Cek sweep di 5 candle terakhir (lebih agresif)
NEAR_SWEEP_THRESHOLD = 1.0  # Toleransi near-sweep ($1.0 = ~100 pips XAUUSD)
NEAR_SWEEP_ENABLED = False  # False = hanya exact sweep. True = near-sweep aktif (London/NY + bias searah).
IFVG_LOOKBACK = 15  # Candle ke belakang untuk cari FVG (fallback jika tanpa sweep)
IFVG_AFTER_SWEEP_WINDOW = 5  # IFVG harus terbentuk max 5 candle setelah sweep
DATA_M15_COUNT = 60  # Jumlah candle M15 yang di-fetch (harus > MA_SLOW_PERIOD)
DATA_H4_COUNT = 60  # Jumlah candle H4 (butuh >= 50 untuk MA_SLOW)

# === CONFLUENCE TIERS ===
# Tier SWING (default): Hanya sinyal berkualitas tinggi, minimum 3/4.
#   → Cocok untuk swing trader yang ingin akurasi lebih baik.
# Tier AGGRESSIVE: Sinyal lebih sering, minimum 2/4.
#   → Lebih banyak setup, tapi potensi false signal lebih tinggi.
MIN_CONFLUENCE_SCORE = 3  # Default tier SWING (min 3/4 untuk kirim sinyal)

# === TIMING ===
SCAN_INTERVAL = 30  # Detik antara setiap scan
SLEEP_OUTSIDE_KZ = 60  # Detik sleep di luar killzone
ERROR_SLEEP = 10  # Detik sleep setelah error
WEEKEND_SLEEP = 3600  # Detik sleep di weekend (1 jam)
