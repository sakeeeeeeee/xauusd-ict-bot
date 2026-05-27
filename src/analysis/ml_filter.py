"""
ml_filter.py — Modul untuk memprediksi probabilitas kemenangan (Win Rate)
berdasarkan model Machine Learning yang telah dilatih.
Saat ini berfungsi sebagai placeholder.
"""

import logging

logger = logging.getLogger("ml_filter")


def predict_win_probability(features: dict) -> float:
    """
    Fungsi placeholder untuk memprediksi P(Win).
    Menerima dictionary fitur (atr, spread, confluence, time, dll.)
    Mengembalikan probabilitas (0.0 - 1.0).
    """
    import joblib
    import pandas as pd
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    model_path = project_root / "model.pkl"

    if not model_path.exists():
        logger.warning(
            "Model ML (model.pkl) belum dilatih/tidak ditemukan. P(Win) = 0.5"
        )
        return 0.5

    try:
        model = joblib.load(model_path)

        # Transform features to DataFrame expected by Pipeline
        df_features = pd.DataFrame(
            [
                {
                    "confluence_score": features.get("confluence", 0),
                    "bias": features.get("bias", "UNKNOWN"),
                    "tier": features.get("tier", "UNKNOWN"),
                    "session": features.get("session", "UNKNOWN"),
                    "risk": features.get("risk", 0.0),
                    "near_sweep": int(features.get("near_sweep", False)),
                }
            ]
        )

        # predict_proba returns array of shape (n_samples, n_classes)
        # Assuming class 1 is WIN and class 0 is LOSS
        prob = model.predict_proba(df_features)[0][1]
        return float(prob)

    except Exception as e:
        logger.error(f"Gagal memprediksi via ML Model: {e}")
        return 0.5
