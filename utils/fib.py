from typing import Tuple

def clamp(value: float, low: float, high: float) -> float:
    try:
        v = float(value)
    except Exception:
        return float(low)
    return max(low, min(high, v))


def compute_fibonacci_levels(swing_high: float, swing_low: float, levels=None) -> dict:
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


def compute_tp_sl_from_fib(current_price: float, side: str, swing_high: float, swing_low: float, tp_extension: float, sl_retracement: float) -> Tuple[float, float]:
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
