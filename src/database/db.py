import sqlite3
import os
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger("xauusd_bot")

DB_FILE = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
    "bot_database.db"
)

def get_connection() -> sqlite3.Connection:
    """Mendapatkan koneksi ke SQLite database."""
    conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inisialisasi skema database jika belum ada."""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Tabel trades
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT,
                time TEXT,
                side TEXT,
                entry REAL,
                sl REAL,
                tp1 REAL,
                tp2 REAL,
                risk REAL,
                confluence_score INTEGER,
                bias TEXT,
                tier TEXT,
                session TEXT,
                atr REAL,
                spread REAL,
                near_sweep BOOLEAN,
                ifvg_after_sweep BOOLEAN,
                ticket1 INTEGER,
                ticket2 INTEGER,
                result TEXT,
                pnl REAL DEFAULT 0.0
            )
        """)
        
        # Tabel scans (Opsional, untuk melacak signal/rejection)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT,
                symbol TEXT,
                price REAL,
                signal TEXT,
                reason TEXT
            )
        """)
        
        conn.commit()
    logger.info("SQLite Database diinisialisasi: " + DB_FILE)

def insert_trade(trade: Dict[str, Any]) -> int:
    """Menyimpan trade baru ke database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trades (
                version, time, side, entry, sl, tp1, tp2, risk,
                confluence_score, bias, tier, session, atr, spread,
                near_sweep, ifvg_after_sweep, ticket1, ticket2, result, pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade.get("version", "v2"),
            trade.get("time", datetime.now().isoformat()),
            trade.get("side"),
            trade.get("entry"),
            trade.get("sl"),
            trade.get("tp1"),
            trade.get("tp2"),
            trade.get("risk"),
            trade.get("confluence_score"),
            trade.get("bias"),
            trade.get("tier"),
            trade.get("session"),
            trade.get("atr"),
            trade.get("spread"),
            bool(trade.get("near_sweep", False)),
            bool(trade.get("ifvg_after_sweep", False)),
            trade.get("ticket1"),
            trade.get("ticket2"),
            trade.get("result", "PENDING"),
            trade.get("pnl", 0.0)
        ))
        conn.commit()
        return cursor.lastrowid

def update_trade_result(ticket: int, result: str, pnl: float = 0.0):
    """Update result dan PNL berdasarkan ticket number (berlaku untuk ticket1 atau ticket2)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Cari trade yang punya ticket1 atau ticket2 sama dengan ticket
        cursor.execute("""
            SELECT id, result, pnl FROM trades
            WHERE ticket1 = ? OR ticket2 = ?
        """, (ticket, ticket))
        row = cursor.fetchone()
        
        if row:
            trade_id = row["id"]
            current_result = row["result"]
            current_pnl = row["pnl"]
            
            # Update result: 
            # Jika current_result = 'PENDING', kita ganti ke 'WIN TP1' dsb.
            # Jika sudah 'WIN TP1' lalu ada update lagi, bisa jadi kita update jd 'WIN TP2' / 'TP1 + BEP'
            # Di sini kita simply replace (sesuai behavior json lama atau outcome tracker).
            # Bisa di-enhance agar result digabung jika multi-ticket.
            # Tapi Outcome Tracker akan melakukan override ke result terbaru (WIN TP1, WIN TP2).
            # Karena ticket2 punya event tersendiri, kita akan update ke result terbaru dan akumulasi PnL.
            
            new_pnl = current_pnl + pnl
            
            # Logic merge result (contoh sederhana)
            new_result = result
            if current_result != "PENDING" and current_result != "EXPIRED":
                # Jika sudah ada result sebelumnya
                if result == "WIN TP2":
                    new_result = "WIN TP2"
                elif result == "LOSS" and current_result == "WIN TP1":
                    new_result = "TP1 + BEP"  # Anggap loss pada posisi sisa berarti hit BEP
                    
            cursor.execute("""
                UPDATE trades
                SET result = ?, pnl = ?
                WHERE id = ?
            """, (new_result, new_pnl, trade_id))
            conn.commit()
            return True
    return False

def update_trade_result_by_id(trade_id: int, result: str, pnl: float = 0.0):
    """Update result dan PNL berdasarkan id trade (dipakai oleh outcome_tracker)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE trades SET result = ?, pnl = ? WHERE id = ?", (result, pnl, trade_id))
        conn.commit()
        return True

def get_pending_trades() -> List[Dict[str, Any]]:
    """Ambil semua trade yang statusnya masih PENDING."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE result = 'PENDING' ORDER BY time ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_all_trades() -> List[Dict[str, Any]]:
    """Ambil semua history trade, output format dictionary agar compatible."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY time ASC")
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]

def get_trades_by_date(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Ambil trade di antara start_date dan end_date (ISO format)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM trades 
            WHERE time >= ? AND time <= ? 
            ORDER BY time ASC
        """, (start_date, end_date))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def log_scan(symbol: str, price: float, signal: str, reason: str = ""):
    """Mencatat aktivitas scanning."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scans (time, symbol, price, signal, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), symbol, price, signal, reason))
        conn.commit()
