"""
export_weekly_report.py — Script untuk mengekspor data trade 7 hari terakhir.
Membaca trade_history.json, menyaring 7 hari terakhir, lalu menghasilkan file CSV dan HTML (berisi metrik performa).
"""

# ruff: noqa: E402

import sys
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.backtest.report import calculate_r

from src.database.db import get_all_trades


def load_trade_history():
    try:
        trades = get_all_trades()
        return pd.DataFrame(trades)
    except Exception as e:
        print(f"Error fetching from DB: {e}")
        return None


def generate_weekly_report():
    df = load_trade_history()
    if df is None or df.empty:
        print("Data trade kosong.")
        return

    # Filter 7 hari terakhir
    df["time_parsed"] = pd.to_datetime(df["time"])
    seven_days_ago = datetime.now() - timedelta(days=7)

    # Menghapus timezone jika ada (karena datetime.now() biasanya naive)
    # Atasi error perbandingan jika tz-aware
    if df["time_parsed"].dt.tz is not None:
        seven_days_ago = seven_days_ago.astimezone(df["time_parsed"].dt.tz)

    weekly_df = df[df["time_parsed"] >= seven_days_ago].copy()

    if weekly_df.empty:
        print("Tidak ada trade dalam 7 hari terakhir.")
        return

    weekly_df["r_multiple"] = weekly_df.apply(calculate_r, axis=1)

    # Pisahkan trade resolved untuk metrik
    resolved = weekly_df[weekly_df["result"].isin(["WIN_TP1", "WIN_TP2", "LOSS"])]
    total_trades = len(weekly_df)
    total_resolved = len(resolved)

    win_rate = 0.0
    net_r = 0.0
    profit_factor = 0.0
    wins_count = 0
    losses_count = 0

    if total_resolved > 0:
        wins = resolved[resolved["result"].str.startswith("WIN")]
        losses = resolved[resolved["result"] == "LOSS"]
        wins_count = len(wins)
        losses_count = len(losses)
        win_rate = (wins_count / total_resolved) * 100
        gross_profit = wins["r_multiple"].sum()
        gross_loss = abs(losses["r_multiple"].sum())
        net_r = gross_profit - gross_loss
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Pastikan folder reports ada
    reports_dir = project_root / "reports"
    reports_dir.mkdir(exist_ok=True)

    csv_path = reports_dir / "weekly_report.csv"
    html_path = reports_dir / "weekly_report.html"

    # Hapus kolom helper sebelum save
    weekly_df.drop(columns=["time_parsed"], inplace=True)
    weekly_df.to_csv(csv_path, index=False)

    html_content = f"""
    <html>
    <head>
        <title>Weekly Trade Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; color: #333; }}
            .container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; }}
            .summary-cards {{ display: flex; gap: 20px; margin-bottom: 30px; }}
            .card {{ flex: 1; background: #ecf0f1; padding: 15px; border-radius: 5px; text-align: center; font-weight: bold; }}
            .card.profit {{ background: #d5f5e3; color: #1e8449; }}
            .card.loss {{ background: #fadbd8; color: #c0392b; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 12px; border-bottom: 1px solid #ddd; text-align: left; }}
            th {{ background-color: #34495e; color: white; }}
            tr:hover {{ background-color: #f1f1f1; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Weekly Trade Report (Last 7 Days)</h1>
            <p>Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            
            <div class="summary-cards">
                <div class="card">Total Trades<br/><h2>{total_trades}</h2></div>
                <div class="card">Win Rate<br/><h2>{win_rate:.1f}%</h2></div>
                <div class="card {"profit" if net_r > 0 else "loss"}">Net Return (R)<br/><h2>{net_r:.2f} R</h2></div>
                <div class="card">Profit Factor<br/><h2>{profit_factor:.2f}</h2></div>
            </div>

            <h3>Resolved Breakdown</h3>
            <p>Wins: {wins_count} | Losses: {losses_count}</p>

            <h3>Recent Trades</h3>
            {weekly_df.to_html(index=False, classes="table")}
        </div>
    </body>
    </html>
    """

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("Laporan mingguan berhasil diekspor!")
    print(f"CSV : {csv_path.resolve()}")
    print(f"HTML: {html_path.resolve()}")


if __name__ == "__main__":
    generate_weekly_report()
