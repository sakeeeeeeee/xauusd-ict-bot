"""
run.py — Entry point untuk menjalankan XAUUSD ICT Bot
Jalankan: python run.py
Validasi cepat: python run.py validate
"""

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="XAUUSD ICT Bot runner (run/validate).",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("run", help="Jalankan bot (default).")
    sub.add_parser(
        "validate",
        help="Cek .env + MT5 + symbol tanpa menjalankan loop bot.",
    )

    args = parser.parse_args(argv)
    cmd = args.cmd or "run"

    if cmd == "validate":
        from src.main import setup_logging, validate_startup
        import MetaTrader5 as mt5

        logger = setup_logging()
        ok = validate_startup(logger)
        mt5.shutdown()
        return 0 if ok else 1

    from src.main import run_engine

    run_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
