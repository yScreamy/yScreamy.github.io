import joblib
import pandas as pd
import os
import numpy as np
from data.processor import DataProcessor


class AIModel:
    def __init__(self):
        self.model_path = "ai/trading_model.pkl"
        self.model = self._load_model()
        self.processor = DataProcessor()
        self.features_path = "ai/trading_model_features.pkl"
        self.features = self._load_features()

    def _load_model(self):
        if os.path.exists(self.model_path):
            print(f"--- MI MODELL BETÖLTVE: {self.model_path} ---")
            try:
                return joblib.load(self.model_path)
            except Exception as e:
                print(f"[AIModel] Modell betöltési hiba: {e}")
                return None
        print("--- FIGYELEM: NINCS MODELL, HOLD ÜZEMMÓD ---")
        return None

    def predict(self, df):
        """
        Return a numpy array-like similar to sklearn's predict (e.g. [0], [1], [2]).
        If an sklearn model is available we delegate to it. Otherwise return [0] (HOLD).
        """
        # If underlying sklearn model exists, prefer delegating
        if self.model is not None and hasattr(self.model, "predict"):
            try:
                # model.predict should accept a DataFrame; let it raise if incompatible
                out = self.model.predict(df)
                return np.array(out)
            except Exception:
                # Fall back to internal light prediction below
                pass

        # Friss adatok előkészítése (ugyanazok a feature-ök kellenek)
        processed_df = self.processor.prepare_features(df)
        if processed_df is None or processed_df.empty:
            return np.array([0])

        # Az utolsó gyertya alapján jósolunk (használjuk a betanított feature listát ha elérhető)
        features = self.features or ["return", "volatility", "rsi", "ma_dist"]
        missing = [f for f in features if f not in processed_df.columns]
        if missing:
            # Ha hiányzó feature-k, fallback: próbáljuk a közönséges négyet
            features = [f for f in ["return", "volatility", "rsi", "ma_dist"] if f in processed_df.columns]
            if not features:
                return np.array([0])

        last_row = processed_df[features].tail(1)

        # Simple heuristic fallback: neutral
        prediction_code = 0
        try:
            # Azt feltételezzük: 1=BUY, 2=SELL
            # Itt egyszerű heuristika példa: rsi alapú döntés
            rsi = float(last_row["rsi"].iloc[0])
            if rsi < 35:
                prediction_code = 1
            elif rsi > 65:
                prediction_code = 2
        except Exception:
            prediction_code = 0

        return np.array([int(prediction_code)])

    def _load_features(self):
        try:
            if os.path.exists(self.features_path):
                return joblib.load(self.features_path)
        except Exception:
            pass
        return None
