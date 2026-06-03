# 🚨 Laporan Analisis: Evaluasi 6 Critical Issues

Berdasarkan pengecekan mendalam terhadap basis kode saat ini, saya mengonfirmasi bahwa **keenam masalah (issues) yang dilaporkan oleh model AI lain tersebut adalah BENAR (100% Valid)**. 

Berikut adalah rincian investigasi dan dampak dari setiap *issue* yang ditemukan pada proyek Anda:

---

## 1. [C1/C5] Timezone double-offset (Korupsi Sesi Killzone)
* **Lokasi File:** `src/backtest/backtest_engine.py` baris 195.
* **Analisis Kode:** `current_time = df_m5.iloc[i]["time"] + timedelta(hours=UTC_OFFSET)`
* **Fakta:** Waktu yang ditarik dari broker MT5 (misal Exness) biasanya sudah berada di zona waktu EET/EEST (UTC+2 atau UTC+3). Anda kemudian menambahkan `UTC_OFFSET` bernilai `7` (WIB). Ini berarti waktu *backtest* Anda bergeser menjadi UTC+9 / UTC+10!
* **Dampak Kritis:** Semua eksekusi *backtest* yang bergantung pada waktu (seperti filter sesi London/NY) salah total. Sinyal yang Anda kira terjadi di sesi "New York" di hasil *backtest*, sebenarnya terjadi di sesi London atau Asia.

## 2. [C2] Live bot tidak pernah memanggil `update_outcomes()`
* **Lokasi File:** `src/main.py` (Missing function call)
* **Analisis Kode:** Fungsi inti yang menggerakkan *live trading loop* di `main.py` terbukti tidak pernah mengimpor atau mengeksekusi `update_outcomes(df)` dari `outcome_tracker.py`.
* **Dampak Kritis:** Seluruh sinyal yang dieksekusi di bot *Live* akan tersimpan selamanya dalam status `PENDING` di *database* SQLite. Statistik *Win Rate* pada *dashboard* Anda tidak akan pernah bergerak untuk data *Live*.

## 3. [C3] Outcome tracker hanya membaca ujung ekor (last candle)
* **Lokasi File:** `src/risk/outcome_tracker.py` baris 93-94.
* **Analisis Kode:** 
  `current_high = df_trigger["high"].iloc[-1]`
  `current_low = df_trigger["low"].iloc[-1]`
* **Fakta:** Sistem *tracking* hanya mengecek harga tinggi/rendah pada *candle* iterasi terakhir detik ini.
* **Dampak Kritis:** Jika bot sempat terputus, atau interval *scan* telat, *candle-candle* perantara yang sempat menyentuh garis Target Profit (TP) atau Stop Loss (SL) akan diabaikan/terlewat. Sinyal akan dibiarkan "menggantung" tanpa batas waktu karena momen TP/SL tidak terekam.

## 4. [C4] Teks sinyal Telegram menipu (Hardcoded R:R)
* **Lokasi File:** `src/main.py` baris 326-327.
* **Analisis Kode:** Di dalam fungsi `build_signal_message()`, tertulis secara *hardcode* `rr1 = 2` dan `rr2 = 4`.
* **Fakta:** Di file `src/config.py` terbaru (Silver Bullet FVG), target sebenarnya adalah `TP1_MULTIPLIER = 1.0` (1R) dan `TP2_MULTIPLIER = 2.0` (2R).
* **Dampak Kritis:** Notifikasi Telegram akan mengirim pesan bahwa target adalah 2R/4R, padahal secara matematika harga yang dipatok untuk TP1 hanyalah sejauh 1R. Ini memberikan rasio palsu kepada *subscriber* atau *user* Telegram.

## 5. [C6] *Race condition* pada file gambar (Telegram)
* **Lokasi File:** `src/telegram/telegram_bot.py` baris 569-579.
* **Analisis Kode:** 
  ```python
  with open(photo_path, "rb") as f:
      coro = _bot_app.bot.send_photo(photo=f, ...)
      future = asyncio.run_coroutine_threadsafe(coro, _bot_loop)
  ```
* **Fakta:** Fungsi di atas mendelegasikan tugas pengiriman gambar ke *thread* `asyncio`. Namun, blok `with open(...)` segera selesai sedetik kemudian dan **menutup (close)** *file* gambar tersebut sementara *thread async* di latar belakang mungkin baru mulai membaca *byte* gambarnya.
* **Dampak Kritis:** Bot akan sering gagal memuat gambar (Chart) ke Telegram dengan error *I/O operation on closed file*. 

## 6. [W3] Ketidakcocokan Timeframe Backtest vs Live (M5 vs M15)
* **Lokasi File:** `src/backtest/backtest_engine.py` baris 234 vs `src/main.py` baris 501.
* **Analisis Kode:** 
  - Di **Backtest Engine**, `detect_fvg_retest(df_trigger)` dipanggil menggunakan *dataframe* `df_trigger` yang merupakan potongan dari M5 (5 Menit).
  - Di **Live Bot** (`main.py`), dipanggil `detect_fvg_retest(df_m15)` (15 Menit).
* **Dampak Kritis:** Ini malapetaka untuk optimasi strategi. Hasil performa gemilang yang didapatkan dari script *backtest* (`run_backtest.py`) sebenarnya dihasilkan dari *candle* 5 menit, sedangkan bot akan mengambil sinyal dari *candle* 15 menit saat dijalankan secara asli. Akibatnya, strategi yang Anda uji tidak ekuivalen dengan eksekusi nyatanya.

---

**Kesimpulan:**
Analisis dari AI tersebut sangat tajam dan akurat. Semua celah ini bersifat sangat kritikal karena memengaruhi data historis (*corrupted backtest*), *race condition*, dan inakurasi logika *real-time*.

*(Saya belum melakukan perbaikan apa pun sesuai dengan perintah Anda).*
