import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import pandas as pd
from hyperliquid.info import Info

import config


@dataclass(frozen=True)
class CandleRequest:
    symbol: str
    interval: str
    start_ms: int
    end_ms: int


class MarketDataHandler:
    """
    Market data handler for Hyperliquid candles.

    IMPORTANT:
    - Candles come from the environment defined by config.BASE_URL.
      If BASE_URL points to testnet -> testnet candles.
      If BASE_URL points to mainnet -> mainnet candles.
    """

    def __init__(self):
        self.base_url = getattr(config, "BASE_URL", None)
        if not self.base_url:
            raise ValueError("config.BASE_URL is missing. Cannot initialize market data Info client.")

        self.symbol = getattr(config, "SYMBOL", "BTC")
        self.default_interval = getattr(config, "CANDLE_INTERVAL", "1m")
        self.info = Info(self.base_url, skip_ws=True)

    def get_environment_info(self) -> Dict[str, str]:
        return {
            "base_url": str(self.base_url),
            "symbol": str(self.symbol),
            "default_interval": str(self.default_interval),
        }

    def get_historical_ohlcv(
        self,
        limit: int = 5000,
        interval: Optional[str] = None,
        end_time_ms: Optional[int] = None,
        allow_multi_fetch: bool = True,
        max_per_request: int = 5000,
        request_pause_seconds: float = 0.15,
    ) -> Optional[pd.DataFrame]:
        interval = interval or self.default_interval
        limit = int(limit)
        if limit <= 0:
            raise ValueError("limit must be > 0")

        end_time_ms = int(end_time_ms or (time.time() * 1000))

        candle_ms = self._interval_to_milliseconds(interval)
        if candle_ms <= 0:
            raise ValueError(f"Unsupported interval: {interval!r}")

        if (limit <= max_per_request) or (not allow_multi_fetch):
            start_time_ms = end_time_ms - limit * candle_ms
            candles = self._fetch_candles(CandleRequest(self.symbol, interval, start_time_ms, end_time_ms))
            df = self._candles_to_dataframe(candles)
            return self._finalize_dataframe(df)

        remaining = limit
        chunk_end = end_time_ms
        frames: List[pd.DataFrame] = []

        while remaining > 0:
            chunk_limit = min(max_per_request, remaining)
            chunk_start = chunk_end - chunk_limit * candle_ms

            candles = self._fetch_candles(CandleRequest(self.symbol, interval, chunk_start, chunk_end))
            df = self._candles_to_dataframe(candles)
            df = self._finalize_dataframe(df)
            if df is not None and not df.empty:
                frames.append(df)

            remaining -= chunk_limit
            chunk_end = chunk_start
            time.sleep(float(request_pause_seconds))

        if not frames:
            return None

        merged = pd.concat(frames, axis=0, ignore_index=True)
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        merged = merged.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

        if len(merged) > limit:
            merged = merged.iloc[-limit:].reset_index(drop=True)

        return merged

    def get_latest_data(
        self,
        lookback_candles: int = 200,
        interval: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        interval = interval or self.default_interval
        lookback_candles = int(lookback_candles)
        if lookback_candles <= 0:
            lookback_candles = 200

        candle_ms = self._interval_to_milliseconds(interval)
        end_time_ms = int(time.time() * 1000)
        start_time_ms = end_time_ms - lookback_candles * candle_ms

        candles = self._fetch_candles(CandleRequest(self.symbol, interval, start_time_ms, end_time_ms))
        df = self._candles_to_dataframe(candles)
        return self._finalize_dataframe(df)

    def _fetch_candles(self, req: CandleRequest) -> List[Dict[str, Any]]:
        try:
            candles = self.info.candles_snapshot(req.symbol, req.interval, req.start_ms, req.end_ms)
            if not candles:
                return []
            if not isinstance(candles, list):
                if isinstance(candles, dict) and "candles" in candles and isinstance(candles["candles"], list):
                    return candles["candles"]
                return []
            return candles
        except Exception as e:
            print(
                f"[MarketData] candles_snapshot error: {e} | symbol={req.symbol} interval={req.interval} "
                f"start={req.start_ms} end={req.end_ms} base_url={self.base_url}"
            )
            return []

    def _candles_to_dataframe(self, candles: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
        if not candles:
            return None

        df = pd.DataFrame(candles)
        if df.empty:
            return None

        column_map = {
            "t": "timestamp",
            "timestamp": "timestamp",
            "time": "timestamp",
            "o": "open",
            "open": "open",
            "h": "high",
            "high": "high",
            "l": "low",
            "low": "low",
            "c": "close",
            "close": "close",
            "v": "volume",
            "volume": "volume",
        }

        rename_dict = {}
        for col in df.columns:
            if col in column_map:
                rename_dict[col] = column_map[col]
        df = df.rename(columns=rename_dict)

        needed = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            print(f"[MarketData] Missing expected candle columns: {missing}. Available columns: {list(df.columns)}")
            return None

        df = df[needed].copy()

        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def _finalize_dataframe(self, df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None

        df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
        if df.empty:
            return None

        df["timestamp"] = df["timestamp"].astype("int64")

        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

        df = df[
            (df["high"] >= df["low"]) &
            (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0) & (df["open"] > 0)
        ].copy()
        if df.empty:
            return None

        return df

    @staticmethod
    def _interval_to_milliseconds(interval: str) -> int:
        s = str(interval).strip().lower()
        if len(s) < 2:
            return 0

        unit = s[-1]
        value_str = s[:-1]
        try:
            value = int(value_str)
        except Exception:
            return 0

        if value <= 0:
            return 0

        if unit == "m":
            return value * 60_000
        if unit == "h":
            return value * 3_600_000
        if unit == "d":
            return value * 86_400_000
        return 0
