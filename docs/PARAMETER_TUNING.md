# 🎛️ Panduan Tuning Parameter (Parameter Tuning)

Bot XAUUSD ICT ini dilengkapi dengan puluhan variabel di `src/config.py` yang mengatur sensitivitas indikator, manajemen risiko, dan filter sesi. 

Meskipun Anda diberi kebebasan penuh untuk memodifikasi parameter ini, **TERDAPAT ATURAN EMAS** yang pantang dilanggar demi menjaga kelangsungan portofolio (*equity*) Anda.

---

## ⚠️ ATURAN EMAS: DILARANG KERAS MENGUBAH PARAMETER SECARA "BLIND" (Tanpa Uji Coba)

**Jangan pernah melakukan *tweaking* atau pengubahan parameter langsung di lingkungan Live/Real tanpa pengujian komprehensif sebelumnya!**

Mengubah satu variabel sekecil apa pun (misalnya menurunkan `NEAR_SWEEP_THRESHOLD` dari 1.0 ke 0.5) dapat berdampak domino dan merusak seluruh rasio probabilitas (Win Rate) serta metrik *Profit Factor* strategi ini.

---

## 🧪 Siklus Pengujian yang Wajib Dilalui (Walk-Forward Testing)

Jika Anda ingin mencoba pengaturan agresif (misalnya preset `STRATEGY_PRESET=aggressive`), mengecilkan jarak *Stop Loss*, atau menambah indikator, Anda **WAJIB** mengikuti metodologi *Walk-Forward* berikut:

### 1. In-Sample Backtesting (Pengujian Masa Lalu)
Jalankan skrip *backtest* mandiri pada data masa lalu selama minimal 3 hingga 6 bulan.
```bash
python -m scripts.run_backtest --symbol XAUUSD --days 90
```
Tujuannya adalah melihat apakah parameter baru Anda mampu "bertahan hidup" (*survive*) menghadapi berbagai kondisi masa lalu (tren kuat, konsolidasi, berita *High-Impact*).
*Catat hasil: Win Rate, Profit Factor, dan Max Drawdown.*

### 2. Out-of-Sample Backtesting (Pengujian Validasi Masa Lalu)
Gunakan periode data yang **berbeda** (tidak disentuh saat uji coba langkah pertama). Misalnya, uji parameter tersebut pada data setahun sebelumnya. 
Jika *Win Rate* hancur di langkah ini, maka parameter Anda **Overfitted** (terlalu kaku dan hanya cocok di satu bulan spesifik). Hapus parameter tersebut dan ulangi *tuning*.

### 3. Forward Testing di Akun Demo (Inkubasi Wajib)
Jika backtest berhasil, jalankan bot dengan parameter baru tersebut **hanya di Akun Demo** selama minimal **1 Bulan Penuh**.
Langkah ini sangat penting untuk membuktikan apakah kalkulasi Anda tahan terhadap:
- Slippage mendadak.
- Pelebaran *spread* broker saat jeda sesi.
- *Execution delay*.

### 4. Evaluasi Menggunakan Machine Learning / AI
Setelah bot berjalan 1 bulan di akun Demo dan mengumpulkan setidaknya 100-200 riwayat *trade* di SQLite (`bot_database.db`), silakan jalankan:
```bash
python scripts/export_weekly_report.py
python scripts/analyze_with_gemini.py
```
Biarkan AI menganalisis secara luring (*offline*) apakah performa parameter Anda konsisten. Anda juga bisa melatih ulang model Machine Learning (`train_model.py`) dengan data parameter baru.

### 5. Deployment Terukur ke Live (Live Deployment)
Hanya jika semua langkah 1-4 menunjukkan *Profit Factor* positif, Anda diperbolehkan menerapkannya ke akun *Live*. Disarankan untuk menurunkan besaran risiko (*risk percent*) sebesar 50% selama minggu pertama *Live deployment*.

---

## 🔧 Komponen Parameter Utama

Beberapa area di `src/config.py` yang paling sensitif terhadap perubahan:

1. **`MIN_CONFLUENCE_SCORE`**: Mengontrol seberapa perfeksionis bot tersebut. Nilai 4/4 berarti jarang *entry* tapi probabilitas tinggi. Nilai 2/4 memicu *overtrading*.
2. **`SWEEP_LOOKBACK` & `NEAR_SWEEP_THRESHOLD`**: Menentukan jarak pantauan Swing High/Low. Jika *threshold* diubah, bot akan rentan mendeteksi *breakout* palsu.
3. **`MIN_RISK` & `MAX_RISK`**: Jangan diturunkan di bawah `$1.50` (15 Pips) untuk XAUUSD. Volatilitas *Gold* normal pasti akan menyentuh area ini dengan mudah.

***Kesimpulan:** Perlakukan setiap perubahan `config.py` seperti Anda merakit ulang mesin mobil balap. Uji di sirkuit simulasi sebelum membawanya ke jalan raya sesungguhnya.*
