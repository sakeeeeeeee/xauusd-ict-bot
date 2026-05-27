"""
report.py — Backtest Reporting Module
Menganalisis hasil backtest (DataFrame trades) dan menghitung statistik performa:
Win Rate, Profit Factor, Average R, Max Drawdown, dll.
"""

import pandas as pd


def calculate_r(row):
    """Menghitung multiplier Risk (R) berdasarkan hasil trade."""
    res = row.get("result", "")
    if res in ["PENDING", "EXPIRED"]:
        return 0.0

    entry = float(row.get("entry", 0))
    sl = float(row.get("sl", 0))
    tp1 = float(row.get("tp1", 0))
    tp2 = float(row.get("tp2", 0))

    risk = abs(entry - sl)
    if risk == 0:
        return 0.0

    if res == "LOSS":
        return -1.0
    elif res == "WIN_TP1":
        return abs(tp1 - entry) / risk
    elif res == "WIN_TP2":
        return abs(tp2 - entry) / risk

    return 0.0


def generate_report(df: pd.DataFrame):
    if df is None or df.empty:
        print("\n[REPORT] Tidak ada data trade untuk dianalisis.")
        return

    # Hitung R-Multiple
    df["r_multiple"] = df.apply(calculate_r, axis=1)

    # Filter hanya trade yang resolved (menang/kalah)
    resolved = df[df["result"].isin(["WIN_TP1", "WIN_TP2", "LOSS"])].copy()

    total_trades = len(df)
    total_resolved = len(resolved)

    if total_resolved == 0:
        print("\n[REPORT] Belum ada trade yang resolved (semua PENDING/EXPIRED).")
        return

    # Basic Metrics
    wins = resolved[resolved["result"].str.startswith("WIN")]
    losses = resolved[resolved["result"] == "LOSS"]

    win_rate = (len(wins) / total_resolved) * 100
    gross_profit = wins["r_multiple"].sum()
    gross_loss = abs(losses["r_multiple"].sum())
    net_r = gross_profit - gross_loss

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_r = net_r / total_resolved

    # Drawdown
    resolved["cum_r"] = resolved["r_multiple"].cumsum()
    resolved["peak"] = resolved["cum_r"].cummax()
    resolved["drawdown"] = resolved["peak"] - resolved["cum_r"]
    max_drawdown = resolved["drawdown"].max()

    # Time metrics
    df["time"] = pd.to_datetime(df["time"])
    days = (df["time"].max() - df["time"].min()).days
    months = days / 30.0 if days > 0 else 1.0
    signals_per_month = total_trades / months

    print("\n=======================================================")
    print("                 BACKTEST REPORT                       ")
    print("=======================================================")
    print(f"Total Trades Generated : {total_trades}")
    print(f"Total Resolved Trades  : {total_resolved}")
    print(f"Win Rate               : {win_rate:.2f}% ({len(wins)}W / {len(losses)}L)")
    print(f"Net R                  : {net_r:.2f} R")
    print(f"Average R per Trade    : {avg_r:.2f} R")
    print(f"Profit Factor          : {profit_factor:.2f}")
    print(f"Max Drawdown           : {max_drawdown:.2f} R")
    print(f"Signals per Month      : {signals_per_month:.1f}")

    # Breakdown per Tier
    print("\n--- Breakdown by Tier ---")
    if "tier" in resolved.columns:
        for tier, group in resolved.groupby("tier"):
            twins = group[group["result"].str.startswith("WIN")]
            twr = (len(twins) / len(group)) * 100
            tnet = group["r_multiple"].sum()
            print(
                f"Tier {tier:5s} | Trades: {len(group):3d} | Win Rate: {twr:5.1f}% | Net R: {tnet:6.2f}"
            )
    else:
        print("Data tier tidak tersedia.")

    # Breakdown per Session
    print("\n--- Breakdown by Session ---")
    if "session" in resolved.columns:
        for sess, group in resolved.groupby("session"):
            swins = group[group["result"].str.startswith("WIN")]
            swr = (len(swins) / len(group)) * 100
            snet = group["r_multiple"].sum()
            print(
                f"Session {sess:7s} | Trades: {len(group):3d} | Win Rate: {swr:5.1f}% | Net R: {snet:6.2f}"
            )
    else:
        print("Data session tidak tersedia.")

    print("=======================================================\n")
    return resolved
