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

# === SESSION RULES ===
SESSION_RULES = {
    "ASIA": ["WATCH", "SCALP"],
    "LONDON": ["WATCH", "SCALP", "SWING"],
    "NY": ["WATCH", "SCALP", "SWING"],
}

# === RISK & MONEY MANAGEMENT ===
MIN_RISK = 1.5  # Minimal SL distance (dalam dollar)
MAX_RISK = 15.0  # Maksimal SL distance (dalam dollar)
SL_BUFFER = 0.5  # Buffer di bawah swing low / di atas swing high
TP1_MULTIPLIER = 2.0  # Target Profit 1 (default 2R)
TP2_MULTIPLIER = 4.0  # Target Profit 2 (4R)
MAX_TRADE_DURATION_CANDLES = 24  # Maksimal umur trade sebelum dianggap EXPIRED
MIN_RR = 1.5  # Minimal Risk to Reward ratio untuk TP1

# === ATR DYNAMIC RISK ===
ATR_PERIOD = 14
ATR_MIN_RISK_MULT = 0.5
ATR_MAX_RISK_MULT = 2.0
ATR_SL_BUFFER_MULT = 0.2

# === MACHINE LEARNING CONFIG ===
MIN_TRADES_FOR_ML = 200  # Minimal jumlah data resolved (WIN/LOSS) sebelum melatih model ML
USE_ML_FILTER = False    # Aktifkan jika model ML sudah dilatih dan siap digunakan
ML_THRESHOLD = 0.65      # Minimal probabilitas (P) kemenangan untuk mengizinkan sinyal dikirim

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

# === SWEEP & IFVG ===
SWEEP_LOOKBACK = 15  # Candle untuk cari swing high/low (lebih agresif)
SWEEP_CANDLE_WINDOW = 5  # Cek sweep di 5 candle terakhir (lebih agresif)
NEAR_SWEEP_THRESHOLD = 1.0  # Toleransi near-sweep ($1.0 = ~100 pips XAUUSD)
NEAR_SWEEP_ENABLED = False  # False = hanya exact sweep. True = near-sweep aktif (London/NY + bias searah).
REQUIRE_SWEEP = True   # True = sweep wajib ada untuk valid entry
REQUIRE_IFVG = True    # True = IFVG wajib ada untuk valid entry
IFVG_LOOKBACK = 15  # Candle ke belakang untuk cari FVG (fallback jika tanpa sweep)
IFVG_AFTER_SWEEP_WINDOW = 5  # IFVG harus terbentuk max 5 candle setelah sweep
DATA_M15_COUNT = 60  # Jumlah candle M15 yang di-fetch (harus > MA_SLOW_PERIOD)
DATA_M5_COUNT = 60  # Jumlah candle M5 yang di-fetch (untuk precise entry)
DATA_H4_COUNT = 60  # Jumlah candle H4 (butuh >= 50 untuk MA_SLOW)

# === M5 TRIGGER MODE ===
USE_M5_TRIGGER = True  # True = sweep/IFVG dari M5, False = dari M15 (legacy)

# === CONFLUENCE TIERS ===
# Tier SCALP: Entry cepat dengan syarat ketat sweep+IFVG alignment.
MIN_CONFLUENCE_SCALP = 2
TP1_SCALP_R = 1.2  # TP1 = 1.2R (target kecil, cepat keluar)
TP2_SCALP_R = 2.0  # TP2 = 2R

# Tier SWING: Sinyal berkualitas tinggi, minimum 3/4 confluence.
MIN_CONFLUENCE_SWING = 3
# (TP1/TP2 SWING menggunakan TP1_MULTIPLIER/TP2_MULTIPLIER default: 2R/4R)

# === TIMING ===
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", 15))
SLEEP_OUTSIDE_KZ = int(os.getenv("SLEEP_OUTSIDE_KZ", 300))
ERROR_SLEEP = int(os.getenv("ERROR_SLEEP", 60))
WEEKEND_SLEEP = int(os.getenv("WEEKEND_SLEEP", 3600))
HEALTH_PING_INTERVAL_HOURS = int(os.getenv("HEALTH_PING_INTERVAL_HOURS", 6))
MIN_CONFLUENCE_SCORE = int(os.getenv("MIN_CONFLUENCE_SCORE", 3))

# === STRATEGY PRESETS ===
STRATEGY_PRESET = os.getenv("STRATEGY_PRESET", "balanced").lower()

STRATEGY_PRESETS = {
    "conservative": {
        "MIN_CONFLUENCE_SCORE": 4,
        "REQUIRE_SWEEP": True,
        "NEAR_SWEEP_ENABLED": False,
        "REQUIRE_IFVG": True,
    },
    "balanced": {
        "MIN_CONFLUENCE_SCORE": 3,
        "REQUIRE_SWEEP": True,
        "NEAR_SWEEP_ENABLED": False,
        "REQUIRE_IFVG": True,
    },
    "aggressive": {
        "MIN_CONFLUENCE_SCORE": 2,
        "REQUIRE_SWEEP": False,
        "NEAR_SWEEP_ENABLED": True,
        "REQUIRE_IFVG": False,
    }
}

# Apply Preset Overrides
if STRATEGY_PRESET in STRATEGY_PRESETS:
    preset = STRATEGY_PRESETS[STRATEGY_PRESET]
    MIN_CONFLUENCE_SCORE = preset.get("MIN_CONFLUENCE_SCORE", MIN_CONFLUENCE_SCORE)
    REQUIRE_SWEEP = preset.get("REQUIRE_SWEEP", REQUIRE_SWEEP)
    NEAR_SWEEP_ENABLED = preset.get("NEAR_SWEEP_ENABLED", NEAR_SWEEP_ENABLED)
    REQUIRE_IFVG = preset.get("REQUIRE_IFVG", REQUIRE_IFVG)
