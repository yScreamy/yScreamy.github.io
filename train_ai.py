import os
import json
from datetime import datetime

import joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import RandomizedSearchCV

from data.market_data import MarketDataHandler
from data.processor import DataProcessor
import config

FEATURES_PATH = "ai/trading_model_features.pkl"
MODEL_PATH = "ai/trading_model.pkl"
META_PATH = "ai/training_meta.json"


def _build_feature_list(processed_data: pd.DataFrame):
    base = ["return", "volatility", "rsi", "ma_dist", "range_pos"]
    pattern_cols = sorted([c for c in processed_data.columns if c.startswith("pattern_")])
    chart_cols = sorted([c for c in processed_data.columns if c.startswith("chart_")])
    # include both single-candle patterns and multi-candle chart patterns
    return [c for c in base if c in processed_data.columns] + pattern_cols + chart_cols


def _ensure_dir(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _pick_interval() -> str:
    interval = str(getattr(config, "TRAIN_CANDLE_INTERVAL", "") or "").strip()
    if not interval:
        interval = str(getattr(config, "CANDLE_INTERVAL", "1m")).strip()
    if not interval:
        interval = "1m"
    return interval


def train_model():
    print("--- MI TANÍTÁSI FOLYAMAT INDUL ---")

    interval = _pick_interval()
    limit = int(getattr(config, "TRAIN_OHLCV_LIMIT", 5000))
    if limit <= 0:
        limit = 5000

    dh = MarketDataHandler()
    try:
        env = dh.get_environment_info()
    except Exception:
        env = {}

    raw_df = dh.get_historical_ohlcv(limit=limit, interval=interval)
    if raw_df is None or raw_df.empty:
        print("Hiba: Nem sikerült adatot gyűjteni (raw_df üres).")
        return

    dp = DataProcessor()
    processed_data = dp.prepare_features(raw_df)
    if processed_data is None or processed_data.empty:
        print("Hiba: A feldolgozott adat üres (nincs elég gyertya / túl sok NaN).")
        return

    if "target" not in processed_data.columns:
        print("Hiba: target oszlop hiányzik a feldolgozott adatokból.")
        return

    features = _build_feature_list(processed_data)
    if len(features) == 0:
        print("Hiba: Nem találtam feature-öket (se base, se pattern_).")
        return

    X = processed_data[features].copy()
    y = processed_data["target"].copy()

    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = y.replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)

    uniq = sorted(pd.Series(y).unique().tolist())
    if len(uniq) < 2:
        print(f"Hiba: Target túl kevés osztállyal rendelkezik: {uniq}. (Nem érdemes így tanítani.)")
        return

    n_jobs = int(getattr(config, "TRAIN_N_JOBS", -1))
    if n_jobs == 0:
        n_jobs = 1

    # Hyperparameter tuning with RandomizedSearchCV
    param_distributions = {
        'n_estimators': [100, 200, 300, 400, 500],
        'max_depth': [None, 5, 8, 10, 15, 20],
        'min_samples_split': [2, 5, 10, 15],
        'min_samples_leaf': [1, 2, 5, 10],
        'max_features': ['sqrt', 'log2'],  # Removed 'auto' as it's deprecated
        'bootstrap': [True, False]
    }

    rf = RandomForestClassifier(
        random_state=int(getattr(config, "RF_RANDOM_STATE", 42)),
        n_jobs=n_jobs,
        class_weight=getattr(config, "RF_CLASS_WEIGHT", None),
    )

    cv_folds = int(getattr(config, "CV_FOLDS", 3))
    n_iter = int(getattr(config, "CV_N_ITER", 20))

    search = RandomizedSearchCV(
        estimator=rf,
        param_distributions=param_distributions,
        n_iter=n_iter,
        cv=cv_folds,
        scoring='accuracy',
        random_state=42,
        n_jobs=n_jobs,
        verbose=1
    )

    print(f"[TRAIN] Hyperparameter tuning: n_iter={n_iter}, cv={cv_folds}")
    search.fit(X, y)

    model = search.best_estimator_
    best_params = search.best_params_

    print(f"[TRAIN] Best params: {best_params}")
    print(f"[TRAIN] Best CV score: {search.best_score_:.4f}")

    _ensure_dir(MODEL_PATH)
    _ensure_dir(FEATURES_PATH)
    _ensure_dir(META_PATH)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(features, FEATURES_PATH)

    meta = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": str(getattr(config, "SYMBOL", "BTC")),
        "interval": str(interval),
        "limit": int(limit),
        "classes": uniq,
        "x_shape": [int(X.shape[0]), int(X.shape[1])],
        "n_jobs": int(n_jobs),
        "cv_folds": int(cv_folds),
        "cv_n_iter": int(n_iter),
        "best_params": best_params,
        "best_cv_score": float(search.best_score_),
        "environment": env,
        "features_count": int(len(features)),
        "patterns_count": int(len([f for f in features if f.startswith("pattern_")])),
        "model_path": MODEL_PATH,
        "features_path": FEATURES_PATH,
    }

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Siker: Modell elmentve ide: '{MODEL_PATH}'")
    print(f"Siker: Feature lista elmentve ide: '{FEATURES_PATH}'")
    print(f"Siker: Meta elmentve ide: '{META_PATH}'")


if __name__ == "__main__":
    train_model()
