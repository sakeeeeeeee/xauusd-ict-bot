import MetaTrader5 as mt5
import pandas as pd
import time
import requests
from datetime import datetime

# --- 1. SETUP & CREDENTIALS ---
TOKEN = "8728365642:AAGCMsd7CSs4aVgUGnqdxoYa9YpNyGxIE8w"
CHAT_ID = "980248102"
SYMBOL = "XAUUSD"
UTC_OFFSET = 7 # Set ke 7 untuk WIB (Jakarta/Medan)

# State tracker untuk cegah SPAM (Fix #2)
last_sent_signal_time = None 

def kirim_telegram(pesan):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": pesan, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e: print(f" [!] Telegram Error: {e}")

# --- 2. DATA GUARD & ROBUST BIAS ---
def get_data(symbol, timeframe, n=100):
    if not mt5.initialize(): return pd.DataFrame()
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None or len(rates) < 21: # Fix #3 (Guard < 21 candle)
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def detect_robust_bias(df): # Fix #6 (Lebih Robust)
    # Pake Moving Average sederhana atau cek 3 candle terakhir
    short_ma = df['close'].rolling(window=10).mean()
    if df['close'].iloc[-1] > short_ma.iloc[-1]: return "BULLISH"
    return "BEARISH"

# --- 3. FIX LOGIC IFVG & SWEEP (Fix #1) ---
def detect_sweep(df):
    if df.empty or len(df) < 21: return "Searching...", 0
    last_candle = df.iloc[-1]
    lookback = df.iloc[-21:-1]
    prev_high, prev_low = lookback['high'].max(), lookback['low'].min()
    
    if last_candle['low'] < prev_low and last_candle['close'] > prev_low:
        return "SWEEP BUY 💧", last_candle['low']
    elif last_candle['high'] > prev_high and last_candle['close'] < prev_high:
        return "SWEEP SELL 💧", last_candle['high']
    return "Searching...", 0

def detect_ifvg_fixed(df, sweep_status): # Logic IFVG Terkoreksi
    if sweep_status == "Searching..." or len(df) < 5: return False, "No IFVG"
    last_close = df['close'].iloc[-1]
    
    # Cari FVG di candle ke-2, 3, 4 ke belakang
    for i in range(len(df) - 5, len(df) - 2):
        c1_low, c1_high = df['low'].iloc[i], df['high'].iloc[i]
        c3_low, c3_high = df['low'].iloc[i+2], df['high'].iloc[i+2]
        
        if sweep_status == "SWEEP BUY 💧":
            # Mencari Bearish FVG (C1_Low > C3_High) yang ditembus ke ATAS
            if c1_low > c3_high and last_close > c1_low:
                return True, "IFVG BUY 🧲"
        elif sweep_status == "SWEEP SELL 💧":
            # Mencari Bullish FVG (C1_High < C3_Low) yang ditembus ke BAWAH
            if c1_high < c3_low and last_close < c1_high:
                return True, "IFVG SELL 🧲"
    return False, "Waiting IFVG..."

# --- 4. TIMEZONE & KILLZONE (Fix #4) ---
def is_killzone():
    jam_now = datetime.now().hour # Sesuaikan dengan jam laptop/VPS lu
    # London (14-17 WIB) atau NY (19-23 WIB)
    if (14 <= jam_now < 17) or (19 <= jam_now < 23):
        return True
    return False

# --- 5. EXECUTION LOOP ---
def run_engine():
    global last_sent_signal_time
    print(f"🚀 BOT FIXED VERSION STARTING... (Timezone WIB: GMT+{UTC_OFFSET})")
    
    while True:
        try:
            if not mt5.initialize(): 
                time.sleep(10); continue

            # Check Killzone
            if not is_killzone():
                print(f" [{datetime.now().strftime('%H:%M')}] Outside Killzone. Sleeping..."); time.sleep(60); continue

            # Get Data
            df_m15 = get_data(SYMBOL, mt5.TIMEFRAME_M15, 50)
            df_h4 = get_data(SYMBOL, mt5.TIMEFRAME_H4, 20)
            
            if df_m15.empty or df_h4.empty:
                time.sleep(10); continue

            # Analysis
            bias = detect_robust_bias(df_h4)
            sweep_status, extreme_p = detect_sweep(df_m15)
            is_ifvg, ifvg_msg = detect_ifvg_fixed(df_m15, sweep_status)
            
            harga_now = df_m15['close'].iloc[-1]
            current_candle_time = df_m15['time'].iloc[-1]

            # Logic Entry & Anti-Spam (Fix #2)
            if is_ifvg and (last_sent_signal_time != current_candle_time):
                
                # Risk Guard (Fix #5)
                risk = abs(harga_now - extreme_p)
                if risk < 0.10: # Guard kalau SL terlalu mepet
                    time.sleep(60); continue

                # Determine Signal Type
                side = None
                if bias == "BULLISH" and sweep_status == "SWEEP BUY 💧": side = "BUY 🟢"
                elif bias == "BEARISH" and sweep_status == "SWEEP SELL 💧": side = "SELL 🔴"

                if side:
                    sl = extreme_p
                    tp1 = round(harga_now + (risk if "BUY" in side else -risk), 2)
                    tp2 = round(harga_now + (2*risk if "BUY" in side else -2*risk), 2)
                    
                    pesan = f"🎯 *XAUUSD {side}*\nPrice: {harga_now}\n\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\n\n_Fixed Version - No Spam_"
                    kirim_telegram(pesan)
                    last_sent_signal_time = current_candle_time # Lock sinyal untuk candle ini
                    print(f" [!] Sinyal {side} terkirim!")

            print(f" [{datetime.now().strftime('%H:%M:%S')}] Scanning {SYMBOL}... Bias: {bias}", end='\r')
            time.sleep(30) # Cek tiap 30 detik biar lebih responsif tapi hemat data

        except Exception as e:
            print(f"Error: {e}"); time.sleep(10)

if __name__ == "__main__":
    run_engine()