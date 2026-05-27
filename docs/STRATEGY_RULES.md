# 📖 Aturan Strategi XAUUSD ICT Bot

Dokumen ini menjelaskan secara rinci logika algoritmik di balik keputusan masuk (*entry*), keluar (*exit*), dan pengelolaan risiko (*risk management*) dari bot trading ini. Strategi utamanya didasarkan pada konsep **Inner Circle Trader (ICT)** yang dimodifikasi untuk menargetkan probabilitas tinggi pada komoditas XAUUSD (Gold).

---

## 🕒 Waktu Perdagangan (Killzone)

Bot hanya aktif berburu sinyal pada sesi waktu dengan volume dan likuiditas tinggi. Di luar waktu-waktu ini, bot akan "tidur" (Sleep) untuk menghindari pergerakan palsu atau pelebaran *spread* yang merugikan.

Zona waktu didasarkan pada **Waktu Indonesia Barat (WIB)**:
- **Sesi Asia**: 08:00 - 10:00 WIB (Sangat ideal untuk *Scalping* XAUUSD yang memantul di dalam *range*).
- **Sesi London**: 14:00 - 17:00 WIB (Ledakan likuiditas, seringkali menciptakan nilai tinggi/rendah harian).
- **Sesi New York**: 19:00 - 23:00 WIB (Volatilitas paling masif, pergerakan tren struktural).

**Aturan Gating:** Fitur agresif seperti **Near-Sweep** hanya diizinkan memicu eksekusi pada sesi London dan New York.

---

## ⚙️ Persyaratan Masuk Posisi (Entry Rules)

Sebelum mengeksekusi perdagangan, bot menghitung **Skor Konfluensi** (Maksimal 4 poin). Konfluensi dibangun dari:
1. Keselarasan Trend Utama (H4 Bias) = +1
2. Sapuan Likuiditas M15 (*Liquidity Sweep*) = +1
3. Struktur Konfirmasi M15 (*IFVG / Inversed FVG*) = +1
4. Konfirmasi *Candle Close* (Penolakan valid) = +1

### 📈 Syarat BUY (Long)
1. **Bias H4 (Trend dominan)**: Berada dalam keadaan `BULLISH` (Harga M15/H4 di atas Dual Moving Average).
2. **Liquidity Sweep**: Harus terjadi penyapuan likuiditas di bawah level **Swing Low (Dasar Harga)** terbaru (M15). Ini mengindikasikan bahwa _retail trader_ telah kehilangan posisi *stop-loss* mereka, memberikan likuiditas bagi institusi.
3. **Konfirmasi (IFVG)**: Pasca Sweep, harus terbentuk *Inversed Fair Value Gap* (IFVG) ke arah atas.
4. **Invalidasi**: Harga tidak boleh turun lebih jauh hingga memecah *Swing Low* absolut yang menjadi titik *sweep* awal (jika ya, struktur dianggap rusak / *Invalidated*).

### 📉 Syarat SELL (Short)
1. **Bias H4 (Trend dominan)**: Berada dalam keadaan `BEARISH` (Harga M15/H4 di bawah Dual Moving Average).
2. **Liquidity Sweep**: Harus terjadi penyapuan likuiditas di atas level **Swing High (Puncak Harga)** terbaru (M15). Institusi mengambil likuiditas *buy stop* milik publik sebelum membanting harga turun.
3. **Konfirmasi (IFVG)**: Pasca Sweep, harus terbentuk IFVG ke arah bawah sebagai sinyal momentum.
4. **Invalidasi**: Harga dilarang keras menembus ke atas pucuk absolut yang baru saja memanipulasi pasar.

---

## 📊 Kategori Sinyal (Tiers)

Berdasarkan kualitas konfluensi dan *setup*, sinyal dibagi menjadi dua kategori (Tiers):

### 1. Tier SWING (Confluence ≥ 3)
- **Ciri-ciri**: Setup dengan akurasi sangat tinggi dan selaras sempurna dengan tren arah H4.
- **Tujuan**: Menahan posisi (*Hold*) untuk mendapatkan rasio imbal hasil yang sangat masif.
- **Syarat Wajib**: Arah M15 wajib sama dengan H4 (Contoh: H4 Bullish + Sweep Bawah + IFVG Atas).

### 2. Tier SCALP (Confluence = 2)
- **Ciri-ciri**: *Counter-trend* (melawan tren utama) atau kondisi *sideways*.
- **Tujuan**: Keluar dan masuk pasar secara kilat mengambil keuntungan pendek tanpa berlama-lama.
- **Syarat Wajib**: Mendapatkan *Liquidity Sweep* + IFVG, tetapi tidak selaras dengan tren H4. (Contoh: H4 Bearish, tetapi muncul setup BUY di M15 akibat memantul di zona *support* kuat).

---

## 🛡️ Aturan Stop Loss (SL) & Take Profit (TP)

Modul `risk_manager.py` mengalkulasi level keluar pasar secara otomatis berdasarkan volatilitas (*ATR*) dan struktur harga (bukan pips statis).

### Perhitungan Stop Loss (SL)
- **BUY SL**: Ditempatkan sedikir di bawah *Wick Low* dari *candle* yang melakukan manipulasi *sweep*, lalu dikurangi nilai *Buffer* (`0.5`).
- **SELL SL**: Ditempatkan sedikit di atas *Wick High* dari *candle* yang melakukan manipulasi *sweep*, lalu ditambah nilai *Buffer* (`0.5`).
- **Validasi Minimum/Maksimum**: 
  - Jarak SL harus lebih besar dari **$1.50** (XAU) agar tidak mudah tersentuh (*noise spike*).
  - Jarak SL harus lebih kecil dari **$15.00** agar kerugian satu perdagangan (*risk per trade*) tidak terlalu melebar dari target *equity*.

### Perhitungan Take Profit (TP)
- **TP1 (Target Pertama)**: Berdasarkan kelipatan risiko (`SL Distance * 2R`). Pada tier SCALP, TP1 didiskon menjadi hanya `1.2R`.
- **TP2 (Target Maksimal)**: Berdasarkan kelipatan risiko eksponensial (`SL Distance * 4R`). Pada tier SCALP, TP2 menjadi hanya `2R`.
- Jika struktur pasar berdekatan (*Near Structure*), TP akan disesuaikan untuk diletakkan persis di *Swing High/Low* selanjutnya daripada mengandalkan nilai "R" secara kaku, guna memastikan probabilitas eksekusi tinggi.

---

## 🚫 Pembatalan Setup (Invalidation Rules)

Sebuah sinyal (meskipun memenuhi kriteria di atas) akan **DIBATALKAN** atau ditolak oleh bot jika:
1. **Premium/Discount Mismatch**: Mencoba BUY saat harga XAUUSD sedang berada di area sangat mahal (Zona *Premium*), atau mencoba SELL saat harga sedang sangat murah (Zona *Discount*).
2. **Struktur Rusak**: Sinyal muncul namun terdeteksi bahwa harga telah melebihi batas ekstrem *sweep* dari *candle* pemicu.
3. **Risiko Tidak Wajar**: Perhitungan matematis menunjukkan jarak antara entri ke SL berada di bawah `$1.50` (rentan) atau di atas `$15.00` (terlampau mematikan).
4. **Konfluensi Kurang**: Nilai Skor Konfluensi tidak memenuhi nilai yang diwajibkan oleh parameter `MIN_CONFLUENCE_SCORE` pada `STRATEGY_PRESET`.

---
*Dokumen ini merupakan panduan teori logika mesin bot. Pastikan untuk memahami parameter konfigurasi di `src/config.py` yang meregulasi seluruh sensitivitas aturan-aturan di atas.*
