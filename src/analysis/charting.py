"""
charting.py - Utility to generate trade visualization charts.
"""

import pandas as pd
import mplfinance as mpf
import logging

logger = logging.getLogger("xauusd_bot")


def generate_trade_chart(
    df: pd.DataFrame,
    symbol: str,
    side: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    output_path: str = "generate_chart.png",
):
    """
    Generate a candlestick chart with SL, TP, and Entry lines.
    Saves the chart to output_path.
    df must be a pandas DataFrame with datetime index and Open, High, Low, Close columns.
    """
    try:
        if df is None or df.empty:
            logger.error("Chart generation failed: DataFrame is empty")
            return None

        # Ambil maksimal 50 bar terakhir agar chart terlihat proporsional
        plot_df = df.tail(50).copy()

        # Pastikan kolom sesuai format mplfinance
        col_map = {
            c: c.capitalize()
            for c in plot_df.columns
            if c.lower()
            in ["open", "high", "low", "close", "tick_volume", "real_volume", "volume"]
        }
        plot_df.rename(columns=col_map, inplace=True)

        if not isinstance(plot_df.index, pd.DatetimeIndex):
            plot_df.index = pd.to_datetime(plot_df.index)

        hline_levels = [sl, entry, tp1, tp2]
        hline_colors = ["r", "b", "g", "g"]
        hline_styles = ["--", "-", "--", "-."]

        # Style kustom yang bersih
        mc = mpf.make_marketcolors(
            up="#26a69a", down="#ef5350", edge="inherit", wick="inherit"
        )
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle=":", y_on_right=True)

        title = f"{symbol} {side} Setup"

        mpf.plot(
            plot_df,
            type="candle",
            style=s,
            hlines=dict(
                hlines=hline_levels,
                colors=hline_colors,
                linestyle=hline_styles,
                linewidths=1.5,
            ),
            title=title,
            savefig=output_path,
            tight_layout=True,
            figsize=(10, 6),
        )
        return output_path
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return None


def generate_chart(
    df: pd.DataFrame,
    symbol: str,
    entry_price: float,
    sl_price: float,
    tp1_price: float,
    tp2_price: float,
    save_path: str = "generate_chart.png",
) -> str | None:
    """
    Wrapper yang cocok dengan pemanggilan di main.py.
    Mendeteksi side otomatis dari posisi entry vs SL.
    """
    side = "BUY" if tp1_price > entry_price else "SELL"
    return generate_trade_chart(
        df=df,
        symbol=symbol,
        side=side,
        entry=entry_price,
        sl=sl_price,
        tp1=tp1_price,
        tp2=tp2_price,
        output_path=save_path,
    )
