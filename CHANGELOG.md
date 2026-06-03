# Changelog

Semua perubahan penting pada proyek ini akan didokumentasikan dalam file ini.

Format pencatatan log mengacu pada [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), dan proyek ini mematuhi [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Catatan Strategi (Strategy Versioning):**
> Setiap perubahan signifikan yang memengaruhi logika utama penghasil sinyal trading—seperti perubahan batas `MIN_CONFLUENCE_SCORE`, penyesuaian aturan *Liquidity Sweep* (`REQUIRE_SWEEP`, `NEAR_SWEEP_ENABLED`), atau perubahan perhitungan `IFVG`—akan dicatat secara eksplisit di bawah tag khusus **[Strategy Update]**.

## [Unreleased]

### Added
- **Dashboard Streamlit**: Dashboard minimal (`dashboard/app.py`) untuk visualisasi data historis dari SQLite (grafik *win rate* dan tabel trade).
- **Automated CI/CD**: Workflow GitHub Actions (`.github/workflows/ci.yml`) untuk menjalankan instalasi *library*, *Ruff linting*, dan `pytest` secara in-memory (tanpa MetaTrader 5 live server).
- **Windows Task Scheduler Guide**: Dokumentasi (`docs/windows_service.md`) dan script pengawas (`scripts/watchdog.py`) untuk menjaga proses bot *up* secara permanen di server VPS.

### Changed
- **[Strategy Update] Robust Anti-Overfitting Profile**: Menghapus paksaan masuk (*Scalping*) di hari Kamis-Jumat untuk sesi NY akibat drawdawn tinggi (-45R) dalam uji mundur 300 hari. Aturan baru menstandarkan sesi London hanya beroperasi di hari Senin-Rabu dengan Skor minimal 2, sementara Sesi NY bebas hari namun diwajibkan memiliki skor konfluensi sempurna 3/3 (menghasilkan rasio kemenangan NY historis 100%).

## [2.1.0] - 2026-05-27

### Added
- **Database Terintegrasi (SQLite)**: Seluruh pencatatan *trade history* dipindahkan dari format lama `trade_history.json` ke `bot_database.db` menggunakan modul `src/database/db.py` untuk efisiensi penyimpanan (*schema: trades & scans*).
- **Multiple Symbols Scanning**: Mendukung *scanning* beberapa instrumen sekaligus (`SYMBOLS = ["XAUUSD"]`) dengan metode rotasi per siklus di `main.py`.
- **Fitur Diagram Telegram (Charting)**: Penambahan visualisasi *candlestick* berbasis Matplotlib (`mplfinance`) yang langsung terlampir ketika mengirimkan perintah atau sinyal ke Telegram via bot asinkron (*UI inline keyboard*).
- **Perintah Telegram Baru**: `/why`, `/lastsignal`, `/performance` untuk memberikan laporan kesehatan bot dan memanggil data riwayat perdagangan terakhir.

### Changed
- **Arsitektur Dual Tier (Core & Telegram)**: Pemisahan thread bot utama (`main.py`) dari *background polling thread* asinkron untuk interface bot telegram.

### Fixed
- **Robust Initialization**: `initialize_mt5_robust()` kini secara otomatis mencoba melakukan fallback ke berbagai direktori (seperti di AppData, Program Files, Exness, FBS) jika gagal menghubungkan MetaTrader 5 dengan argumen kosong.
- Perbaikan sinkronisasi dan *deadlocks* yang sempat terjadi di *Event Loop* `asyncio` pada saat mengirim pesan notifikasi ke Telegram (via transisi ke fungsi *thread-safe* Telegram PTB).

## [2.0.0] - 2026-05-18

### Added
- **[Strategy Update] Parameter Filter Likuiditas Lanjutan**: Memperkenalkan metode deteksi *Inversed Fair Value Gap* (IFVG) dan *Liquidity Sweep*. 
- **[Strategy Update] Konfluensi Wajib**: Mulai versi 2.0, entri sinyal trading diwajibkan untuk memiliki setidaknya skor konfluensi 3 (*Tier SWING*) yang didasarkan dari struktur arah H4 (HTF).
- Penambahan fungsi pelacakan *Killzone* pasar spesifik (London, New York, Asia) menggunakan zona waktu spesifik WIB.
- Integrasi Machine Learning (Logistic Regression) yang diuji secara opsional (`USE_ML_FILTER`) melalui utilitas `train_model.py`.

### Changed
- Refaktor perhitungan Stop Loss dan Take Profit menjadi metode kalkulasi *Structure-Based* dengan batas minimum `$1.50` dan maksimum `$15.00` (*Smart Risk Management*).
- Skema JSON *Trade History* diperbarui ke `v2` dengan *tracking* sesi transaksi dan label kelas (*tier*).

## [1.0.0] - 2026-05-01

### Added
- Rilis awal stabilitas (Initial Release).
- Koneksi dasar ke *MetaTrader 5 API* menggunakan library resmi dari MetaQuotes.
- Kalkulasi Dual MA Fast dan Slow H4 untuk *trend direction baseline*.
- Notifikasi Telegram sederhana untuk eksekusi pesanan.
