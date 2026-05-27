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

import logging
import threading
import asyncio
from datetime import datetime, timezone, timedelta

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from src.config import (
    SYMBOLS,
    RISK_PERCENT, REQUIRE_SWEEP, REQUIRE_IFVG, MIN_RR,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    UTC_OFFSET,
    MIN_RISK,
    MAX_RISK,
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
    # health/ops tracking
    "last_health_ping": None,
    "mt5_disconnect_time": None,
    "mt5_disconnect_alert_sent": False,
    "mt5_reconnect_attempts": 0,
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
        import copy
        return copy.deepcopy(bot_state)


def update_symbol_state(symbol: str, data: dict):
    """Thread-safe batch update per-symbol nested state."""
    with _state_lock:
        if "symbols" not in bot_state:
            bot_state["symbols"] = {}
        if symbol not in bot_state["symbols"]:
            bot_state["symbols"][symbol] = {}
        bot_state["symbols"][symbol].update(data)


def set_symbol_state(symbol: str, key: str, value):
    """Thread-safe write satu key di nested symbol state."""
    with _state_lock:
        if "symbols" not in bot_state:
            bot_state["symbols"] = {}
        if symbol not in bot_state["symbols"]:
            bot_state["symbols"][symbol] = {}
        bot_state["symbols"][symbol][key] = value


def get_symbol_state(symbol: str, key: str, default=None):
    """Thread-safe read satu key dari nested symbol state."""
    with _state_lock:
        return bot_state.get("symbols", {}).get(symbol, {}).get(key, default)


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
    run_status = "✅ RUNNING" if s.get("running") else "🛑 STOPPED"
    if s.get("paused"):
        run_status = "⏸️ PAUSED"
    mt5_conn = "✅ Connected" if s.get("mt5_connected") else "❌ Disconnected"
    
    out = [f"🖥️ *SYSTEM STATUS* ({wib})\n\n🤖 Bot: {run_status}\n🔌 MT5: {mt5_conn}\n"]
    for sym in SYMBOLS:
        sym_s = s.get("symbols", {}).get(sym, {})
        market = "✅ Open" if sym_s.get("market_open") else "😴 Closed"
        kz = "🔥 Active" if sym_s.get("killzone_active") else "⏳ Waiting"
        out.append(f"\n🔸 *{sym}*\n🏛️ Market: {market}\n🎯 Killzone: {kz}")
        out.append(f"⏱️ Last Scan: `{sym_s.get('last_scan_time', 'N/A')}`")
        out.append(f"📌 Last Signal: `{sym_s.get('last_signal_time', 'N/A')}`")
    return "\n".join(out)


def _txt_bias() -> str:
    s = snapshot_state()
    out = ["📈 *CURRENT BIAS (H4)*"]
    for sym in SYMBOLS:
        sym_s = s.get("symbols", {}).get(sym, {})
        out.append(f"\n🔸 *{sym}*")
        out.append(f"Direction: `{sym_s.get('bias', 'UNKNOWN')}`")
        out.append(f"Structure: `{sym_s.get('h4_struct', 'UNKNOWN')}`")
        out.append(f"PD Zone: `{sym_s.get('pd_zone', 'UNKNOWN')}`")
    return "\n".join(out)

def _txt_signal() -> str:
    s = snapshot_state()
    out = ["🎯 *LAST SIGNAL INFO*"]
    for sym in SYMBOLS:
        sym_s = s.get("symbols", {}).get(sym, {})
        out.append(f"\n🔸 *{sym}*")
        out.append(f"Sweep: `{sym_s.get('sweep', 'N/A')}`")
        out.append(f"IFVG: `{sym_s.get('ifvg', 'N/A')}`")
        out.append(f"Confluence: `{sym_s.get('confluence', 0)}/4`")
        out.append(f"Price: `{sym_s.get('price', 0.0)}`")
    return "\n".join(out)

def _txt_stats() -> str:
    s = snapshot_state()
    wib = _wib_now().strftime("%H:%M:%S WIB")
    out = [f"🎯 *SCAN RESULT*\n⏰ {wib}\n" + "━"*22]
    for sym in SYMBOLS:
        sym_s = s.get("symbols", {}).get(sym, {})
        out.append(f"\n🔸 *{sym}*: `{sym_s.get('price', 0)}`")
        out.append(f"📈 Bias: {sym_s.get('bias', 'N/A')} | 💧 Sweep: {sym_s.get('sweep', 'N/A')}")
        out.append(f"🧲 IFVG: {sym_s.get('ifvg', 'N/A')} | 🔗 Confluence: {sym_s.get('confluence', 0)}/4")
    return "\n".join(out)

def _txt_config() -> str:
    return (
        "⚙️ *KONFIGURASI AKTIF*\n" + "━"*22 + "\n\n"
        f"🪙 Symbol: `{', '.join(SYMBOLS)}`\n🕐 Timezone: UTC+{UTC_OFFSET} (WIB)\n\n"
        f"*Risk Management:*\n"
        f"  Min Risk: ${MIN_RISK}  |  Max Risk: ${MAX_RISK}\n"
        f"  Risk Per Trade: {RISK_PERCENT * 100}%\n\n"
        f"*Confluence Requirements:*\n"
        f"  Sweep: {'✅ Required' if REQUIRE_SWEEP else '❌ Optional'}\n"
        f"  IFVG: {'✅ Required' if REQUIRE_IFVG else '❌ Optional'}\n"
        f"  Min Target RR: 1:{MIN_RR}\n\n"
        f"💡 _Semua pengaturan bisa diubah di config.py_"
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


async def _cmd_lastsignal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(_txt_signal(), parse_mode="Markdown", reply_markup=_kb_back())

async def _cmd_performance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(_txt_stats(), parse_mode="Markdown", reply_markup=_kb_back())

async def _cmd_why(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    s = snapshot_state()
    wib = _wib_now().strftime("%H:%M:%S WIB")
    out = [f"🤔 *WHY REJECTED?*\n🕒 {wib}\n\nAlasan penolakan sinyal terakhir:"]
    for sym in SYMBOLS:
        sym_s = s.get("symbols", {}).get(sym, {})
        reason = sym_s.get("last_rejection_reason", "Belum ada penolakan.")
        out.append(f"🔸 *{sym}*: `{reason}`")
    
    await update.message.reply_text("\n".join(out), parse_mode="Markdown", reply_markup=_kb_back())

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


def kirim_photo(photo_path: str, caption: str = "", timeout: int = 20) -> bool:
    """Kirim foto ke Telegram via sendPhoto API."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    # Jalur Utama: PTB Application bot
    if _bot_app and _bot_loop and _bot_loop.is_running():
        try:
            with open(photo_path, "rb") as f:
                coro = _bot_app.bot.send_photo(
                    chat_id=TELEGRAM_CHAT_ID,
                    photo=f,
                    caption=caption,
                    parse_mode="Markdown",
                    read_timeout=timeout,
                    write_timeout=timeout,
                )
                future = asyncio.run_coroutine_threadsafe(coro, _bot_loop)
                future.result(timeout=timeout + 5)
            logger.info("Telegram: Photo terkirim (via PTB async).")
            return True
        except Exception as e:
            logger.warning(f"Telegram PTB Photo Error: {e}. Mencoba fallback...")

    # Jalur Fallback: requests.post
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo:
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
            files = {"photo": photo}
            resp = requests.post(url, data=data, files=files, timeout=timeout)
            resp.raise_for_status()
        logger.info("Telegram: Photo terkirim (via requests fallback).")
        return True
    except Exception as e:
        logger.error(f"Gagal kirim photo: {e}")
        return False


# Alias untuk kompatibilitas
kirim_foto_telegram = kirim_photo


def kirim_health_ping():
    """Kirim health ping status ke Telegram."""
    start_t = get_state("start_time")
    from datetime import datetime as _dt
    uptime = str(_dt.now() - start_t).split('.')[0] if start_t else "Unknown"
    mt5_conn = "✅ Connected" if get_state("mt5_connected") else "❌ Disconnected"

    kirim_telegram(
        f"🩺 *Bot Health Ping*\n\n"
        f"⏳ Uptime: {uptime}\n"
        f"🖥️ MT5: {mt5_conn}\n\n"
        f"_Bot is running normally._"
    )


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
        app.add_handler(CommandHandler("lastsignal", _cmd_lastsignal))
        app.add_handler(CommandHandler("performance", _cmd_performance))
        app.add_handler(CommandHandler("why", _cmd_why))
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
