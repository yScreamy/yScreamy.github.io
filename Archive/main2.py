import time
import sys
from datetime import datetime
import numpy as np

from data.market_data import MarketDataHandler
from data.processor import DataProcessor
from data.news_handler import NewsHandler
from ai.model import AIModel
from trade.executor import TradeExecutor
from train_ai import train_model
import config


class HyperliquidBot:
    def __init__(self):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- BOT INICIALIZÁLÁSA ---")

        self.market_data = MarketDataHandler()
        self.processor = DataProcessor()
        self.executor = TradeExecutor()
        self.news_handler = NewsHandler()

        self.symbol = config.SYMBOL

        self.loop_interval = int(getattr(config, "LOOP_INTERVAL", 60))
        self.retrain_interval = int(getattr(config, "RETRAIN_INTERVAL", 5))
        self.news_refresh_rate = int(getattr(config, "NEWS_REFRESH_RATE", 3600))

        # 0.30 = ha HOLD, de BUY vagy SELL proba >= 0.30, akkor engedjük az entry-t
        self.risk_factor = float(getattr(config, "RISK_FACTOR", 0.30))

        self.iteration_count = 0
        self.current_sentiment = 0.0
        self.last_news_update = 0.0

        self._cached_feature_list = None
        self._load_or_train_model()

    def _load_or_train_model(self):
        try:
            self.model = AIModel()
            print("[INFO] Modell betöltve.")
        except Exception as e:
            print(f"[INFO] Modell nincs/hibás: {e} -> tanítás indul")
            train_model()
            self.model = AIModel()
            print("[INFO] Modell betöltve tanítás után.")

    @staticmethod
    def _sentiment_label(score: float) -> str:
        if score > 0.1:
            return "POZ"
        if score < -0.1:
            return "NEG"
        return "SEM"

    @staticmethod
    def _build_feature_list(df_features):
        base = ["return", "volatility", "rsi", "ma_dist", "range_pos"]
        pattern_cols = sorted([c for c in df_features.columns if c.startswith("pattern_")])
        return [c for c in base if c in df_features.columns] + pattern_cols

    @staticmethod
    def _normalize_prediction(pred):
        if isinstance(pred, (int, np.integer)):
            return int(pred)
        if isinstance(pred, (float, np.floating)):
            return int(round(float(pred)))
        if isinstance(pred, str):
            p = pred.strip().upper()
            if p in ("H", "HOLD", "NONE", "0"):
                return 0
            if p in ("B", "BUY", "LONG", "1"):
                return 1
            if p in ("S", "SELL", "SHORT", "2"):
                return 2
            return int(p)
        raise ValueError(f"Ismeretlen predikció: {pred!r}")

    def _get_raw_model(self):
        return getattr(self.model, "model", self.model)

    def _predict_code(self, last_row, features) -> int:
        raw = self.model.predict(last_row[features])[0]
        return self._normalize_prediction(raw)

    def _predict_proba(self, last_row, features):
        m = self._get_raw_model()
        if not hasattr(m, "predict_proba") or not hasattr(m, "classes_"):
            return None
        try:
            p = m.predict_proba(last_row[features])[0]
            classes = list(m.classes_)
            out = {int(cls): float(prob) for cls, prob in zip(classes, p)}
            out.setdefault(0, 0.0)
            out.setdefault(1, 0.0)
            out.setdefault(2, 0.0)
            return out
        except Exception:
            return None

    def _status(self, price, pos, sentiment, sent_label, ai_raw, ai_final, probas, action, note):
        t = datetime.now().strftime("%H:%M:%S")

        line1 = f"[{t}] {self.symbol}  price={price:.2f}  pos={pos}  sentiment={sent_label}({sentiment:+.3f})"
        line2 = f"AI: {ai_raw} -> {ai_final}   risk={self.risk_factor:.2f}"

        if probas is not None:
            line2 += f"   proba(H/B/S)={probas.get(0,0):.2f}/{probas.get(1,0):.2f}/{probas.get(2,0):.2f}"

        line3 = f"ACTION: {action}"
        if note:
            line3 += f" | {note}"

        print("\n" + line1)
        print(line2)
        print(line3)

    def run_cycle(self):
        # --- NEWS ---
        now = time.time()
        if now - self.last_news_update > self.news_refresh_rate:
            try:
                self.current_sentiment = float(self.news_handler.get_sentiment_score())
                self.last_news_update = now
            except Exception as e:
                print(f"[WARN] News update hiba: {e} (marad cache)")

        sentiment = float(self.current_sentiment)
        sent_label = self._sentiment_label(sentiment)

        # --- MARKET DATA ---
        df_raw = self.market_data.get_latest_data()
        if df_raw is None or df_raw.empty:
            print("[ERROR] Nincs piaci adat.")
            return

        df_features = self.processor.prepare_features(df_raw)
        if df_features is None or df_features.empty:
            print("[ERROR] Nincs elég adat feature-khöz.")
            return

        last_row = df_features.iloc[[-1]]
        price = float(last_row["close"].iloc[0])

        # --- FEATURES LIST ---
        if self._cached_feature_list is None:
            self._cached_feature_list = self._build_feature_list(df_features)
        features = self._cached_feature_list
        if any(f not in last_row.columns for f in features):
            self._cached_feature_list = self._build_feature_list(df_features)
            features = self._cached_feature_list

        # --- PREDICT ---
        try:
            pred_code = self._predict_code(last_row, features)
            probas = self._predict_proba(last_row, features)
        except Exception as e:
            print(f"[WARN] Predikció hiba: {e} -> retrain")
            train_model()
            self.model = AIModel()
            pred_code = self._predict_code(last_row, features)
            probas = self._predict_proba(last_row, features)

        ai_raw = "HOLD"
        if pred_code == 1:
            ai_raw = "BUY"
        elif pred_code == 2:
            ai_raw = "SELL"

        # --- POSITION ---
        pos = self.executor.get_current_position(self.symbol)

        # --- DECISION ---
        ai_final = ai_raw
        note = ""

        if pos == "NONE":
            # HOLD lazítás probával
            if probas is not None and ai_raw == "HOLD":
                p_buy = probas.get(1, 0.0)
                p_sell = probas.get(2, 0.0)
                best = max(p_buy, p_sell)
                if best >= self.risk_factor:
                    ai_final = "BUY" if p_buy >= p_sell else "SELL"
                    note = f"risk_override best={best:.2f}"

            # sentiment filter csak entry-re
            if ai_final == "BUY" and sentiment < -0.2:
                ai_final = "HOLD"
                note = "blocked_by_sentiment(BUY)"
            elif ai_final == "SELL" and sentiment > 0.2:
                ai_final = "HOLD"
                note = "blocked_by_sentiment(SELL)"

        elif pos == "LONG":
            # nyitott pozinál: zárást priorizáljuk, sentiment ne blokkolja
            if ai_raw == "SELL" or (probas is not None and probas.get(2, 0.0) >= self.risk_factor):
                ai_final = "CLOSE_LONG"
            else:
                ai_final = "HOLD_LONG"

        elif pos == "SHORT":
            if ai_raw == "BUY" or (probas is not None and probas.get(1, 0.0) >= self.risk_factor):
                ai_final = "CLOSE_SHORT"
            else:
                ai_final = "HOLD_SHORT"

        # --- EXECUTE (előszűrés: size==0 esetén ne próbáljon nyitni) ---
        action = "WAIT"

        if pos == "NONE" and ai_final in ("BUY", "SELL"):
            # ha az executor tud preview-t (ajánlott), előre nézzük meg
            equity = lev = notional = size = None
            if hasattr(self.executor, "calc_full_size"):
                try:
                    equity, lev, notional, size = self.executor.calc_full_size(self.symbol)
                except Exception:
                    equity = lev = notional = size = None

            if size is not None and float(size) <= 0:
                action = f"OPEN {ai_final} BLOCKED"
                extra = f"size={size} equity={equity} lev={lev} notional={notional}"
                note = (note + " | " + extra).strip(" |")
            else:
                action = f"OPEN {ai_final} (FULL)"
                self.executor.open_full_position(ai_final, self.symbol)

        elif pos == "LONG":
            if ai_final == "CLOSE_LONG":
                action = "CLOSE LONG (FULL)"
                self.executor.close_position_fully(self.symbol)
            else:
                action = "HOLD LONG"

        elif pos == "SHORT":
            if ai_final == "CLOSE_SHORT":
                action = "CLOSE SHORT (FULL)"
                self.executor.close_position_fully(self.symbol)
            else:
                action = "HOLD SHORT"

        self._status(price, pos, sentiment, sent_label, ai_raw, ai_final, probas, action, note)

    def run(self):
        print(f"\n[{datetime.now()}] A bot elindult.")
        print(f"Loop={self.loop_interval}s | Retrain={self.retrain_interval} ciklus | News={self.news_refresh_rate}s")
        print("-" * 60)

        while True:
            if self.iteration_count >= self.retrain_interval:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Retrain...")
                try:
                    train_model()
                    self.model = AIModel()
                    self._cached_feature_list = None
                    self.iteration_count = 0
                    print("[INFO] Retrain OK.")
                except Exception as e:
                    print(f"[WARN] Retrain hiba: {e}")

            try:
                self.run_cycle()
            except Exception as e:
                print(f"[CRITICAL] run_cycle hiba: {e}")

            self.iteration_count += 1
            time.sleep(self.loop_interval)


if __name__ == "__main__":
    try:
        bot = HyperliquidBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n[STOP] Bot leáll.")
        sys.exit(0)
