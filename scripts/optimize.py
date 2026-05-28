import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import itertools
import logging

# Tambahkan src ke system path jika dijalankan dari root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.risk.risk_manager as rm
import src.backtest.backtest_engine as engine
from src.backtest.report import calculate_r


def run_optimization():
    print("=== XAUUSD BACKTEST OPTIMIZER ===")

    # 1. Tentukan Parameter Grid
    # Kita akan menguji kombinasi dari nilai-nilai ini:
    atr_sl_mults = [0.1, 0.3, 0.5, 0.8]  # Pengali ATR untuk tambahan Stop Loss
    tp1_multipliers = [1.0, 1.5, 2.0, 2.5]  # Target Profit 1 (dalam R)
    min_confluence_scalps = [2, 3]  # Minimal skor untuk Scalp

    symbol = "XAUUSD"
    days = 30
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # 2. Download Data (Hanya Sekali!)
    print(f"\n[1/3] Mengambil data historis {days} hari dari MT5...")
    df_m5, df_m15, df_h4 = engine.fetch_historical_data(symbol, start_date, end_date)

    if df_m5 is None:
        print("[X] Gagal mengambil data dari MT5. Pastikan MT5 terbuka dan login.")
        return

    print(f"[OK] Data berhasil diambil! (M5: {len(df_m5)} candle)")

    # Buat kombinasi dari semua parameter
    combinations = list(
        itertools.product(atr_sl_mults, tp1_multipliers, min_confluence_scalps)
    )
    total_combinations = len(combinations)

    print(f"\n[2/3] Memulai simulasi untuk {total_combinations} kombinasi parameter...")

    # Disable logging completely for speed
    logging.disable(logging.CRITICAL)

    results = []

    # 3. Looping untuk setiap kombinasi
    for idx, (atr_sl, tp1, scalp_conf) in enumerate(combinations):
        # --- MONKEY PATCHING ---
        import src.config as config

        config.SESSION_SETTINGS["NY"]["ATR_SL_BUFFER_MULT"] = atr_sl
        config.SESSION_SETTINGS["NY"]["TP1_MULTIPLIER"] = tp1

        # Biarkan London tetap di settingan dewa nya
        config.SESSION_SETTINGS["LONDON"]["ATR_SL_BUFFER_MULT"] = 0.8
        config.SESSION_SETTINGS["LONDON"]["TP1_MULTIPLIER"] = 1.0

        rm.ATR_MAX_RISK_MULT = 5.0  # Agar SL besar tidak ter-reject otomatis
        rm.TP2_MULTIPLIER = tp1 * 2  # TP2 kita buat selalu 2x TP1

        engine.MIN_CONFLUENCE_SCALP = scalp_conf
        engine.MIN_CONFLUENCE_SWING = scalp_conf

        # --- RUN BACKTEST IN MEMORY ---
        # quiet=True agar tidak spam console
        df_trades = engine.run_backtest(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            output_file="temp_opt.csv",
            df_m5=df_m5,
            df_m15_full=df_m15,
            df_h4_full=df_h4,
            quiet=True,
        )

        # --- HITUNG HASIL (KHUSUS NY) ---
        if df_trades is not None and not df_trades.empty:
            df_trades["r_multiple"] = df_trades.apply(calculate_r, axis=1)
            # Filter HANYA trade dari sesi NY untuk melihat performanya
            resolved = df_trades[
                (df_trades["result"].isin(["WIN_TP1", "WIN_TP2", "LOSS"]))
                & (df_trades["session"] == "NY")
            ]

            total_trades = len(resolved)
            if total_trades > 0:
                wins = len(resolved[resolved["result"].str.startswith("WIN")])
                win_rate = (wins / total_trades) * 100
                net_r = resolved["r_multiple"].sum()
            else:
                win_rate = 0.0
                net_r = 0.0
                total_trades = 0
        else:
            win_rate = 0.0
            net_r = 0.0
            total_trades = 0

        results.append(
            {
                "ATR_SL_MULT": atr_sl,
                "TP1_MULT": tp1,
                "MIN_SCALP": scalp_conf,
                "Trades": total_trades,
                "WinRate(%)": round(win_rate, 2),
                "Net_R": round(net_r, 2),
            }
        )

        # Print progress (overwrite line)
        sys.stdout.write(
            f"\rProgress: {idx + 1}/{total_combinations} | Net R: {net_r:.2f} (ATR_SL:{atr_sl}, TP:{tp1})"
        )
        sys.stdout.flush()

    # Re-enable logging
    logging.disable(logging.NOTSET)
    print("\n\n[3/3] Simulasi Selesai! Mengurutkan hasil terbaik...\n")

    # 4. Tampilkan Hasil Terbaik
    df_results = pd.DataFrame(results)
    # Urutkan berdasarkan Net R tertinggi
    df_results = df_results.sort_values(by="Net_R", ascending=False).reset_index(
        drop=True
    )

    print("=== TOP 10 KOMBINASI PARAMETER ===")
    print(df_results.head(10).to_string(index=False))

    # Simpan hasil lengkap
    df_results.to_csv("optimization_results.csv", index=False)
    print("\n[OK] Hasil lengkap disimpan ke 'optimization_results.csv'")


if __name__ == "__main__":
    run_optimization()
