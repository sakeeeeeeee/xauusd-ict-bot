import sqlite3
import pandas as pd
import streamlit as st
import os
import plotly.express as px

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="XAUUSD ICT Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Definisi Path DB relative to dashboard folder
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bot_database.db"))

@st.cache_data(ttl=60)  # Cache data selama 1 menit agar tidak sering query ke DB
def load_data():
    """Load data dari SQLite ke pandas DataFrame."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM trades ORDER BY time DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if not df.empty:
        # Konversi string time ISO ke datetime object
        df["time"] = pd.to_datetime(df["time"])
        # Tambahkan kolom minggu dan tahun untuk grouping
        df["week"] = df["time"].dt.to_period("W").apply(lambda r: r.start_time)
        
    return df

# CSS Kustom (opsional untuk merapikan UI)
st.markdown("""
    <style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📈 XAUUSD ICT Bot Dashboard")
st.markdown("Dashboard ini menampilkan riwayat trade dari database SQLite secara real-time.")

# Load Data
df = load_data()

if df.empty:
    st.warning(f"Database tidak ditemukan atau kosong. (Path yang dicari: {DB_PATH})")
    st.stop()

# ==========================================
# 1. KPI CARDS
# ==========================================
st.header("📊 Ringkasan Kinerja")

# Filter hanya trade yang memiliki status selesai (menang atau kalah)
resolved_df = df[df["result"].isin(["WIN_TP1", "WIN_TP2", "LOSS", "TP1 + BEP"])]

total_trades = len(df)
total_resolved = len(resolved_df)

wins = len(resolved_df[resolved_df["result"].str.contains("WIN|TP1 \+ BEP", regex=True)])
losses = len(resolved_df[resolved_df["result"] == "LOSS"])

win_rate = (wins / total_resolved * 100) if total_resolved > 0 else 0.0
total_pnl = resolved_df["pnl"].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Trades", total_trades)
col2.metric("Resolved Trades", total_resolved)
col3.metric("Win Rate", f"{win_rate:.1f}%")
col4.metric("Total PnL (Mock)", f"${total_pnl:.2f}")

st.divider()

# ==========================================
# 2. CHART WIN RATE PER MINGGU
# ==========================================
st.header("📅 Win Rate per Minggu")

if not resolved_df.empty:
    # Agregasi data per minggu
    weekly_stats = resolved_df.groupby("week").apply(
        lambda x: pd.Series({
            "total": len(x),
            "wins": len(x[x["result"].str.contains("WIN|TP1 \+ BEP", regex=True)]),
        })
    ).reset_index()
    
    weekly_stats["win_rate"] = (weekly_stats["wins"] / weekly_stats["total"]) * 100

    # Buat Bar Chart Interaktif menggunakan Plotly
    fig = px.bar(
        weekly_stats, 
        x="week", 
        y="win_rate", 
        text="win_rate",
        labels={"week": "Awal Minggu", "win_rate": "Win Rate (%)"},
        title="Persentase Kemenangan Mingguan",
        color="win_rate",
        color_continuous_scale=px.colors.sequential.Tealgrn
    )
    fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    fig.update_layout(yaxis_range=[0, 100])
    
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Belum ada trade yang selesai (Resolved) untuk menampilkan grafik.")

st.divider()

# ==========================================
# 3. TABEL DATA TRADES
# ==========================================
st.header("🗂️ Riwayat Trade")

# Fitur Filter di Sidebar
st.sidebar.header("Filter Data")
selected_side = st.sidebar.multiselect(
    "Filter by Side:", 
    options=df["side"].unique(), 
    default=df["side"].unique()
)

selected_result = st.sidebar.multiselect(
    "Filter by Result:", 
    options=df["result"].unique(), 
    default=df["result"].unique()
)

# Terapkan filter
filtered_df = df[(df["side"].isin(selected_side)) & (df["result"].isin(selected_result))]

# Tampilkan tabel (sembunyikan kolom yg terlalu teknis kalau mau rapi, atau tampilkan semua)
columns_to_show = ["time", "side", "entry", "sl", "tp1", "tp2", "result", "pnl", "confluence_score", "bias"]
st.dataframe(
    filtered_df[columns_to_show].style.format({"entry": "{:.2f}", "sl": "{:.2f}", "tp1": "{:.2f}", "tp2": "{:.2f}", "pnl": "{:.2f}"}),
    use_container_width=True,
    height=400
)

# Tombol Refresh Manual
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()
