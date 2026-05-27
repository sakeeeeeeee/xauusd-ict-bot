import os
import json
import sys

# Set parent dir to path so we can import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.db import init_db, insert_trade, DB_FILE

TRADE_LOG = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "trade_history.json"
)

def migrate():
    print("=== Migrating JSON to SQLite ===")
    
    if not os.path.exists(TRADE_LOG):
        print(f"File {TRADE_LOG} tidak ditemukan. Tidak ada data untuk dimigrasi.")
        return
        
    with open(TRADE_LOG, "r", encoding="utf-8") as f:
        try:
            history = json.load(f)
        except json.JSONDecodeError:
            print("Gagal membaca file JSON.")
            return

    print(f"Ditemukan {len(history)} data trade di JSON.")
    
    # Init DB dan skema
    init_db()
    
    # Migrasi data
    success_count = 0
    for trade in history:
        try:
            insert_trade(trade)
            success_count += 1
        except Exception as e:
            print(f"Gagal migrasi trade {trade.get('time')}: {e}")
            
    print(f"Berhasil migrasi {success_count}/{len(history)} trades ke SQLite ({DB_FILE}).")

if __name__ == "__main__":
    migrate()
