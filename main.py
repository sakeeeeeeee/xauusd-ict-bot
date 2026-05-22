"""
main.py — XAUUSD ICT Signal Bot Engine
=====================================
Entry point utama. Menjalankan loop scanning dan mengirim sinyal ke Telegram.

Setup ICT yang dipakai:
  1. HTF Bias (H4 dual MA) → Filter arah
  2. Liquidity Sweep (M15) → Entry trigger
  3. Inversed FVG (M15) → Konfirmasi entry
  4. Killzone filter → Hanya trade saat London/NY
  5. Confluence scoring → Minimum 3/4 untuk kirim sinyal
"""
import time
import logging
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5

from config import (
    SYMBOL, UTC_OFFSET,
    KILLZONES,
    MIN_CONFLUENCE_SCORE,
    DATA_M15_COUNT, DATA_H4_COUNT,
    SCAN_INTERVAL, SLEEP_OUTSIDE_KZ, ERROR_SLEEP, WEEKEND_SLEEP,
)
from telegram_bot import (
    kirim_telegram,
    kirim_startup_notification,
    start_telegram_bot,
    bot_state,
    scan_event,
)
from analysis import (
    get_data,
    detect_robust_bias,
    detect_sweep,
    detect_ifvg,
    calculate_confluence,
)
from risk_manager import validate_risk, calculate_sl_tp, log_trade


# ============================================================
#  LOGGING SETUP
# ============================================================

def setup_logging():
    """Configure logging ke file + console."""
    logger = logging.getLogger("xauusd_bot")
    logger.setLevel(logging.DEBUG)

    # File handler — semua log masuk sini
    file_handler = logging.FileHandler("bot_xauusd.log", encoding="utf-8")
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
    """Cek apakah sekarang masuk killzone session."""
    jam = get_wib_now().hour
    for start, end in KILLZONES:
        if start <= jam < end:
            return True
    return False


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
    rr1 = TP1_MULTIPLIER = 2
    rr2 = TP2_MULTIPLIER = 4
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

    # Initialize MT5 sekali di awal
    if not mt5.initialize():
        logger.critical("❌ MT5 initialization FAILED! Pastikan terminal MT5 terbuka.")
        return

    logger.info("✅ MT5 connected successfully.")

    # === START INTERACTIVE TELEGRAM BOT ===
    bot_state["mt5_connected"] = True
    bot_state["start_time"] = datetime.now()
    bot_state["running"] = True
    start_telegram_bot()

    kirim_startup_notification()

    # Anti-spam tracker
    last_sent_signal_time = None

    try:
        while True:
            try:
                # === PAUSE CHECK ===
                if bot_state["paused"]:
                    logger.debug("⏸️ Bot paused, waiting for resume...")
                    smart_sleep(5)
                    continue

                # === WEEKEND CHECK ===
                if not is_market_open():
                    bot_state["market_open"] = False
                    logger.info("📅 Weekend — market tutup. Sleeping 1 jam...")
                    smart_sleep(WEEKEND_SLEEP)
                    continue

                bot_state["market_open"] = True

                # === KILLZONE CHECK ===
                if not is_killzone():
                    bot_state["killzone_active"] = False
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
                    bot_state["mt5_connected"] = False
                    logger.warning("MT5 connection lost. Reconnecting...")
                    if not mt5.initialize():
                        logger.error("MT5 reconnection failed!")
                        smart_sleep(ERROR_SLEEP)
                        continue
                    logger.info("MT5 reconnected.")
                    bot_state["mt5_connected"] = True

                # === FETCH DATA ===
                df_m15 = get_data(SYMBOL, mt5.TIMEFRAME_M15, DATA_M15_COUNT)
                df_h4 = get_data(SYMBOL, mt5.TIMEFRAME_H4, DATA_H4_COUNT)

                if df_m15.empty or df_h4.empty:
                    logger.warning("Data kosong, retrying...")
                    smart_sleep(ERROR_SLEEP)
                    continue

                # === ANALYSIS ===
                bias = detect_robust_bias(df_h4)
                sweep_status, extreme_price = detect_sweep(df_m15)
                is_ifvg, ifvg_msg = detect_ifvg(df_m15, sweep_status)

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
                    confluence = calculate_confluence(side, bias, sweep_status, ifvg_msg, kz_active)

                # === UPDATE BOT STATE (for Telegram queries) ===
                bot_state.update({
                    "bias": bias,
                    "sweep": sweep_status,
                    "ifvg": ifvg_msg,
                    "confluence": confluence,
                    "price": harga_now,
                    "killzone_active": kz_active,
                    "last_scan_time": get_wib_now().strftime("%H:%M:%S WIB"),
                    "mt5_connected": True,
                    "market_open": True,
                })

                # === ENTRY LOGIC (AGGRESSIVE & ALIGNED) ===
                if (
                    side
                    and confluence >= MIN_CONFLUENCE_SCORE
                    and last_sent_signal_time != current_candle_time
                ):
                    if side:
                        # RISK VALIDATION
                        raw_risk = abs(harga_now - extreme_price)
                        is_valid, reason = validate_risk(raw_risk)
                        if not is_valid:
                            logger.info(f"Risk rejected: {reason}")
                            smart_sleep(SCAN_INTERVAL)
                            continue

                        # CALCULATE SL/TP
                        levels = calculate_sl_tp(side, harga_now, extreme_price)

                        # Confidence label berdasarkan confluence
                        confidence = "⚡ HIGH" if confluence >= 3 else "📊 MODERATE"

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
                            bot_state["last_signal_time"] = (
                                get_wib_now().strftime("%H:%M:%S WIB")
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
        bot_state["running"] = False
        mt5.shutdown()
        logger.info("MT5 connection closed. Bot stopped.")


# ============================================================
#  ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_engine()
