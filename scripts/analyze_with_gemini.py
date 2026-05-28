"""
analyze_with_gemini.py — Script Analisis Laporan Mingguan menggunakan AI.

Skrip mandiri (standalone) ini bertugas membaca agregat statistik dari `trade_history.json`,
mengirimkannya ke Gemini API, dan meminta AI memberikan *insight*, pola, dan saran
perbaikan untuk minggu berikutnya.

Skrip ini HANYA boleh dijalankan secara manual (misal sekali seminggu),
TIDAK BOLEH diletakkan di dalam loop live-trading karena alasan latency dan quota limit.
"""

# ruff: noqa: E402

import os
import sys
import logging
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
import google.generativeai as genai

# Tambahkan root proyek ke sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.backtest.report import calculate_r

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("gemini_analyzer")


from src.database.db import get_all_trades


def load_trade_data() -> pd.DataFrame | None:
    try:
        trades = get_all_trades()
        if not trades:
            logger.error("Data trade kosong di database.")
            return None

        df = pd.DataFrame(trades)
        if df.empty:
            return None

        df["r_multiple"] = df.apply(calculate_r, axis=1)
        # Ambil hanya trade yang sudah selesai
        resolved = df[df["result"].isin(["WIN_TP1", "WIN_TP2", "LOSS"])].copy()
        return resolved

    except Exception as e:
        logger.error(f"Gagal membaca/parsing history: {e}")
        return None


def build_aggregate_stats(df: pd.DataFrame) -> str:
    total_trades = len(df)
    wins = df[df["result"].str.startswith("WIN")]
    losses = df[df["result"] == "LOSS"]

    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    gross_profit = wins["r_multiple"].sum()
    gross_loss = abs(losses["r_multiple"].sum())
    net_r = gross_profit - gross_loss
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    stats_str = "=== STATISTIK KESELURUHAN ===\n"
    stats_str += f"Total Trades: {total_trades}\n"
    stats_str += f"Win Rate: {win_rate:.2f}%\n"
    stats_str += f"Net R: {net_r:.2f}\n"
    stats_str += f"Profit Factor: {pf:.2f}\n\n"

    stats_str += "=== BREAKDOWN PER TIER ===\n"
    for tier, group in df.groupby("tier"):
        t_wins = len(group[group["result"].str.startswith("WIN")])
        t_wr = (t_wins / len(group)) * 100
        t_net = group["r_multiple"].sum()
        stats_str += (
            f"- {tier}: {len(group)} trades, Win Rate {t_wr:.1f}%, Net R {t_net:.2f}\n"
        )

    stats_str += "\n=== BREAKDOWN PER SESI ===\n"
    if "session" in df.columns:
        for sess, group in df.groupby("session"):
            s_wins = len(group[group["result"].str.startswith("WIN")])
            s_wr = (s_wins / len(group)) * 100
            s_net = group["r_multiple"].sum()
            stats_str += f"- {sess}: {len(group)} trades, Win Rate {s_wr:.1f}%, Net R {s_net:.2f}\n"

    stats_str += "\n=== BREAKDOWN PER ARAH BIAS H4 ===\n"
    if "bias" in df.columns:
        for bias, group in df.groupby("bias"):
            b_wins = len(group[group["result"].str.startswith("WIN")])
            b_wr = (b_wins / len(group)) * 100
            b_net = group["r_multiple"].sum()
            stats_str += f"- {bias}: {len(group)} trades, Win Rate {b_wr:.1f}%, Net R {b_net:.2f}\n"

    return stats_str


def main():
    load_dotenv(project_root / ".env")
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.error(
            "❌ GEMINI_API_KEY tidak ditemukan di .env. Silakan tambahkan terlebih dahulu."
        )
        sys.exit(1)

    logger.info("⏳ Membaca data trade history...")
    df = load_trade_data()

    if df is None or df.empty:
        logger.warning(
            "Tidak ada data trade terselesaikan (resolved) untuk dianalisis."
        )
        sys.exit(0)

    stats_text = build_aggregate_stats(df)

    prompt = f"""
Anda adalah analis kuantitatif (Quant Trader) ahli yang mengevaluasi performa bot trading XAUUSD 
yang dibangun menggunakan konsep ICT (Inner Circle Trader) - Sweep & IFVG.

Saya akan memberikan statistik performa trading agregat. Tolong berikan:
1. Analisis pola apa yang sedang terjadi (misal: Sesi mana yang paling buruk, apakah bot buruk di tier tertentu?)
2. Saran konkret filter tambahan atau penyesuaian parameter untuk minggu depan.
3. Kesimpulan singkat dalam 1-2 kalimat.

Gunakan bahasa Indonesia yang profesional namun ringkas (Hindari basa-basi panjang).

BERIKUT DATA STATISTIKNYA:
{stats_text}
"""

    logger.info("🤖 Mengirimkan data agregat ke Gemini API...")

    try:
        genai.configure(api_key=api_key)
        # Menggunakan model gemini-1.5-pro atau gemini-pro
        model = genai.GenerativeModel("gemini-1.5-pro-latest")
        response = model.generate_content(prompt)

        logger.info("\n" + "=" * 50)
        logger.info("💡 HASIL ANALISIS GEMINI")
        logger.info("=" * 50)
        print(response.text)
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"❌ Terjadi kesalahan saat memanggil API Gemini: {e}")


if __name__ == "__main__":
    main()
