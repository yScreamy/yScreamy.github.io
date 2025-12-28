import pandas as pd
from data.processor import DataProcessor


def test_atr_and_atr_pct_computation():
    # Create simple OHLCV data with increasing volatility
    rows = []
    price = 100.0
    for i in range(60):
        high = price * (1 + 0.01)
        low = price * (1 - 0.01)
        close = price
        rows.append({
            'timestamp': i,
            'open': price,
            'high': high,
            'low': low,
            'close': close,
            'volume': 1.0,
        })
        price *= (1 + 0.001)  # slight drift

    df = pd.DataFrame(rows)
    out = DataProcessor.prepare_features(df)
    assert out is not None and not out.empty
    assert 'atr' in out.columns
    assert 'atr_pct' in out.columns

    last_atr = float(out['atr'].iloc[-1])
    last_close = float(out['close'].iloc[-1])
    last_atr_pct = float(out['atr_pct'].iloc[-1])

    assert last_atr > 0
    assert 0 < last_atr_pct < 0.1  # 10% sanity upper bound
    assert abs(last_atr_pct - (last_atr / last_close)) < 1e-9
