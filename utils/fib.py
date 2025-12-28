from typing import Tuple, Dict, Optional

def clamp(value: float, low: float, high: float) -> float:
    try:
        v = float(value)
    except Exception:
        return float(low)
    return max(low, min(high, v))


def compute_fibonacci_levels(swing_high: float, swing_low: float, levels=None) -> dict:
    """
    Compute Fibonacci retracement and extension levels.
    
    Standard levels: 
      Retracements: 0.236, 0.382, 0.5, 0.618, 0.786
      Extensions: 1.0, 1.272, 1.618
    """
    try:
        h = float(swing_high)
        l = float(swing_low)
    except Exception:
        return {}
    if levels is None:
        levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618]
    out = {}
    span = h - l
    for lv in levels:
        try:
            price = l + span * float(lv)
            out[float(lv)] = float(price)
        except Exception:
            continue
    return out


def get_standard_fibonacci_levels() -> list:
    """Return standard Fibonacci ratios used in trading."""
    return [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618, 2.0, 2.618]


def fibonacci_level_names(ratio: float) -> str:
    """Return human-readable name for a Fibonacci ratio."""
    names = {
        0.0: "0% (Swing Low)",
        0.236: "23.6% Retracement",
        0.382: "38.2% Retracement",
        0.5: "50% Retracement",
        0.618: "61.8% Retracement",
        0.786: "78.6% Retracement",
        1.0: "100% (Swing High)",
        1.272: "127.2% Extension",
        1.618: "161.8% Extension (Golden Ratio)",
        2.0: "200% Extension",
        2.618: "261.8% Extension",
    }
    return names.get(float(ratio), f"{float(ratio)*100:.1f}%")



def compute_tp_sl_from_fib(current_price: float, side: str, swing_high: float, swing_low: float, tp_extension: float, sl_retracement: float) -> Tuple[float, float]:
    """
    Auto-compute TP/SL decimals based on Fibonacci levels.
    
    Args:
        current_price: Current market price
        side: "BUY" or "SELL"
        swing_high: Recent swing high
        swing_low: Recent swing low
        tp_extension: Fibonacci extension level for TP (e.g., 1.272 or 1.618)
        sl_retracement: Fibonacci retracement level for SL (e.g., 0.618)
    
    Returns:
        (tp_decimal, sl_decimal) as decimals (0.0-1.0)
    """
    try:
        cp = float(current_price)
        sh = float(swing_high)
        sl = float(swing_low)
    except Exception:
        return 0.0, 0.0
    if cp <= 0 or sh == sl:
        return 0.0, 0.0

    fibs = compute_fibonacci_levels(sh, sl, levels=[0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, float(tp_extension), float(sl_retracement)])

    tp_price = fibs.get(float(tp_extension))
    sl_price = fibs.get(float(sl_retracement))

    span = sh - sl
    if tp_price is None:
        tp_price = sl + span * float(tp_extension)
    if sl_price is None:
        sl_price = sl + span * float(sl_retracement)

    if side.strip().upper() == "BUY":
        tp_dec = (float(tp_price) - cp) / cp
        sl_dec = (cp - float(sl_price)) / cp
    else:
        tp_dec = (cp - float(tp_price)) / cp
        sl_dec = (float(sl_price) - cp) / cp

    tp_dec = clamp(tp_dec, 0.0, 1.0)
    sl_dec = clamp(sl_dec, 0.0, 1.0)
    return float(tp_dec), float(sl_dec)


def find_best_fibonacci_tp_sl(
    current_price: float,
    side: str,
    swing_high: float,
    swing_low: float,
    target_tp_percent: Optional[float] = None,
    target_sl_percent: Optional[float] = None
) -> Tuple[float, float, float, float]:
    """
    Find closest Fibonacci levels to achieve target TP/SL percentages.
    Useful for manual tuning or backtesting.
    
    Args:
        current_price: Current price
        side: "BUY" or "SELL"
        swing_high, swing_low: Swing points
        target_tp_percent: Desired TP % (e.g., 10.0 for 10%)
        target_sl_percent: Desired SL % (e.g., 5.0 for 5%)
    
    Returns:
        (tp_price, tp_percent, sl_price, sl_percent)
    """
    if not target_tp_percent or not target_sl_percent:
        # Default: 1.618 extension for TP, 0.618 retracement for SL
        tp_price, sl_price = compute_tp_sl_from_fib(current_price, side, swing_high, swing_low, 1.618, 0.618)
        return float(tp_price), float(tp_price * 100.0) if side == "BUY" else float(tp_price * 100.0), \
               float(sl_price), float(sl_price * 100.0)
    
    levels = get_standard_fibonacci_levels()
    fibs = compute_fibonacci_levels(swing_high, swing_low, levels=levels)
    
    best_tp_level = None
    best_sl_level = None
    min_tp_diff = float('inf')
    min_sl_diff = float('inf')
    
    for level, price in fibs.items():
        level = float(level)
        price = float(price)
        
        if side.upper() == "BUY":
            pct = ((price - current_price) / current_price) * 100.0
            if target_tp_percent and abs(pct - target_tp_percent) < min_tp_diff and pct > 0:
                min_tp_diff = abs(pct - target_tp_percent)
                best_tp_level = (price, pct)
            pct_sl = ((current_price - price) / current_price) * 100.0
            if target_sl_percent and abs(pct_sl - target_sl_percent) < min_sl_diff and pct_sl > 0:
                min_sl_diff = abs(pct_sl - target_sl_percent)
                best_sl_level = (price, pct_sl)
        else:  # SELL
            pct = ((current_price - price) / current_price) * 100.0
            if target_tp_percent and abs(pct - target_tp_percent) < min_tp_diff and pct > 0:
                min_tp_diff = abs(pct - target_tp_percent)
                best_tp_level = (price, pct)
            pct_sl = ((price - current_price) / current_price) * 100.0
            if target_sl_percent and abs(pct_sl - target_sl_percent) < min_sl_diff and pct_sl > 0:
                min_sl_diff = abs(pct_sl - target_sl_percent)
                best_sl_level = (price, pct_sl)
    
    tp_price, tp_pct = best_tp_level if best_tp_level else (current_price * 1.1, 10.0)
    sl_price, sl_pct = best_sl_level if best_sl_level else (current_price * 0.95, 5.0)
    
    return float(tp_price), float(tp_pct), float(sl_price), float(sl_pct)

