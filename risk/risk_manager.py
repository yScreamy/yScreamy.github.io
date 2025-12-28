# risk/risk_manager.py
import time
import config


class RiskManager:
    """
    Risk gatekeeper for trade decisions.

    Inputs:
      - signal: "BUY" | "SELL" | "HOLD"
      - current_position: "NONE" | "LONG" | "SHORT"
      - current_size: float (position size in asset units, optional)
      - entry_price: float (optional)
      - current_price: float (optional)
      - equity_usd: float (optional)
      - advisor: dict (optional) like:
          {
            "confidence": 0.78,
            "recommendation": "BLOCK|REDUCE_RISK|ALLOW|NONE",
            "block_trading": true/false,
            "bias": "LONG|SHORT|NEUTRAL",
            "rationale": "..."
          }

    Output:
      (allowed: bool, reason: str, size_multiplier: float)
    """

    def __init__(self):
        # Cooldown: avoid overtrading
        self.cooldown_period = int(getattr(config, "RISK_COOLDOWN_SECONDS", 300))
        self.last_trade_time = 0.0

        # Exposure control (optional / best-effort)
        # If your bot sizes in coin units, this can be used as a hard cap.
        default_order_size = float(getattr(config, "DEFAULT_ORDER_SIZE", 0.0))
        self.max_position_size = float(getattr(config, "MAX_POSITION_SIZE", default_order_size * 5 if default_order_size > 0 else 0.0))

        # Advisor gating defaults (can be overridden in config)
        self.advisor_gate_entries = bool(getattr(config, "ADVISOR_GATE_ENTRIES", True))
        self.advisor_min_confidence = float(getattr(config, "ADVISOR_MIN_CONFIDENCE", 0.65))
        self.advisor_reduce_risk_multiplier = float(getattr(config, "ADVISOR_REDUCE_RISK_MULT", 0.5))

        # Daily risk caps
        self.max_trades_per_day = int(getattr(config, "MAX_TRADES_PER_DAY", 0))
        self.max_loss_trades_per_day = int(getattr(config, "MAX_LOSS_TRADES_PER_DAY", 0))
        self.max_daily_drawdown_pct = float(getattr(config, "MAX_DAILY_DRAWDOWN_PCT", 0.0))
        self.max_daily_risk_usd = float(getattr(config, "MAX_DAILY_RISK_USD", 0.0))

        self._day_start_ts = 0.0
        self._trades_today = 0
        self._loss_trades_today = 0
        self._daily_pnl_usd = 0.0
        self._day_peak_equity_usd = None
        self._day_start_equity_usd = None

    def _now(self) -> float:
        return time.time()

    def update_trade_time(self):
        self.last_trade_time = self._now()
        # Count trades per day (simple open counter)
        self._ensure_day_window()
        self._trades_today += 1

    def _cooldown_ok(self) -> bool:
        if self.cooldown_period <= 0:
            return True
        return (self._now() - float(self.last_trade_time)) >= float(self.cooldown_period)

    def _ensure_day_window(self):
        """Reset counters if a new UTC day started."""
        now = self._now()
        if self._day_start_ts <= 0:
            self._day_start_ts = now
            self._trades_today = 0
            self._loss_trades_today = 0
            self._daily_pnl_usd = 0.0
            self._day_peak_equity_usd = None
            self._day_start_equity_usd = None
            return
        # Reset if 24h passed (simplified window)
        if (now - self._day_start_ts) >= 24 * 3600:
            self._day_start_ts = now
            self._trades_today = 0
            self._loss_trades_today = 0
            self._daily_pnl_usd = 0.0
            self._day_peak_equity_usd = None
            self._day_start_equity_usd = None

    def update_on_close(self, pnl_decimal: float, equity_usd: float | None):
        """Update daily stats on position close."""
        self._ensure_day_window()
        try:
            eq = float(equity_usd) if equity_usd is not None else 0.0
            if self._day_start_equity_usd is None and eq > 0:
                self._day_start_equity_usd = eq
            # Approximate pnl in USD using equity * pnl_decimal (rough)
            usd_pnl = (eq * float(pnl_decimal)) if eq > 0 else 0.0
            self._daily_pnl_usd += usd_pnl
            if float(pnl_decimal) < 0:
                self._loss_trades_today += 1
        except Exception:
            pass

    @staticmethod
    def _normalize_signal(signal: str) -> str:
        s = str(signal or "").strip().upper()
        if s in ("BUY", "SELL", "HOLD"):
            return s
        # tolerate common alternatives
        if s in ("LONG", "B"):
            return "BUY"
        if s in ("SHORT", "S"):
            return "SELL"
        if s in ("NONE", "0", ""):
            return "HOLD"
        return "HOLD"

    @staticmethod
    def _normalize_position(pos: str) -> str:
        p = str(pos or "").strip().upper()
        if p in ("NONE", "LONG", "SHORT"):
            return p
        if p in ("FLAT",):
            return "NONE"
        return "NONE"

    def check_risk(
        self,
        signal: str,
        current_position: str,
        *,
        current_size: float = 0.0,
        proposed_size: float | None = None,
        equity_usd: float | None = None,
        current_price: float | None = None,
        advisor: dict | None = None,
    ):
        """
        Returns:
          allowed (bool),
          reason (str),
          size_multiplier (float)
        """
        sig = self._normalize_signal(signal)
        pos = self._normalize_position(current_position)

        # Safety mode: block new openings
        if bool(getattr(config, "SAFE_MODE", False)) and pos == "NONE":
            return False, "SAFE_MODE active", 1.0

        # Prepare daily window and drawdown checks
        self._ensure_day_window()
        try:
            if equity_usd is not None:
                eq = float(equity_usd)
                if self._day_start_equity_usd is None and eq > 0:
                    self._day_start_equity_usd = eq
                if self._day_peak_equity_usd is None or eq > float(self._day_peak_equity_usd):
                    self._day_peak_equity_usd = eq
        except Exception:
            pass

        # 1) No signal => no trade
        if sig == "HOLD":
            return False, "HOLD signal", 1.0

        # 2) Daily caps
        if self.max_trades_per_day > 0 and self._trades_today >= self.max_trades_per_day:
            return False, f"Max trades/day reached ({self._trades_today}/{self.max_trades_per_day})", 1.0
        if self.max_loss_trades_per_day > 0 and self._loss_trades_today >= self.max_loss_trades_per_day:
            return False, f"Max loss trades/day reached ({self._loss_trades_today}/{self.max_loss_trades_per_day})", 1.0
        if self.max_daily_risk_usd > 0 and (-self._daily_pnl_usd) >= self.max_daily_risk_usd:
            return False, f"Max daily risk USD reached ({-self._daily_pnl_usd:.2f} >= {self.max_daily_risk_usd:.2f})", 1.0

        # 3) Drawdown cap (relative to peak)
        if self.max_daily_drawdown_pct > 0 and self._day_peak_equity_usd and equity_usd:
            try:
                peak = float(self._day_peak_equity_usd)
                cur = float(equity_usd)
                if peak > 0:
                    dd_pct = (peak - cur) / peak * 100.0
                    if dd_pct >= self.max_daily_drawdown_pct:
                        return False, f"Daily drawdown cap hit ({dd_pct:.2f}% >= {self.max_daily_drawdown_pct:.2f}%)", 1.0
            except Exception:
                pass

        # 4) Cooldown
        if not self._cooldown_ok():
            dt = int(self._now() - self.last_trade_time)
            return False, f"Cooldown active ({dt}s/{self.cooldown_period}s)", 1.0

        # 5) Position collision (no duplicate direction)
        if sig == "BUY" and pos == "LONG":
            return False, "Already in LONG", 1.0
        if sig == "SELL" and pos == "SHORT":
            return False, "Already in SHORT", 1.0

        # 6) Max exposure (best-effort)
        # If max_position_size is configured (>0), reject any trade that would exceed it.
        # For simplicity we compare on units; if you want notional-based, we can do it too.
        if self.max_position_size and self.max_position_size > 0:
            try:
                cur = float(current_size or 0.0)
                prop = float(proposed_size) if proposed_size is not None else 0.0
                # If flipping direction, the order might close + open; you can relax this if needed.
                # Here we conservatively cap based on proposed size alone.
                if prop > 0 and prop > float(self.max_position_size):
                    return False, f"Proposed size exceeds max_position_size ({prop} > {self.max_position_size})", 1.0
                # Optional: if currently flat and prop+cur > cap (usually cur=0 when flat)
                if prop > 0 and (cur + prop) > float(self.max_position_size) and pos == "NONE":
                    return False, f"Exposure cap hit (cur+prop={cur+prop} > {self.max_position_size})", 1.0
            except Exception:
                # If something is weird, don't block by exposure
                pass

        # 7) Advisor gating (optional)
        size_mult = 1.0
        if self.advisor_gate_entries and advisor and pos == "NONE":
            try:
                conf = float(advisor.get("confidence", 0.0))
            except Exception:
                conf = 0.0

            if conf >= self.advisor_min_confidence:
                rec = str(advisor.get("recommendation", "NONE")).upper()
                block = bool(advisor.get("block_trading", False))
                bias = str(advisor.get("bias", "NEUTRAL")).upper()

                # Hard block
                if block or rec == "BLOCK":
                    return False, f"Advisor BLOCK (conf={conf:.2f})", 1.0

                # Bias conflict => block entries
                if (bias == "LONG" and sig == "SELL") or (bias == "SHORT" and sig == "BUY"):
                    return False, f"Advisor bias conflict (bias={bias}, conf={conf:.2f})", 1.0

                # Reduce risk => allow but scale down
                if rec == "REDUCE_RISK":
                    size_mult = float(self.advisor_reduce_risk_multiplier)
                    if size_mult <= 0 or size_mult > 1:
                        size_mult = 0.5

        # 8) Allow (including flips)
        return True, "OK", size_mult
