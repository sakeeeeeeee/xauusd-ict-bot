"""
telegram_bot.py — Interactive Telegram Bot Module
=================================================
Two-way communication: receive commands + send signals.
Includes inline keyboard for easy interaction.

Architecture:
  - Bot polling runs in a separate daemon thread
  - Shares state with main engine via `bot_state` dict
  - Signal notifications still use requests.post (sync, thread-safe)
"""

import json
import logging
import threading
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from src.config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    SYMBOL,
    UTC_OFFSET,
    KILLZONES,
    MIN_CONFLUENCE_SCORE,
    MIN_RISK,
    MAX_RISK,
    SL_BUFFER,
    TP1_MULTIPLIER,
    TP2_MULTIPLIER,
    MA_FAST_PERIOD,
    MA_SLOW_PERIOD,
    SWEEP_LOOKBACK,
    IFVG_LOOKBACK,
    SCAN_INTERVAL,
    SLEEP_OUTSIDE_KZ,
)

logger = logging.getLogger("xauusd_bot")


# ============================================================
#  SHARED STATE (updated by main engine, read by bot handlers)
# ============================================================

bot_state = {
    "running": False,
    "paused": False,
    "bias": "UNKNOWN",
    "sweep": "N/A",
    "ifvg": "N/A",
    "confluence": 0,
    "price": 0.0,
    "killzone_active": False,
    "last_signal_time": None,
    "last_scan_time": None,
    "mt5_connected": False,
    "start_time": None,
    "market_open": True,
}

_state_lock = threading.Lock()

# Event for waking up the main scan loop (e.g. on /resume)
scan_event = threading.Event()

_bot_thread: threading.Thread | None = None
_bot_app: Application | None = None
_bot_loop: asyncio.AbstractEventLoop | None = None


async def _post_init(app: Application):
    """Dipanggil PTB saat startup, untuk meng-capture asyncio event loop."""
    global _bot_loop
    _bot_loop = asyncio.get_running_loop()
    logger.debug("Captured PTB asyncio event loop.")


# ============================================================
#  THREAD-SAFE STATE HELPERS
# ============================================================


def get_state(key: str):
    """Thread-safe read satu key dari bot_state."""
    with _state_lock:
        return bot_state[key]


def set_state(key: str, value):
    """Thread-safe write satu key ke bot_state."""
    with _state_lock:
        bot_state[key] = value


def update_state(data: dict):
    """Thread-safe batch update bot_state."""
    with _state_lock:
        bot_state.update(data)


def snapshot_state() -> dict:
    """Thread-safe copy seluruh bot_state (untuk render text)."""
    with _state_lock:
        return dict(bot_state)


# ============================================================
#  HELPERS
# ============================================================


def _wib_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=UTC_OFFSET)


def _is_authorized(update: Update) -> bool:
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)


def _uptime() -> str:
    start = get_state("start_time")
    if not start:
        return "N/A"
    delta = datetime.now() - start
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    return f"{h}j {m}m {s}d" if h else (f"{m}m {s}d" if m else f"{s}d")


# ============================================================
#  INLINE KEYBOARDS
# ============================================================


def _kb_main() -> InlineKeyboardMarkup:
    pause_btn = (
        InlineKeyboardButton("▶️ Resume", callback_data="resume")
        if get_state("paused")
        else InlineKeyboardButton("⏸️ Pause", callback_data="pause")
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("📈 Bias", callback_data="bias"),
            ],
            [
                InlineKeyboardButton("🎯 Scan Now", callback_data="signal"),
                InlineKeyboardButton("📋 Stats", callback_data="stats"),
            ],
            [
                InlineKeyboardButton("⚙️ Config", callback_data="config"),
                pause_btn,
            ],
        ]
    )


def _kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu")],
        ]
    )


def _kb_status() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="status"),
                InlineKeyboardButton("🔙 Menu", callback_data="menu"),
            ],
        ]
    )


# ============================================================
#  RESPONSE TEXT BUILDERS
# ============================================================


def _txt_status() -> str:
    s = snapshot_state()
    wib = _wib_now().strftime("%H:%M:%S WIB")
    if s["running"] and not s["paused"]:
        st_e, st_t = "🟢", "SCANNING"
    elif s["paused"]:
        st_e, st_t = "🟡", "PAUSED"
    else:
        st_e, st_t = "🔴", "STOPPED"

    return (
        f"📊 *BOT STATUS*\n⏰ {wib}\n{'━' * 22}\n\n"
        f"{st_e} Engine: *{st_t}*\n"
        f"{'✅' if s['mt5_connected'] else '❌'} MT5: "
        f"{'Connected' if s['mt5_connected'] else 'Disconnected'}\n"
        f"{'🟢' if s['market_open'] else '🔴'} Market: "
        f"{'Open' if s['market_open'] else 'Closed'}\n"
        f"{'🟢' if s['killzone_active'] else '⚪'} Killzone: "
        f"{'Active 🔥' if s['killzone_active'] else 'Inactive'}\n\n"
        f"💰 {SYMBOL}: `{s['price']}`\n"
        f"📈 Bias: {s['bias']}\n"
        f"💧 Sweep: {s['sweep']}\n"
        f"🧲 IFVG: {s['ifvg']}\n"
        f"🔗 Confluence: {s['confluence']}/4\n\n"
        f"⏱️ Uptime: {_uptime()}\n"
        f"🕐 Last Scan: {s['last_scan_time'] or 'N/A'}"
    )


def _txt_bias() -> str:
    s = snapshot_state()
    bias = s["bias"]
    if bias == "BULLISH":
        emoji, desc = "🟢📈", "Price di atas MA Fast & Slow → Trend naik kuat"
    elif bias == "BEARISH":
        emoji, desc = "🔴📉", "Price di bawah MA Fast & Slow → Trend turun kuat"
    elif bias == "RANGING":
        emoji, desc = "🟡↔️", "Price di antara MA → Tidak ada trend jelas"
    else:
        emoji, desc = "❓", "Belum ada data (engine belum scan)"
    return (
        f"📈 *MARKET BIAS — H4*\n⏰ {_wib_now().strftime('%H:%M:%S WIB')}\n"
        f"{'━' * 22}\n\n"
        f"{emoji} Bias: *{bias}*\n\n💡 {desc}\n\n"
        f"📊 MA Fast({MA_FAST_PERIOD}) vs Slow({MA_SLOW_PERIOD})\n"
        f"💰 Price: `{s['price']}`"
    )


def _txt_signal() -> str:
    s = snapshot_state()
    c = s["confluence"]
    if c >= 4:
        q = "🟢 STRONG SETUP"
    elif c >= 3:
        q = "🟡 VALID SETUP"
    elif c >= 2:
        q = "🟠 WEAK"
    else:
        q = "🔴 NO SETUP"
    return (
        f"🎯 *SCAN RESULT*\n⏰ {_wib_now().strftime('%H:%M:%S WIB')}\n"
        f"{'━' * 22}\n\n"
        f"💰 {SYMBOL}: `{s['price']}`\n"
        f"📈 Bias: {s['bias']}\n💧 Sweep: {s['sweep']}\n"
        f"🧲 IFVG: {s['ifvg']}\n"
        f"{'🟢' if s['killzone_active'] else '⚪'} Killzone: "
        f"{'Active' if s['killzone_active'] else 'Inactive'}\n\n"
        f"🔗 Confluence: *{c}/4*\n📊 Quality: {q}\n\n"
        f"_Data dari scan: {s['last_scan_time'] or 'N/A'}_"
    )


def _txt_stats() -> str:
    try:
        fpath = Path("trade_history.json")
        if not fpath.exists():
            return "📋 *TRADE STATS*\n\nBelum ada trade yang tercatat."
        with open(fpath, "r") as f:
            trades = json.load(f)
        if not trades:
            return "📋 *TRADE STATS*\n\nBelum ada trade yang tercatat."
        total = len(trades)
        buys = sum(1 for t in trades if "BUY" in t.get("side", ""))
        sells = sum(1 for t in trades if "SELL" in t.get("side", ""))
        pending = sum(1 for t in trades if t.get("result") == "PENDING")
        recent_lines = ""
        for t in reversed(trades[-3:]):
            e = "🟢" if "BUY" in t.get("side", "") else "🔴"
            recent_lines += (
                f"  {e} {t.get('side', '?')} @ `{t.get('entry', '?')}` — "
                f"{t.get('result', 'PENDING')}\n"
            )
        return (
            f"📋 *TRADE STATISTICS*\n{'━' * 22}\n\n"
            f"📊 Total Signals: *{total}*\n"
            f"🟢 Buy: {buys}  |  🔴 Sell: {sells}\n"
            f"⏳ Pending: {pending}\n\n"
            f"📝 *Recent Trades:*\n{recent_lines}"
        )
    except Exception as e:
        return f"📋 *TRADE STATS*\n\n❌ Error: {e}"


def _txt_config() -> str:
    kz = " | ".join(f"{s:02d}:00-{e:02d}:00" for s, e in KILLZONES)
    return (
        f"⚙️ *KONFIGURASI AKTIF*\n{'━' * 22}\n\n"
        f"🪙 Symbol: `{SYMBOL}`\n🕐 Timezone: UTC+{UTC_OFFSET} (WIB)\n\n"
        f"*Risk Management:*\n"
        f"  Min Risk: ${MIN_RISK}  |  Max Risk: ${MAX_RISK}\n"
        f"  SL Buffer: ${SL_BUFFER}\n"
        f"  TP1: {TP1_MULTIPLIER}R  |  TP2: {TP2_MULTIPLIER}R\n\n"
        f"*Analysis:*\n"
        f"  MA Fast: {MA_FAST_PERIOD}  |  Slow: {MA_SLOW_PERIOD}\n"
        f"  Sweep LB: {SWEEP_LOOKBACK}  |  IFVG LB: {IFVG_LOOKBACK}\n"
        f"  Min Confluence: {MIN_CONFLUENCE_SCORE}/4\n\n"
        f"*Timing:*\n"
        f"  Scan: {SCAN_INTERVAL}s  |  KZ: {kz}\n"
        f"  Sleep Outside KZ: {SLEEP_OUTSIDE_KZ}s"
    )


# ============================================================
#  COMMAND HANDLERS (/command from chat)
# ============================================================


async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    text = (
        "🤖 *XAUUSD ICT Bot — Control Panel*\n"
        f"⏰ {_wib_now().strftime('%H:%M WIB')}\n\n"
        "Selamat datang! Pilih menu di bawah "
        "untuk berinteraksi dengan bot.\n\n"
        "_Powered by ICT Engine v2.0_"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=_kb_main()
    )


async def _cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    text = (
        "📖 *Daftar Command:*\n\n"
        "/start — Menu utama\n"
        "/status — Status bot & engine\n"
        "/bias — Market bias H4\n"
        "/signal — Hasil scan terkini\n"
        "/pause — Pause scanning\n"
        "/resume — Resume scanning\n"
        "/stats — Statistik trade\n"
        "/config — Konfigurasi aktif\n"
        "/help — Tampilkan menu ini"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=_kb_back()
    )


async def _cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        _txt_status(), parse_mode="Markdown", reply_markup=_kb_status()
    )


async def _cmd_bias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        _txt_bias(), parse_mode="Markdown", reply_markup=_kb_back()
    )


async def _cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        _txt_signal(), parse_mode="Markdown", reply_markup=_kb_back()
    )


async def _cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    set_state("paused", True)
    logger.info("⏸️ Bot PAUSED by user via Telegram.")
    await update.message.reply_text(
        "⏸️ *Bot PAUSED*\n\nScanning dihentikan.\nKetik /resume untuk lanjut.",
        parse_mode="Markdown",
        reply_markup=_kb_main(),
    )


async def _cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    set_state("paused", False)
    scan_event.set()
    logger.info("▶️ Bot RESUMED by user via Telegram.")
    await update.message.reply_text(
        "▶️ *Bot RESUMED*\n\nScanning dilanjutkan! 🚀",
        parse_mode="Markdown",
        reply_markup=_kb_main(),
    )


async def _cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        _txt_stats(), parse_mode="Markdown", reply_markup=_kb_back()
    )


async def _cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        _txt_config(), parse_mode="Markdown", reply_markup=_kb_back()
    )


# ============================================================
#  CALLBACK QUERY HANDLER (inline keyboard buttons)
# ============================================================


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_authorized(update):
        await query.answer("⛔ Unauthorized")
        return

    await query.answer()
    data = query.data

    try:
        if data == "menu":
            text = (
                "🤖 *XAUUSD ICT Bot — Control Panel*\n"
                f"⏰ {_wib_now().strftime('%H:%M WIB')}\n\n"
                "Pilih menu di bawah untuk berinteraksi.\n\n"
                "_Powered by ICT Engine v2.0_"
            )
            await query.edit_message_text(
                text, parse_mode="Markdown", reply_markup=_kb_main()
            )
        elif data == "status":
            await query.edit_message_text(
                _txt_status(), parse_mode="Markdown", reply_markup=_kb_status()
            )
        elif data == "bias":
            await query.edit_message_text(
                _txt_bias(), parse_mode="Markdown", reply_markup=_kb_back()
            )
        elif data == "signal":
            await query.edit_message_text(
                _txt_signal(), parse_mode="Markdown", reply_markup=_kb_back()
            )
        elif data == "stats":
            await query.edit_message_text(
                _txt_stats(), parse_mode="Markdown", reply_markup=_kb_back()
            )
        elif data == "config":
            await query.edit_message_text(
                _txt_config(), parse_mode="Markdown", reply_markup=_kb_back()
            )
        elif data == "pause":
            set_state("paused", True)
            logger.info("⏸️ Bot PAUSED by user via Telegram.")
            await query.edit_message_text(
                "⏸️ *Bot PAUSED*\n\nScanning dihentikan.\nTekan ▶️ Resume untuk lanjut.",
                parse_mode="Markdown",
                reply_markup=_kb_main(),
            )
        elif data == "resume":
            set_state("paused", False)
            scan_event.set()
            logger.info("▶️ Bot RESUMED by user via Telegram.")
            await query.edit_message_text(
                "▶️ *Bot RESUMED*\n\nScanning dilanjutkan! 🚀",
                parse_mode="Markdown",
                reply_markup=_kb_main(),
            )
    except Exception as e:
        logger.warning(f"Callback error: {e}")


# ============================================================
#  OUTBOUND NOTIFICATIONS (backward compatible, sync)
# ============================================================


def kirim_telegram(pesan: str, timeout: int = 10) -> bool:
    """
    Kirim pesan ke Telegram.
    Prioritas utama: gunakan PTB async loop via run_coroutine_threadsafe.
    Fallback: requests.post (jika PTB loop mati / belum siap).
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_TOKEN atau TELEGRAM_CHAT_ID belum diset di .env!")
        return False

    # Jalur Utama: PTB Application bot
    if _bot_app and _bot_loop and _bot_loop.is_running():
        try:
            coro = _bot_app.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=pesan,
                parse_mode="Markdown",
                read_timeout=timeout,
                write_timeout=timeout,
            )
            future = asyncio.run_coroutine_threadsafe(coro, _bot_loop)
            future.result(timeout=timeout + 5)
            logger.info("Telegram: Pesan terkirim (via PTB async).")
            return True
        except Exception as e:
            logger.warning(
                f"Telegram PTB Error: {e}. Mencoba fallback requests.post..."
            )
            # Fallback ke requests.post jika gagal via PTB

    # Jalur Fallback: requests.post
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": pesan,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        logger.info("Telegram: Pesan terkirim (via requests fallback).")
        return True
    except requests.exceptions.Timeout:
        logger.warning("Telegram: Timeout saat mengirim pesan (fallback).")
        return False
    except requests.exceptions.HTTPError as e:
        logger.error(f"Telegram HTTP Error (fallback): {e} | Response: {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Telegram Error (fallback): {e}")
        return False


def kirim_startup_notification():
    """Kirim notifikasi bahwa bot sudah online + interactive mode."""
    pesan = (
        "🟢 *BOT XAUUSD ONLINE*\n\n"
        "Interactive mode aktif! 🤖\n"
        "Ketik /start untuk buka control panel.\n\n"
        "_ICT Engine v2.0 — Scanning for setups..._"
    )
    return kirim_telegram(pesan)


# ============================================================
#  BOT LIFECYCLE
# ============================================================


def _run_bot():
    """Entry point for the bot polling thread."""
    global _bot_app
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).post_init(_post_init).build()
        _bot_app = app

        # Command handlers
        app.add_handler(CommandHandler("start", _cmd_start))
        app.add_handler(CommandHandler("help", _cmd_help))
        app.add_handler(CommandHandler("status", _cmd_status))
        app.add_handler(CommandHandler("bias", _cmd_bias))
        app.add_handler(CommandHandler("signal", _cmd_signal))
        app.add_handler(CommandHandler("pause", _cmd_pause))
        app.add_handler(CommandHandler("resume", _cmd_resume))
        app.add_handler(CommandHandler("stats", _cmd_stats))
        app.add_handler(CommandHandler("config", _cmd_config))

        # Inline keyboard callback handler
        app.add_handler(CallbackQueryHandler(_handle_callback))

        logger.info("🤖 Telegram interactive bot started (polling mode).")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            stop_signals=None,  # Non-main thread: skip signal handlers
        )
    except Exception as e:
        logger.error(f"Telegram bot thread error: {e}", exc_info=True)


def start_telegram_bot():
    """Start the interactive Telegram bot in a background daemon thread."""
    global _bot_thread
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Cannot start interactive bot: TELEGRAM_TOKEN/CHAT_ID not set!")
        return

    _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="TelegramBot")
    _bot_thread.start()
    logger.info("✅ Telegram interactive bot thread started.")
