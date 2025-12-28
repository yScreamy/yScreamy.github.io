# main.py
from __future__ import annotations

import os
import time
import math
import json
import re
import threading
from datetime import datetime, timedelta
from collections import deque
from typing import Any

import numpy as np
from flask import Flask, jsonify, send_from_directory, request

# Optional requests for Ollama
try:
    import requests  # type: ignore
except Exception:
    requests = None

from data.market_data import MarketDataHandler
from data.processor import DataProcessor
from utils.fib import compute_fibonacci_levels, compute_tp_sl_from_fib
from data.news_handler import NewsHandler
from ai.model import AIModel
from trade.executor import TradeExecutor
from risk.risk_manager import RiskManager
from utils.logger import Logger
from train_ai import train_model
from ai.rl_model import RLModel
import config


# ============================================================
# Strategy configuration (defaults can be overridden by config.py)
# ============================================================
EQUITY_FRACTION_PER_ENTRY = float(getattr(config, "EQUITY_FRACTION", 1.0))  # 100%

# TP/SL configuration
USE_TRAILING_STOP_LOSS = bool(getattr(config, "USE_TRAILING_STOP_LOSS", True))
TRAILING_STEP_PERCENT = float(getattr(config, "TRAILING_STEP_PERCENT", 0.10))

# Fibonacci TP/SL (PRIMARY)
USE_FIBONACCI_TP_SL = bool(getattr(config, "USE_FIBONACCI_TP_SL", True))
FIB_TP_EXTENSION = float(getattr(config, "FIB_TP_EXTENSION", 1.272))
FIB_SL_RETRACEMENT = float(getattr(config, "FIB_SL_RETRACEMENT", 0.618))
FIB_LOOKBACK_PERIODS = int(getattr(config, "FIB_LOOKBACK_PERIODS", 24))

# Fix TP/SL (FALLBACK only if Fibonacci fails)
TAKE_PROFIT_DECIMAL = float(getattr(config, "TAKE_PROFIT_DECIMAL", 0.20))  # 20%
STOP_LOSS_DECIMAL = float(getattr(config, "STOP_LOSS_DECIMAL", 0.30))      # 30%

REOPEN_COOLDOWN_SECONDS = int(getattr(config, "REOPEN_COOLDOWN_SECONDS", 5))

# Market data
DEFAULT_CANDLE_INTERVAL = str(getattr(config, "CANDLE_INTERVAL", "1m")).strip() or "1m"
DEFAULT_LOOKBACK_CANDLES = int(getattr(config, "LOOKBACK_CANDLES", 250))

# ============================================================
# Ensemble strategy configuration
# ============================================================
ENSEMBLE_WEIGHT_ARTIFICIAL_INTELLIGENCE = float(getattr(config, "ENSEMBLE_WEIGHT_ARTIFICIAL_INTELLIGENCE", 0.40))
ENSEMBLE_WEIGHT_TREND_FOLLOWING = float(getattr(config, "ENSEMBLE_WEIGHT_TREND_FOLLOWING", 0.20))
ENSEMBLE_WEIGHT_BREAKOUT = float(getattr(config, "ENSEMBLE_WEIGHT_BREAKOUT", 0.20))
ENSEMBLE_WEIGHT_MEAN_REVERSION = float(getattr(config, "ENSEMBLE_WEIGHT_MEAN_REVERSION", 0.20))
ENSEMBLE_WEIGHT_TREND_ANALYSIS = float(getattr(config, "ENSEMBLE_WEIGHT_TREND_ANALYSIS", 0.10))
ENSEMBLE_WEIGHT_REINFORCEMENT_LEARNING = float(getattr(config, "ENSEMBLE_WEIGHT_REINFORCEMENT_LEARNING", 0.10))

ENSEMBLE_TRADE_THRESHOLD = float(getattr(config, "ENSEMBLE_TRADE_THRESHOLD", 0.30))

TREND_FOLLOWING_EMA_FAST_PERIOD = int(getattr(config, "TREND_FOLLOWING_EMA_FAST_PERIOD", 20))
TREND_FOLLOWING_EMA_SLOW_PERIOD = int(getattr(config, "TREND_FOLLOWING_EMA_SLOW_PERIOD", 50))

BREAKOUT_LOOKBACK_PERIODS = int(getattr(config, "BREAKOUT_LOOKBACK_PERIODS", 24))

# -------------------------
# Entry confirmation & sizing guards
# -------------------------
ENTRY_CONFIRMATION_REQUIRED = bool(getattr(config, "ENTRY_CONFIRMATION_REQUIRED", True))
ENTRY_MIN_ADX = float(getattr(config, "ENTRY_MIN_ADX", 15.0))
ENTRY_MIN_TREND = float(getattr(config, "ENTRY_MIN_TREND", 0.05))
ENTRY_MIN_BREAKOUT = float(getattr(config, "ENTRY_MIN_BREAKOUT", 0.05))
ENTRY_SIZE_SCALE_BY_ENSEMBLE = bool(getattr(config, "ENTRY_SIZE_SCALE_BY_ENSEMBLE", True))

# -------------------------
# Fibonacci settings (PRIMARY TP/SL calculation)
# -------------------------
FIB_ENABLED = bool(getattr(config, "USE_FIBONACCI_TP_SL", True))
FIB_LOOKBACK = int(getattr(config, "FIB_LOOKBACK_PERIODS", BREAKOUT_LOOKBACK_PERIODS))

MEAN_REVERSION_RSI_OVERSOLD = float(getattr(config, "MEAN_REVERSION_RSI_OVERSOLD", 30.0))
MEAN_REVERSION_RSI_OVERBOUGHT = float(getattr(config, "MEAN_REVERSION_RSI_OVERBOUGHT", 70.0))

SENTIMENT_BLOCK_BUY_BELOW = float(getattr(config, "SENTIMENT_BLOCK_BUY_BELOW", -0.20))
SENTIMENT_BLOCK_SELL_ABOVE = float(getattr(config, "SENTIMENT_BLOCK_SELL_ABOVE", 0.20))

# ============================================================
# Advisor (LLM strategy copilot) configuration
# ============================================================
ADVISOR_ENABLED = bool(getattr(config, "ADVISOR_ENABLED", True))
ADVISOR_INTERVAL_SECONDS = int(getattr(config, "ADVISOR_INTERVAL_SECONDS", 120))
ADVISOR_MIN_CONFIDENCE = float(getattr(config, "ADVISOR_MIN_CONFIDENCE", 0.65))
ADVISOR_GATE_ENTRIES = bool(getattr(config, "ADVISOR_GATE_ENTRIES", True))
ADVISOR_ALLOW_RUNTIME_TUNING = bool(getattr(config, "ADVISOR_ALLOW_RUNTIME_TUNING", False))
ADVISOR_ALLOW_EARLY_CLOSE = bool(getattr(config, "ADVISOR_ALLOW_EARLY_CLOSE", False))
ADVISOR_MAX_CONTEXT_CHARS = int(getattr(config, "ADVISOR_MAX_CONTEXT_CHARS", 9000))


# ============================================================
# Runtime settings update (queued; applied at start of loop)
# ============================================================
PENDING_SETTINGS_LOCK = threading.Lock()
PENDING_SETTINGS: dict | None = None


# ============================================================
# Shared state for Web UI
# ============================================================
STATE_LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "timestamp": None,
    "status": "starting",
    "symbol": None,

    "equity_usd": None,
    "position_size": None,
    "entry_price": None,

    "price": None,
    "price_source": None,

    "position": "UNKNOWN",  # NONE / LONG / SHORT / ERROR

    "sentiment_raw": None,
    "sentiment_label": None,
    "sentiment_effective": None,

    "artificial_intelligence_raw_signal": None,
    "artificial_intelligence_final_signal": None,

    "risk_threshold": None,
    "probabilities": None,

    "ensemble_score": None,
    "ensemble_components": None,

    "action": None,
    "note": None,

    "tp_sl": {
        "active": None,
        "entry_price": None,
        "pnl_percent": None,
        "take_profit_percent": None,
        "stop_loss_percent": None,
        "last_reason": None,
        "last_close_submit_ok": None,
        "trailing_active": None,
        "trailing_stop_price": None,
        "trailing_levels": None,
    },

    "exit_probability": None,
    "exit_eta_median": None,
    "exit_eta_expected": None,

    "runtime_settings": {
        "leverage_target": None,
        "margin_mode_target": None,
        "take_profit_percent": None,
        "stop_loss_percent": None,
        "equity_fraction_percent": None,
        "candle_interval": None,
        "settings_last_applied_note": None,
    },

    "addresses": {
        "trading_address_last6": None,
        "signing_wallet_last6": None,
    },

    "ollama": {
        "base_url": None,
        "model": None,
        "timeout_s": None,
        "requests_installed": None,
        "warmed": None,
        "ready_recently": None,
        "last_ok_age_s": None,
        "last_error": None,
    },

    "advisor": {
        "enabled": None,
        "interval_s": None,
        "min_confidence": None,

        "last_ts": None,
        "last_ok_age_s": None,
        "last_error": None,

        "bias": None,            # LONG / SHORT / NEUTRAL
        "confidence": None,      # 0..1
        "recommendation": None,  # ALLOW / BLOCK / REDUCE_RISK / CLOSE / NONE
        "block_trading": None,   # bool
        "rationale": None,

        "runtime_suggestions": None,
        "raw_json": None,
    },

    # Pipeline/telemetria: AI -> Risk -> main.py
    "pipeline": {
        "cycle_ts": None,
        "ai_ts": None,
        "risk_ts": None,

        "ai_signal": None,
        "ai_probabilities": None,
        "ensemble_decision": None,

        "risk_allowed": None,
        "risk_reason": None,
        "risk_size_mult": None,

        "last_ai_error": None,
        "last_risk_error": None,

        "candle_interval": None,
    },
}


def set_state(**kwargs):
    """
    STATE frissítés (thread-safe).
    Ha dict-et adsz meg és a meglévő érték is dict, akkor merge-eli (nem felülírja teljesen).
    """
    with STATE_LOCK:
        for key, value in kwargs.items():
            if isinstance(value, dict) and isinstance(STATE.get(key), dict):
                merged = dict(STATE.get(key) or {})
                merged.update(value)
                STATE[key] = merged
            else:
                STATE[key] = value
        STATE["timestamp"] = datetime.now().isoformat(timespec="seconds")


# ============================================================
# Log ring buffer
# ============================================================
LOG_LOCK = threading.Lock()
LOG_RING = deque(maxlen=4000)


def log_line(msg: str):
    line = f"{datetime.now().strftime('%H:%M:%S')} | {msg}"
    with LOG_LOCK:
        LOG_RING.append(line)
    Logger.log(line)


def log_tail(n: int = 200) -> str:
    n = max(1, min(int(n), 2000))
    with LOG_LOCK:
        return "\n".join(list(LOG_RING)[-n:])


# ============================================================
# Helpers
# ============================================================
def sentiment_label_from_score(score: float) -> str:
    if score > 0.1:
        return "POSITIVE"
    if score < -0.1:
        return "NEGATIVE"
    return "NEUTRAL"


def normalize_prediction(prediction) -> int:
    if isinstance(prediction, (int, np.integer)):
        return int(prediction)
    if isinstance(prediction, (float, np.floating)):
        return int(round(float(prediction)))
    if isinstance(prediction, str):
        p = prediction.strip().upper()
        if p in ("H", "HOLD", "NONE", "0"):
            return 0
        if p in ("B", "BUY", "LONG", "1"):
            return 1
        if p in ("S", "SELL", "SHORT", "2"):
            return 2
        try:
            return int(p)
        except Exception as e:
            Logger.log(f"Prediction normalize error: {e}")
            # Fallback: unknown string -> HOLD
            return 0
    raise ValueError(f"Unknown prediction type: {prediction!r}")


def estimate_exit_etas(exit_probability: float, loop_interval_seconds: int):
    try:
        p = float(exit_probability)
    except Exception as e:
        Logger.log(f"Exit eta calculation error: {e}")
        return None, None
    if p <= 0.0 or p >= 1.0:
        return None, None
    n_median = math.log(0.5) / math.log(1.0 - p)
    n_expected = 1.0 / p
    now = datetime.now()
    return (
        now + timedelta(seconds=int(round(n_median * loop_interval_seconds))),
        now + timedelta(seconds=int(round(n_expected * loop_interval_seconds))),
    )


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def decimal_to_percent(decimal_value: float) -> float:
    return float(decimal_value) * 100.0


def percent_to_decimal(percent_value: float) -> float:
    return float(percent_value) / 100.0


# Fibonacci helpers moved to utils/fib.py


def _extract_first_json_object(text: str):
    if not text:
        return None

    t = str(text).strip()

    try:
        return json.loads(t)
    except Exception:
        pass

    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m:
        return None
    candidate = m.group(0).strip()
    try:
        return json.loads(candidate)
    except Exception:
        return None


# ============================================================
# Ensemble scoring
# ============================================================
class EnsembleScorer:
    @staticmethod
    def _safe_ema(series, span: int):
        if series is None or len(series) < max(5, span):
            return None
        return series.ewm(span=span, adjust=False).mean()

    @staticmethod
    def artificial_intelligence_score(probabilities: dict | None, fallback_signal: str) -> float:
        if probabilities and isinstance(probabilities, dict):
            p_buy = float(probabilities.get(1, 0.0))
            p_sell = float(probabilities.get(2, 0.0))
            return clamp(p_buy - p_sell, -1.0, 1.0)
        s = str(fallback_signal or "HOLD").upper()
        if s == "BUY":
            return 1.0
        if s == "SELL":
            return -1.0
        return 0.0

    @staticmethod
    def trend_following_score(close_series, current_price: float, ema_fast_period: int, ema_slow_period: int) -> float:
        ema_fast = EnsembleScorer._safe_ema(close_series, ema_fast_period)
        ema_slow = EnsembleScorer._safe_ema(close_series, ema_slow_period)
        if ema_fast is None or ema_slow is None:
            return 0.0
        fast = float(ema_fast.iloc[-1])
        slow = float(ema_slow.iloc[-1])
        price = float(current_price)
        if fast > slow and price > fast:
            return 1.0
        if fast < slow and price < fast:
            return -1.0
        return 0.0

    @staticmethod
    def breakout_score(high_series, low_series, current_price: float, lookback_periods: int) -> float:
        if high_series is None or low_series is None:
            return 0.0
        if len(high_series) < lookback_periods + 2 or len(low_series) < lookback_periods + 2:
            return 0.0
        reference_high = float(high_series.iloc[-(lookback_periods + 2):-2].max())
        reference_low = float(low_series.iloc[-(lookback_periods + 2):-2].min())
        price = float(current_price)
        if price > reference_high:
            return 1.0
        if price < reference_low:
            return -1.0
        return 0.0

    @staticmethod
    def mean_reversion_score(rsi_value: float | None, oversold: float, overbought: float) -> float:
        if rsi_value is None:
            return 0.0
        rsi = float(rsi_value)
        if rsi <= oversold:
            return 1.0
        if rsi >= overbought:
            return -1.0
        score = (50.0 - rsi) / 20.0
        return clamp(score, -1.0, 1.0)

    @staticmethod
    def trend_analysis_score(adx_value: float | None, macd_value: float | None, macd_signal_value: float | None, current_price: float, close_series) -> float:
        score = 0.0
        if adx_value is not None and adx_value > 25:  # Strong trend
            if macd_value is not None and macd_signal_value is not None:
                if macd_value > macd_signal_value:
                    score += 0.5  # Bullish momentum
                elif macd_value < macd_signal_value:
                    score -= 0.5  # Bearish momentum
        # Additional: check if price is above/below SMA
        if close_series is not None and len(close_series) > 20:
            sma_20 = close_series.rolling(window=20).mean().iloc[-1]
            if current_price > sma_20:
                score += 0.3
            elif current_price < sma_20:
                score -= 0.3
        return clamp(score, -1.0, 1.0)

    @staticmethod
    def reinforcement_learning_score(last_row, features, rl_model) -> float:
        """Get RL model prediction and convert to score."""
        if rl_model is None or rl_model.model is None:
            return 0.0

        try:
            # Create observation from last_row
            if features:
                obs_values = []
                for f in features:
                    if f in last_row.columns:
                        obs_values.append(float(last_row[f].iloc[0]))
                    else:
                        obs_values.append(0.0)
                # Add balance and position (simplified)
                obs_values.extend([1.0, 0.0])  # normalized balance=1.0, position=0
                observation = np.array(obs_values, dtype=np.float32)

                action = rl_model.predict_action(observation)
                # Convert action to score: 0=hold(0), 1=buy(1), 2=sell(-1)
                if action == 1:
                    return 1.0
                elif action == 2:
                    return -1.0
                else:
                    return 0.0
        except Exception as e:
            print(f"RL score error: {e}")
            return 0.0

    @staticmethod
    def ensemble_score(
        artificial_intelligence_component: float,
        trend_following_component: float,
        breakout_component: float,
        mean_reversion_component: float,
        trend_analysis_component: float,
        reinforcement_learning_component: float,
        weight_artificial_intelligence: float,
        weight_trend_f: float,
        weight_breakout: float,
        weight_mean_rev: float,
        weight_trend_analysis: float,
        weight_rl: float,
    ) -> tuple[float, dict]:
        weights_sum = float(weight_artificial_intelligence) + float(weight_trend_f) + float(weight_breakout) + float(weight_mean_rev) + float(weight_trend_analysis) + float(weight_rl)
        if weights_sum <= 0:
            weights_sum = 1.0
        score = (
            artificial_intelligence_component * float(weight_artificial_intelligence) +
            trend_following_component * float(weight_trend_f) +
            breakout_component * float(weight_breakout) +
            mean_reversion_component * float(weight_mean_rev) +
            trend_analysis_component * float(weight_trend_analysis) +
            reinforcement_learning_component * float(weight_rl)
        ) / weights_sum
        score = clamp(score, -1.0, 1.0)
        components = {
            "artificial_intelligence": float(artificial_intelligence_component),
            "trend_following": float(trend_following_component),
            "breakout": float(breakout_component),
            "mean_reversion": float(mean_reversion_component),
            "trend_analysis": float(trend_analysis_component),
            "reinforcement_learning": float(reinforcement_learning_component),
            "ensemble_score": float(score),
        }
        return score, components

    @staticmethod
    def decision_from_score(score: float, threshold: float) -> str:
        t = abs(float(threshold))
        s = float(score)
        if abs(s) < t:
            return "HOLD"
        return "BUY" if s > 0 else "SELL"


# ============================================================
# TP/SL manager (synced to real position)
# ============================================================
class SingleTakeProfitStopLossManager:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.position_side = None
        self.entry_price = None
        self.open_size = None
        self.opened_ts = 0.0
        self.last_close_ts = 0.0
        self.last_reason = None
        self.last_close_submit_ok = None

    def can_reopen(self) -> bool:
        return (time.time() - self.last_close_ts) >= REOPEN_COOLDOWN_SECONDS

    def arm_or_update(self, side: str, entry_price: float, size: float):
        side = str(side).upper()
        if side not in ("LONG", "SHORT") or size <= 0 or entry_price <= 0:
            return
        if not self.active:
            self.active = True
            self.opened_ts = time.time()
        self.position_side = side
        self.entry_price = float(entry_price)
        self.open_size = float(size)

    def pnl_decimal(self, current_price: float) -> float:
        entry = float(self.entry_price or 0.0)
        if entry <= 0:
            return 0.0
        price = float(current_price)
        if self.position_side == "LONG":
            return (price - entry) / entry
        return (entry - price) / entry

    def decide(self, current_price: float, tp_dec: float, sl_dec: float):
        if not self.active or not self.entry_price or not self.open_size:
            return "NONE", "", 0.0
        pnl = self.pnl_decimal(current_price)
        tp = abs(float(tp_dec))
        sl = abs(float(sl_dec))
        if tp > 0 and pnl >= tp:
            return "CLOSE_ALL", "TAKE_PROFIT_HIT", pnl
        if sl > 0 and pnl <= -sl:
            return "CLOSE_ALL", "STOP_LOSS_HIT", pnl
        return "NONE", "", pnl


# ============================================================
# Trailing Stop Loss Manager (új fejlesztés)
# ============================================================
class TrailingStopLossManager:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.position_side = None
        self.entry_price = None
        self.open_size = None
        self.opened_ts = 0.0
        self.last_close_ts = 0.0
        self.last_reason = None
        self.last_close_submit_ok = None

        # Trailing stop specifikus
        self.trailing_stop_price = None
        self.highest_price_since_entry = None
        self.lowest_price_since_entry = None
        self.trailing_step_percent = 0.10  # 10% lépések
        self.trailing_levels = []  # Sikeres trailing szintek

    def can_reopen(self) -> bool:
        return (time.time() - self.last_close_ts) >= REOPEN_COOLDOWN_SECONDS

    def arm_or_update(self, side: str, entry_price: float, size: float):
        side = str(side).upper()
        if side not in ("LONG", "SHORT") or size <= 0 or entry_price <= 0:
            return
        if not self.active:
            self.active = True
            self.opened_ts = time.time()
            self.trailing_stop_price = None
            self.highest_price_since_entry = entry_price
            self.lowest_price_since_entry = entry_price
            self.trailing_levels = []
        self.position_side = side
        self.entry_price = float(entry_price)
        self.open_size = float(size)

    def pnl_decimal(self, current_price: float) -> float:
        entry = float(self.entry_price or 0.0)
        if entry <= 0:
            return 0.0
        price = float(current_price)
        if self.position_side == "LONG":
            return (price - entry) / entry
        return (entry - price) / entry

    def _update_trailing_levels(self, current_price: float):
        """Frissíti a trailing szinteket és stop árat."""
        if not self.active or not self.entry_price:
            return

        # Track highest/lowest price
        if self.position_side == "LONG":
            if current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price

                # Calculate new trailing stop if profitable
                pnl = self.pnl_decimal(current_price)
                if pnl > 0:
                    # 10% lépések: minden 10% profit után húzzuk fel a stop-ot
                    profit_steps = int(pnl / self.trailing_step_percent)
                    if profit_steps > len(self.trailing_levels):
                        # Új szint elérve - húzzuk fel a stop-ot
                        new_stop_level = profit_steps * self.trailing_step_percent
                        self.trailing_stop_price = self.entry_price * (1 + new_stop_level - self.trailing_step_percent)
                        self.trailing_levels.append(new_stop_level)
                        print(f"[TRAILING] LONG: New stop at {self.trailing_stop_price:.2f} (level {profit_steps})")

        else:  # SHORT
            if current_price < self.lowest_price_since_entry:
                self.lowest_price_since_entry = current_price

                # Calculate new trailing stop if profitable
                pnl = self.pnl_decimal(current_price)
                if pnl > 0:
                    # 10% lépések short pozícióhoz
                    profit_steps = int(pnl / self.trailing_step_percent)
                    if profit_steps > len(self.trailing_levels):
                        new_stop_level = profit_steps * self.trailing_step_percent
                        self.trailing_stop_price = self.entry_price * (1 - new_stop_level + self.trailing_step_percent)
                        self.trailing_levels.append(new_stop_level)
                        print(f"[TRAILING] SHORT: New stop at {self.trailing_stop_price:.2f} (level {profit_steps})")

    def decide(self, current_price: float, tp_dec: float, sl_dec: float):
        if not self.active or not self.entry_price or not self.open_size:
            return "NONE", "", 0.0

        # Frissítjük a trailing szinteket
        self._update_trailing_levels(current_price)

        pnl = self.pnl_decimal(current_price)

        # Take profit check (ha be van állítva)
        tp = abs(float(tp_dec))
        if tp > 0 and pnl >= tp:
            return "CLOSE_ALL", "TAKE_PROFIT_HIT", pnl

        # Trailing stop check (csak ha már be van állítva stop)
        if self.trailing_stop_price is not None:
            if self.position_side == "LONG" and current_price <= self.trailing_stop_price:
                return "CLOSE_ALL", f"TRAILING_STOP_HIT_LEVEL_{len(self.trailing_levels)}", pnl
            elif self.position_side == "SHORT" and current_price >= self.trailing_stop_price:
                return "CLOSE_ALL", f"TRAILING_STOP_HIT_LEVEL_{len(self.trailing_levels)}", pnl

        # Regular stop loss (csak veszteséges pozíciókra)
        sl = abs(float(sl_dec))
        if sl > 0 and pnl <= -sl:
            return "CLOSE_ALL", "STOP_LOSS_HIT", pnl

        return "NONE", "", pnl


# ============================================================
# Ollama (stable)
# ============================================================
OLLAMA_WARM_LOCK = threading.Lock()
OLLAMA_LAST_OK_TS = 0.0
OLLAMA_WARMED = False
OLLAMA_LAST_ERROR = None


def ollama_mark_ok():
    global OLLAMA_LAST_OK_TS, OLLAMA_WARMED, OLLAMA_LAST_ERROR
    with OLLAMA_WARM_LOCK:
        OLLAMA_LAST_OK_TS = time.time()
        OLLAMA_WARMED = True
        OLLAMA_LAST_ERROR = None


def ollama_mark_err(err: str):
    global OLLAMA_LAST_ERROR
    with OLLAMA_WARM_LOCK:
        OLLAMA_LAST_ERROR = str(err)[:500]


def ollama_is_ready_recently() -> bool:
    with OLLAMA_WARM_LOCK:
        return bool(OLLAMA_LAST_OK_TS and (time.time() - OLLAMA_LAST_OK_TS) < 60)


def ollama_warmup_async():
    base = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "").strip()
    timeout_s = int(os.getenv("OLLAMA_TIMEOUT_S", "120"))
    if not base or not model or requests is None:
        return
    try:
        r = requests.post(base + "/api/generate", json={"model": model, "prompt": "ping", "stream": False}, timeout=timeout_s)
        if r.status_code == 200:
            ollama_mark_ok()
    except Exception as e:
        ollama_mark_err(str(e))


def _ollama_chat(messages: list[dict]) -> str:
    base = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "").strip()
    timeout_s = int(os.getenv("OLLAMA_TIMEOUT_S", "120"))

    if not base or not model or requests is None:
        return "Ollama nincs beállítva. Állítsd be: OLLAMA_BASE_URL és OLLAMA_MODEL."

    # Prefer /api/chat
    try:
        payload = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("system", "user", "assistant")],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        r = requests.post(base + "/api/chat", json=payload, timeout=timeout_s)
        if r.status_code == 200:
            data = r.json()
            msg = data.get("message") or {}
            text = str(msg.get("content") or "").strip()
            if text:
                ollama_mark_ok()
                return text
    except Exception as e:
        ollama_mark_err(str(e))

    # Fallback /api/generate
    prompt_parts = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            prompt_parts.append(f"[SYSTEM]\n{m.get('content','')}\n")
        elif role == "user":
            prompt_parts.append(f"[USER]\n{m.get('content','')}\n")
        elif role == "assistant":
            prompt_parts.append(f"[ASSISTANT]\n{m.get('content','')}\n")
    prompt = "\n".join(prompt_parts).strip()

    r = requests.post(
        base + "/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
        timeout=timeout_s,
    )
    r.raise_for_status()
    data = r.json()
    text = str(data.get("response") or "").strip()
    if text:
        ollama_mark_ok()
        return text
    return "(Empty response from Ollama)"


def _ollama_ui_snapshot():
    base = os.getenv("OLLAMA_BASE_URL", "").strip()
    model = os.getenv("OLLAMA_MODEL", "").strip()
    timeout_s = int(os.getenv("OLLAMA_TIMEOUT_S", "120"))

    with OLLAMA_WARM_LOCK:
        warmed = bool(OLLAMA_WARMED)
        last_ok_age = (time.time() - OLLAMA_LAST_OK_TS) if OLLAMA_LAST_OK_TS else None
        last_err = OLLAMA_LAST_ERROR

    return {
        "base_url": base or None,
        "model": model or None,
        "timeout_s": timeout_s,
        "requests_installed": bool(requests is not None),
        "warmed": warmed,
        "ready_recently": ollama_is_ready_recently(),
        "last_ok_age_s": last_ok_age,
        "last_error": last_err,
    }


# ============================================================
# Advisor (LLM copilot)
# ============================================================
class StrategyAdvisor:
    SYSTEM_PROMPT = (
        "You are a strategy copilot for a live crypto trading bot.\n"
        "IMPORTANT RULES:\n"
        "- Output ONLY valid JSON. No markdown, no extra text.\n"
        "- You do NOT execute trades. You only advise.\n"
        "- Be conservative: if uncertain, choose NEUTRAL with low confidence.\n"
        "- If conditions look unstable, suggest BLOCK or REDUCE_RISK.\n"
        "\n"
        "Return JSON schema:\n"
        "{\n"
        '  "bias": "LONG|SHORT|NEUTRAL",\n'
        '  "confidence": 0.0,\n'
        '  "recommendation": "ALLOW|BLOCK|REDUCE_RISK|CLOSE|NONE",\n'
        '  "block_trading": true|false,\n'
        '  "rationale": "short reason",\n'
        '  "runtime_suggestions": {\n'
        '     "leverage_target": 10,\n'
        '     "margin_mode_target": "cross|isolated",\n'
        '     "take_profit_percent": 20,\n'
        '     "stop_loss_percent": 30,\n'
        '     "equity_fraction_percent": 100\n'
        "   }\n"
        "}\n"
        "Notes:\n"
        "- confidence must be between 0 and 1.\n"
        "- runtime_suggestions is optional and should be omitted if not needed.\n"
    )

    def __init__(self, interval_s: int, min_confidence: float):
        self.interval_s = int(max(10, interval_s))
        self.min_confidence = float(min_confidence)
        self.last_run_ts = 0.0
        self.last_ok_ts = 0.0
        self.last_error = None
        self.last_json = None

    def should_run(self) -> bool:
        return (time.time() - self.last_run_ts) >= self.interval_s

    def ok_age_s(self):
        if not self.last_ok_ts:
            return None
        return time.time() - self.last_ok_ts

    def run(self, context: dict) -> dict | None:
        self.last_run_ts = time.time()

        ctx_text = json.dumps(context, ensure_ascii=False)
        if len(ctx_text) > ADVISOR_MAX_CONTEXT_CHARS:
            ctx_text = ctx_text[:ADVISOR_MAX_CONTEXT_CHARS] + " ...[TRUNCATED]"

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": ctx_text},
        ]

        out = _ollama_chat(messages)
        parsed = _extract_first_json_object(out)
        if not isinstance(parsed, dict):
            self.last_error = "Advisor output not valid JSON object."
            return None

        bias = str(parsed.get("bias", "NEUTRAL")).upper()
        if bias not in ("LONG", "SHORT", "NEUTRAL"):
            bias = "NEUTRAL"

        try:
            conf = float(parsed.get("confidence", 0.0))
        except Exception as e:
            Logger.log(f"Advisor confidence parse error: {e}")
            conf = 0.0
        conf = clamp(conf, 0.0, 1.0)

        rec = str(parsed.get("recommendation", "NONE")).upper()
        if rec not in ("ALLOW", "BLOCK", "REDUCE_RISK", "CLOSE", "NONE"):
            rec = "NONE"

        bt = parsed.get("block_trading", None)
        if isinstance(bt, bool):
            block_trading = bt
        else:
            block_trading = True if rec == "BLOCK" else False

        rationale = str(parsed.get("rationale", "")).strip()[:400]

        runtime_suggestions = parsed.get("runtime_suggestions", None)
        if runtime_suggestions is not None and not isinstance(runtime_suggestions, dict):
            runtime_suggestions = None

        clean = {
            "bias": bias,
            "confidence": conf,
            "recommendation": rec,
            "block_trading": bool(block_trading),
            "rationale": rationale,
        }
        if runtime_suggestions:
            clean["runtime_suggestions"] = runtime_suggestions

        self.last_ok_ts = time.time()
        self.last_error = None
        self.last_json = clean
        return clean


# ============================================================
# Bot
# ============================================================
class HyperliquidBot:
    def __init__(self):
        self.market_data = MarketDataHandler()
        self.processor = DataProcessor()
        self.executor = TradeExecutor()
        self.news_handler = NewsHandler()
        self.risk = RiskManager()

        self.symbol = getattr(config, "SYMBOL", "BTC")
        self.loop_interval_seconds = int(getattr(config, "LOOP_INTERVAL", 10))
        self.retrain_interval_cycles = int(getattr(config, "RETRAIN_INTERVAL", 5))
        self.news_refresh_seconds = int(getattr(config, "NEWS_REFRESH_RATE", 3600))
        self.risk_threshold = float(getattr(config, "RISK_FACTOR", 0.20))

        # Candle interval used for AI chart / feature generation
        self.candle_interval = str(getattr(config, "CANDLE_INTERVAL", DEFAULT_CANDLE_INTERVAL)).strip() or DEFAULT_CANDLE_INTERVAL

        self.sentiment_raw = 0.0
        self.sentiment_effective = 0.0
        self.last_news_update_ts = 0.0

        self.margin_mode_target = str(getattr(config, "MARGIN_MODE", "cross")).lower()
        self.leverage_target = float(getattr(config, "DEFAULT_LEVERAGE", 10))
        self.take_profit_decimal = float(TAKE_PROFIT_DECIMAL)
        self.stop_loss_decimal = float(STOP_LOSS_DECIMAL)
        self.equity_fraction_per_entry = float(EQUITY_FRACTION_PER_ENTRY)

        self.cached_feature_list = None

        # TP/SL Manager választás
        if USE_TRAILING_STOP_LOSS:
            self.position_manager = TrailingStopLossManager()
            print(f"[INIT] Using TRAILING STOP LOSS with {TRAILING_STEP_PERCENT*100:.0f}% steps")
        else:
            self.position_manager = SingleTakeProfitStopLossManager()
            print(f"[INIT] Using FIXED TP/SL: TP={TAKE_PROFIT_DECIMAL*100:.1f}%, SL={STOP_LOSS_DECIMAL*100:.1f}%")

        self.iteration_counter = 0
        self._load_or_train_model()

        self.advisor = None
        if ADVISOR_ENABLED:
            self.advisor = StrategyAdvisor(ADVISOR_INTERVAL_SECONDS, ADVISOR_MIN_CONFIDENCE)

        trading_address = getattr(self.executor, "trading_address", "") or ""
        signing_address = ""
        try:
            signing_address = str(getattr(self.executor, "account", None).address)
        except Exception:
            signing_address = ""

        set_state(
            status="live",
            symbol=self.symbol,
            risk_threshold=float(self.risk_threshold),
            addresses={
                "trading_address_last6": trading_address[-6:] if trading_address else None,
                "signing_wallet_last6": signing_address[-6:] if signing_address else None,
            },
            runtime_settings=self._runtime_settings_snapshot(note="initial"),
            advisor=self._advisor_ui_snapshot(),
            ollama=_ollama_ui_snapshot(),
            pipeline={
                "cycle_ts": None,
                "ai_ts": None,
                "risk_ts": None,
                "ai_signal": None,
                "ai_probabilities": None,
                "ensemble_decision": None,
                "risk_allowed": None,
                "risk_reason": None,
                "risk_size_mult": None,
                "last_ai_error": None,
                "last_risk_error": None,
                "candle_interval": self.candle_interval,
            },
        )
        log_line(f"[BOT] Started symbol={self.symbol} loop_interval={self.loop_interval_seconds}s tf={self.candle_interval}")

    def _runtime_settings_snapshot(self, note: str = "") -> dict:
        return {
            "leverage_target": float(self.leverage_target),
            "margin_mode_target": str(self.margin_mode_target),
            "take_profit_percent": float(round(decimal_to_percent(self.take_profit_decimal), 4)),
            "stop_loss_percent": float(round(decimal_to_percent(self.stop_loss_decimal), 4)),
            "equity_fraction_percent": float(round(self.equity_fraction_per_entry * 100.0, 2)),
            "candle_interval": str(self.candle_interval),
            "settings_last_applied_note": note or None,
        }

    def _advisor_ui_snapshot(self) -> dict:
        adv = self.advisor
        if not adv:
            return {
                "enabled": False,
                "interval_s": int(ADVISOR_INTERVAL_SECONDS),
                "min_confidence": float(ADVISOR_MIN_CONFIDENCE),
                "last_ts": None,
                "last_ok_age_s": None,
                "last_error": None,
                "bias": None,
                "confidence": None,
                "recommendation": None,
                "block_trading": None,
                "rationale": None,
                "runtime_suggestions": None,
                "raw_json": None,
            }

        last_ok_age = adv.ok_age_s()
        last_json = adv.last_json or {}
        return {
            "enabled": True,
            "interval_s": int(adv.interval_s),
            "min_confidence": float(adv.min_confidence),
            "last_ts": datetime.fromtimestamp(adv.last_run_ts).isoformat(timespec="seconds") if adv.last_run_ts else None,
            "last_ok_age_s": float(last_ok_age) if last_ok_age is not None else None,
            "last_error": adv.last_error,
            "bias": last_json.get("bias"),
            "confidence": last_json.get("confidence"),
            "recommendation": last_json.get("recommendation"),
            "block_trading": last_json.get("block_trading"),
            "rationale": last_json.get("rationale"),
            "runtime_suggestions": last_json.get("runtime_suggestions"),
            "raw_json": last_json if last_json else None,
        }

    def _queue_runtime_settings_from_advisor(self, runtime_suggestions: dict):
        global PENDING_SETTINGS
        try:
            leverage_target = float(runtime_suggestions.get("leverage_target", self.leverage_target))
            margin_mode_target = str(runtime_suggestions.get("margin_mode_target", self.margin_mode_target)).lower()
            take_profit_percent = float(runtime_suggestions.get("take_profit_percent", decimal_to_percent(self.take_profit_decimal)))
            stop_loss_percent = float(runtime_suggestions.get("stop_loss_percent", decimal_to_percent(self.stop_loss_decimal)))
            equity_fraction_percent = float(runtime_suggestions.get("equity_fraction_percent", self.equity_fraction_per_entry * 100.0))

            pending = {
                "leverage_target": clamp(leverage_target, 1.0, 100.0),
                "margin_mode_target": "cross" if margin_mode_target not in ("cross", "isolated") else margin_mode_target,
                "take_profit_decimal": clamp(percent_to_decimal(take_profit_percent), 0.0, 1.0),
                "stop_loss_decimal": clamp(percent_to_decimal(stop_loss_percent), 0.0, 1.0),
                "equity_fraction_per_entry": clamp(equity_fraction_percent / 100.0, 0.01, 1.0),
            }

            with PENDING_SETTINGS_LOCK:
                PENDING_SETTINGS = pending

            log_line(
                "[ADVISOR] Queued runtime settings: "
                f"lev={pending['leverage_target']} mode={pending['margin_mode_target']} "
                f"TP={pending['take_profit_decimal']*100:.3f}% SL={pending['stop_loss_decimal']*100:.3f}% "
                f"eq_frac={pending['equity_fraction_per_entry']*100:.2f}%"
            )
        except Exception as e:
            log_line(f"[ADVISOR] Failed to queue runtime settings: {e}")

    def _apply_pending_settings_if_any(self):
        global PENDING_SETTINGS
        with PENDING_SETTINGS_LOCK:
            pending = PENDING_SETTINGS
            PENDING_SETTINGS = None
        if not pending:
            return

        try:
            self.leverage_target = float(pending.get("leverage_target", self.leverage_target))
            self.margin_mode_target = str(pending.get("margin_mode_target", self.margin_mode_target)).lower()
            self.take_profit_decimal = float(pending.get("take_profit_decimal", self.take_profit_decimal))
            self.stop_loss_decimal = float(pending.get("stop_loss_decimal", self.stop_loss_decimal))
            self.equity_fraction_per_entry = float(pending.get("equity_fraction_per_entry", self.equity_fraction_per_entry))

            if "candle_interval" in pending and pending["candle_interval"]:
                self.candle_interval = str(pending["candle_interval"]).strip() or self.candle_interval

            self.leverage_target = clamp(self.leverage_target, 1.0, 100.0)
            if self.margin_mode_target not in ("cross", "isolated"):
                self.margin_mode_target = "cross"
            self.take_profit_decimal = clamp(self.take_profit_decimal, 0.0, 1.0)
            self.stop_loss_decimal = clamp(self.stop_loss_decimal, 0.0, 1.0)
            self.equity_fraction_per_entry = clamp(self.equity_fraction_per_entry, 0.01, 1.0)

            try:
                if hasattr(self.executor, "set_leverage"):
                    is_cross = True if self.margin_mode_target == "cross" else False
                    self.executor.set_leverage(self.leverage_target, self.symbol, is_cross=is_cross)
            except Exception as e:
                log_line(f"[RuntimeSettings] set_leverage failed (best-effort): {e}")

            set_state(
                runtime_settings=self._runtime_settings_snapshot(note="applied"),
                pipeline={"candle_interval": self.candle_interval},
            )
            log_line(
                f"[RuntimeSettings] Applied: lev={self.leverage_target} mode={self.margin_mode_target} "
                f"TP={decimal_to_percent(self.take_profit_decimal):.3f}% SL={decimal_to_percent(self.stop_loss_decimal):.3f}% "
                f"eq_frac={self.equity_fraction_per_entry*100:.2f}% tf={self.candle_interval}"
            )
        except Exception as e:
            set_state(runtime_settings=self._runtime_settings_snapshot(note=f"apply_error: {e}"))
            log_line(f"[RuntimeSettings] Error applying settings: {e}")

    def _load_or_train_model(self):
        try:
            self.model = AIModel()
            self.rl_model = RLModel()
        except Exception:
            train_model()
            self.model = AIModel()
            self.rl_model = RLModel()

    def _raw_model(self):
        return getattr(self.model, "model", self.model)

    @staticmethod
    def _build_feature_list(feature_dataframe):
        base = ["return", "volatility", "rsi", "ma_dist", "range_pos"]
        patterns = sorted([c for c in feature_dataframe.columns if c.startswith("pattern_")])
        return [c for c in base if c in feature_dataframe.columns] + patterns

    def _predict_probabilities(self, last_row, features):
        model = self._raw_model()
        if not hasattr(model, "predict_proba") or not hasattr(model, "classes_"):
            return None
        try:
            probabilities = model.predict_proba(last_row[features])[0]
            classes = list(model.classes_)
            out = {int(cls): float(prob) for cls, prob in zip(classes, probabilities)}
            out.setdefault(0, 0.0)
            out.setdefault(1, 0.0)
            out.setdefault(2, 0.0)
            return out
        except Exception:
            return None

    def _account_equity_usd(self) -> float:
        try:
            return float(self.executor.get_account_equity_usd())
        except Exception:
            return 0.0

    def _position_details(self):
        return self.executor.get_position_details(self.symbol)

    def _get_price_best_effort(self, candle_close: float) -> tuple[float, str]:
        try:
            p = float(self.executor.get_mid_price(self.symbol))
            if p > 0:
                return p, "mid"
        except Exception:
            pass
        return float(candle_close), "candle_close"

    def _round_size(self, size: float) -> float:
        try:
            return float(self.executor.round_size(self.symbol, float(size)))
        except Exception:
            decimals = int(getattr(config, "SIZE_DECIMALS", 6))
            return float(round(float(size), decimals))

    def _close_position_fully(self) -> bool:
        try:
            self.executor.close_position_fully(self.symbol)
            return True
        except Exception as e:
            log_line(f"[TP/SL] close_position_fully failed: {e}")
            return False

    def _open_position(self, signal: str, size: float):
        self.executor.execute_order(signal, self._round_size(size), self.symbol, reduce_only=False)

    def _log_close_diagnostics(
        self,
        reason: str,
        position_side: str,
        position_size: float,
        entry_price: float,
        current_price: float,
        pnl_decimal: float,
        equity_usd: float,
    ):
        log_line(
            f"[CLOSE_DIAG] reason={reason} side={position_side} size={position_size:.8f} entry={entry_price:.2f} "
            f"price={current_price:.2f} pnl={pnl_decimal*100:+.4f}% equity={equity_usd:.2f} "
            f"TP={self.take_profit_decimal*100:.4f}% SL={self.stop_loss_decimal*100:.4f}% tf={self.candle_interval}"
        )

    def _maybe_run_advisor(self, context: dict):
        if not self.advisor:
            set_state(advisor=self._advisor_ui_snapshot())
            return

        if not self.advisor.should_run():
            set_state(advisor=self._advisor_ui_snapshot())
            return

        if not ollama_is_ready_recently():
            set_state(advisor=self._advisor_ui_snapshot())
            return

        try:
            out = self.advisor.run(context)
            if out:
                conf = float(out.get("confidence", 0.0))
                rec = str(out.get("recommendation", "NONE")).upper()
                bias = str(out.get("bias", "NEUTRAL")).upper()
                log_line(f"[ADVISOR] bias={bias} conf={conf:.2f} rec={rec} block={bool(out.get('block_trading'))} rationale={str(out.get('rationale',''))[:120]}")
                if ADVISOR_ALLOW_RUNTIME_TUNING and conf >= ADVISOR_MIN_CONFIDENCE:
                    rs = out.get("runtime_suggestions")
                    if isinstance(rs, dict):
                        self._queue_runtime_settings_from_advisor(rs)
            set_state(advisor=self._advisor_ui_snapshot())
        except Exception as e:
            if self.advisor:
                self.advisor.last_error = str(e)[:500]
            set_state(advisor=self._advisor_ui_snapshot())

    def run_cycle(self):
        # Apply runtime settings at loop start
        self._apply_pending_settings_if_any()

        # Pipeline heartbeat
        set_state(pipeline={"cycle_ts": datetime.now().isoformat(timespec="seconds"), "candle_interval": self.candle_interval})

        equity_usd = self._account_equity_usd()

        # Sentiment refresh
        now = time.time()
        if now - self.last_news_update_ts > self.news_refresh_seconds:
            try:
                self.sentiment_raw = float(self.news_handler.get_sentiment_score())
                self.last_news_update_ts = now
            except Exception as e:
                log_line(f"[NewsHandler] Error: {e}")

        self.sentiment_effective = float(self.sentiment_raw)
        sentiment_label = sentiment_label_from_score(self.sentiment_effective)

        # Market data (interval explicit)
        lookback = int(getattr(config, "LOOKBACK_CANDLES", DEFAULT_LOOKBACK_CANDLES))
        raw_df = self.market_data.get_latest_data(lookback_candles=lookback, interval=self.candle_interval)
        if raw_df is None or raw_df.empty:
            set_state(status="error", note="No market data.", advisor=self._advisor_ui_snapshot(), ollama=_ollama_ui_snapshot())
            return

        # Get microstructure features
        microstructure_features = self.market_data.get_microstructure_features()

        # Features (YOUR processor.py)
        feat_df = self.processor.prepare_features(raw_df, microstructure_features)
        if feat_df is None or feat_df.empty:
            set_state(status="error", note="Not enough data for features.", advisor=self._advisor_ui_snapshot(), ollama=_ollama_ui_snapshot())
            return

        last_row = feat_df.iloc[[-1]]
        candle_close = float(last_row["close"].iloc[0])
        current_price, price_source = self._get_price_best_effort(candle_close)

        # Feature list
        if self.cached_feature_list is None:
            self.cached_feature_list = self._build_feature_list(feat_df)
        features = self.cached_feature_list
        if any(f not in last_row.columns for f in features):
            self.cached_feature_list = self._build_feature_list(feat_df)
            features = self.cached_feature_list

        # Predict (+ pipeline AI telemetria)
        probabilities = None
        try:
            prediction_code = normalize_prediction(self.model.predict(last_row[features])[0])
            probabilities = self._predict_probabilities(last_row, features)

            ai_signal_tmp = "HOLD"
            if prediction_code == 1:
                ai_signal_tmp = "BUY"
            elif prediction_code == 2:
                ai_signal_tmp = "SELL"

            set_state(pipeline={
                "ai_ts": datetime.now().isoformat(timespec="seconds"),
                "ai_signal": ai_signal_tmp,
                "ai_probabilities": probabilities,
                "last_ai_error": None,
                "candle_interval": self.candle_interval,
            })

        except Exception as e:
            set_state(pipeline={
                "ai_ts": datetime.now().isoformat(timespec="seconds"),
                "last_ai_error": str(e)[:220],
                "candle_interval": self.candle_interval,
            })

            train_model()
            self.model = AIModel()
            prediction_code = normalize_prediction(self.model.predict(last_row[features])[0])
            probabilities = self._predict_probabilities(last_row, features)

        ai_raw_signal = "HOLD"
        if prediction_code == 1:
            ai_raw_signal = "BUY"
        elif prediction_code == 2:
            ai_raw_signal = "SELL"

        # Position snapshot
        details = self._position_details() or {}
        position_side = details.get("side", "NONE")
        position_size = float(details.get("size", 0.0) or 0.0)
        entry_price = float(details.get("entry_price", 0.0) or 0.0)

        # Sync TP/SL manager with real position always
        if position_side in ("LONG", "SHORT") and position_size > 0 and entry_price > 0:
            self.position_manager.arm_or_update(position_side, entry_price, position_size)
        else:
            if self.position_manager.active:
                self.position_manager.reset()

        # Exit probability ETA
        exit_probability = None
        exit_eta_median = None
        exit_eta_expected = None
        if probabilities is not None and position_side in ("LONG", "SHORT"):
            exit_probability = float(probabilities.get(2, 0.0)) if position_side == "LONG" else float(probabilities.get(1, 0.0))
            exit_eta_median, exit_eta_expected = estimate_exit_etas(exit_probability, self.loop_interval_seconds)

        # Ensemble telemetry
        close_series = raw_df["close"] if "close" in raw_df.columns else None
        high_series = raw_df["high"] if "high" in raw_df.columns else None
        low_series = raw_df["low"] if "low" in raw_df.columns else None

        rsi_value = None
        if "rsi" in last_row.columns:
            try:
                rsi_value = float(last_row["rsi"].iloc[0])
            except Exception:
                rsi_value = None

        adx_value = None
        if "adx" in last_row.columns:
            try:
                adx_value = float(last_row["adx"].iloc[0])
            except Exception:
                adx_value = None

        macd_value = None
        if "macd" in last_row.columns:
            try:
                macd_value = float(last_row["macd"].iloc[0])
            except Exception:
                macd_value = None

        macd_signal_value = None
        if "macd_signal" in last_row.columns:
            try:
                macd_signal_value = float(last_row["macd_signal"].iloc[0])
            except Exception:
                macd_signal_value = None

        ai_component = EnsembleScorer.artificial_intelligence_score(probabilities, ai_raw_signal)
        rl_component = EnsembleScorer.reinforcement_learning_score(last_row, features, self.rl_model)
        trend_component = EnsembleScorer.trend_following_score(
            close_series=close_series, current_price=current_price,
            ema_fast_period=TREND_FOLLOWING_EMA_FAST_PERIOD, ema_slow_period=TREND_FOLLOWING_EMA_SLOW_PERIOD
        )
        breakout_component = EnsembleScorer.breakout_score(
            high_series=high_series, low_series=low_series,
            current_price=current_price, lookback_periods=BREAKOUT_LOOKBACK_PERIODS
        )
        meanrev_component = EnsembleScorer.mean_reversion_score(
            rsi_value=rsi_value, oversold=MEAN_REVERSION_RSI_OVERSOLD, overbought=MEAN_REVERSION_RSI_OVERBOUGHT
        )
        trend_analysis_component = EnsembleScorer.trend_analysis_score(
            adx_value=adx_value, macd_value=macd_value, macd_signal_value=macd_signal_value,
            current_price=current_price, close_series=close_series
        )

        ensemble_score, ensemble_components = EnsembleScorer.ensemble_score(
            artificial_intelligence_component=ai_component,
            trend_following_component=trend_component,
            breakout_component=breakout_component,
            mean_reversion_component=meanrev_component,
            trend_analysis_component=trend_analysis_component,
            reinforcement_learning_component=rl_component,
            weight_artificial_intelligence=ENSEMBLE_WEIGHT_ARTIFICIAL_INTELLIGENCE,
            weight_trend_f=ENSEMBLE_WEIGHT_TREND_FOLLOWING,
            weight_breakout=ENSEMBLE_WEIGHT_BREAKOUT,
            weight_mean_rev=ENSEMBLE_WEIGHT_MEAN_REVERSION,
            weight_trend_analysis=ENSEMBLE_WEIGHT_TREND_ANALYSIS,
            weight_rl=ENSEMBLE_WEIGHT_REINFORCEMENT_LEARNING,
        )

        probabilities_out = None
        if probabilities is not None:
            probabilities_out = {
                "hold": float(probabilities.get(0, 0.0)),
                "buy": float(probabilities.get(1, 0.0)),
                "sell": float(probabilities.get(2, 0.0)),
            }

        # Advisor context + run (periodic)
        advisor_context = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "symbol": self.symbol,
            "price": float(current_price),
            "price_source": price_source,
            "candle_interval": self.candle_interval,
            "position": {
                "side": position_side,
                "size": float(position_size),
                "entry_price": float(entry_price),
            },
            "sentiment": {
                "raw": float(self.sentiment_raw),
                "effective": float(self.sentiment_effective),
                "label": sentiment_label,
            },
            "ml": {
                "ai_raw_signal": ai_raw_signal,
                "probabilities": probabilities_out,
            },
            "ensemble": {
                "score": float(ensemble_score),
                "components": ensemble_components,
                "threshold": float(ENSEMBLE_TRADE_THRESHOLD),
            },
            "runtime_settings": self._runtime_settings_snapshot(note="live"),
            "log_tail": log_tail(60),
        }
        if ADVISOR_ENABLED:
            self._maybe_run_advisor(advisor_context)

        action = "WAIT"
        note = ""
        pnl_dec = None

        # Helper: get advisor state for risk manager
        advisor_state = None
        try:
            advisor_state = self.advisor.last_json if (hasattr(self, "advisor") and self.advisor) else None
        except Exception:
            advisor_state = None

        # ====================================================
        # Manage open position FIRST (TP/SL + optional advisor CLOSE)
        # ====================================================
        if position_side in ("LONG", "SHORT") and self.position_manager.active:
            if ADVISOR_ALLOW_EARLY_CLOSE and self.advisor and self.advisor.last_json:
                aj = self.advisor.last_json
                try:
                    conf = float(aj.get("confidence", 0.0))
                except Exception:
                    conf = 0.0
                rec = str(aj.get("recommendation", "NONE")).upper()
                if conf >= ADVISOR_MIN_CONFIDENCE and rec == "CLOSE":
                    equity_usd = self._account_equity_usd()
                    pnl_tmp = self.position_manager.pnl_decimal(current_price)
                    self._log_close_diagnostics("ADVISOR_CLOSE", position_side, position_size, entry_price, current_price, pnl_tmp, equity_usd)
                    ok = self._close_position_fully()
                    action = f"CLOSE_ALL ({position_side})"
                    note = f"ADVISOR_CLOSE submit_ok={ok}"
                    self.position_manager.last_close_ts = time.time()
                    self.position_manager.last_reason = "ADVISOR_CLOSE"
                    self.position_manager.last_close_submit_ok = ok
                    self.position_manager.reset()

                    set_state(
                        status="live",
                        symbol=self.symbol,
                        price=float(current_price),
                        price_source=price_source,
                        position=position_side,
                        sentiment_raw=float(self.sentiment_raw),
                        sentiment_effective=float(self.sentiment_effective),
                        sentiment_label=sentiment_label,
                        artificial_intelligence_raw_signal=ai_raw_signal,
                        artificial_intelligence_final_signal="MANAGE_POSITION",
                        probabilities=probabilities_out,
                        ensemble_score=float(ensemble_score),
                        ensemble_components=ensemble_components,
                        action=action,
                        note=note,
                        equity_usd=float(equity_usd) if equity_usd is not None else None,
                        position_size=float(position_size) if position_size is not None else None,
                        entry_price=float(entry_price) if entry_price is not None else None,
                        exit_probability=float(exit_probability) if exit_probability is not None else None,
                        exit_eta_median=exit_eta_median.isoformat(timespec="seconds") if exit_eta_median else None,
                        exit_eta_expected=exit_eta_expected.isoformat(timespec="seconds") if exit_eta_expected else None,
                        runtime_settings=self._runtime_settings_snapshot(note="live"),
                        tp_sl={
                            "active": False,
                            "entry_price": float(entry_price) if entry_price else None,
                            "pnl_percent": None,
                            "take_profit_percent": float(self.take_profit_decimal * 100.0),
                            "stop_loss_percent": float(self.stop_loss_decimal * 100.0),
                            "last_reason": "ADVISOR_CLOSE",
                            "last_close_submit_ok": ok,
                        },
                        ollama=_ollama_ui_snapshot(),
                        advisor=self._advisor_ui_snapshot(),
                    )
                    return

            decision, reason, pnl = self.position_manager.decide(
                current_price=current_price,
                tp_dec=self.take_profit_decimal,
                sl_dec=self.stop_loss_decimal,
            )
            pnl_dec = float(pnl)

            if decision == "CLOSE_ALL":
                equity_usd = self._account_equity_usd()
                self._log_close_diagnostics(reason, position_side, position_size, entry_price, current_price, pnl_dec, equity_usd)

                ok = self._close_position_fully()
                action = f"CLOSE_ALL ({position_side})"
                note = f"{reason} submit_ok={ok}"
                self.position_manager.last_close_ts = time.time()
                self.position_manager.last_reason = reason
                self.position_manager.last_close_submit_ok = ok
                self.position_manager.reset()
            else:
                action = "MANAGE_OPEN_POSITION"
                note = f"pnl={pnl_dec*100:+.3f}% ({price_source})"

            set_state(
                status="live",
                symbol=self.symbol,
                price=float(current_price),
                price_source=price_source,
                position=position_side,
                sentiment_raw=float(self.sentiment_raw),
                sentiment_effective=float(self.sentiment_effective),
                sentiment_label=sentiment_label,
                artificial_intelligence_raw_signal=ai_raw_signal,
                artificial_intelligence_final_signal="MANAGE_POSITION",
                probabilities=probabilities_out,
                ensemble_score=float(ensemble_score),
                ensemble_components=ensemble_components,
                action=action,
                note=note,
                equity_usd=float(equity_usd) if equity_usd is not None else None,
                position_size=float(position_size) if position_size is not None else None,
                entry_price=float(entry_price) if entry_price is not None else None,
                exit_probability=float(exit_probability) if exit_probability is not None else None,
                exit_eta_median=exit_eta_median.isoformat(timespec="seconds") if exit_eta_median else None,
                exit_eta_expected=exit_eta_expected.isoformat(timespec="seconds") if exit_eta_expected else None,
                runtime_settings=self._runtime_settings_snapshot(note="live"),
                tp_sl={
                    "active": True if position_side in ("LONG", "SHORT") else False,
                    "entry_price": float(entry_price) if entry_price else None,
                    "pnl_percent": float(pnl_dec * 100.0) if pnl_dec is not None else None,
                    "take_profit_percent": float(self.take_profit_decimal * 100.0),
                    "stop_loss_percent": float(self.stop_loss_decimal * 100.0),
                    "last_reason": self.position_manager.last_reason,
                    "last_close_submit_ok": self.position_manager.last_close_submit_ok,
                },
                ollama=_ollama_ui_snapshot(),
                advisor=self._advisor_ui_snapshot(),
            )
            return

        # ====================================================
        # Entry logic when flat
        # ====================================================
        final_decision = EnsembleScorer.decision_from_score(ensemble_score, ENSEMBLE_TRADE_THRESHOLD)

        if position_side == "NONE":
            if not self.position_manager.can_reopen():
                final_decision = "HOLD"
                action = "WAIT"
                note = f"Reopen cooldown active: {REOPEN_COOLDOWN_SECONDS}s"
            else:
                # Sentiment blocks
                if final_decision == "BUY" and self.sentiment_effective <= SENTIMENT_BLOCK_BUY_BELOW:
                    final_decision = "HOLD"
                    note = "Entry blocked by sentiment (too negative for BUY)."
                elif final_decision == "SELL" and self.sentiment_effective >= SENTIMENT_BLOCK_SELL_ABOVE:
                    final_decision = "HOLD"
                    note = "Entry blocked by sentiment (too positive for SELL)."

                if final_decision in ("BUY", "SELL"):
                    # Entry confirmation gates
                    if ENTRY_CONFIRMATION_REQUIRED:
                        ok_confirm = True
                        if final_decision == "BUY":
                            if trend_component is not None and float(trend_component) < ENTRY_MIN_TREND:
                                ok_confirm = False
                                note = (note + " | " if note else "") + f"Trend weak for BUY ({float(trend_component):+.3f} < {ENTRY_MIN_TREND})"
                            if breakout_component is not None and float(breakout_component) < ENTRY_MIN_BREAKOUT:
                                ok_confirm = False
                                note = (note + " | " if note else "") + f"Breakout weak for BUY ({float(breakout_component):+.3f} < {ENTRY_MIN_BREAKOUT})"
                            if adx_value is not None and float(adx_value) < ENTRY_MIN_ADX:
                                ok_confirm = False
                                note = (note + " | " if note else "") + f"ADX too low ({float(adx_value):.1f} < {ENTRY_MIN_ADX})"
                        elif final_decision == "SELL":
                            if trend_component is not None and float(trend_component) > -ENTRY_MIN_TREND:
                                ok_confirm = False
                                note = (note + " | " if note else "") + f"Trend weak for SELL ({float(trend_component):+.3f} > {-ENTRY_MIN_TREND})"
                            if breakout_component is not None and float(breakout_component) > -ENTRY_MIN_BREAKOUT:
                                ok_confirm = False
                                note = (note + " | " if note else "") + f"Breakout weak for SELL ({float(breakout_component):+.3f} > {-ENTRY_MIN_BREAKOUT})"
                            if adx_value is not None and float(adx_value) < ENTRY_MIN_ADX:
                                ok_confirm = False
                                note = (note + " | " if note else "") + f"ADX too low ({float(adx_value):.1f} < {ENTRY_MIN_ADX})"

                        if not ok_confirm:
                            final_decision = "HOLD"
                            action = "WAIT"

                    equity = self._account_equity_usd()
                    notional = equity * float(self.equity_fraction_per_entry) * float(self.leverage_target)
                    if equity <= 0 or notional <= 0:
                        action = "OPEN_BLOCKED"
                        note = (note + " | " if note else "") + f"Equity invalid. equity={equity:.2f}"
                    else:
                        raw_size = notional / float(current_price)
                        size = self._round_size(raw_size)

                        # Ensemble magnitude-based size scaling
                        if ENTRY_SIZE_SCALE_BY_ENSEMBLE and isinstance(ensemble_score, (int, float)):
                            mag = abs(float(ensemble_score))
                            scale = max(0.25, min(1.0, mag))
                            if scale < 1.0:
                                size = self._round_size(size * scale)
                                note = (note + " | " if note else "") + f"Size scaled x{scale:.2f} by ensemble"

                        # ---- RISK GATE (includes advisor gating in risk manager) ----
                        try:
                            allowed, risk_reason, size_mult = self.risk.check_risk(
                                final_decision,
                                position_side,
                                current_size=position_size,
                                proposed_size=size,
                                equity_usd=equity,
                                current_price=current_price,
                                advisor=advisor_state,
                            )
                            set_state(pipeline={
                                "risk_ts": datetime.now().isoformat(timespec="seconds"),
                                "risk_allowed": bool(allowed),
                                "risk_reason": str(risk_reason)[:220],
                                "risk_size_mult": float(size_mult),
                                "last_risk_error": None,
                                "ensemble_decision": str(final_decision),
                                "candle_interval": self.candle_interval,
                            })
                        except Exception as e:
                            allowed, risk_reason, size_mult = False, f"risk_exception: {e}", 1.0
                            set_state(pipeline={
                                "risk_ts": datetime.now().isoformat(timespec="seconds"),
                                "risk_allowed": False,
                                "risk_reason": str(risk_reason)[:220],
                                "risk_size_mult": 1.0,
                                "last_risk_error": str(e)[:220],
                                "ensemble_decision": str(final_decision),
                                "candle_interval": self.candle_interval,
                            })
                        # ----------------------------------------------------------------

                        if not allowed:
                            action = "OPEN_BLOCKED"
                            note = (note + " | " if note else "") + f"Risk blocked: {risk_reason}"
                            final_decision = "HOLD"
                        else:
                            if size_mult != 1.0:
                                size = self._round_size(size * float(size_mult))
                                note = (note + " | " if note else "") + f"Risk size_mult={float(size_mult):.2f} ({risk_reason})"

                        # Min size check + open
                        if final_decision in ("BUY", "SELL"):
                            min_size = float(getattr(config, "MIN_ORDER_SIZE", 0.0))
                            if min_size <= 0.0:
                                min_size = 0.0001 if self.symbol == "BTC" else 0.001

                            if size < min_size:
                                action = "OPEN_BLOCKED"
                                note = (note + " | " if note else "") + f"size below min. size={size} min={min_size}"
                            else:
                                # --- Fibonacci: compute levels and set TP/SL automatically (PRIMARY) ---
                                fib_success = False
                                try:
                                    if FIB_ENABLED and high_series is not None and low_series is not None and len(high_series) >= 3 and len(low_series) >= 3:
                                        # use last N bars to determine swing
                                        hb = high_series.iloc[-FIB_LOOKBACK:] if len(high_series) >= FIB_LOOKBACK else high_series
                                        lb = low_series.iloc[-FIB_LOOKBACK:] if len(low_series) >= FIB_LOOKBACK else low_series
                                        swing_high = float(hb.max())
                                        swing_low = float(lb.min())
                                        fib_levels = compute_fibonacci_levels(swing_high, swing_low)

                                        # Choose TP/SL by config (extension for TP, retracement for SL)
                                        tp_price = fib_levels.get(float(FIB_TP_EXTENSION)) if float(FIB_TP_EXTENSION) in fib_levels else None
                                        sl_price = fib_levels.get(float(FIB_SL_RETRACEMENT)) if float(FIB_SL_RETRACEMENT) in fib_levels else None

                                        # Fallback: if missing, compute via linear interpolation
                                        span = swing_high - swing_low if swing_high and swing_low else None
                                        if tp_price is None and span is not None:
                                            tp_price = swing_low + span * float(FIB_TP_EXTENSION)
                                        if sl_price is None and span is not None:
                                            sl_price = swing_low + span * float(FIB_SL_RETRACEMENT)

                                        if tp_price and sl_price and current_price and current_price > 0:
                                            if final_decision == "BUY":
                                                tp_dec = (float(tp_price) - float(current_price)) / float(current_price)
                                                sl_dec = (float(current_price) - float(sl_price)) / float(current_price)
                                            else:
                                                # SELL (short)
                                                tp_dec = (float(current_price) - float(tp_price)) / float(current_price)
                                                sl_dec = (float(sl_price) - float(current_price)) / float(current_price)

                                            # sanitize
                                            tp_dec = clamp(tp_dec, 0.0, 1.0)
                                            sl_dec = clamp(sl_dec, 0.0, 1.0)

                                            # Apply for this bot instance (affects TP/SL manager)
                                            self.take_profit_decimal = float(tp_dec)
                                            self.stop_loss_decimal = float(sl_dec)
                                            fib_success = True

                                            # Arm local TP/SL manager with estimated entry
                                            try:
                                                self.position_manager.arm_or_update("LONG" if final_decision == "BUY" else "SHORT", float(current_price), float(size))
                                            except Exception:
                                                pass

                                            note = (note + " | " if note else "") + f"Fib: TP={tp_dec*100:.2f}% SL={sl_dec*100:.2f}%"

                                            # Try drawing the Fibonacci on the exchange/chart (best-effort)
                                            try:
                                                ann = {
                                                    "type": "fibonacci",
                                                    "symbol": self.symbol,
                                                    "swing_high": float(swing_high),
                                                    "swing_low": float(swing_low),
                                                    "tp_price": float(tp_price),
                                                    "sl_price": float(sl_price),
                                                    "tp_level": float(FIB_TP_EXTENSION),
                                                    "sl_level": float(FIB_SL_RETRACEMENT),
                                                    "levels": {str(k): v for k, v in fib_levels.items()},
                                                    "side": final_decision,
                                                    "entry_price": float(current_price),
                                                    "created_ts": datetime.now().isoformat(timespec="seconds"),
                                                }
                                                exch = getattr(self.executor, "exchange", None)
                                                if exch is not None:
                                                    if hasattr(exch, "create_annotation"):
                                                        try:
                                                            exch.create_annotation(ann)
                                                        except Exception:
                                                            pass
                                                    elif hasattr(exch, "add_annotation"):
                                                        try:
                                                            exch.add_annotation(ann)
                                                        except Exception:
                                                            pass
                                                # save to public state so web UI shows it
                                                set_state(runtime_settings=self._runtime_settings_snapshot(note="live"),
                                                          tp_sl={
                                                              "active": None,
                                                              "entry_price": float(current_price),
                                                              "pnl_percent": None,
                                                              "take_profit_percent": float(self.take_profit_decimal * 100.0),
                                                              "stop_loss_percent": float(self.stop_loss_decimal * 100.0),
                                                              "last_reason": "FIB_AUTO",
                                                              "last_close_submit_ok": None,
                                                          },
                                                          last_fibonacci={
                                                              "swing_high": float(swing_high),
                                                              "swing_low": float(swing_low),
                                                              "levels": {str(k): v for k, v in fib_levels.items()},
                                                              "tp_price": float(tp_price),
                                                              "sl_price": float(sl_price),
                                                          })
                                            except Exception as e:
                                                log_line(f"[FIB] error while preparing annotation/state: {e}")
                                except Exception as e:
                                    # Non-fatal Fibonacci error: fall back to fixed TP/SL
                                    log_line(f"[FIB] Fibonacci TP/SL failed ({e}), using fallback TP/SL")
                                    if not fib_success:
                                        # Use fixed TP/SL as fallback
                                        self.take_profit_decimal = float(TAKE_PROFIT_DECIMAL)
                                        self.stop_loss_decimal = float(STOP_LOSS_DECIMAL)
                                        try:
                                            self.position_manager.arm_or_update("LONG" if final_decision == "BUY" else "SHORT", float(current_price), float(size))
                                        except Exception:
                                            pass
                                        note = (note + " | " if note else "") + f"Fallback TP/SL: {self.take_profit_decimal*100:.2f}% / {self.stop_loss_decimal*100:.2f}%"

                                self._open_position("BUY" if final_decision == "BUY" else "SELL", size)
                                self.risk.update_trade_time()
                                action = f"OPEN {final_decision}"
                                note = (note + " | " if note else "") + f"Ensemble score={ensemble_score:+.3f} ({price_source}) tf={self.candle_interval}"
                else:
                    action = "WAIT"
                    note = (note + " | " if note else "") + f"Ensemble below threshold: {ensemble_score:+.3f}"

        set_state(
            status="live",
            symbol=self.symbol,
            price=float(current_price),
            price_source=price_source,
            position=position_side,
            sentiment_raw=float(self.sentiment_raw),
            sentiment_effective=float(self.sentiment_effective),
            sentiment_label=sentiment_label,
            artificial_intelligence_raw_signal=ai_raw_signal,
            artificial_intelligence_final_signal=final_decision,
            probabilities=probabilities_out,
            ensemble_score=float(ensemble_score),
            ensemble_components=ensemble_components,
            action=action,
            note=note,
            exit_probability=float(exit_probability) if exit_probability is not None else None,
            exit_eta_median=exit_eta_median.isoformat(timespec="seconds") if exit_eta_median else None,
            exit_eta_expected=exit_eta_expected.isoformat(timespec="seconds") if exit_eta_expected else None,
            runtime_settings=self._runtime_settings_snapshot(note="live"),
            tp_sl={
                "active": bool(self.position_manager.active),
                "entry_price": float(entry_price) if entry_price else None,
                "pnl_percent": float(pnl_dec * 100.0) if pnl_dec is not None else None,
                "take_profit_percent": float(self.take_profit_decimal * 100.0),
                "stop_loss_percent": float(self.stop_loss_decimal * 100.0),
                "last_reason": self.position_manager.last_reason,
                "last_close_submit_ok": self.position_manager.last_close_submit_ok,
                "trailing_active": USE_TRAILING_STOP_LOSS,
                "trailing_stop_price": getattr(self.position_manager, 'trailing_stop_price', None),
                "trailing_levels": getattr(self.position_manager, 'trailing_levels', []),
            },
            ollama=_ollama_ui_snapshot(),
            advisor=self._advisor_ui_snapshot(),
        )

        log_line(
            f"[CYCLE] {self.symbol} price={current_price:.2f}({price_source}) tf={self.candle_interval} pos={position_side} "
            f"AI={ai_raw_signal} ens={ensemble_score:+.3f} action={action} note={note}"
        )

    def run(self):
        while True:
            if self.iteration_counter >= self.retrain_interval_cycles:
                try:
                    train_model()
                    self.model = AIModel()
                    self.cached_feature_list = None
                    self.iteration_counter = 0
                    log_line("[AI] Retraining OK")
                except Exception as e:
                    log_line(f"[AI] Retraining error: {e}")

            try:
                self.run_cycle()
            except Exception as e:
                set_state(status="error", note=f"Bot error: {e}", advisor=self._advisor_ui_snapshot(), ollama=_ollama_ui_snapshot())
                log_line(f"[BOT] Error: {e}")

            self.iteration_counter += 1
            time.sleep(self.loop_interval_seconds)


# ============================================================
# Web UI (Flask)
# ============================================================
WWWROOT_DIR = os.path.join(os.path.dirname(__file__), "wwwroot")
if not os.path.isdir(WWWROOT_DIR):
    raise RuntimeError(f"wwwroot folder not found: {WWWROOT_DIR}")

app = Flask(__name__, static_folder=WWWROOT_DIR)


@app.get("/")
def index():
    return send_from_directory(WWWROOT_DIR, "index.html")


@app.get("/status")
def status():
    response = jsonify(STATE)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.get("/ohlcv")
def ohlcv_latest():
    """Return latest OHLCV candles fetched from Hyperliquid via MarketDataHandler.

    Query params:
      - limit: number of candles (default 500)
      - interval: candle interval (default from config.CANDLE_INTERVAL)
      - symbol: optional override for symbol (defaults to handler.symbol)
    """
    try:
        limit = int(request.args.get("limit", 500))
        interval = str(request.args.get("interval", getattr(config, "CANDLE_INTERVAL", "1m")))
        symbol_override = request.args.get("symbol")

        md = MarketDataHandler()
        if symbol_override:
            try:
                md.symbol = str(symbol_override).strip() or md.symbol
            except Exception:
                pass

        df = md.get_latest_data(lookback_candles=limit, interval=interval)
        if df is None or df.empty:
            return jsonify({"ok": False, "symbol": md.symbol, "interval": interval, "candles": []})

        # Normalize columns
        cols = {c.lower(): c for c in df.columns}
        ts_col = cols.get("timestamp") or cols.get("time") or cols.get("t")
        o_col = cols.get("open")
        h_col = cols.get("high")
        l_col = cols.get("low")
        c_col = cols.get("close")
        v_col = cols.get("volume") if "volume" in cols else None

        candles = []
        for _, row in df.iterrows():
            try:
                item = {
                    "t": int(row[ts_col]),
                    "o": float(row[o_col]),
                    "h": float(row[h_col]),
                    "l": float(row[l_col]),
                    "c": float(row[c_col]),
                }
                if v_col:
                    item["v"] = float(row[v_col])
                candles.append(item)
            except Exception:
                continue

        return jsonify({"ok": True, "symbol": md.symbol, "interval": interval, "candles": candles})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/runtime-settings/apply")
def apply_runtime_settings():
    payload = request.get_json(force=True, silent=True) or {}
    global PENDING_SETTINGS

    try:
        leverage_target = float(payload.get("leverage_target", getattr(config, "DEFAULT_LEVERAGE", 10)))
        margin_mode_target = str(payload.get("margin_mode_target", getattr(config, "MARGIN_MODE", "cross"))).lower()
        take_profit_percent = float(payload.get("take_profit_percent", decimal_to_percent(TAKE_PROFIT_DECIMAL)))
        stop_loss_percent = float(payload.get("stop_loss_percent", decimal_to_percent(STOP_LOSS_DECIMAL)))
        equity_fraction_percent = float(payload.get("equity_fraction_percent", EQUITY_FRACTION_PER_ENTRY * 100.0))
        candle_interval = str(payload.get("candle_interval", getattr(config, "CANDLE_INTERVAL", DEFAULT_CANDLE_INTERVAL))).strip() or DEFAULT_CANDLE_INTERVAL

        pending = {
            "leverage_target": clamp(leverage_target, 1.0, 100.0),
            "margin_mode_target": "cross" if margin_mode_target not in ("cross", "isolated") else margin_mode_target,
            "take_profit_decimal": clamp(percent_to_decimal(take_profit_percent), 0.0, 1.0),
            "stop_loss_decimal": clamp(percent_to_decimal(stop_loss_percent), 0.0, 1.0),
            "equity_fraction_per_entry": clamp(equity_fraction_percent / 100.0, 0.01, 1.0),
            "candle_interval": candle_interval,
        }

        with PENDING_SETTINGS_LOCK:
            PENDING_SETTINGS = pending

        return jsonify({"ok": True, "message": "Settings queued. Applied at start of next cycle."})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 400


@app.get("/runtime-settings/current")
def runtime_settings_current():
    with STATE_LOCK:
        response = jsonify({"ok": True, "runtime_settings": STATE.get("runtime_settings")})
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response


@app.get("/copilot/ollama_info")
def copilot_ollama_info():
    return jsonify({"ok": True, "ollama": _ollama_ui_snapshot()})


@app.get("/health")
def health():
    return "ok", 200


def start_bot():
    bot = HyperliquidBot()
    bot.run()


if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    log_line("[WEB] http://127.0.0.1:8080")
    if os.getenv("OLLAMA_WARMUP_ON_START", "1").strip() == "1":
        threading.Thread(target=ollama_warmup_async, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True, use_reloader=False)
