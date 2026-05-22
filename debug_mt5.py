"""
debug_mt5.py — Script untuk diagnosa kenapa MT5 gagal initialize
"""
import sys
import struct
import os

print("=" * 50)
print("🔍 MT5 DEBUG DIAGNOSTIC")
print("=" * 50)

# 1. Cek Python version & architecture
print(f"\n[1] Python Version : {sys.version}")
print(f"    Python Arch    : {struct.calcsize('P') * 8}-bit")
print(f"    Python Path    : {sys.executable}")

if struct.calcsize('P') * 8 != 64:
    print("    ⚠️  WARNING: MetaTrader5 butuh Python 64-bit!")

# 2. Cek apakah library MetaTrader5 terinstall
print(f"\n[2] Checking MetaTrader5 library...")
try:
    import MetaTrader5 as mt5
    print(f"    ✅ MetaTrader5 version: {mt5.__version__}")
except ImportError as e:
    print(f"    ❌ MetaTrader5 TIDAK terinstall: {e}")
    print("    Fix: pip install MetaTrader5")
    sys.exit(1)

# 3. Cek path terminal MT5
print(f"\n[3] Attempting mt5.initialize()...")

# Coba default dulu
result = mt5.initialize()
print(f"    Default initialize: {result}")

if not result:
    error = mt5.last_error()
    print(f"    ❌ Error code : {error[0]}")
    print(f"    ❌ Error msg  : {error[1]}")

    # Coba cari terminal MT5 di lokasi umum
    common_paths = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal"),
        r"C:\Program Files\RoboForex - MetaTrader 5\terminal64.exe",
        r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
        r"C:\Program Files\FBS MetaTrader 5\terminal64.exe",
    ]

    print(f"\n[4] Scanning MT5 terminal paths...")
    found_any = False
    for path in common_paths:
        exists = os.path.exists(path)
        status = "✅ FOUND" if exists else "  not found"
        print(f"    {status}: {path}")
        if exists and path.endswith(".exe"):
            found_any = True
            print(f"\n    → Trying initialize with: {path}")
            result2 = mt5.initialize(path)
            print(f"      Result: {result2}")
            if result2:
                info = mt5.terminal_info()
                if info:
                    print(f"      ✅ Terminal: {info.name}")
                    print(f"      ✅ Company:  {info.company}")
                    print(f"      ✅ Path:     {info.path}")
                    print(f"      ✅ Connected: {info.connected}")
                mt5.shutdown()
                break
            else:
                err2 = mt5.last_error()
                print(f"      ❌ Error: {err2}")

    if not found_any:
        print("\n    ⚠️  Tidak ditemukan terminal64.exe di lokasi umum.")
        print("    Coba cari manual: dir /s /b C:\\terminal64.exe")

else:
    # Berhasil connect — tampilkan info
    print(f"    ✅ MT5 initialized successfully!")
    info = mt5.terminal_info()
    if info:
        print(f"\n[4] Terminal Info:")
        print(f"    Name      : {info.name}")
        print(f"    Company   : {info.company}")
        print(f"    Path      : {info.path}")
        print(f"    Connected : {info.connected}")
        print(f"    Trade OK  : {info.trade_allowed}")

    account = mt5.account_info()
    if account:
        print(f"\n[5] Account Info:")
        print(f"    Login   : {account.login}")
        print(f"    Server  : {account.server}")
        print(f"    Balance : {account.balance}")
    else:
        print(f"\n[5] Account: Belum login ke akun trading")

    mt5.shutdown()

print("\n" + "=" * 50)
print("🏁 DEBUG SELESAI")
print("=" * 50)
