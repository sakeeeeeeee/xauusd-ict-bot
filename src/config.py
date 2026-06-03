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

# === TRADING SYMBOLS ===
SYMBOLS = ["XAUUSD"]
SYMBOL_ALIASES = {
    "XAUUSD": ["XAUUSD.m", "XAUUSD.ecn", "XAUUSD.pro", "XAUUSDm", "GOLD"],
    "EURUSD": ["EURUSD.m", "EURUSD.ecn", "EURUSD.pro", "EURUSDm"],
    "GBPUSD": ["GBPUSD.m", "GBPUSD.ecn", "GBPUSD.pro", "GBPUSDm"],
}


# === KILLZONE SESSIONS (dalam jam WIB) ===
KILLZONES = [
    (8, 10),  # Asia Session (XAUUSD tetap aktif)
    (14, 17),  # London Session
    (19, 23),  # New York Session
]

# === DYNAMIC WEEKLY PROFILE ===
TREND_DAYS = [0, 1, 2]     # Monday, Tuesday, Wednesday (SWING only)
RANGING_DAYS = [3, 4]      # Thursday, Friday (SCALP only)

# Subset killzone London/NY — digunakan untuk gating near-sweep
LONDON_NY_KILLZONES = [
    (14, 18),  # London (14:00 - 18:00 WIB)
    (19, 23),  # NY (19:00 - 23:00 WIB)
]

# === SESSION RULES ===
# Tiers allowed per session. SCALP requires confluence 2, SWING requires confluence 3.
# (But dynamically filtered by Weekly Profile in main.py)
SESSION_RULES = {
    "ASIA": [],
    "LONDON": ["WATCH", "SCALP", "SWING"],
    "NY": ["WATCH", "SCALP", "SWING"],
}

# === RISK & MONEY MANAGEMENT ===
MIN_RISK = 1.5  # Minimal SL distance (dalam dollar)
MAX_RISK = 15.0  # Maksimal SL distance (dalam dollar)
SL_BUFFER = 0.5  # Buffer di bawah swing low / di atas swing high
TP1_MULTIPLIER = 1.0  # Target Profit 1 (default 1R berdasarkan optimize)
TP2_MULTIPLIER = 2.0  # Target Profit 2 (2R)
MAX_TRADE_DURATION_CANDLES = 48  # Maksimal umur trade sebelum dianggap EXPIRED (48 x M15 = 12 jam)
MIN_RR = 1.0  # Minimal Risk to Reward ratio untuk TP1

# === ATR DYNAMIC RISK ===
ATR_PERIOD = 14
ATR_MIN_RISK_MULT = 0.5
ATR_MAX_RISK_MULT = 5.0
ATR_SL_BUFFER_MULT = 0.8

# === PER-SESSION OVERRIDES ===
# Pengaturan ini menimpa konfigurasi global di atas berdasarkan sesi aktif
SESSION_SETTINGS = {
    "LONDON": {
        "ATR_SL_BUFFER_MULT": 0.8,
        "TP1_MULTIPLIER": 1.0,
        "MIN_CONFLUENCE": 2,  # London: 2/3 cukup (RANGING FVG = 60% WR)
    },
    "NY": {
        "ATR_SL_BUFFER_MULT": 0.8,
        "TP1_MULTIPLIER": 1.0,
        "MIN_CONFLUENCE": 2,  # NY SCALP requires 2 (dynamically filtered by DOW)
    },
}


# === EXECUTION CONFIG ===
TRADING_MODE = "SIGNAL_ONLY"  # "SIGNAL_ONLY" atau "AUTO_TRADE"
RISK_PERCENT = 1.0  # % equity yang di-risk per trade (hanya berlaku jika AUTO_TRADE / untuk lot suggestion)
MAX_OPEN_POSITIONS = 2  # Maksimal posisi XAUUSD yang boleh terbuka bersamaan
MAX_SLIPPAGE_POINTS = 20  # Maksimal slippage dalam points (20 points = 2 pips XAU)
MAX_SPREAD = (
    0.50  # Maksimal spread yang diizinkan (dalam dollar, e.g. 50 pips di XAUUSD)
)

# === TELEGRAM NOTIFICATION CONFIG ===
HEALTH_PING_INTERVAL = 6  # Interval pengiriman status bot secara periodik (dalam jam)

# === VISUALIZATION CONFIG ===
CHART_ENABLED = True  # Aktifkan untuk mengirim gambar grafik M15 ke Telegram

# === NEWS BLACKOUT CONFIG ===
NEWS_BLACKOUT_MINUTES = 30  # Window (sebelum & sesudah) dalam menit untuk skip trade
NEWS_SCHEDULE_FILE = "news_blackout.json"  # File JSON berisi array string jam news (WIB), e.g. ["19:30", "21:00"]

# === BIAS DETECTION ===
MA_FAST_PERIOD = 10  # Fast MA untuk H4 bias
MA_SLOW_PERIOD = 50  # Slow MA untuk H4 bias

# === SILVER BULLET & FVG ===
DATA_M15_COUNT = 60  # Jumlah candle M15 yang di-fetch (harus > MA_SLOW_PERIOD)
DATA_M5_COUNT = 60  # Jumlah candle M5 yang di-fetch (untuk precise entry)
DATA_H4_COUNT = 60  # Jumlah candle H4 (butuh >= 50 untuk MA_SLOW)

# === CONFLUENCE TIERS ===
# Tier SWING: Sinyal berkualitas tinggi, minimum 2/3 confluence (Time + Bias + FVG).
MIN_CONFLUENCE_SWING = 3

# === TIMING ===
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", 15))
SLEEP_OUTSIDE_KZ = int(os.getenv("SLEEP_OUTSIDE_KZ", 300))
# Konfigurasi offset jam (Standar WIB adalah 7)
UTC_OFFSET = int(os.getenv("UTC_OFFSET", 7))
# Offset timezone Broker (Exness biasanya UTC+2/3)
BROKER_UTC_OFFSET = int(os.getenv("BROKER_UTC_OFFSET", 3))
ERROR_SLEEP = int(os.getenv("ERROR_SLEEP", 60))
WEEKEND_SLEEP = int(os.getenv("WEEKEND_SLEEP", 3600))
HEALTH_PING_INTERVAL_HOURS = int(os.getenv("HEALTH_PING_INTERVAL_HOURS", 6))
MIN_CONFLUENCE_SCORE = int(os.getenv("MIN_CONFLUENCE_SCORE", 3))

# Catatan: STRATEGY_PRESET (conservative/balanced/aggressive) dari versi sebelumnya
# telah dihapus karena Silver Bullet murni berbasis pada setup mekanikal (FVG Momentum + Time)
# dan tidak memerlukan penyesuaian berlapis seperti strategi Sweep lama.
