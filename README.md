# 🎯 XAUUSD ICT Trading Signal Bot (v2.0 - Aggressive & Aligned)

Bot trading otomatis berbasis Python yang diintegrasikan langsung dengan **MetaTrader 5 (MT5)** dan **Telegram** untuk melakukan pemindaian (scanning) sinyal trading presisi tinggi pada pasangan mata uang **XAUUSD (Gold)** menggunakan konsep **ICT (Inner Circle Trader)**.

---

## 🚀 Fitur Utama

1. **Analisis Tren HTF (High Timeframe H4 Bias):**
   * Menggunakan **Dual Moving Average** (MA Fast & MA Slow) pada Timeframe H4.
   * Menyaring arah perdagangan agar selalu selaras dengan tren pasar yang dominan (`BULLISH`, `BEARISH`, atau `RANGING`).

2. **Deteksi Likuiditas (M15 Liquidity Sweep & Near-Sweep):**
   * Mencari pembersihan likuiditas (*liquidity sweep*) pada level puncak (*swing high*) dan dasar (*swing low*) dalam rentang waktu yang dinamis.
   * Dilengkapi fitur **Near-Sweep** dengan toleransi threshold ($1.0) dan validasi harga penutupan (*close price rejection*) untuk menghindari sinyal *breakout* palsu.

3. **Konfirmasi Struktur (Inversed Fair Value Gap - IFVG):**
   * Menggunakan **Inversed FVG (IFVG)** pada timeframe M15 sebagai konfirmasi entri yang valid.
   * Pemindaian dilakukan secara mundur (*backwards-scanning*) untuk memprioritaskan FVG terbaru dan tersegar (*fresh IFVG*).

4. **Filter Waktu Sesi (Killzone Session):**
   * Hanya melakukan pemindaian dan eksekusi pada jam-jam pasar aktif berlikuiditas tinggi: **Sesi Asia**, **Sesi London**, dan **Sesi New York (WIB)**.

5. **Manajemen Risiko Cerdas (Smart Risk Manager):**
   * Otomatis menghitung rasio **Risk to Reward (R:R)** yang ideal.
   * Menentukan level **Stop Loss (SL)** dengan buffer pengaman, serta **Take Profit 1 (2R)** dan **Take Profit 2 (4R)**.
   * Validasi risiko batas minimum ($1.50) dan maksimum ($15.00) untuk mencegah *noise* pasar atau jarak entri yang terlalu jauh.
   * Koreksi SL otomatis (*self-correcting SL*) jika harga sudah bergerak melampaui titik ekstrem.

6. **Telegram Bot Interaktif & Dashboard:**
   * Pengiriman sinyal instan lengkap dengan grafik detail harga entri, SL, TP1, TP2, nilai risiko, bias tren, dan skor konfluensi.
   * Fitur interaktif via `/start`, `/pause`, `/resume`, `/performance`, `/why`, `/lastsignal`.
   * **Dashboard Streamlit** mandiri terpisah untuk melihat analitik dan *win rate* riwayat trade via SQLite.

---

## 📐 Arsitektur Sistem (Dual Tier Architecture)

Bot ini menggunakan **Arsitektur Dual-Tier (Dua Lapisan)** untuk memisahkan proses logika yang berat dari proses pengiriman notifikasi/antarmuka (UI):
1. **Tier 1: Core Engine (`main.py`)** berjalan di *main thread*. Tugasnya murni melakukan *heavy-lifting*: koneksi ke MT5, *fetching* data *tick/candle*, menjalankan algoritma deteksi ICT, validasi sinyal, dan menyimpan ke SQLite (`bot_database.db`).
2. **Tier 2: Telegram Interface (`telegram_bot.py`)** berjalan secara asinkron (async) di *background thread*. Tugasnya mem-polling perintah Telegram (seperti `/status`, `/why`), mengambil data dari `bot_state` di memori via *Thread Lock*, dan membalas *user* tanpa menghalangi (blocking) proses *scan* di Tier 1.

```mermaid
graph TD
    A[Start Scan M15 & H4] --> B{Apakah Killzone Aktif?}
    B -- Tidak --> C[Sleep & Tunggu Sesi Berikutnya]
    B -- Ya --> D[Deteksi H4 Bias & M15 Sweep]
    D --> E{Apakah Ada Sweep?}
    E -- Tidak --> A
    E -- Ya: SWEEP BUY --> F{Apakah IFVG BUY Terbentuk?}
    E -- Ya: SWEEP SELL --> G{Apakah IFVG SELL Terbentuk?}
    F -- Ya --> H[Hitung Confluence & Validasi Risiko]
    F -- Tidak --> A
    G -- Ya --> H
    G -- Tidak --> A
    H --> I{Confluence >= 3 & Risiko Valid?}
    I -- Ya --> J[Simpan ke SQLite & Broadcast via Telegram]
    I -- Tidak --> A
```

---

## 🧠 Arsitektur Kecerdasan Buatan (ML Opsional & LLM Offline)

Bot ini menggunakan pendekatan *Hybrid Intelligence* untuk memaksimalkan akurasi tanpa mengorbankan kecepatan eksekusi (latency):
1. **Aturan Dasar (ICT Rules) sebagai Generator Kandidat:** Seluruh deteksi Sweep, IFVG, Bias H4, dan perhitungan Konfluensi murni menggunakan logika matematika *Price Action* yang deterministik dan instan (0 *latency*).
2. **Filter Machine Learning (Opsional):** Sinyal yang telah divalidasi oleh aturan ICT dapat difilter secara cerdas oleh model `Logistic Regression` (*scikit-learn*). Model ini memprediksi *Win Probability* berdasarkan historis *trade* SQLite. Fitur ini baru bisa dinyalakan di `config.py` (`USE_ML_FILTER = True`) setelah bot mengumpulkan minimal 200 sampel riil. **(ML ini bersifat opsional / *opt-in*)**.
3. **Analisis Gemini (Eksklusif Offline):** AI Generatif (LLM) seperti Gemini **HANYA** digunakan secara luring (*offline*) seminggu sekali melalui skrip utilitas `scripts/analyze_with_gemini.py`. Agen LLM dilarang keras untuk berpartisipasi dalam siklus *live scanning* untuk mencegah pembengkakan biaya API, *rate limit*, keterlambatan jaringan, serta halusinasi *non-deterministic*.

---

## 🛠️ Panduan Instalasi & Setup

### 1. Prasyarat Sistem
* **Sistem Operasi:** Windows (Wajib untuk MetaTrader 5 API).
* **Python:** Versi 3.8 hingga 3.11.
* **Aplikasi:** Terminal MetaTrader 5 terinstal dan login ke akun trading Anda.

### 2. Kloning Repositori
```bash
git clone https://github.com/sakeeeeeeee/xauusd-ict-bot.git
cd xauusd-ict-bot
```

### 3. Instal Dependensi
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Konfigurasi Lingkungan Variabel (`.env`)
Buat file bernama `.env` di direktori utama proyek Anda dan lengkapi variabel berikut (Wajib!):
```env
# --- TELEGRAM SETTINGS ---
TELEGRAM_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=-987654321

# --- GEMINI SETTINGS (OPSIONAL, untuk analyze_with_gemini.py) ---
GEMINI_API_KEY=AIzaSyA...
```

### 5. Pengaturan Parameter (`src/config.py`)
Sesuaikan perilaku bot pada file `src/config.py`. Beberapa yang penting:
* `SYMBOLS`: *List* dari mata uang yang di-scan (contoh: `["XAUUSD"]`).
* `CHART_ENABLED`: (`True`/`False`) Nyalakan untuk otomatis merender dan mengirim *chart* ke Telegram saat ada sinyal.
* `USE_ML_FILTER`: (`True`/`False`) Aktifkan hanya jika Anda sudah men-training model via `train_model.py`.
* `MIN_CONFLUENCE_SCORE`: Batas skor (default `3` untuk SWING).

---

## 🚀 Cara Menjalankan Bot & Util

### 1. Jalankan Bot Utama (VPS / Background)
Gunakan *script launcher* (yang mengaktifkan environment dan watchdog).
```bash
python scripts\watchdog.py
```
*(Direkomendasikan untuk mendaftarkan `watchdog.py` di Windows Task Scheduler `At Startup`.)*

### 2. Menjalankan Dashboard Analitik (Streamlit)
```bash
streamlit run dashboard/app.py
```

### 3. Ekspor Laporan & Analisa Gemini (Mingguan)
```bash
python scripts/export_weekly_report.py
python scripts/analyze_with_gemini.py
```

---

## 🧪 Cara Melakukan Backtest

Bot ini menyediakan *Backtest Engine* mandiri yang membaca *historical data* (M15 dan H4) dan menyimulasikan berjalannya logika (Sweep, IFVG, Bias) tanpa memerlukan *live tick* MT5.

```bash
# Pastikan MT5 Anda terbuka dan login (untuk men-download history data)
python -m scripts.run_backtest --symbol XAUUSD --days 30
```
*Hasil simulasi PnL, Win Rate, dan Profit Factor akan dicetak di layar console.*

---

## ⚖️ Penafian (Disclaimer & Peringatan Risiko)

**BACA DENGAN SEKSAMA SEBELUM MENGGUNAKAN PERANGKAT LUNAK INI:**

1. **Bukan Nasihat Keuangan (*Not Financial Advice*):** Perangkat lunak (bot) ini, beserta seluruh kode, skrip, dan dokumentasinya, disediakan semata-mata untuk tujuan **edukasi, penelitian, dan pembelajaran algoritma**. Tidak ada satupun output dari bot ini yang boleh dianggap sebagai rekomendasi investasi atau penasihat keuangan (*financial advice*).
2. **Risiko Kerugian Ekstrem:** Perdagangan valuta asing (Forex) dan komoditas (terutama XAUUSD/Emas) melibatkan risiko kerugian finansial yang sangat tinggi. Pergerakan pasar dapat menyebabkan hilangnya seluruh modal (dana) Anda secara instan.
3. **Wajib Akun Demo (Mandatory Demo):** Pengguna **DIWAJIBKAN** untuk menggunakan bot ini hanya di akun **Demo/Simulasi** dengan dana virtual. Anda sepenuhnya bertanggung jawab atas segala konsekuensi dan kerugian yang timbul jika Anda secara sengaja menyambungkan bot ini ke akun *Live* (dana riil).
4. **Perbedaan Lingkungan Pasar:** Terdapat perbedaan signifikan antara lingkungan akun Demo dan akun Live, antara lain:
   * **Slippage (Lonjakan Harga):** Saat likuiditas rendah atau volatilitas tinggi (seperti rilis berita ekonomi), *order* dapat tereksekusi jauh dari harga sinyal (slippage).
   * **Spread Pelebaran:** Broker melebarkan *spread* secara dinamis di akun Live yang bisa mempercepat *Stop Loss* tersentuh (*Stop Out*).
   * **Execution Delay:** Order di server *Live* seringkali mengalami *delay* eksekusi.
5. **Ketiadaan Jaminan:** Pengembang bot tidak memberikan jaminan keuntungan (*profit*) apa pun, baik tersurat maupun tersirat.

*Dengan mengunduh, menyalin, dan menjalankan *source code* proyek ini, Anda setuju membebaskan pengembang dari segala bentuk tuntutan atau kerugian finansial.*

---

*Dikembangkan dengan penuh dedikasi untuk keunggulan teknikal perdagangan otomatis.* 🚀
