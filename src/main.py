"""
main.py — XAUUSD ICT Signal Bot Engine
=====================================
Entry point utama. Menjalankan loop scanning dan mengirim sinyal ke Telegram.

Setup ICT yang dipakai:
  1. HTF Bias (H4 dual MA) → Filter arah
  2. Liquidity Sweep (M15) → Entry trigger
  3. Inversed FVG (M15) → Konfirmasi entry
  4. Killzone filter → Hanya trade saat London/NY
  5. Confluence scoring → Minimum 3/4 untuk kirim sinyal (tier SWING)
"""

import sys
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5

from src.config import (
    SYMBOLS,
    SYMBOL_ALIASES,
    UTC_OFFSET,
    KILLZONES,
    SESSION_RULES,
    MIN_CONFLUENCE_SCORE,
    MIN_RR,
    MAX_SPREAD,
    NEWS_BLACKOUT_MINUTES,
    NEWS_SCHEDULE_FILE,
    DATA_M15_COUNT,
    DATA_H4_COUNT,
    SCAN_INTERVAL,
    ERROR_SLEEP,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    CHART_ENABLED,
)
from src.telegram import (
    kirim_telegram,
    kirim_photo,
    kirim_startup_notification,
    start_telegram_bot,
    get_state,
    set_state,
    update_symbol_state,
    set_symbol_state,
    scan_event,
)
from src.analysis import (
    generate_chart,
    get_data,
    detect_robust_bias,
    detect_premium_discount,
    detect_fvg_retest,
    calculate_confluence,
    check_invalidation,
    get_atr,
    detect_h4_structure,
)
from src.risk import validate_risk, calculate_sl_tp, log_trade


# ============================================================
#  LOGGING SETUP
# ============================================================


def setup_logging():
    """Configure logging ke file + console."""
    logger = logging.getLogger("xauusd_bot")
    logger.setLevel(logging.DEBUG)

    # File handler — rotating, max 5MB x 5 backup
    file_handler = RotatingFileHandler(
        "bot_xauusd.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    # Console handler — INFO ke atas saja
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(console_fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


# ============================================================
#  STARTUP VALIDATION
# ============================================================


def initialize_mt5_robust(logger: logging.Logger) -> bool:
    """Mencoba initialize MT5 dengan default, lalu path alternatif jika gagal."""
    if mt5.initialize():
        logger.info("✅ MT5 initialized successfully dengan path default.")
        return True

    error = mt5.last_error()
    logger.warning(
        f"⚠️ Default MT5 initialization FAILED! "
        f"Error code: {error[0]}, message: {error[1]}. "
        f"Mencoba path alternatif..."
    )

    import os

    common_paths = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        r"C:\Program Files\RoboForex - MetaTrader 5\terminal64.exe",
        r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
        r"C:\Program Files\FBS MetaTrader 5\terminal64.exe",
    ]

    appdata_base = os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal")
    if os.path.exists(appdata_base):
        for folder in os.listdir(appdata_base):
            exe_path = os.path.join(appdata_base, folder, "terminal64.exe")
            if os.path.exists(exe_path):
                common_paths.append(exe_path)

    for path in common_paths:
        if os.path.exists(path) and path.endswith(".exe"):
            logger.info(f"Mencoba initialize dari: {path}")
            if mt5.initialize(path):
                logger.info(f"✅ MT5 initialized successfully menggunakan path: {path}")
                return True

    logger.critical("❌ Semua percobaan MT5 initialization FAILED!")
    return False


def validate_startup(logger: logging.Logger) -> bool:
    """
    Validasi semua prasyarat sebelum engine loop dimulai.
    Cek: Telegram credentials, MT5 connection, dan symbol availability.
    Returns True jika semua OK, False jika ada yang gagal.
    """
    all_ok = True

    # --- 1. Cek Telegram credentials ---
    if not TELEGRAM_TOKEN:
        logger.critical(
            "❌ TELEGRAM_TOKEN tidak ditemukan! Pastikan sudah diset di file .env"
        )
        all_ok = False
    else:
        logger.info("✅ TELEGRAM_TOKEN ditemukan.")

    if not TELEGRAM_CHAT_ID:
        logger.critical(
            "❌ TELEGRAM_CHAT_ID tidak ditemukan! Pastikan sudah diset di file .env"
        )
        all_ok = False
    else:
        logger.info("✅ TELEGRAM_CHAT_ID ditemukan.")

    if not all_ok:
        logger.critical("Startup GAGAL: Telegram credentials tidak lengkap.")
        return False

    # --- 2. Cek MT5 initialize (dengan fallback path) ---
    if not initialize_mt5_robust(logger):
        return False

    # --- 3. Cek symbols tersedia di Market Watch ---
    resolved_symbols = []
    for sym in SYMBOLS:
        symbol_info = mt5.symbol_info(sym)
        resolved_sym = sym

        if symbol_info is None:
            aliases = SYMBOL_ALIASES.get(sym, [])
            found_alias = False
            for alias in aliases:
                s_info = mt5.symbol_info(alias)
                if s_info is not None:
                    logger.info(
                        f"🔄 Resolving symbol '{sym}' ke alias broker '{alias}'..."
                    )
                    resolved_sym = alias
                    symbol_info = s_info
                    found_alias = True
                    break

            if not found_alias:
                logger.critical(
                    f"❌ Symbol '{sym}' (maupun aliasnya) tidak ditemukan di MT5! "
                    f"Pastikan sudah ditambahkan ke Market Watch."
                )
                mt5.shutdown()
                return False

        if not symbol_info.visible:
            logger.info(
                f"🔄 '{resolved_sym}' belum aktif di Market Watch. Mengaktifkan..."
            )
            if not mt5.symbol_select(resolved_sym, True):
                logger.critical(
                    f"❌ Gagal mengaktifkan '{resolved_sym}' di Market Watch! "
                )
                mt5.shutdown()
                return False
            logger.info(f"✅ Symbol '{resolved_sym}' berhasil diaktifkan.")
        else:
            logger.info(f"✅ Symbol '{resolved_sym}' tersedia di Market Watch.")

        resolved_symbols.append(resolved_sym)

    # Override SYMBOLS dengan nama symbol spesifik broker
    SYMBOLS.clear()
    SYMBOLS.extend(resolved_symbols)

    return True


# ============================================================
#  MARKET & KILLZONE CHECKS
# ============================================================


def get_wib_now() -> datetime:
    """Get current time in WIB (UTC+7), tidak tergantung timezone sistem."""
    return datetime.now(timezone.utc) + timedelta(hours=UTC_OFFSET)


def is_market_open(symbol: str) -> bool:
    """Cek apakah market buka untuk symbol tertentu."""
    wib_now = get_wib_now()

    if wib_now.weekday() in (5, 6):
        return False

    if not mt5.terminal_info():
        return True

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False

    if symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        return False

    tick = mt5.symbol_info_tick(symbol)
    if tick:
        tick_time = datetime.fromtimestamp(tick.time, tz=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        if (now_utc - tick_time).total_seconds() > 1800:  # 30 menit
            return False

    return True


def is_killzone() -> bool:
    """Cek apakah waktu saat ini berada di dalam salah satu Killzone."""
    jam = get_wib_now().hour
    for start, end in KILLZONES:
        if start <= jam < end:
            return True
    return False


def get_current_session() -> str:
    """Mengembalikan string sesi aktif berdasarkan waktu."""
    jam = get_wib_now().hour
    if 8 <= jam < 10:
        return "ASIA"
    elif 14 <= jam < 17:
        return "LONDON"
    elif 19 <= jam < 23:
        return "NY"
    return "UNKNOWN"


def is_news_blackout() -> tuple[bool, str]:
    """Cek apakah waktu saat ini berada di dalam news blackout window"""
    wib_now = get_wib_now()
    try:
        with open(NEWS_SCHEDULE_FILE, "r") as f:
            news_times = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False, ""

    for nt in news_times:
        try:
            hour, minute = map(int, nt.split(":"))
            news_time = wib_now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            diff = abs((wib_now - news_time).total_seconds()) / 60.0
            if diff <= NEWS_BLACKOUT_MINUTES:
                return True, nt
        except Exception:
            continue

    return False, ""


# ============================================================
#  SIGNAL BUILDER
# ============================================================


def build_signal_message(
    side: str,
    harga: float,
    sl: float,
    tp1: float,
    tp2: float,
    risk: float,
    bias: str,
    confluence: int,
) -> str:
    """Format pesan sinyal untuk Telegram."""
    rr1 = 2
    rr2 = 4
    wib_time = get_wib_now().strftime("%H:%M WIB")

    return (
        f"🎯 *XAUUSD {side}*\n"
        f"⏰ {wib_time}\n\n"
        f"📍 Entry: `{harga}`\n"
        f"🛑 SL: `{sl}` (buffer applied)\n"
        f"✅ TP1: `{tp1}` ({rr1}R)\n"
        f"🏆 TP2: `{tp2}` ({rr2}R)\n\n"
        f"📊 Risk: ${risk}\n"
        f"📈 Bias: {bias}\n"
        f"🔗 Confluence: {confluence}/4\n\n"
        f"_ICT Engine v2.0 — Sweep + IFVG + KZ + Bias_"
    )


# ============================================================
#  SMART SLEEP (interruptible via scan_event)
# ============================================================


def smart_sleep(seconds: float):
    """Sleep yang bisa di-interrupt oleh scan_event (misal saat /resume)."""
    scan_event.wait(timeout=seconds)
    scan_event.clear()


# ============================================================
#  MAIN ENGINE LOOP
# ============================================================


def run_engine():
    logger = setup_logging()
    logger.info(f"🚀 BOT XAUUSD v2.0 STARTING... (WIB: UTC+{UTC_OFFSET})")

    # === STARTUP VALIDATION ===
    if not validate_startup(logger):
        logger.critical("🛑 Startup validation GAGAL. Bot tidak bisa jalan.")
        sys.exit(1)

    # === START INTERACTIVE TELEGRAM BOT ===
    set_state("mt5_connected", True)
    set_state("start_time", datetime.now())
    set_state("running", True)
    start_telegram_bot()

    kirim_startup_notification()

    # Anti-spam tracker
    signal_trackers = {}
    for sym in SYMBOLS:
        signal_trackers[sym] = {
            "BUY": {"last_time": None, "last_candle_time": None, "last_extreme": 0.0},
            "SELL": {"last_time": None, "last_candle_time": None, "last_extreme": 0.0},
        }

    try:
        while True:
            try:
                # === PAUSE CHECK ===
                if get_state("paused"):
                    logger.debug("⏸️ Bot paused, waiting for resume...")
                    smart_sleep(5)
                    continue

                # === HEALTH PING CHECK ===
                last_ping = get_state("last_health_ping")
                if not last_ping:
                    last_ping = datetime.now()
                    set_state("last_health_ping", last_ping)
                else:
                    from src.config import HEALTH_PING_INTERVAL_HOURS

                    if (
                        datetime.now() - last_ping
                    ).total_seconds() >= HEALTH_PING_INTERVAL_HOURS * 3600:
                        start_t = get_state("start_time")
                        uptime = (
                            str(datetime.now() - start_t).split(".")[0]
                            if start_t
                            else "Unknown"
                        )
                        mt5_conn = (
                            "✅ Connected"
                            if get_state("mt5_connected")
                            else "❌ Disconnected"
                        )

                        kirim_telegram(
                            f"🩺 *Bot Health Ping*\n\n"
                            f"⏳ Uptime: {uptime}\n"
                            f"🖥️ MT5: {mt5_conn}\n\n"
                            f"_Bot is running normally._"
                        )
                        set_state("last_health_ping", datetime.now())

                # Set global state for market/killzone just as default
                set_state("market_open", True)
                set_state("killzone_active", is_killzone())

                # === CHECK MT5 CONNECTION ===
                if not mt5.terminal_info():
                    set_state("mt5_connected", False)

                    disc_time = get_state("mt5_disconnect_time")
                    if not disc_time:
                        set_state("mt5_disconnect_time", datetime.now())
                    else:
                        if not get_state("mt5_disconnect_alert_sent"):
                            if (datetime.now() - disc_time).total_seconds() > 300:
                                kirim_telegram(
                                    "⚠️ *CRITICAL: MT5 Disconnected!*\n\n"
                                    "Bot telah terputus dari MetaTrader 5 selama lebih dari 5 menit.\n"
                                    "Harap periksa terminal MT5 atau VPS Anda."
                                )
                                set_state("mt5_disconnect_alert_sent", True)

                    reconnect_attempts = get_state("mt5_reconnect_attempts") or 0
                    reconnect_attempts += 1
                    set_state("mt5_reconnect_attempts", reconnect_attempts)

                    logger.warning(
                        f"MT5 connection lost. Reconnecting... (Attempt {reconnect_attempts})"
                    )
                    if not initialize_mt5_robust(logger):
                        # Exponential backoff: min 5s, max 300s
                        backoff = min(5 * (2 ** (reconnect_attempts - 1)), 300)
                        logger.error(
                            f"MT5 reconnection failed! Backing off for {backoff}s..."
                        )
                        smart_sleep(backoff)
                        continue

                    if get_state("mt5_disconnect_alert_sent"):
                        kirim_telegram(
                            "✅ *RESOLVED: MT5 Reconnected!*\n\nKoneksi MetaTrader 5 telah pulih."
                        )
                    set_state("mt5_disconnect_time", None)
                    set_state("mt5_disconnect_alert_sent", False)
                    set_state("mt5_reconnect_attempts", 0)
                    logger.info("MT5 reconnected.")
                    set_state("mt5_connected", True)
                else:
                    if not get_state("mt5_connected"):
                        set_state("mt5_connected", True)
                    if get_state("mt5_disconnect_time") is not None:
                        set_state("mt5_disconnect_time", None)
                        set_state("mt5_disconnect_alert_sent", False)
                        set_state("mt5_reconnect_attempts", 0)

                # === MULTI SYMBOL EXECUTION ===
                for sym in SYMBOLS:
                    if not is_market_open(sym):
                        continue
                    if not is_killzone():
                        continue

                    # === FETCH DATA ===
                    df_m15 = get_data(sym, mt5.TIMEFRAME_M15, DATA_M15_COUNT)
                    df_h4 = get_data(sym, mt5.TIMEFRAME_H4, DATA_H4_COUNT)

                    if df_m15.empty or df_h4.empty:
                        logger.warning(f"Data {sym} kosong, retrying...")
                        continue

                    # === ANALYSIS ===
                    bias = detect_robust_bias(df_h4)
                    pd_zone = detect_premium_discount(df_h4)
                    h4_struct = detect_h4_structure(df_h4)
                    atr = get_atr(df_m15)

                    # FVG Retest Detection
                    fvg_status, extreme_price, fvg_idx = detect_fvg_retest(
                        df_m15, bias=bias
                    )

                    harga_now = df_m15["close"].iloc[-1]
                    current_candle_time = df_m15["time"].iloc[-1]
                    session = get_current_session()

                    # === DETERMINE TRADE SIDE ===
                    side = None
                    if "BUY" in fvg_status:
                        side = "BUY"
                    elif "SELL" in fvg_status:
                        side = "SELL"

                    # Filter based on SESSION_RULES
                    if side:
                        allowed_tiers = SESSION_RULES.get(session, [])
                        # Our silver bullet is basically the "SWING" tier equivalent
                        if "SWING" not in allowed_tiers:
                            logger.info(
                                f"Signal {side} rejected: SWING not allowed in {session} session."
                            )
                            set_symbol_state(
                                sym,
                                "last_rejection_reason",
                                f"Not allowed in {session}",
                            )
                            side = None

                    # === CONFLUENCE CHECK ===
                    kz_active = is_killzone()
                    confluence = 0
                    if side:
                        confluence = calculate_confluence(
                            side, bias, fvg_status, kz_active
                        )

                    # === UPDATE BOT STATE (for Telegram queries) ===
                    update_symbol_state(
                        sym,
                        {
                            "bias": bias,
                            "pd_zone": pd_zone,
                            "h4_struct": h4_struct,
                            "sweep": fvg_status,  # reuse sweep property for display
                            "ifvg": session,  # reuse ifvg property for display
                            "confluence": confluence,
                            "price": harga_now,
                            "killzone_active": kz_active,
                            "last_scan_time": get_wib_now().strftime("%H:%M:%S WIB"),
                            "mt5_connected": True,
                            "market_open": True,
                        },
                    )

                    # === ENTRY LOGIC (AGGRESSIVE & ALIGNED) ===
                    if (
                        side
                        and confluence >= MIN_CONFLUENCE_SCORE
                        and signal_trackers[sym][side.split()[0]]["last_candle_time"]
                        != current_candle_time
                    ):
                        if side:
                            # NEWS BLACKOUT VALIDATION
                            in_blackout, nt = is_news_blackout()
                            if in_blackout:
                                logger.info(
                                    f"Signal ditolak (News Blackout): Mendekati news rilis {nt} WIB"
                                )
                                set_symbol_state(
                                    sym, "last_rejection_reason", "News Blackout"
                                )
                                continue

                            # SPREAD VALIDATION
                            tick = mt5.symbol_info_tick(sym)
                            if tick:
                                spread = tick.ask - tick.bid
                                if spread > MAX_SPREAD:
                                    logger.info(
                                        f"Signal ditolak (Spread terlalu besar): {spread:.2f} > {MAX_SPREAD}"
                                    )
                                    set_symbol_state(
                                        sym,
                                        "last_rejection_reason",
                                        "Spread terlalu besar",
                                    )
                                    continue

                            # VALIDASI PREMIUM / DISCOUNT
                            if side == "BUY" and pd_zone != "DISCOUNT":
                                logger.info(
                                    f"Signal BUY ditolak karena berada di {pd_zone} zone (harus DISCOUNT)."
                                )
                                set_symbol_state(
                                    sym,
                                    "last_rejection_reason",
                                    "Bukan Discount Zone (BUY)",
                                )
                                continue
                            elif side == "SELL" and pd_zone != "PREMIUM":
                                logger.info(
                                    f"Signal SELL ditolak karena berada di {pd_zone} zone (harus PREMIUM)."
                                )
                                set_symbol_state(
                                    sym,
                                    "last_rejection_reason",
                                    "Bukan Premium Zone (SELL)",
                                )
                                continue

                            # INVALIDATION CHECK
                            is_invalid, inv_reason = check_invalidation(
                                df_m15, side, extreme_price
                            )
                            if is_invalid:
                                logger.info(
                                    f"Signal ditolak (Invalidation): {inv_reason}"
                                )
                                set_symbol_state(
                                    sym,
                                    "last_rejection_reason",
                                    "Invalidation (misal Wick/Close salah)",
                                )
                                continue

                            # RISK VALIDATION
                            raw_risk = abs(harga_now - extreme_price)
                            is_valid, reason = validate_risk(raw_risk, atr=atr)
                            if not is_valid:
                                logger.info(f"Risk rejected: {reason}")
                                set_symbol_state(
                                    sym,
                                    "last_rejection_reason",
                                    "Risk to Reward atau SL terlalu besar/kecil",
                                )
                                continue

                            # CALCULATE SL/TP
                            levels = calculate_sl_tp(
                                side,
                                harga_now,
                                extreme_price,
                                df=df_m15,
                                atr=atr,
                                session=session,
                            )

                            # RR VALIDATION (TP1)
                            if levels["risk"] > 0:
                                actual_rr = (
                                    abs(levels["tp1"] - harga_now) / levels["risk"]
                                )
                                if actual_rr < MIN_RR:
                                    logger.info(
                                        f"Signal ditolak (RR insufficient): "
                                        f"Risk=${levels['risk']:.2f}, Target=${abs(levels['tp1'] - harga_now):.2f}, "
                                        f"RR={actual_rr:.2f} < {MIN_RR}"
                                    )
                                    set_symbol_state(
                                        sym,
                                        "last_rejection_reason",
                                        "RR tidak mencapai Minimum (1:1.5)",
                                    )
                                    continue

                            # Confidence label berdasarkan confluence
                            if confluence >= 3:
                                confidence = "🔥 PERFECT"
                            elif confluence >= 2:
                                confidence = "⚡ SWING"
                            else:
                                confidence = "📊 AGGRESSIVE"

                            # H4 STRUCTURE VALIDATION (Khusus SWING/PERFECT)
                            if "SWING" in confidence or "PERFECT" in confidence:
                                if side == "BUY" and h4_struct == "BEARISH":
                                    logger.info(
                                        "Signal BUY ditolak (Structure): Setup SWING tapi H4 Structure BEARISH"
                                    )
                                    set_symbol_state(
                                        sym,
                                        "last_rejection_reason",
                                        "H4 Structure Bearish (Setup Swing BUY)",
                                    )
                                    continue
                                elif side == "SELL" and h4_struct == "BULLISH":
                                    logger.info(
                                        "Signal SELL ditolak (Structure): Setup SWING tapi H4 Structure BULLISH"
                                    )
                                    set_symbol_state(
                                        sym,
                                        "last_rejection_reason",
                                        "H4 Structure Bullish (Setup Swing SELL)",
                                    )
                                    continue

                            # BUILD & SEND SIGNAL
                            pesan = build_signal_message(
                                side=side,
                                harga=harga_now,
                                sl=levels["sl"],
                                tp1=levels["tp1"],
                                tp2=levels["tp2"],
                                risk=levels["risk"],
                                bias=bias,
                                confluence=confluence,
                            )

                            # KIRIM — hanya lock anti-spam jika BERHASIL terkirim
                            if kirim_telegram(pesan):
                                signal_trackers[sym][side.split()[0]][
                                    "last_candle_time"
                                ] = current_candle_time
                                set_symbol_state(
                                    sym,
                                    "last_signal_time",
                                    get_wib_now().strftime("%H:%M:%S WIB"),
                                )
                                logger.info(
                                    f"✅ SIGNAL {side} SENT @ {harga_now} "
                                    f"[{confidence}] Confluence={confluence}/3"
                                )

                                # KIRIM CHART JIKA ENABLED
                                if CHART_ENABLED:
                                    chart_path = "generate_chart.png"
                                    try:
                                        generate_chart(
                                            df=df_m15,
                                            symbol=sym,
                                            entry_price=harga_now,
                                            sl_price=levels["sl"],
                                            tp1_price=levels["tp1"],
                                            tp2_price=levels["tp2"],
                                            save_path=chart_path,
                                        )
                                        kirim_photo(
                                            chart_path,
                                            caption=f"📊 Chart {sym} M15 ({confidence})",
                                        )
                                    except Exception as ce:
                                        logger.error(f"Gagal kirim chart: {ce}")

                                # LOG TRADE
                                log_trade(
                                    side=side,
                                    entry=harga_now,
                                    sl=levels["sl"],
                                    tp1=levels["tp1"],
                                    tp2=levels["tp2"],
                                    risk=levels["risk"],
                                    confluence_score=confluence,
                                    bias=bias,
                                )
                            else:
                                logger.warning(
                                    "⚠️ Signal gagal terkirim, akan dicoba lagi."
                                )

                    # STATUS LOG (visible di console supaya user tau bot jalan)
                    wib_str = get_wib_now().strftime("%H:%M:%S")
                    logger.info(
                        f"🔍 [{wib_str}] {sym} | Bias: {bias} | "
                        f"FVG: {fvg_status} | Session: {session} | "
                        f"Confluence: {confluence}/3"
                    )

                smart_sleep(SCAN_INTERVAL)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Loop error: {e}", exc_info=True)
                smart_sleep(ERROR_SLEEP)

    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh user (Ctrl+C).")
        kirim_telegram("🛑 *SISTEM OFFLINE*\n\nBot XAUUSD telah dimatikan secara manual (Ctrl+C).")
    finally:
        set_state("running", False)
        mt5.shutdown()
        logger.info("MT5 connection closed. Bot stopped.")


# ============================================================
#  ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_engine()
