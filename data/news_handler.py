import time
from typing import List

import requests
import config

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

try:
    from transformers import pipeline
except Exception:
    pipeline = None


class NewsHandler:
    def __init__(self):
        self.api_key = (getattr(config, "CRYPTO_PANIC_KEY", "") or "").strip()
        self.enabled = True if self.api_key else False
        if not self.enabled:
            print("[NewsHandler] Nincs CRYPTO_PANIC_KEY. Hírszűrés kikapcsolva (0.0 bias).")

        api_plan = (getattr(config, "CRYPTO_PANIC_PLAN", "developer") or "developer").strip().lower()
        self.base_url = f"https://cryptopanic.com/api/{api_plan}/v2/posts/"

        self.params = {
            "auth_token": self.api_key,
            "kind": str(getattr(config, "NEWS_KIND", "news") or "news"),
            "currencies": (getattr(config, "NEWS_CURRENCIES", "BTC") or "BTC").replace(" ", ""),
            "regions": str(getattr(config, "NEWS_REGION", "en") or "en"),
            "public": "true",
        }

        self.timeout_seconds = float(getattr(config, "NEWS_TIMEOUT_SECONDS", 10))
        self.fetch_limit = int(getattr(config, "NEWS_FETCH_LIMIT", 10))

        # Internal cache (prevents accidental spam calls)
        self.cache_seconds = int(getattr(config, "NEWS_CACHE_SECONDS", 55))
        self._cache_ts = 0.0
        self._cache_score = 0.0

        # VADER baseline
        self.vader = SentimentIntensityAnalyzer()

        # Transformer (crypto headline model) selection from config
        self.model_name = str(getattr(config, "NEWS_SENTIMENT_MODEL", "mathugo/crypto_news_bert"))
        self.model_weight = float(getattr(config, "NEWS_MODEL_WEIGHT", 0.65))
        self.vader_weight = float(getattr(config, "NEWS_VADER_WEIGHT", 0.35))

        self.disagreement_threshold = float(getattr(config, "NEWS_DISAGREEMENT_THRESHOLD", 0.6))
        self.disagreement_scale = float(getattr(config, "NEWS_DISAGREEMENT_SCALE", 0.5))

        self._transformer = None
        if pipeline is not None and self.enabled:
            try:
                self._transformer = pipeline("sentiment-analysis", model=self.model_name)
                print(f"[NewsHandler] Loaded transformer sentiment model: {self.model_name}")
            except Exception as e:
                print(f"[NewsHandler] Transformer model load failed ({self.model_name}): {e}")
                self._transformer = None
        else:
            print("[NewsHandler] transformers not available vagy hírek kikapcsolva, VADER only / 0.0.")

    def get_sentiment_score(self) -> float:
        """
        Returns sentiment score in [-1, +1].
        Uses ensemble: transformer (domain) + VADER baseline.
        Falls back to VADER only if transformer is unavailable.
        """
        if not self.enabled:
            return 0.0
        if self.cache_seconds > 0 and (time.time() - self._cache_ts) < self.cache_seconds:
            return float(self._cache_score)

        titles = self._fetch_latest_titles()
        if not titles:
            return 0.0

        scores: List[float] = []
        for title in titles[: self.fetch_limit]:
            scores.append(self._ensemble_score(title))

        if not scores:
            return 0.0

        avg = sum(scores) / len(scores)
        avg = max(-1.0, min(1.0, float(avg)))

        self._cache_ts = time.time()
        self._cache_score = float(round(avg, 3))
        return float(self._cache_score)

    def _fetch_latest_titles(self) -> List[str]:
        if not self.enabled:
            return []
        try:
            response = requests.get(self.base_url, params=self.params, timeout=self.timeout_seconds)
            if response.status_code != 200:
                print(f"[NewsHandler] CryptoPanic API error: HTTP {response.status_code}")
                return []

            data = response.json()
            results = data.get("results", []) or []

            titles: List[str] = []
            for post in results:
                t = str(post.get("title") or "").strip()
                if t:
                    titles.append(t)

            return titles

        except Exception as e:
            print(f"[NewsHandler] Fetch error: {e}")
            return []

    def _ensemble_score(self, text: str) -> float:
        vader_score = float(self.vader.polarity_scores(text).get("compound", 0.0))
        vader_score = max(-1.0, min(1.0, vader_score))

        if self._transformer is None:
            return vader_score

        model_score = self._transformer_score(text)
        denom = max(1e-9, (self.vader_weight + self.model_weight))
        combined = (self.vader_weight * vader_score + self.model_weight * model_score) / denom

        # Disagreement gating
        if abs(vader_score - model_score) >= self.disagreement_threshold:
            combined *= self.disagreement_scale

        return float(max(-1.0, min(1.0, combined)))

    def _transformer_score(self, text: str) -> float:
        """
        Converts CryptoBERT output to [-1, +1].
        ElKulako/cryptobert labels: Bearish / Neutral / Bullish. :contentReference[oaicite:1]{index=1}
        """
        try:
            out = self._transformer(text)
            if not out or not isinstance(out, list):
                return 0.0

            label = str(out[0].get("label", "")).upper()
            confidence = float(out[0].get("score", 0.0))

            if "BULL" in label:
                return max(-1.0, min(1.0, confidence))
            if "BEAR" in label:
                return max(-1.0, min(1.0, -confidence))

            # NEUTRAL or unknown label
            return 0.0
        except Exception:
            return 0.0

