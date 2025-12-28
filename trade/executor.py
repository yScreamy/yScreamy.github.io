# trade/executor.py
from __future__ import annotations

import math
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

import config


# -------------------------
# Small helpers
# -------------------------
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _s(v: Any) -> str:
    return (str(v) if v is not None else "").strip()


def _env(*names: str) -> str:
    # Case sensitive on some systems; in Windows it's not, but still.
    for n in names:
        val = os.getenv(n)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return ""


def _normalize_privkey(key: str) -> str:
    k = _s(key)
    if not k:
        return ""
    if k.startswith("0x") or k.startswith("0X"):
        k2 = k[2:]
    else:
        k2 = k

    if len(k2) < 64:
        raise ValueError(f"PRIVATE_KEY túl rövid ({len(k2)} hex karakter).")
    # If longer than 64, often it's accidental copy; keep last 64 as a safety fallback? -> NO.
    # Better to be strict:
    if len(k2) != 64:
        raise ValueError(f"PRIVATE_KEY hossza nem 64 hex karakter (most: {len(k2)}).")

    if not _HEX_RE.match(k2):
        raise ValueError("PRIVATE_KEY nem hex formátumú.")

    return "0x" + k2.lower()


def _normalize_address(addr: str) -> str:
    a = _s(addr)
    if not a:
        return ""
    if not a.startswith("0x") and not a.startswith("0X"):
        a = "0x" + a
    # Minimal sanity length check for EVM address
    if len(a) != 42:
        # don't hard fail: some libs accept checksum etc; but length should still be 42
        return a
    return a


@dataclass
class Addresses:
    agent_wallet_address: str
    trading_address: str


class _InfoProxy:
    """
    Proxy Info so that user_state() ALWAYS reads from trading_address,
    even if caller passes agent/API address (main.py currently does that).

    All other attributes/methods are delegated to the underlying Info.
    """

    def __init__(self, info: Info, trading_address: str):
        self._info = info
        self._trading_address = trading_address

    def user_state(self, *_args, **_kwargs):
        if self._trading_address:
            return self._info.user_state(self._trading_address)
        # fallback to passed arg if trading missing (not ideal, but avoids crashing instantly)
        if _args and _args[0]:
            return self._info.user_state(_args[0])
        raise RuntimeError("Nincs trading address (HL_trading_address / TRADING_ADDRESS).")

    def __getattr__(self, name: str):
        return getattr(self._info, name)


class TradeExecutor:
    """
    - Signing: HL_private_key (agent/api wallet)
    - Positions/equity/user_state: HL_trading_address (main/master wallet)
    """

    def __init__(self):
        self.base_url = getattr(config, "BASE_URL", None) or _env("BASE_URL") or "https://api.hyperliquid.xyz"

        # --- Resolve keys/addresses from config OR env ---
        # Your current registry env vars:
        #   HL_private_key, HL_wallet_address, crypto_panic_key
        # We'll support both old and new naming.
        raw_priv = _s(getattr(config, "PRIVATE_KEY", "")) or _env("HL_private_key", "HL_PRIVATE_KEY", "PRIVATE_KEY")
        raw_agent_addr = _s(getattr(config, "WALLET_ADDRESS", "")) or _env(
            "HL_wallet_address", "HL_WALLET_ADDRESS", "WALLET_ADDRESS", "HL_AGENT_WALLET_ADDRESS"
        )

        # NEW: main/master address for user_state
        raw_trading_addr = _s(getattr(config, "TRADING_ADDRESS", "")) or _env(
            "HL_trading_address", "HL_TRADING_ADDRESS", "TRADING_ADDRESS", "ACCOUNT_ADDRESS", "HL_ACCOUNT_ADDRESS"
        )

        try:
            self.api_private_key = _normalize_privkey(raw_priv)
        except Exception as e:
            print("\n--- DEMO MÓD ---")
            print("Nincs private key beállítva. Demo mód aktiválva.")
            print("A bot csak szimulált kereskedést végez.")
            self.api_private_key = None
            self.demo_mode = True
            return

        # Build signing account
        try:
            self.account = Account.from_key(self.api_private_key)
            self.demo_mode = False
        except Exception as e:
            print("\n--- DEMO MÓD ---")
            print(f"Érvénytelen private key: {e}")
            print("Demo mód aktiválva.")
            self.api_private_key = None
            self.account = None
            self.demo_mode = True

        # Agent wallet address (optional sanity only)
        self.agent_wallet_address = _normalize_address(raw_agent_addr) if raw_agent_addr else ""
        if not self.demo_mode:
            signing_addr = _normalize_address(self.account.address)
            print(f"API Signing Wallet aktív: {signing_addr}")
            if self.agent_wallet_address and self.agent_wallet_address.lower() != signing_addr.lower():
                print(
                    f"[WARN] HL_wallet_address != signing wallet address\n"
                    f"       HL_wallet_address: {self.agent_wallet_address}\n"
                    f"       signing address  : {signing_addr}\n"
                    f"       (Ez nem feltétlen gond, de legyen tudatos.)"
                )
        else:
            print("Demo mód: nincs valódi wallet kapcsolat.")

        # Trading (main/master) address
        self.trading_address = _normalize_address(raw_trading_addr)

        if not self.trading_address:
            print("\n--- FIGYELEM ---")
            print("Nincs megadva HL_trading_address (main/master account cím).")
            print("A bot lehet, hogy tud nyitni/zárni (agent), de a pozíciók/equity nem lesznek megbízhatóan olvashatók.")
            # Fallback: try using agent address (not recommended)
            if not self.demo_mode:
                self.trading_address = self.agent_wallet_address or signing_addr
                print(f"[WARN] Fallback trading_address: {self.trading_address}")
            else:
                self.trading_address = self.agent_wallet_address or "demo_address"
                print(f"[WARN] Demo fallback trading_address: {self.trading_address}")

        print(f"Trading account (positions/equity): {self.trading_address}")

        # Exchange (trade) + Info (read)
        # NOTE: Hyperliquid SDK recommends: account_address = MAIN wallet (not API wallet).
        self.exchange = Exchange(self.account, self.base_url, account_address=self.trading_address)

        # Login if needed (some SDK versions require it)
        if hasattr(self.exchange, "login_if_needed"):
            try:
                self.exchange.login_if_needed()
            except Exception as e:
                print(f"[WARN] login_if_needed hiba: {e}")

        # Underlying Info + proxy to force trading address for user_state
        _raw_info = Info(self.base_url, skip_ws=True)
        self.info = _InfoProxy(_raw_info, self.trading_address)

        # meta cache (szDecimals, maxLeverage, stb.)
        self._meta_cache: Optional[dict[str, dict[str, Any]]] = None
        self._meta_cache_ts = 0.0
        self._meta_ttl = 300  # 5 perc

        # Skip automatic leverage initialization in demo mode
        if not getattr(self, "demo_mode", False):
            self._initialize_leverage()
        else:
            print("[Demo] Leverage init kihagyva.")

    # -------------------------
    # META / PRICE / EQUITY
    # -------------------------
    def _refresh_meta(self, force: bool = False):
        now = time.time()
        if (not force) and self._meta_cache is not None and (now - self._meta_cache_ts) < self._meta_ttl:
            return
        meta = self.info.meta()
        universe = meta.get("universe", []) or []
        self._meta_cache = {a.get("name"): a for a in universe if a.get("name")}
        self._meta_cache_ts = now

    def get_sz_decimals(self, symbol: str) -> int:
        self._refresh_meta()
        a = (self._meta_cache or {}).get(symbol)
        return int(a.get("szDecimals", 3)) if a else int(getattr(config, "SIZE_DECIMALS", 3) or 3)

    def get_max_leverage(self, symbol: str) -> float:
        self._refresh_meta()
        a = (self._meta_cache or {}).get(symbol)
        if not a:
            return float(getattr(config, "DEFAULT_LEVERAGE", 1))
        return float(a.get("maxLeverage", getattr(config, "DEFAULT_LEVERAGE", 1)))

    def get_mid_price(self, symbol: str) -> float:
        mids = self.info.all_mids()
        px = mids.get(symbol)
        if px is None:
            raise RuntimeError(f"Nincs mid ár a {symbol}-hoz az allMids-ben.")
        return float(px)

    def get_account_equity_usd(self) -> float:
        user_state = self.info.user_state(self.trading_address)  # proxy forces trading address anyway
        ms = user_state.get("marginSummary") or user_state.get("crossMarginSummary") or {}
        for k in ("accountValue", "totalValue", "equity"):
            if k in ms and ms[k] is not None:
                return float(ms[k])
        raise RuntimeError(f"Nem találok equity mezőt a marginSummary-ben: {ms}")

    # -------------------------
    # LEVERAGE
    # -------------------------
    def set_leverage(self, leverage: float, symbol: str, is_cross: bool = True):
        """
        SDK verziófüggő: paraméter sorrend eltérhet.
        """
        if getattr(self, "demo_mode", False):
            print(f"[Demo] set_leverage no-op: {leverage}x {symbol} (is_cross={is_cross})")
            return True
        lev = int(round(float(leverage)))

        try:
            return self.exchange.update_leverage(lev, symbol, is_cross)
        except Exception as e1:
            try:
                return self.exchange.update_leverage(symbol, lev, is_cross)
            except Exception as e2:
                # last chance: keyword style
                try:
                    return self.exchange.update_leverage(leverage=lev, name=symbol, is_cross=is_cross)
                except Exception as e3:
                    raise RuntimeError(f"Leverage update elbukott. 1) {e1}  2) {e2}  3) {e3}")

    def _initialize_leverage(self):
        try:
            sym = getattr(config, "SYMBOL", "BTC")
            use_max = bool(getattr(config, "USE_MAX_LEVERAGE", False))
            lev = self.get_max_leverage(sym) if use_max else float(getattr(config, "DEFAULT_LEVERAGE", 1))

            print(f"Tőkeáttétel beállítása: {lev}x ({sym})")
            self.set_leverage(lev, sym, True)
            print("Tőkeáttétel sikeresen beállítva.")
        except Exception as e:
            print(f"[WARN] Tőkeáttétel beállítási hiba: {e}")

    # -------------------------
    # POSITION (robosztus)
    # -------------------------
    def _user_state(self) -> dict:
        # proxy ensures trading address
        return self.info.user_state(self.trading_address)

    def get_position_size(self, symbol: str) -> float:
        """Signed size: >0 LONG, <0 SHORT"""
        try:
            user_state = self._user_state()
            for ap in user_state.get("assetPositions", []) or []:
                pos = ap.get("position", {}) or {}
                if pos.get("coin") != symbol:
                    continue

                for k in ("szi", "s_size", "sSize", "positionSize", "size", "sz"):
                    if k in pos and pos[k] is not None:
                        try:
                            return float(pos[k])
                        except Exception:
                            pass
                return 0.0
            return 0.0
        except Exception as e:
            print(f"[WARN] Hiba a pozíció méretének lekérésekor: {e}")
            return 0.0

    def get_current_position(self, symbol: str) -> str:
        """Returns: NONE | LONG | SHORT | ERROR"""
        try:
            s = self.get_position_size(symbol)
            if s > 0:
                return "LONG"
            if s < 0:
                return "SHORT"

            # fallback: try side fields if signed size missing
            user_state = self._user_state()
            for ap in user_state.get("assetPositions", []) or []:
                pos = ap.get("position", {}) or {}
                if pos.get("coin") != symbol:
                    continue

                side = None
                for k in ("side", "posSide", "positionSide"):
                    if k in pos and isinstance(pos[k], str):
                        side = pos[k].strip().upper()
                        break
                if side is None and "isLong" in pos:
                    try:
                        side = "LONG" if bool(pos["isLong"]) else "SHORT"
                    except Exception:
                        side = None

                if side in ("LONG", "SHORT"):
                    return side

            return "NONE"
        except Exception as e:
            print(f"[WARN] Hiba a pozíció lekérésekor: {e}")
            return "ERROR"

    def get_position_details(self, symbol: str) -> dict:
        """
        Returns: {"side":"NONE|LONG|SHORT", "size": float, "entry_price": float}
        """
        try:
            user_state = self._user_state()
            for ap in user_state.get("assetPositions", []) or []:
                pos = ap.get("position", {}) or {}
                if pos.get("coin") != symbol:
                    continue

                signed = None
                for k in ("szi", "s_size", "sSize", "positionSize", "size", "sz"):
                    if k in pos and pos[k] is not None:
                        try:
                            signed = float(pos[k])
                            break
                        except Exception:
                            pass
                if signed is None:
                    signed = 0.0

                entry = 0.0
                for k in ("entryPx", "entry_px", "entryPrice", "avgPx", "avgEntryPx"):
                    if k in pos and pos[k] is not None:
                        try:
                            entry = float(pos[k])
                            break
                        except Exception:
                            pass

                side = None
                for k in ("side", "posSide", "positionSide"):
                    if k in pos and isinstance(pos[k], str):
                        side = pos[k].strip().upper()
                        break
                if side is None and "isLong" in pos:
                    try:
                        side = "LONG" if bool(pos["isLong"]) else "SHORT"
                    except Exception:
                        side = None

                if signed > 0 or side == "LONG":
                    return {"side": "LONG", "size": abs(float(signed)), "entry_price": entry}
                if signed < 0 or side == "SHORT":
                    return {"side": "SHORT", "size": abs(float(signed)), "entry_price": entry}

                return {"side": "NONE", "size": 0.0, "entry_price": entry}

            return {"side": "NONE", "size": 0.0, "entry_price": 0.0}

        except Exception as e:
            print(f"[WARN] Hiba a position_details lekérésekor: {e}")
            return {"side": "NONE", "size": 0.0, "entry_price": 0.0}

    # -------------------------
    # SIZING / ROUNDING
    # -------------------------
    def round_size(self, symbol: str, size: float) -> float:
        dec = self.get_sz_decimals(symbol)
        factor = 10 ** dec
        return math.floor(float(size) * factor) / factor

    def calc_full_size(self, symbol: str):
        """returns: equity, lev, notional, size (FULL = 100% equity * max lev)"""
        equity = self.get_account_equity_usd()
        lev = self.get_max_leverage(symbol)
        mid = self.get_mid_price(symbol)

        notional = equity * lev
        size = notional / mid
        size = self.round_size(symbol, size)
        return equity, lev, notional, size

    # -------------------------
    # ORDERS
    # -------------------------
    def _market_open(self, sym: str, is_buy: bool, size: float, slippage: float, reduce_only: bool = False):
        """
        SDK signature differs across versions.
        We'll try a few compatible call styles.
        """
        # 1) positional with reduceOnly at end
        try:
            return self.exchange.market_open(sym, is_buy, float(size), None, float(slippage), reduce_only)
        except Exception:
            pass

        # 2) keyword reduce_only / reduceOnly
        try:
            return self.exchange.market_open(sym, is_buy, float(size), None, float(slippage), reduce_only=reduce_only)
        except Exception:
            pass
        try:
            return self.exchange.market_open(sym, is_buy, float(size), None, float(slippage), reduceOnly=reduce_only)
        except Exception:
            pass

        # 3) some SDKs take params dict
        try:
            return self.exchange.market_open(
                sym, is_buy, float(size), None, float(slippage), {"reduceOnly": bool(reduce_only)}
            )
        except Exception:
            pass

        # 4) last resort: no reduceOnly available
        return self.exchange.market_open(sym, is_buy, float(size), None, float(slippage))

    def execute_order(self, signal: str, size: float, symbol: str | None = None, reduce_only: bool = False):
        sym = symbol or getattr(config, "SYMBOL", "BTC")
        sig = signal.strip().upper()
        is_buy = True if sig == "BUY" else False
        slippage = float(getattr(config, "SLIPPAGE", 0.01))

        try:
            print(f"Rendelés küldése: {sig} | {sym} | size={size} | slippage={slippage} | reduce_only={reduce_only}")
            return self._market_open(sym, is_buy, float(size), slippage, reduce_only=reduce_only)
        except Exception as e:
            print(f"[ERROR] Rendelési hiba: {e}")
            return None

    def open_full_position(self, signal: str, symbol: str | None = None):
        """FULL mód: 100% equity + max leverage."""
        sym = symbol or getattr(config, "SYMBOL", "BTC")

        equity, lev, notional, size = self.calc_full_size(sym)
        if size <= 0:
            print("[ERROR] Size <= 0, nem nyitok pozíciót.")
            return None

        try:
            self.set_leverage(lev, sym, True)
        except Exception as e:
            print(f"[WARN] Leverage beállítás nem ment: {e} (megpróbálok nyitni így is)")

        print(f"[FULL] equity={equity:.2f} USD | lev={lev:.2f}x | notional={notional:.2f} USD | size={size} {sym}")
        return self.execute_order(signal, size, sym, reduce_only=False)

    def close_position_fully(self, symbol: str | None = None):
        """
        Teljes zárás:
        - elsőként market_close (ha elérhető)
        - fallback: ellenirányú reduceOnly market_open abs(size)-zal
        """
        sym = symbol or getattr(config, "SYMBOL", "BTC")
        slippage = float(getattr(config, "SLIPPAGE", 0.01))

        # Try native market_close
        if hasattr(self.exchange, "market_close"):
            try:
                print(f"[CLOSE] market_close: {sym} | slippage={slippage}")
                return self.exchange.market_close(sym, None, None, float(slippage))
            except Exception as e1:
                print(f"[WARN] market_close nem sikerült: {e1} -> fallback reduceOnly market_open")

        s = self.get_position_size(sym)
        if s == 0:
            print("[INFO] Nincs mit zárni.")
            return None

        signal = "SELL" if s > 0 else "BUY"
        size = self.round_size(sym, abs(s))
        return self.execute_order(signal, size, sym, reduce_only=True)

    # -------------------------
    # Annotation helpers (best-effort wrappers)
    # -------------------------
    def create_annotation(self, annotation: dict) -> bool:
        """Best-effort: ask underlying exchange client to create an annotation/chart object.

        Returns True if a supported method was called without raising, False otherwise.
        """
        try:
            if hasattr(self.exchange, "create_annotation"):
                try:
                    self.exchange.create_annotation(annotation)
                    return True
                except Exception:
                    pass
            if hasattr(self.exchange, "add_annotation"):
                try:
                    self.exchange.add_annotation(annotation)
                    return True
                except Exception:
                    pass
            # generic 'annotate' variants
            for name in ("annotate", "create_note", "add_chart_object"):
                if hasattr(self.exchange, name):
                    try:
                        getattr(self.exchange, name)(annotation)
                        return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def add_annotation(self, annotation: dict) -> bool:
        return self.create_annotation(annotation)
