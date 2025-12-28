import pandas as pd
import numpy as np

class DataProcessor:
    @staticmethod
    def _calculate_rsi(series, window):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    @staticmethod
    def _calculate_adx(high, low, close, window=14):
        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement
        dm_plus = high - high.shift(1)
        dm_minus = low.shift(1) - low
        dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
        dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)
        
        # Smoothed averages
        atr = tr.ewm(span=window, adjust=False).mean()
        di_plus = (dm_plus.ewm(span=window, adjust=False).mean() / atr) * 100
        di_minus = (dm_minus.ewm(span=window, adjust=False).mean() / atr) * 100
        
        # DX and ADX
        dx = ((di_plus - di_minus).abs() / (di_plus + di_minus)) * 100
        adx = dx.ewm(span=window, adjust=False).mean()
        return adx.fillna(0)

    @staticmethod
    def _calculate_macd(close, fast=12, slow=26, signal=9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        return macd, signal_line

    # ---------------------------
    # Candlestick helper layer
    # ---------------------------
    @staticmethod
    def _add_candlestick_patterns(data: pd.DataFrame) -> pd.DataFrame:
        o = data["open"]
        h = data["high"]
        l = data["low"]
        c = data["close"]

        rng = (h - l).replace(0, np.nan)
        body = (c - o).abs()
        upper = (h - np.maximum(o, c)).clip(lower=0)
        lower = (np.minimum(o, c) - l).clip(lower=0)

        body_ma = body.rolling(20).mean().replace(0, np.nan)
        rng_ma = rng.rolling(20).mean().replace(0, np.nan)

        is_bull = c > o
        is_bear = c < o

        long_body = body > (body_ma * 1.3)
        short_body = body < (body_ma * 0.7)

        is_doji = body <= (rng * 0.10)
        is_long_legged = (rng > (rng_ma * 1.3)) & is_doji
        is_rickshaw = is_doji & (upper > rng * 0.35) & (lower > rng * 0.35)

        open_near_low = (o - l) <= (rng * 0.05)
        open_near_high = (h - o) <= (rng * 0.05)
        close_near_low = (c - l) <= (rng * 0.05)
        close_near_high = (h - c) <= (rng * 0.05)

        prev_h = h.shift(1)
        prev_l = l.shift(1)
        gap_up = l > prev_h
        gap_down = h < prev_l

        uptrend = c > c.shift(3)
        downtrend = c < c.shift(3)

        # --- ide gyűjtünk mindent ---
        feats = {}

        # base candle features
        feats["candle_body"] = body.fillna(0)
        feats["candle_range"] = rng.fillna(0)
        feats["candle_upper_wick"] = upper.fillna(0)
        feats["candle_lower_wick"] = lower.fillna(0)
        feats["candle_is_doji"] = is_doji.fillna(False).astype(int)

        # single candle
        feats["pattern_candle_black"] = is_bear.astype(int)
        feats["pattern_candle_white"] = is_bull.astype(int)
        feats["pattern_candle_short_black"] = (is_bear & short_body).astype(int)
        feats["pattern_candle_short_white"] = (is_bull & short_body).astype(int)
        feats["pattern_long_day_black"] = (is_bear & long_body).astype(int)
        feats["pattern_long_day_white"] = (is_bull & long_body).astype(int)
        feats["pattern_spinning_top_black"] = (is_bear & short_body & (upper > body * 0.5) & (lower > body * 0.5)).astype(int)
        feats["pattern_spinning_top_white"] = (is_bull & short_body & (upper > body * 0.5) & (lower > body * 0.5)).astype(int)
        feats["pattern_high_wave"] = ((upper > rng * 0.35) & (lower > rng * 0.35) & (body < rng * 0.25)).astype(int)

        # doji variants
        feats["pattern_rickshaw_man"] = is_rickshaw.astype(int)
        feats["pattern_doji_long_legged"] = is_long_legged.astype(int)
        feats["pattern_doji_dragonfly"] = (is_doji & (upper <= rng * 0.10) & (lower >= rng * 0.60)).astype(int)
        feats["pattern_doji_gravestone"] = (is_doji & (upper >= rng * 0.60) & (lower <= rng * 0.10)).astype(int)
        mid = (h + l) / 2
        feats["pattern_doji_northern"] = (is_doji & (c >= mid)).astype(int)
        feats["pattern_doji_southern"] = (is_doji & (c < mid)).astype(int)
        feats["pattern_doji_gapping_up"] = (is_doji & gap_up).astype(int)
        feats["pattern_doji_gapping_down"] = (is_doji & gap_down).astype(int)

        # marubozu-ish
        feats["pattern_marubozu_black"] = (is_bear & open_near_high & close_near_low & long_body).astype(int)
        feats["pattern_marubozu_white"] = (is_bull & open_near_low & close_near_high & long_body).astype(int)
        feats["pattern_marubozu_closing_black"] = (is_bear & close_near_low & long_body).astype(int)
        feats["pattern_marubozu_closing_white"] = (is_bull & close_near_high & long_body).astype(int)
        feats["pattern_marubozu_opening_black"] = (is_bear & open_near_high & long_body).astype(int)
        feats["pattern_marubozu_opening_white"] = (is_bull & open_near_low & long_body).astype(int)

        # engulfing patterns
        prev_body = body.shift(1)
        prev_is_bear = is_bear.shift(1)
        prev_is_bull = is_bull.shift(1)
        feats["pattern_engulfing_bullish"] = (prev_is_bear & is_bull & (body > prev_body)).astype(int)
        feats["pattern_engulfing_bearish"] = (prev_is_bull & is_bear & (body > prev_body)).astype(int)

        # hammer family
        hammer_like = (lower >= body * 2.0) & (upper <= body * 0.5) & (body > 0)
        inv_hammer_like = (upper >= body * 2.0) & (lower <= body * 0.5) & (body > 0)
        shooting_star_like = (upper >= body * 2.0) & (lower <= body * 0.5) & (body > 0) & (o < c)  # small lower wick, upper long
        feats["pattern_hammer"] = (hammer_like & downtrend).astype(int)
        feats["pattern_hanging_man"] = (hammer_like & uptrend).astype(int)
        feats["pattern_hammer_inverted"] = (inv_hammer_like & downtrend).astype(int)
        feats["pattern_shooting_star"] = (shooting_star_like & uptrend).astype(int)
        feats["pattern_shooting_star"] = (inv_hammer_like & uptrend).astype(int)
        feats["pattern_takuri_line"] = ((lower >= body * 3.0) & (upper <= body) & (body > 0)).astype(int)

        feats["pattern_belt_hold_bullish"] = (is_bull & open_near_low & long_body & (upper <= rng * 0.10)).astype(int)
        feats["pattern_belt_hold_bearish"] = (is_bear & open_near_high & long_body & (lower <= rng * 0.10)).astype(int)

        # 2-candle
        o1, h1, l1, c1 = o.shift(1), h.shift(1), l.shift(1), c.shift(1)
        bull_eng = (is_bull & (c1 < o1) & (o <= c1) & (c >= o1))
        bear_eng = (is_bear & (c1 > o1) & (o >= c1) & (c <= o1))
        feats["pattern_engulfing"] = bull_eng.astype(int) - bear_eng.astype(int)
        feats["pattern_engulfing_bullish"] = bull_eng.astype(int)
        feats["pattern_engulfing_bearish"] = bear_eng.astype(int)

        harami_bull = (is_bull & (c1 < o1) & (o >= c1) & (c <= o1))
        harami_bear = (is_bear & (c1 > o1) & (o <= c1) & (c >= o1))
        feats["pattern_harami_bullish"] = harami_bull.astype(int)
        feats["pattern_harami_bearish"] = harami_bear.astype(int)
        feats["pattern_harami_cross_bullish"] = (harami_bull & is_doji).astype(int)
        feats["pattern_harami_cross_bearish"] = (harami_bear & is_doji).astype(int)

        feats["pattern_piercing_pattern"] = (
            (c1 < o1) & long_body.shift(1) &
            is_bull & (o < l1) &
            (c > (o1 + c1) / 2) & (c < o1)
        ).astype(int)

        feats["pattern_dark_cloud_cover"] = (
            (c1 > o1) & long_body.shift(1) &
            is_bear & (o > h1) &
            (c < (o1 + c1) / 2) & (c > o1)
        ).astype(int)

        close_eq = (np.abs(c - c1) <= (rng * 0.05))
        feats["pattern_meeting_lines_bullish"] = ((c1 < o1) & is_bull & close_eq).astype(int)
        feats["pattern_meeting_lines_bearish"] = ((c1 > o1) & is_bear & close_eq).astype(int)

        prior_long_black = (c1 < o1) & long_body.shift(1)
        opens_below = o < c1
        close_near_prev_low = np.abs(c - l1) <= (rng * 0.10)
        close_into_lower_third = (c > l1) & (c <= (l1 + (o1 - c1) * 0.33))
        close_into_mid = (c > (l1 + (o1 - c1) * 0.33)) & (c < (l1 + (o1 - c1) * 0.66))
        feats["pattern_in_neck"] = (prior_long_black & opens_below & is_bull & close_near_prev_low).astype(int)
        feats["pattern_on_neck"] = (prior_long_black & opens_below & is_bull & close_into_lower_third).astype(int)
        feats["pattern_thrusting"] = (prior_long_black & opens_below & is_bull & close_into_mid).astype(int)

        feats["pattern_above_the_stomach"] = (
            (c1 < o1) & long_body.shift(1) &
            (o < c1) & is_bull & (c > c1) & (c < o1)
        ).astype(int)

        feats["pattern_below_the_stomach"] = (
            (c1 > o1) & long_body.shift(1) &
            (o > c1) & is_bear & (c < c1) & (c > o1)
        ).astype(int)

        feats["pattern_homing_pigeon"] = ((c1 < o1) & (c < o) & (h <= h1) & (l >= l1)).astype(int)
        feats["pattern_matching_low"] = ((c1 < o1) & (c < o) & (np.abs(c - c1) <= rng * 0.05)).astype(int)

        feats["pattern_tweezers_top"] = ((np.abs(h - h1) <= rng * 0.05) & (c1 > o1) & is_bear).astype(int)
        feats["pattern_tweezers_bottom"] = ((np.abs(l - l1) <= rng * 0.05) & (c1 < o1) & is_bull).astype(int)

        maru_white = (is_bull & open_near_low & close_near_high & long_body)
        maru_black = (is_bear & open_near_high & close_near_low & long_body)
        feats["pattern_kicking_bullish"] = (maru_black.shift(1) & maru_white & gap_up).astype(int)
        feats["pattern_kicking_bearish"] = (maru_white.shift(1) & maru_black & gap_down).astype(int)

        # Star patterns
        c2, o2, h2, l2 = c.shift(2), o.shift(2), h.shift(2), l.shift(2)
        small_body = body < (body_ma * 0.7)
        star_gap_up = l > h1
        star_gap_down = l > h1  # Wait, no: gap down is current low > prev high? Wait, for morning star, second candle gaps down, meaning opens below first close.
        # Actually, standard morning star: second candle opens below first close, small body.
        # But in code, star_gap_down = l > h1 ? No.
        # Gap down typically means price gaps lower, so current open < prev close.
        # Let's fix: star_gap_down = o < c1
        star_gap_down = o < c1
        feats["pattern_morning_star"] = (
            (c2 < o2) & long_body.shift(2) &  # first bearish long
            small_body.shift(1) & star_gap_down.shift(1) &  # second small with gap down
            is_bull & (c > (o2 + c2) / 2)  # third bullish closing above midpoint
        ).astype(int)
        feats["pattern_evening_star"] = (
            (c2 > o2) & long_body.shift(2) &  # first bullish long
            small_body.shift(1) & star_gap_up.shift(1) &  # second small with gap up
            is_bear & (c < (o2 + c2) / 2)  # third bearish closing below midpoint
        ).astype(int)
        feats["pattern_abandoned_baby_bullish"] = (
            (c2 < o2) & star_gap_down.shift(1) & is_doji.shift(1) & star_gap_up & is_bull
        ).astype(int)
        feats["pattern_abandoned_baby_bearish"] = (
            (c2 > o2) & star_gap_up.shift(1) & is_doji.shift(1) & star_gap_down & is_bear
        ).astype(int)

        # Three soldiers/crows
        higher_highs = (h > h.shift(1)) & (h.shift(1) > h.shift(2))
        higher_lows = (l > l.shift(1)) & (l.shift(1) > l.shift(2))
        lower_highs = (h < h.shift(1)) & (h.shift(1) < h.shift(2))
        lower_lows = (l < l.shift(1)) & (l.shift(1) < l.shift(2))
        feats["pattern_three_white_soldiers"] = (
            is_bull & is_bull.shift(1) & is_bull.shift(2) & higher_highs & higher_lows
        ).astype(int)
        feats["pattern_three_black_crows"] = (
            is_bear & is_bear.shift(1) & is_bear.shift(2) & lower_highs & lower_lows
        ).astype(int)

        # 3+ candle stuff (a többi detektorod ugyanígy mehet ide "feats[...] = ..." formában)
        # --- a te jelenlegi kódodból ide másold át ugyanazokat a kifejezéseket, csak data[...] helyett feats[...] ---

        # New price lines helper (kept)
        def new_price_lines(n: int):
            cons_up = (c > c.shift(1)).rolling(n).apply(
                lambda x: 1.0 if np.all(x[1:] > x[:-1]) else 0.0, raw=True
            )
            cons_dn = (c < c.shift(1)).rolling(n).apply(
                lambda x: 1.0 if np.all(x[1:] < x[:-1]) else 0.0, raw=True
            )
            new_hi = c == c.rolling(n).max()
            new_lo = c == c.rolling(n).min()
            up_sig = (cons_up == 1.0) & new_hi
            dn_sig = (cons_dn == 1.0) & new_lo
            return up_sig.astype(int) - dn_sig.astype(int)

        feats["pattern_8_new_price_lines"] = new_price_lines(8).fillna(0).astype(int)
        feats["pattern_10_new_price_lines"] = new_price_lines(10).fillna(0).astype(int)
        feats["pattern_12_new_price_lines"] = new_price_lines(12).fillna(0).astype(int)
        feats["pattern_13_new_price_lines"] = new_price_lines(13).fillna(0).astype(int)

        # --- egyben ráillesztés ---
        feat_df = pd.DataFrame(feats, index=data.index)

        # pattern oszlopok (int), a többi marad float
        pattern_cols = [c for c in feat_df.columns if c.startswith("pattern_")]
        if pattern_cols:
            feat_df[pattern_cols] = feat_df[pattern_cols].fillna(0).astype(int)

        out = pd.concat([data, feat_df], axis=1)

        # extra biztos: defragmentálás (opcionális, de jól jön live botnál)
        out = out.copy()
        return out

    @staticmethod
    def _add_chart_patterns(data: pd.DataFrame) -> pd.DataFrame:
        """
        Add chart patterns based on ThePatternSite.com (Thomas Bulkowski).
        These are simplified detections for common patterns.
        """
        h = data["high"]
        l = data["low"]
        c = data["close"]
        o = data["open"]

        feats = {}

        # Double Top/Bottom detection (simplified: two peaks/valleys within tolerance)
        tolerance = 0.02  # 2% tolerance
        window = 20  # lookback window

        # Double Top: two highs close together
        high_peaks = h.rolling(window).apply(lambda x: 1 if x[-1] == max(x) and x[-1] >= x[-2] * (1 - tolerance) else 0, raw=True)
        double_top = (high_peaks == 1) & (high_peaks.shift(1) == 1) & (h - h.shift(1)).abs() / h < tolerance
        feats["chart_double_top"] = double_top.astype(int)

        # Double Bottom: two lows close together
        low_valleys = l.rolling(window).apply(lambda x: 1 if x[-1] == min(x) and x[-1] <= x[-2] * (1 + tolerance) else 0, raw=True)
        double_bottom = (low_valleys == 1) & (low_valleys.shift(1) == 1) & (l - l.shift(1)).abs() / l < tolerance
        feats["chart_double_bottom"] = double_bottom.astype(int)

        # Ascending Triangle: higher lows, flat highs
        higher_lows = l > l.shift(5)
        flat_highs = (h.rolling(5).max() - h.rolling(5).min()) / h.rolling(5).mean() < 0.05
        feats["chart_ascending_triangle"] = (higher_lows & flat_highs).astype(int)

        # Descending Triangle: lower highs, flat lows
        lower_highs = h < h.shift(5)
        flat_lows = (l.rolling(5).max() - l.rolling(5).min()) / l.rolling(5).mean() < 0.05
        feats["chart_descending_triangle"] = (lower_highs & flat_lows).astype(int)

        # Rectangle: flat highs and lows
        flat_highs_rect = (h.rolling(10).max() - h.rolling(10).min()) / h.rolling(10).mean() < 0.03
        flat_lows_rect = (l.rolling(10).max() - l.rolling(10).min()) / l.rolling(10).mean() < 0.03
        feats["chart_rectangle"] = (flat_highs_rect & flat_lows_rect).astype(int)

        # Head and Shoulders (very simplified: three peaks, middle higher)
        peaks = h.rolling(window).apply(lambda x: 1 if x[-1] == max(x) else 0, raw=True)
        # ensure boolean series from peaks
        head_shoulder = (
            (peaks == 1) & (h > h.shift(1)) & (h > h.shift(-1)) &  # middle peak higher
            (h.shift(2) < h) & (h.shift(-2) < h)  # shoulders lower
        )
        feats["chart_head_and_shoulders"] = head_shoulder.astype(int)

        # Broadening Formation (megaphone: expanding highs/lows)
        expanding_highs = h > h.shift(5)
        expanding_lows = l < l.shift(5)
        feats["chart_broadening_formation"] = (expanding_highs & expanding_lows).astype(int)

        # Wedge (converging lines, simplified)
        converging_highs = h < h.shift(5)
        converging_lows = l > l.shift(5)
        feats["chart_wedge"] = (converging_highs & converging_lows).astype(int)

        feat_df = pd.DataFrame(feats, index=data.index)
        chart_cols = [c for c in feat_df.columns if c.startswith("chart_")]
        if chart_cols:
            feat_df[chart_cols] = feat_df[chart_cols].fillna(0).astype(int)

        out = pd.concat([data, feat_df], axis=1)
        out = out.copy()
        return out


    @staticmethod
    def prepare_features(df, microstructure_features=None):
        if df is None or len(df) < 50:
            return None

        data = df.copy()

        # --- JELLEMZŐK ---
        data['return'] = data['close'].pct_change()
        data['volatility'] = data['return'].rolling(window=20).std()
        data['rsi'] = DataProcessor._calculate_rsi(data['close'], 14)
        ma_20 = data['close'].rolling(window=20).mean()
        data['ma_dist'] = (data['close'] - ma_20) / ma_20

        # Trend analysis indicators
        data['adx'] = DataProcessor._calculate_adx(data['high'], data['low'], data['close'], 14)
        data['macd'], data['macd_signal'] = DataProcessor._calculate_macd(data['close'])

        # Candlestick minták (ThePatternSite Visual Index alapján széles készlet)
        data = DataProcessor._add_candlestick_patterns(data)

        # Chart patterns (ThePatternSite.com alapján, egyszerűsített detekció)
        data = DataProcessor._add_chart_patterns(data)

        # Range pozíció
        low_20 = data['low'].rolling(window=20).min()
        high_20 = data['high'].rolling(window=20).max()
        data['range_pos'] = (data['close'] - low_20) / (high_20 - low_20).replace(0, 0.0001)

        # --- MICROSTRUCTURE FEATURES ---
        if microstructure_features:
            # Add microstructure features to each row (they're point-in-time)
            for key, value in microstructure_features.items():
                data[key] = value

        # --- GYORSÍTOTT TARGET SZÁMÍTÁS ---
        data['target'] = 0
        tp = 0.003  # 0.3%
        sl = 0.005  # 0.5%

        # Csak a tanítás során futtatjuk a nehéz hurkot
        if 'target' in data.columns:
            prices = data['close'].values
            targets = np.zeros(len(prices))

            # Ez a rész felelős a "gondolkodásért"
            for i in range(len(prices) - 15):
                curr = prices[i]
                future = prices[i+1 : i+16]  # 15 perces ablak

                # Vételi feltétel (eléri a TP-t mielőtt eléri a SL-t)
                for p in future:
                    if p >= curr * (1 + tp):
                        targets[i] = 1
                        break
                    if p <= curr * (1 - sl):
                        break

                # Eladási feltétel
                if targets[i] == 0:
                    for p in future:
                        if p <= curr * (1 - tp):
                            targets[i] = 2
                            break
                        if p >= curr * (1 + sl):
                            break

            data['target'] = targets

        return data.dropna()
