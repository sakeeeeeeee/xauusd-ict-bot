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
    SYMBOL,
    UTC_OFFSET,
    KILLZONES,
    LONDON_NY_KILLZONES,
    MIN_CONFLUENCE_SCORE,
    MIN_RR,
    MAX_SPREAD,
    NEWS_BLACKOUT_MINUTES,
    NEWS_SCHEDULE_FILE,
    DATA_M15_COUNT,
    DATA_H4_COUNT,
    SCAN_INTERVAL,
    SLEEP_OUTSIDE_KZ,
    ERROR_SLEEP,
    WEEKEND_SLEEP,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
)
from src.telegram import (
    kirim_telegram,
    kirim_startup_notification,
    start_telegram_bot,
    get_state,
    set_state,
    update_state,
    scan_event,
)
from src.analysis import (
    get_data,
    detect_robust_bias,
    detect_premium_discount,
    detect_sweep,
    detect_ifvg,
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

    # --- 2. Cek MT5 initialize ---
    if not mt5.initialize():
        error = mt5.last_error()
        logger.critical(
            f"❌ MT5 initialization FAILED! "
            f"Error code: {error[0]}, message: {error[1]}. "
            f"Pastikan terminal MetaTrader 5 sudah terbuka dan login."
        )
        return False
    logger.info("✅ MT5 initialized successfully.")

    # --- 3. Cek symbol XAUUSD tersedia di Market Watch ---
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        logger.critical(
            f"❌ Symbol '{SYMBOL}' tidak ditemukan di MT5! "
            f"Pastikan '{SYMBOL}' sudah ditambahkan ke Market Watch."
        )
        mt5.shutdown()
        return False

    if not symbol_info.visible:
        # Coba aktifkan otomatis
        if not mt5.symbol_select(SYMBOL, True):
            logger.critical(
                f"❌ Gagal mengaktifkan '{SYMBOL}' di Market Watch! "
                f"Tambahkan manual: klik kanan Market Watch → Show All / Symbols."
            )
            mt5.shutdown()
            return False
        logger.info(f"✅ Symbol '{SYMBOL}' berhasil diaktifkan di Market Watch.")
    else:
        logger.info(f"✅ Symbol '{SYMBOL}' tersedia di Market Watch.")

    return True


# ============================================================
#  MARKET & KILLZONE CHECKS
# ============================================================


def get_wib_now() -> datetime:
    """Get current time in WIB (UTC+7), tidak tergantung timezone sistem."""
    return datetime.now(timezone.utc) + timedelta(hours=UTC_OFFSET)


def is_market_open() -> bool:
    """Cek apakah market forex buka (bukan weekend)."""
    wib_now = get_wib_now()
    # Sabtu(5) dan Minggu(6) market tutup
    if wib_now.weekday() in (5, 6):
        return False
    return True


def is_killzone() -> bool:
    """Cek apakah sekarang masuk killzone session (Asia/London/NY)."""
    jam = get_wib_now().hour
    for start, end in KILLZONES:
        if start <= jam < end:
            return True
    return False


def is_london_ny_killzone() -> bool:
    """Cek apakah sekarang masuk killzone London/NY (bukan Asia)."""
    jam = get_wib_now().hour
    for start, end in LONDON_NY_KILLZONES:
        if start <= jam < end:
            return True
    return False


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
    last_sent_signal_time = None

    try:
        while True:
            try:
                # === PAUSE CHECK ===
                if get_state("paused"):
                    logger.debug("⏸️ Bot paused, waiting for resume...")
                    smart_sleep(5)
                    continue

                # === WEEKEND CHECK ===
                if not is_market_open():
                    set_state("market_open", False)
                    logger.info("📅 Weekend — market tutup. Sleeping 1 jam...")
                    smart_sleep(WEEKEND_SLEEP)
                    continue

                set_state("market_open", True)

                # === KILLZONE CHECK ===
                if not is_killzone():
                    set_state("killzone_active", False)
                    wib_str = get_wib_now().strftime("%H:%M")
                    logger.info(
                        f"⏸️  [{wib_str}] Outside Killzone. "
                        f"Next KZ: London 14:00 / NY 19:00 WIB. "
                        f"Sleeping {SLEEP_OUTSIDE_KZ}s..."
                    )
                    smart_sleep(SLEEP_OUTSIDE_KZ)
                    continue

                # === CHECK MT5 CONNECTION ===
                if not mt5.terminal_info():
                    set_state("mt5_connected", False)
                    logger.warning("MT5 connection lost. Reconnecting...")
                    if not mt5.initialize():
                        logger.error("MT5 reconnection failed!")
                        smart_sleep(ERROR_SLEEP)
                        continue
                    logger.info("MT5 reconnected.")
                    set_state("mt5_connected", True)

                # === FETCH DATA ===
                df_m15 = get_data(SYMBOL, mt5.TIMEFRAME_M15, DATA_M15_COUNT)
                df_h4 = get_data(SYMBOL, mt5.TIMEFRAME_H4, DATA_H4_COUNT)

                if df_m15.empty or df_h4.empty:
                    logger.warning("Data kosong, retrying...")
                    smart_sleep(ERROR_SLEEP)
                    continue

                # === ANALYSIS ===
                bias = detect_robust_bias(df_h4)
                pd_zone = detect_premium_discount(df_h4)
                h4_struct = detect_h4_structure(df_h4)
                atr = get_atr(df_m15)
                sweep_status, extreme_price, sweep_idx = detect_sweep(
                    df_m15,
                    bias=bias,
                    is_london_ny_kz=is_london_ny_killzone(),
                )
                is_ifvg, ifvg_msg = detect_ifvg(df_m15, sweep_status, sweep_idx)

                harga_now = df_m15["close"].iloc[-1]
                current_candle_time = df_m15["time"].iloc[-1]

                # === DETERMINE TRADE SIDE & DIRECTION ALIGNMENT ===
                side = None
                if sweep_status == "SWEEP BUY 💧" and ifvg_msg == "IFVG BUY 🧲":
                    side = "BUY 🟢"
                elif sweep_status == "SWEEP SELL 💧" and ifvg_msg == "IFVG SELL 🧲":
                    side = "SELL 🔴"
                else:
                    if "SWEEP" in sweep_status:
                        logger.debug(
                            f"Setup rejected due to mismatched or missing IFVG: "
                            f"Sweep={sweep_status}, IFVG={ifvg_msg}"
                        )

                # === CONFLUENCE CHECK ===
                kz_active = is_killzone()
                confluence = 0
                if side:
                    confluence = calculate_confluence(
                        side, bias, sweep_status, ifvg_msg, kz_active
                    )

                # === UPDATE BOT STATE (for Telegram queries) ===
                update_state(
                    {
                        "bias": bias,
                        "pd_zone": pd_zone,
                        "h4_struct": h4_struct,
                        "sweep": sweep_status,
                        "ifvg": ifvg_msg,
                        "confluence": confluence,
                        "price": harga_now,
                        "killzone_active": kz_active,
                        "last_scan_time": get_wib_now().strftime("%H:%M:%S WIB"),
                        "mt5_connected": True,
                        "market_open": True,
                    }
                )

                # === ENTRY LOGIC (AGGRESSIVE & ALIGNED) ===
                if (
                    side
                    and confluence >= MIN_CONFLUENCE_SCORE
                    and last_sent_signal_time != current_candle_time
                ):
                    if side:
                        # NEWS BLACKOUT VALIDATION
                        in_blackout, nt = is_news_blackout()
                        if in_blackout:
                            logger.info(
                                f"Signal ditolak (News Blackout): Mendekati news rilis {nt} WIB"
                            )
                            smart_sleep(SCAN_INTERVAL)
                            continue

                        # SPREAD VALIDATION
                        tick = mt5.symbol_info_tick(SYMBOL)
                        if tick:
                            spread = tick.ask - tick.bid
                            if spread > MAX_SPREAD:
                                logger.info(
                                    f"Signal ditolak (Spread terlalu besar): {spread:.2f} > {MAX_SPREAD}"
                                )
                                smart_sleep(SCAN_INTERVAL)
                                continue

                        # VALIDASI PREMIUM / DISCOUNT
                        if side == "BUY 🟢" and pd_zone != "DISCOUNT":
                            logger.info(
                                f"Signal BUY ditolak karena berada di {pd_zone} zone (harus DISCOUNT)."
                            )
                            smart_sleep(SCAN_INTERVAL)
                            continue
                        elif side == "SELL 🔴" and pd_zone != "PREMIUM":
                            logger.info(
                                f"Signal SELL ditolak karena berada di {pd_zone} zone (harus PREMIUM)."
                            )
                            smart_sleep(SCAN_INTERVAL)
                            continue

                        # INVALIDATION CHECK
                        is_invalid, inv_reason = check_invalidation(
                            df_m15, side, extreme_price
                        )
                        if is_invalid:
                            logger.info(f"Signal ditolak (Invalidation): {inv_reason}")
                            smart_sleep(SCAN_INTERVAL)
                            continue

                        # RISK VALIDATION
                        raw_risk = abs(harga_now - extreme_price)
                        is_valid, reason = validate_risk(raw_risk, atr=atr)
                        if not is_valid:
                            logger.info(f"Risk rejected: {reason}")
                            smart_sleep(SCAN_INTERVAL)
                            continue

                        # CALCULATE SL/TP
                        levels = calculate_sl_tp(
                            side, harga_now, extreme_price, df=df_m15, atr=atr
                        )

                        # RR VALIDATION (TP1)
                        if levels["risk"] > 0:
                            actual_rr = abs(levels["tp1"] - harga_now) / levels["risk"]
                            if actual_rr < MIN_RR:
                                logger.info(
                                    f"Signal ditolak (RR insufficient): "
                                    f"Risk=${levels['risk']:.2f}, Target=${abs(levels['tp1'] - harga_now):.2f}, "
                                    f"RR={actual_rr:.2f} < {MIN_RR}"
                                )
                                smart_sleep(SCAN_INTERVAL)
                                continue

                        # Confidence label berdasarkan confluence
                        if confluence >= 4:
                            confidence = "🔥 PERFECT"
                        elif confluence >= 3:
                            confidence = "⚡ SWING"
                        else:
                            confidence = "📊 AGGRESSIVE"

                        # H4 STRUCTURE VALIDATION (Khusus SWING/PERFECT)
                        if "SWING" in confidence or "PERFECT" in confidence:
                            if side == "BUY 🟢" and h4_struct == "BEARISH":
                                logger.info(
                                    "Signal BUY ditolak (Structure): Setup SWING tapi H4 Structure BEARISH"
                                )
                                smart_sleep(SCAN_INTERVAL)
                                continue
                            elif side == "SELL 🔴" and h4_struct == "BULLISH":
                                logger.info(
                                    "Signal SELL ditolak (Structure): Setup SWING tapi H4 Structure BULLISH"
                                )
                                smart_sleep(SCAN_INTERVAL)
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
                            last_sent_signal_time = current_candle_time
                            set_state(
                                "last_signal_time",
                                get_wib_now().strftime("%H:%M:%S WIB"),
                            )
                            logger.info(
                                f"✅ SIGNAL {side} SENT @ {harga_now} "
                                f"[{confidence}] Confluence={confluence}/4"
                            )

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
                            logger.warning("⚠️ Signal gagal terkirim, akan dicoba lagi.")

                # STATUS LOG (visible di console supaya user tau bot jalan)
                wib_str = get_wib_now().strftime("%H:%M:%S")
                logger.info(
                    f"🔍 [{wib_str}] {SYMBOL} | Bias: {bias} | "
                    f"Sweep: {sweep_status} | IFVG: {ifvg_msg} | "
                    f"Confluence: {confluence}/4"
                )

                smart_sleep(SCAN_INTERVAL)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Loop error: {e}", exc_info=True)
                smart_sleep(ERROR_SLEEP)

    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh user (Ctrl+C).")
    finally:
        set_state("running", False)
        mt5.shutdown()
        logger.info("MT5 connection closed. Bot stopped.")


# ============================================================
#  ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_engine()
