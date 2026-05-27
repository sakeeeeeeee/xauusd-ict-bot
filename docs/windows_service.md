# Menjalankan Bot XAUUSD via Windows Task Scheduler

Dokumen ini menjelaskan cara mengatur bot agar berjalan otomatis setiap kali VPS/Windows Server direstart (Startup) menggunakan **Windows Task Scheduler**.

## Keuntungan Menggunakan Task Scheduler
- **Auto-Start**: Bot otomatis jalan saat server reboot tanpa perlu login manual.
- **Restart on Failure**: Jika bot crash, Task Scheduler bisa diatur untuk otomatis menjalankannya kembali.
- **Background Process**: Berjalan di background tanpa jendela CMD yang mengganggu (opsional).

---

## Langkah 1: Buat Script Launcher (`run_bot.bat`)

Karena kita menggunakan Virtual Environment (venv) dan working directory spesifik, kita perlu membuat file `.bat` kecil sebagai launcher.

1. Buka folder root project bot Anda (misal: `C:\Users\Hp\Documents\UPB\vscode\mt5`)
2. Buat file baru bernama `run_bot.bat`
3. Isi dengan kode berikut:

```bat
@echo off
cd /d "C:\Users\Hp\Documents\UPB\vscode\mt5"
call .venv\Scripts\activate.bat
python scripts\watchdog.py
```

*(Catatan: Sesuaikan path `C:\Users\Hp\Documents\UPB\vscode\mt5` dengan lokasi instalasi bot Anda dan pastikan nama folder venv Anda benar, misal `.venv` atau `venv`)*

---

## Langkah 2: Setup Windows Task Scheduler

1. Buka Start Menu, ketik **Task Scheduler**, lalu tekan Enter.
2. Di panel kanan (Actions), klik **Create Task...** (Jangan pilih Basic Task).

### Tab "General"
- **Name**: `XAUUSD_ICT_Bot`
- **Description**: Bot Trading MT5
- Centang **Run whether user is logged on or not** (Ini penting agar bot jalan sebelum Anda RDP/login).
- Centang **Run with highest privileges**.
- *Optional*: Ubah "Configure for" menjadi Windows 10 / Windows Server 2016.

### Tab "Triggers"
- Klik **New...**
- Begin the task: Pilih **At startup**.
- Pastikan "Enabled" dicentang.
- Klik **OK**.

### Tab "Actions"
- Klik **New...**
- Action: Pilih **Start a program**.
- **Program/script**: Klik Browse, lalu pilih file `run_bot.bat` yang kita buat di Langkah 1 (contoh: `C:\Users\Hp\Documents\UPB\vscode\mt5\run_bot.bat`).
- **Start in (optional)**: Isi dengan path folder bot Anda (SANGAT PENTING untuk load file `.env` dan `config`).
  Contoh: `C:\Users\Hp\Documents\UPB\vscode\mt5\` (pastikan ada backslash di akhir, atau setidaknya tidak pakai tanda kutip).
- Klik **OK**.

### Tab "Conditions"
- **Uncheck** "Start the task only if the computer is on AC power" (Jika pakai laptop/VPS, pastikan tidak bergantung pada baterai).
- **Uncheck** "Stop if the computer switches to battery power".

### Tab "Settings" (Penting untuk Restart on Failure)
- Centang **Allow task to be run on demand**.
- Centang **Run task as soon as possible after a scheduled start is missed**.
- Centang **If the task fails, restart every:** 
  - Pilih **1 minute**.
  - Attempt to restart up to: **999 times**.
- Hilangkan centang pada **Stop the task if it runs longer than**. (Bot kita harus jalan 24/5 tanpa batas waktu).
- If the running task does not end when requested, force it to stop: Centang.
- Di bagian bawah, pastikan pilihan dropdown adalah: **Do not start a new instance** (agar bot tidak berjalan dobel).

---

## Langkah 3: Simpan dan Uji Coba

1. Klik **OK** pada jendela Create Task.
2. Windows akan meminta Anda memasukkan **Password** dari user Windows tersebut. Masukkan password Anda (ini agar Task Scheduler bisa run task di background).
3. Setelah tersimpan, cari task `XAUUSD_ICT_Bot` di daftar Task Scheduler Library.
4. Klik kanan pada task tersebut, pilih **Run**.

### Cara Mengecek Apakah Bot Berjalan:
- Cek pesan di Telegram. Seharusnya ada pesan "🟢 BOT XAUUSD ONLINE" atau Health Ping.
- Buka Task Manager (Ctrl+Shift+Esc), cari proses bernama `python.exe` atau `terminal64.exe`.
- Cek file log `bot_xauusd.log` di folder bot. Seharusnya ada log baru yang tertulis.

---

## Tips Tambahan
- **MetaTrader 5 Auto-Start**: Bot ICT ini sudah memiliki `initialize_mt5_robust()` yang akan otomatis membuka MT5 di background. Jadi Anda **tidak perlu** menjadwalkan MT5 secara terpisah di Task Scheduler.
- **Menghentikan Bot**: Jika Anda perlu mematikan bot secara paksa, buka Task Scheduler, klik kanan task `XAUUSD_ICT_Bot`, lalu pilih **End**.
- **Mengubah Kode**: Jika Anda mengedit `main.py` atau `config.py`, klik kanan task di Task Scheduler lalu pilih **End**, kemudian pilih **Run** untuk merestart bot agar perubahan diterapkan.

## Mengapa menggunakan `watchdog.py`?
Alih-alih menjalankan `python -m src.main` secara langsung, kita menjalankan `python scripts\watchdog.py`. Watchdog adalah script kecil yang bertugas mengawasi proses utama bot. Jika bot crash (misalnya karena terputus koneksi API tak terduga atau kehabisan memori), Watchdog akan:
1. Menangkap error tersebut.
2. Mencatat di file `watchdog.log`.
3. Menunggu 10 detik.
4. Otomatis menjalankan ulang `main.py`.

Hal ini memberikan layer proteksi ganda: **Task Scheduler** memastikan script jalan saat server reboot, dan **Watchdog** memastikan script tetap hidup meskipun terjadi crash aplikasi (tanpa bergantung penuh pada fitur restart Task Scheduler yang terkadang lambat/bermasalah).

