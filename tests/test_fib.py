import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.fib import compute_fibonacci_levels, compute_tp_sl_from_fib


def test_compute_fib_levels():
    high = 110.0
    low = 100.0
    levels = compute_fibonacci_levels(high, low)
    assert abs(levels[0.0] - 100.0) < 1e-6
    assert abs(levels[1.0] - 110.0) < 1e-6
    assert 0.236 in levels


def test_tp_sl_buy():
    cp = 105.0
    sh = 110.0
    sl = 100.0
    tp_dec, sl_dec = compute_tp_sl_from_fib(cp, "BUY", sh, sl, 1.272, 0.618)
    assert 0.0 <= tp_dec <= 1.0
    assert 0.0 <= sl_dec <= 1.0


def test_tp_sl_sell():
    cp = 105.0
    sh = 110.0
    sl = 100.0
    tp_dec, sl_dec = compute_tp_sl_from_fib(cp, "SELL", sh, sl, 1.272, 0.618)
    assert 0.0 <= tp_dec <= 1.0
    assert 0.0 <= sl_dec <= 1.0


if __name__ == '__main__':
    test_compute_fib_levels()
    test_tp_sl_buy()
    test_tp_sl_sell()
    print('ALL TESTS PASSED')
