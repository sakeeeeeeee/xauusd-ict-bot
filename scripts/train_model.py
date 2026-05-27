"""
train_model.py — Placeholder script untuk melatih model Machine Learning.
Hanya akan dieksekusi jika data histori trade yang terlabel (resolved)
telah memenuhi ambang batas minimal untuk mencegah overfitting model pada data yang terlalu sedikit.
"""

# ruff: noqa: E402

import sys
import logging
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.config import MIN_TRADES_FOR_ML
from src.database.db import get_all_trades

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ml_trainer")


def load_history(filepath: str) -> list:
    """
    Load data trade history dari SQLite (mengabaikan filepath arg).
    """
    try:
        trades = get_all_trades()
        # Saring hanya trade yang memiliki label (bukan PENDING/EXPIRED)
        resolved = [
            t for t in trades if t.get("result") in ["WIN_TP1", "WIN_TP2", "LOSS"]
        ]
        return resolved
    except Exception as e:
        logger.error(f"Gagal membaca history dari DB: {e}")
        return []


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ML Model Trainer for XAUUSD ICT Bot")
    parser.add_argument(
        "--history",
        type=str,
        default="bot_database.db",
        help="Ignored. Now uses SQLite DB.",
    )
    parser.add_argument(
        "--out", type=str, default="model.pkl", help="Path to save the output model.pkl"
    )
    args = parser.parse_args()

    logger.info("====================================")
    logger.info("       ML MODEL TRAINER PREP        ")
    logger.info("====================================")

    history_file = Path(args.history)

    trades = load_history(str(history_file))
    total_resolved = len(trades)

    logger.info(f"Source History      : {history_file}")
    logger.info(f"Target Output Model : {args.out}")
    logger.info(f"Target Minimum Data : {MIN_TRADES_FOR_ML} trades")
    logger.info(f"Data Berlabel Tersedia: {total_resolved} trades")
    logger.info("------------------------------------")

    if total_resolved < MIN_TRADES_FOR_ML:
        logger.warning(
            f"ABORT: Jumlah data trade terselesaikan ({total_resolved}) masih "
            f"berada di bawah batas minimum yang diwajibkan ({MIN_TRADES_FOR_ML}).\n"
            "Mengapa? Melatih model ML dengan data <200 akan menyebabkan OVERFITTING parah.\n"
            "Biarkan bot terus berjalan untuk mengumpulkan lebih banyak dataset riil."
        )
        sys.exit(1)

    logger.info("SUCCESS: Data mencukupi! Memulai pelatihan Logistic Regression...")

    import pandas as pd
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler, OneHotEncoder
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, roc_auc_score
    import joblib

    df = pd.DataFrame(trades)

    # 1. Feature Engineering
    # Features required: confluence, bias, tier, session, risk, near_sweep
    # Label: win=TP1/TP2 -> 1, LOSS -> 0
    df["label"] = df["result"].apply(lambda x: 1 if "WIN" in x else 0)
    df["near_sweep"] = df["near_sweep"].astype(int)

    X = df[["confluence_score", "bias", "tier", "session", "risk", "near_sweep"]].copy()
    y = df["label"]

    # Fill missing values for robustness
    X["bias"] = X["bias"].fillna("UNKNOWN")
    X["tier"] = X["tier"].fillna("UNKNOWN")
    X["session"] = X["session"].fillna("UNKNOWN")
    X["risk"] = X["risk"].fillna(0.0)
    X["confluence_score"] = X["confluence_score"].fillna(0)

    # 2. Preprocessing Pipeline
    numeric_features = ["confluence_score", "risk", "near_sweep"]
    categorical_features = ["bias", "tier", "session"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
        ]
    )

    # 3. Model Pipeline
    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced", random_state=42, max_iter=1000
                ),
            ),
        ]
    )

    # 4. Train-Test Split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 5. Train Model
    model.fit(X_train, y_train)

    # 6. Evaluate Model
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, y_prob)
    logger.info("\n--- EVALUASI MODEL (TEST SET 20% Holdout) ---")
    logger.info(f"ROC AUC Score: {auc:.3f}")
    logger.info(
        f"Classification Report (Precision, Recall, F1-Score):\n{classification_report(y_test, y_pred)}"
    )

    # 7. Save Model
    model_path = Path(args.out)
    if not model_path.is_absolute():
        model_path = project_root / model_path

    joblib.dump(model, model_path)

    logger.info(f"Pelatihan selesai! Model berhasil disimpan di: {model_path}")


if __name__ == "__main__":
    main()
