# -*- coding: utf-8 -*-
"""Konten lengkap panduan upgrade - dipakai generate_upgrade_docs.py"""

CONTEXT_PROMPT = """Kamu mengupgrade proyek Python "XAUUSD ICT Signal Bot" di Windows.
Stack: MetaTrader5, pandas, python-telegram-bot, requests, dotenv.
Struktur: src/ (main, config, analysis, risk, telegram, mt5), scripts/, tests/, run.py.
Bot: scan M15/H4 (atau M5 jika sudah ditambah), sweep/IFVG, killzone WIB, confluence, Telegram, bot_state + thread polling.
Jangan commit secret. Ikuti konvensi kode yang ada. Minimalkan scope per task."""

PHASE_BATCH_PROMPTS = [
    ("FASE 1 - P0 + fondasi minimal", """Kerjakan berurutan:
A1-A6 keamanan (hapus cek_emas.py, .env.example, README keamanan)
B2 validasi startup, B3 rotating log, B7 fix doc confluence, E1 outcome tracking trade_history, E2 schema log v2
Jangan refactor folder besar dulu. Berikan ringkasan file yang diubah."""),
    ("FASE 2 - Win rate + frekuensi", """Kerjakan: C1-C4, C6, D1-D2, D6-D7, H1, E7 stats Telegram.
Dual tier SCALP/SWING, watchlist terpisah, IFVG setelah sweep, RANGING no point untuk SWING."""),
    ("FASE 3 - Struktur & ukur", """Kerjakan: B1 struktur src/, B8 pytest, C5 C7-C9 C12, D3 M5 trigger, E3-E5 backtest, K1 preset, K2 strategy doc."""),
    ("FASE 4 - ML & produksi", """Kerjakan: F2-F7 ML filter opsional, G1-G2 signal only mode, H2-H5, I1-I5, J1-J7, B4 B5 B6 B9 B10."""),
]

ITEM_PROMPTS = [
    # A
    ("A1", "Keamanan - hapus cek_emas.py", "Hapus atau pindahkan file cek_emas.py ke folder archive/ karena berisi Telegram TOKEN dan CHAT_ID hardcoded. Pastikan tidak ada secret lain di repo. Update README jika file itu pernah disebut."),
    ("A2", "Keamanan - revoke token", "Dokumentasikan di README bahwa user harus revoke token Telegram di BotFather dan buat token baru jika cek_emas.py pernah ter-commit atau dibagikan. Jangan simpan token di kode."),
    ("A3", "Keamanan - .env only", "Pastikan semua credential hanya dari .env: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID. Tambah placeholder opsional GEMINI_API_KEY di .env.example. Validasi di startup jika kosong."),
    ("A4", "Keamanan - .env.example", "Buat file .env.example dengan key yang dibutuhkan bot tanpa nilai rahasia, plus komentar singkat tiap variabel."),
    ("A5", "Keamanan - audit git", "Buat section README Keamanan yang menjelaskan cara audit git history untuk secret (git log -p) dan langkah jika token bocor."),
    ("A6", "Keamanan - .gitignore", "Verifikasi .gitignore mencakup .env, *.log, trade_history.json, __pycache__, venv. Jangan ubah jika sudah benar."),
    # B
    ("B1", "Engineering - struktur folder", "Refactor struktur proyek XAUUSD ICT bot menjadi: src/ dengan analysis/, risk/, telegram/, mt5/, main.py, config.py; scripts/ untuk debug; tests/. Buat run.py di root sebagai entry point. Update import dan README. Pastikan python run.py masih jalan."),
    ("B2", "Engineering - validasi startup", "Tambah fungsi validate_startup() sebelum loop: cek TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID ada, mt5.initialize() sukses, symbol XAUUSD tersedia. Log error jelas dan exit jika gagal."),
    ("B3", "Engineering - rotating log", "Ganti FileHandler logging dengan RotatingFileHandler (maxBytes 5MB, backupCount 5) untuk bot_xauusd.log. Pertahankan console handler INFO."),
    ("B4", "Engineering - pin versi", "Pin versi semua dependency di requirements.txt dengan versi stabil kompatibel Python 3.10-3.11."),
    ("B5", "Engineering - thread lock", "Tambah threading.Lock untuk akses bot_state di main dan telegram_bot. Semua read/write bot_state lewat helper dengan lock."),
    ("B6", "Engineering - satukan Telegram", "Satukan pengiriman pesan Telegram ke satu jalur. Hindari duplikasi logic requests.post terpisah kecuali fallback terdokumentasi."),
    ("B7", "Engineering - fix doc confluence", "Perbaiki inkonsistensi: main.py header vs config MIN_CONFLUENCE_SCORE. Samakan docstring, README, dan config."),
    ("B8", "Engineering - pytest", "Tambah pytest di tests/: unit test detect_sweep, detect_ifvg, calculate_confluence, calculate_sl_tp, validate_risk dengan DataFrame fixture. Tanpa MT5 live."),
    ("B9", "Engineering - ruff", "Tambah konfigurasi ruff dan jalankan lint pada modul utama tanpa ubah logika trading."),
    ("B10", "Engineering - CLI diagnose", "Buat CLI tunggal scripts/diagnose.py dengan opsi --mt5, --signal, --arah. Pindahkan debug ke scripts/ dan update README."),
    # C
    ("C1", "Trading WR - confluence SWING", "Set MIN_CONFLUENCE_SCORE default 3 untuk tier SWING. Di main hanya kirim sinyal SWING jika confluence >= 3. Dokumentasikan di README."),
    ("C2", "Trading WR - RANGING no point", "Ubah calculate_confluence: untuk SWING, bias RANGING tidak mendapat poin. Hanya BULLISH untuk BUY dan BEARISH untuk SELL."),
    ("C3", "Trading WR - near-sweep", "Tambah NEAR_SWEEP_ENABLED=false default. Jika true, near-sweep hanya di London/NY killzone dan bias H4 searah."),
    ("C4", "Trading WR - IFVG setelah sweep", "Ubah detect_ifvg: IFVG valid hanya dalam 5 candle setelah candle sweep. IFVG harus searah sweep."),
    ("C5", "Trading WR - premium/discount", "Tambah detect_premium_discount(df_h4). BUY hanya discount, SELL hanya premium. Integrasikan ke main sebelum SWING."),
    ("C6", "Trading WR - invalidation", "Tambah check_invalidation: untuk BUY jika close di bawah extreme sweep, skip. Mirror untuk SELL. Log alasan."),
    ("C7", "Trading WR - TP struktural", "Tambah calculate_tp_structural: TP1 ke swing terdekat, fallback 2R jika terlalu dekat."),
    ("C8", "Trading WR - minimum RR", "Sebelum kirim sinyal, hitung RR ke TP1. Jika RR < MIN_RR (default 1.5), skip dan log."),
    ("C9", "Trading WR - ATR SL", "Tambah get_atr. SL buffer dan validate_risk gunakan kelipatan ATR dengan fallback MIN/MAX_RISK USD."),
    ("C10", "Trading WR - filter spread", "Baca spread dari symbol_info_tick. Jika spread > MAX_SPREAD, skip sinyal."),
    ("C11", "Trading WR - filter news", "Tambah NEWS_BLACKOUT_MINUTES dan list waktu manual. Skip entry dalam blackout."),
    ("C12", "Trading WR - struktur H4", "Tambah detect_h4_structure HH/HL atau LH/LL. SWING BUY hanya bullish/netral, SELL bearish/netral."),
    # D
    ("D1", "Frekuensi - watchlist", "Pisahkan watchlist dari entry: confluence >= 2 kirim pesan WATCH max 1x per candle M15. Entry SWING confluence >= 3."),
    ("D2", "Frekuensi - dual tier", "Implement dual tier SCALP (confluence 2 ketat, TP1 1.2R) dan SWING (confluence 3, TP 2R/4R). Prefix pesan berbeda."),
    ("D3", "Frekuensi - trigger M5", "Tambah analisis M5 untuk sweep/IFVG, bias tetap H4. Config USE_M5_TRIGGER=true."),
    ("D4", "Frekuensi - scan interval", "SCAN_INTERVAL 15 detik di killzone, 60 detik di luar. Config terpisah."),
    ("D5", "Frekuensi - re-entry", "Cooldown 15 menit per arah setelah sinyal, kecuali extreme price baru."),
    ("D6", "Frekuensi - aturan sesi", "Asia: watchlist+scalp only. London/NY: SWING+SCALP."),
    ("D7", "Frekuensi - command /watch", "Tambah command Telegram /watch untuk setup forming dari bot_state."),
    # E
    ("E1", "Data - outcome tracking", "Loop cek harga MT5, update trade_history result: WIN_TP1, WIN_TP2, LOSS, EXPIRED."),
    ("E2", "Data - schema v2", "Perluas log: near_sweep, killzone, tier, session, atr, spread. Migrasi backward compatible."),
    ("E3", "Data - backtest engine", "Buat backtest_engine.py replay rules candle by candle dari MT5 atau CSV."),
    ("E4", "Data - metrik backtest", "Hitung win rate, profit factor, avg R, max drawdown, breakdown per tier."),
    ("E5", "Data - walk-forward", "Walk-forward: train periode A, test periode B. CLI tanggal."),
    ("E6", "Data - laporan mingguan", "Script export_weekly_report.py CSV/HTML dari trade_history."),
    ("E7", "Data - stats Telegram", "Upgrade /stats: win rate, profit factor, avg R dari trade berlabel."),
    # F
    ("F1", "AI - no LLM di loop", "Jangan integrasikan Gemini di loop scanning tiap 15-30 detik. Dokumentasikan di README."),
    ("F2", "AI - min trades ML", "Tambah MIN_TRADES_FOR_ML=200. train_model.py exit jelas jika data kurang."),
    ("F3", "AI - ML lokal", "Buat ml_filter.py train XGBoost/sklearn dari fitur trade_history, label win=TP1 sebelum SL, simpan model.pkl."),
    ("F4", "AI - toggle ML filter", "USE_ML_FILTER dan ML_THRESHOLD di config. Skip sinyal jika P(win) < threshold."),
    ("F5", "AI - Gemini offline", "Script analyze_with_gemini.py ringkasan trade_history mingguan. GEMINI_API_KEY dari .env. Manual saja."),
    ("F6", "AI - train_model CLI", "python train_model.py --history trade_history.json --out model.pkl. Log precision/recall holdout."),
    ("F7", "AI - dokumentasi", "README section AI: rule generate setup, ML filter opsional, Gemini analisis offline."),
    # G
    ("G1", "Risk - percent equity", "Opsi RISK_PERCENT hitung lot suggestion dari equity. Tampilkan di Telegram jika SIGNAL_ONLY."),
    ("G2", "Risk - trading mode", "TRADING_MODE=SIGNAL_ONLY|AUTO_TRADE default signal only."),
    ("G3", "Risk - validasi order", "AUTO_TRADE: validasi margin, max positions, slippage sebelum order_send."),
    ("G4", "Risk - breakeven", "AUTO_TRADE: pindah SL ke BE setelah TP1."),
    ("G5", "Risk - partial close", "AUTO_TRADE: close 50% di TP1, sisanya TP2."),
    # H
    ("H1", "Telegram - prefix tier", "Standardkan prefix WATCH, SCALP ENTRY, SWING ENTRY."),
    ("H2", "Telegram - chart", "generate_chart.png matplotlib M15 + entry SL TP, kirim photo Telegram. CHART_ENABLED config."),
    ("H3", "Telegram - commands", "Tambah /lastsignal /performance /why dari bot_state."),
    ("H4", "Telegram - health ping", "Health ping tiap 6 jam: MT5, last scan, uptime."),
    ("H5", "Telegram - disconnect alert", "Alert jika MT5 disconnect > 5 menit."),
    # I
    ("I1", "MT5 - auto path", "Startup coba path terminal64.exe umum jika initialize gagal."),
    ("I2", "MT5 - trading hours", "is_market_open cek session symbol MT5 selain weekend."),
    ("I3", "MT5 - multi symbol", "SYMBOLS list loop scan per symbol jika enabled."),
    ("I4", "MT5 - aliases", "SYMBOL_ALIASES map suffix broker."),
    ("I5", "MT5 - reconnect backoff", "Reconnect exponential backoff max 5 menit."),
    # J
    ("J1", "Produksi - Task Scheduler", "docs/windows_service.md untuk Task Scheduler at startup."),
    ("J2", "Produksi - watchdog", "scripts/watchdog.py restart main.py jika exit."),
    ("J3", "Produksi - SQLite", "Migrasi trade_history ke SQLite db.py."),
    ("J4", "Produksi - dashboard", "Streamlit dashboard win rate per minggu."),
    ("J5", "Produksi - CI", "GitHub Actions ruff pytest tanpa MT5 di CI."),
    ("J6", "Produksi - README", "Update README arsitektur dual tier, backtest, ML, disclaimer."),
    ("J7", "Produksi - CHANGELOG", "CHANGELOG.md Keep a Changelog per versi strategi."),
    # K
    ("K1", "Strategi - preset", "STRATEGY_PRESET conservative|balanced|aggressive load subset parameter."),
    ("K2", "Strategi - rules doc", "docs/STRATEGY_RULES.md syarat BUY/SELL SWING dan SCALP bahasa Indonesia."),
    ("K3", "Strategi - disclaimer", "Perkuat disclaimer demo vs live di README."),
    ("K4", "Strategi - tuning doc", "docs/PARAMETER_TUNING.md: ubah parameter hanya lewat backtest."),
    # L
    ("L1", "File - cek_emas", "Hapus atau archive/legacy_cek_emas.py dengan banner WARNING."),
    ("L2", "File - config validasi", "config pydantic-settings validasi MIN_RISK < MAX_RISK, enum modes."),
    ("L3", "File - SignalEngine", "Refactor main.py class SignalEngine scan should_enter send_signal."),
    ("L4", "File - split analysis", "Split analysis ke bias.py sweep.py ifvg.py confluence.py atr.py."),
    ("L5", "File - risk extend", "risk_manager structural TP ATR outcome hook schema v2."),
    ("L6", "File - telegram extend", "telegram tier commands chart thread-safe bot_state."),
    ("L7", "File - sample history", "docs/sample_trade_history.json schema v2."),
    ("L8", "File - requirements extras", "requirements extras [ml] [gemini] [dev]."),
    ("L9", "File - scripts imports", "debug di scripts/ import dari src perbaiki README."),
]

def build_sections():
    sections = []

    sections.append(("RINGKASAN EKSEKUTIF", 1, [
        "Dokumen VERSI LENGKAP - semua saran upgrade, penjelasan strategi, dan prompt siap copas untuk model AI lain.",
        "Proyek: XAUUSD ICT Signal Bot - Python, MetaTrader 5, Telegram.",
        "Tujuan: win rate tinggi + update sering (watchlist + dual tier) + fondasi ML opsional.",
    ]))

    sections.append(("HASIL AUDIT AWAL (RINGKAS)", 2, [
        "Kekuatan: pipeline ICT jelas, near-sweep, self-correcting SL, anti-spam per candle, Telegram interaktif, config terpusat.",
        "Masalah kritis: cek_emas.py token hardcoded; trade_history result selalu PENDING; doc confluence 3 vs config 2; bot_state tanpa lock; near-sweep agresif menurunkan WR; IFVG independen dari sweep.",
    ]))

    sections.append(("LEGENDA PRIORITAS", 2, [
        "P0 = segera (keamanan, fondasi). P1 = dampak besar trading. P2 = ML, produksi, UX. P3 = jangka panjang.",
    ]))

    # Master list with fuller descriptions
    groups = [
        ("A. KEAMANAN & KEBERSIHAN REPO (P0)", [
            "A1: Hapus/archive cek_emas.py - token Telegram hardcoded.",
            "A2: Revoke token BotFather jika pernah ter-commit.",
            "A3: Credential hanya .env + validasi startup.",
            "A4: Buat .env.example.",
            "A5: README section audit git history.",
            "A6: Verifikasi .gitignore lengkap.",
        ]),
        ("B. FONDASI ENGINEERING (P0-P1)", [
            "B1: Struktur src/scripts/tests + run.py (modular, bukan flat).",
            "B2: validate_startup .env MT5 symbol.",
            "B3: RotatingFileHandler log.",
            "B4: Pin versi dependencies.",
            "B5: threading.Lock bot_state.",
            "B6: Satukan kirim Telegram.",
            "B7: Fix inkonsistensi doc confluence.",
            "B8: pytest unit tests.",
            "B9: ruff formatter.",
            "B10: CLI diagnose tunggal.",
        ]),
        ("C. TRADING - KUALITAS & WIN RATE (P1)", [
            "C1: MIN_CONFLUENCE 3 untuk SWING.",
            "C2: RANGING tanpa poin SWING.",
            "C3: Batasi near-sweep.",
            "C4: IFVG setelah sweep.",
            "C5: Premium/discount H4.",
            "C6: Invalidation setup.",
            "C7: TP struktural.",
            "C8: Minimum RR.",
            "C9: ATR untuk SL/risk.",
            "C10: Filter spread.",
            "C11: Filter news blackout.",
            "C12: Struktur HH/HL H4.",
        ]),
        ("D. TRADING - FREKUENSI & UPDATE (P1)", [
            "D1: Watchlist vs entry terpisah.",
            "D2: Dual tier SCALP vs SWING.",
            "D3: Trigger M5 + bias H4.",
            "D4: Scan 15s killzone / 60s luar.",
            "D5: Re-entry cooldown 15 menit.",
            "D6: Asia watchlist/scalp; London/NY full.",
            "D7: Command /watch.",
        ]),
        ("E. DATA, TRACKING & BACKTEST (P1)", [
            "E1: Outcome tracking WIN/LOSS.",
            "E2: Schema log v2.",
            "E3: Backtest engine.",
            "E4: Metrik WR PF DD.",
            "E5: Walk-forward.",
            "E6: Laporan mingguan.",
            "E7: Stats Telegram lengkap.",
        ]),
        ("F. AI / ML (P2)", [
            "F1: Jangan LLM di loop scan.",
            "F2: Min 200 trade berlabel.",
            "F3: ML lokal XGBoost/sklearn.",
            "F4: USE_ML_FILTER threshold.",
            "F5: Gemini analisis offline mingguan.",
            "F6: train_model.py -> model.pkl.",
            "F7: Dokumentasi arsitektur AI.",
        ]),
        ("G. RISK & EKSEKUSI (P2)", [
            "G1: Risk % equity.",
            "G2: SIGNAL_ONLY vs AUTO_TRADE.",
            "G3: Validasi margin/slippage.",
            "G4: Breakeven setelah TP1.",
            "G5: Partial close 50%.",
        ]),
        ("H. TELEGRAM & UX (P2)", [
            "H1: Prefix WATCH/SCALP/SWING.",
            "H2: Chart screenshot.",
            "H3: /lastsignal /performance /why.",
            "H4: Health ping 6 jam.",
            "H5: Alert disconnect MT5.",
        ]),
        ("I. MT5 & MARKET (P2)", [
            "I1: Auto-detect terminal path.",
            "I2: Trading hours symbol.",
            "I3: Multi-symbol.",
            "I4: Symbol aliases broker.",
            "I5: Reconnect backoff.",
        ]),
        ("J. PRODUKSI & OPERASIONAL (P2-P3)", [
            "J1: Windows Task Scheduler.",
            "J2: Watchdog restart.",
            "J3: SQLite.",
            "J4: Dashboard Streamlit.",
            "J5: GitHub Actions CI.",
            "J6: README lengkap.",
            "J7: CHANGELOG.",
        ]),
        ("K. STRATEGI & DOKUMENTASI (P2)", [
            "K1: Preset conservative/balanced/aggressive.",
            "K2: STRATEGY_RULES.md.",
            "K3: Disclaimer demo/live.",
            "K4: PARAMETER_TUNING.md.",
        ]),
        ("L. FILE SPESIFIK (P0-P1)", [
            "L1: Hapus cek_emas.",
            "L2: Config validasi pydantic.",
            "L3: Class SignalEngine.",
            "L4: Split analysis modules.",
            "L5: Extend risk_manager.",
            "L6: Extend telegram_bot.",
            "L7: Sample trade_history v2.",
            "L8: Requirements extras.",
            "L9: Scripts import src.",
        ]),
    ]
    for title, items in groups:
        lines = [("bullet", x) for x in items]
        sections.append((title, 1, lines))

    sections.append(("ROADMAP IMPLEMENTASI", 1, [
        "Fase 1 (minggu 1): A1-A6, B2, B3, B7, E1, E2.",
        "Fase 2 (minggu 2-3): C1-C4, C6, D1-D2, D6-D7, H1, E7.",
        "Fase 3 (minggu 4-6): B1, B8, C5-C12, D3-D6, E3-E5, K1-K2.",
        "Fase 4 (bulan 2+): F, G, H, I, J.",
        "Fase 5 (opsional): auto-trade, dashboard, multi-symbol.",
    ]))

    sections.append(("QUICK WINS", 2, []))
    for q in [
        "1. Hapus cek_emas.py + rotate token.",
        "2. Outcome tracking trade_history.",
        "3. MIN_CONFLUENCE=3, RANGING no point SWING.",
        "4. Watchlist Telegram.",
        "5. Dual tier SCALP/SWING.",
        "6. Matikan atau batasi near-sweep.",
    ]:
        sections[-1][2].append(("bullet", q))

    sections.append(("WIN RATE VS FREKUENSI (PENJELASAN)", 2, [
        "Sering sinyal dan WR tinggi tidak eksklusif jika dipisah: watchlist sering update; entry SWING ketat; SCALP TP kecil 1-1.2R (WR statistik lebih tinggi).",
        "Jangan longgarkan semua filter sekaligus. Ukur dengan backtest tiap perubahan.",
        "Near-sweep dan MIN_CONFLUENCE=2 menambah sinyal tapi menurunkan WR.",
    ]))

    sections.append(("AI GOOGLE GEMINI (PENJELASAN)", 2, [
        "API Gemini gratis = inference/analisis, BUKAN training model trading seperti ML klasik.",
        "Fine-tune permanen dari trade_history kecil tidak realistis di tier gratis.",
        "Alur disarankan: label WIN/LOSS -> 200+ trade -> train ML lokal (XGBoost) -> filter live -> Gemini opsional laporan mingguan.",
        "Jangan panggil Gemini tiap 15-30 detik di loop bot (quota, latency, tidak deterministik).",
    ]))

    sections.append(("REFACTOR B1 - STRUKTUR FOLDER (PENJELASAN)", 2, [
        "Maksud: pindah kode ke src/, debug ke scripts/, tests/, jalankan python run.py, hapus duplikat root setelah tes.",
        "Bukan ubah strategi ICT - hanya organisasi file dan import.",
        "Setelah Proceed: tes run.py, diagnose, .env di root, update Task Scheduler ke run.py.",
    ]))

    sections.append(("ESTIMASI EFFORT", 2, [
        "Fase 1: 3-5 hari - keamanan, stabilitas.",
        "Fase 2: 2-3 minggu - WR + watchlist + dual tier.",
        "Fase 3: 3-6 minggu - backtest, M5, struktur.",
        "Fase 4: 1-2 bulan - ML, produksi.",
    ]))

    sections.append(("MATRIKS TUJUAN", 2, [
        "Win rate naik: C1-C12, E1-E5, F3 (nanti).",
        "Sinyal tidak terasa jarang: D1-D7 watchlist + dual tier + M5.",
        "AI masuk akal: F setelah E1 + 200 trade.",
        "Bot stabil: A, B, I, J1-J2.",
        "Terukur: E3-E7 backtest.",
    ]))

    sections.append(("PENAFIAN", 2, [
        "Software edukasi dan informasi sinyal. Trading riil risiko pengguna. Wajib demo dan backtest sebelum live.",
    ]))

    return sections


def build_prompt_sections():
    """Sections khusus lampiran prompt lengkap."""
    sections = []
    sections.append(("LAMPIRAN A: KONTEKS PROMPT (COPAS SEKALI)", 1, [
        "Copas blok berikut di awal chat model AI lain sebelum prompt per item:",
        CONTEXT_PROMPT,
    ]))
    sections.append(("LAMPIRAN B: PROMPT BATCH PER FASE", 1, [
        "Tambahkan di akhir tiap batch: Lakukan hanya item ini. List file yang diubah.",
    ]))
    for name, prompt in PHASE_BATCH_PROMPTS:
        sections[-1][2].append((f"prompt_{name}", f"[{name}]\n{prompt}"))

    sections.append(("LAMPIRAN C: SEMUA PROMPT PER ITEM (A1-L9)", 1, [
        "Satu prompt per item. Tambahkan: Lakukan hanya item ini. Jangan ubah file lain. List file yang diubah setelah selesai.",
    ]))
    current_group = None
    for code, title, prompt in ITEM_PROMPTS:
        group = code[0]
        if group != current_group:
            current_group = group
        sections[-1][2].append((f"prompt_{code}", f"[{code}] {title}\n\n{prompt}"))
    return sections
