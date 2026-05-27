import os
import sys
import time
import subprocess
import logging
from logging.handlers import RotatingFileHandler

# ============================================================
#  WATCHDOG CONFIGURATION
# ============================================================

BOT_MODULE = "src.main"
RESTART_DELAY = 10  # Detik jeda sebelum merestart bot yang mati
MAX_RESTARTS = 50   # Maksimal restart dalam satu sesi sebelum menyerah (opsional)

# Set working directory ke root project (parent folder dari scripts)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(PROJECT_ROOT)

def setup_watchdog_logger():
    """Setup logging khusus untuk watchdog."""
    logger = logging.getLogger("watchdog")
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        "watchdog.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_fmt = logging.Formatter(
        "%(asctime)s [WATCHDOG] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # Console output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(file_fmt)
    logger.addHandler(console_handler)

    return logger

def run_watchdog():
    logger = setup_watchdog_logger()
    logger.info("=== Watchdog Started ===")
    logger.info(f"Monitoring module: {BOT_MODULE}")
    logger.info(f"Working Directory: {PROJECT_ROOT}")

    restart_count = 0
    
    while True:
        try:
            logger.info(f"Starting bot process (Attempt {restart_count + 1})...")
            
            # Gunakan executable python yang saat ini menjalankan watchdog (misal dari venv)
            python_exe = sys.executable
            
            # Jalankan bot
            process = subprocess.Popen([python_exe, "-m", BOT_MODULE])
            
            # Tunggu sampai proses selesai/mati
            exit_code = process.wait()
            
            # Jika bot berhenti (baik karena crash atau hal lain)
            logger.warning(f"Bot process exited with code {exit_code}.")
            
            # Jangan restart jika exit code == 0 dan disengaja, tapi dalam kasus bot 24/7,
            # kita asumsikan semua exit harus di-restart.
            
            restart_count += 1
            if MAX_RESTARTS and restart_count >= MAX_RESTARTS:
                logger.critical(f"Max restarts ({MAX_RESTARTS}) reached. Watchdog stopping.")
                break
                
            logger.info(f"Restarting in {RESTART_DELAY} seconds...")
            time.sleep(RESTART_DELAY)

        except KeyboardInterrupt:
            logger.info("Watchdog dihentikan oleh user (Ctrl+C). Menghentikan bot...")
            if 'process' in locals() and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            break
        except Exception as e:
            logger.error(f"Watchdog error: {e}")
            time.sleep(RESTART_DELAY)

if __name__ == "__main__":
    run_watchdog()
