import joblib
import pandas as pd
import os
from data.processor import DataProcessor

class AIModel:
    def __init__(self):
        self.model_path = 'ai/trading_model.pkl'
        self.model = self._load_model()
        self.processor = DataProcessor()

    def _load_model(self):
        if os.path.exists(self.model_path):
            print(f"--- MI MODELL BETÖLTVE: {self.model_path} ---")
            return joblib.load(self.model_path)
        print("--- FIGYELEM: NINCS MODELL, HOLD ÜZEMMÓD ---")
        return None

    def predict(self, df):
        if self.model is None:
            return "HOLD"

        # Friss adatok előkészítése (ugyanazok a feature-ök kellenek)
        processed_df = self.processor.prepare_features(df)
        if processed_df is None or processed_df.empty:
            return "HOLD"

        # Az utolsó gyertya alapján jósolunk
        features = ['return', 'volatility', 'rsi', 'ma_dist']
        last_row = processed_df[features].tail(1)
        
        prediction = self.model.predict(last_row)[0]

        # Visszaalakítás szöveges jelzéssé
        if prediction == 1: return "BUY"
        if prediction == 2: return "SELL"
        return "HOLD"
