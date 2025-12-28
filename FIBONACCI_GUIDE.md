# 📊 Fibonacci TP/SL Kézikönyv

## Áttekintés

A trading bot automatikusan **Fibonacci retracement és extension** szinteket használ a **Take Profit (TP)** és **Stop Loss (SL)** szintek meghatározásához. Ez eltávolítja a manuális TP/SL konfigurációk szükségességét és helyette matematikai alapon számított szinteket használ.

## Fibonacci szintek magyarázata

### Retracement szintek (visszamozgás)
Amikor az ár egy irányba mozog, majd visszahúzódik, a Fibonacci szintek azt mutatják, hol fordulhat meg:
- **23.6%** - Gyenge támogatás/ellenállás
- **38.2%** - Közepes támogatás/ellenállás
- **50%** - Pszichológiai szint
- **61.8%** - Erős támogatás/ellenállás (Golden Ratio)
- **78.6%** - Nagyon erős szint

### Extension szintek (kiterjesztés)
Az ár továbbmozoghat az eredeti mozgást meghaladóan. Ezek az extension szintek:
- **100%** - Swing High/Low
- **127.2%** - Első extension target
- **161.8%** - Golden Ratio extension (erős TP szint)
- **200%** - Kettős extension

## Bot Fibonacci TP/SL funkciók

### 1. Automatikus kalkuláció az entry-nél

Amikor a bot pozíciót nyit:
1. **Swing High/Low meghatározása**: Az utolsó 24 candleból keresi a legmagasabb és legalacsonyabb pontot
2. **Fibonacci szintek számítása**: A swing high és low közötti távolságból kalkulál
3. **TP szint**: Default **1.272 extension** szint (27.2% kiterjesztés)
4. **SL szint**: Default **0.618 retracement** szint (61.8% visszamozgás)
5. **Chart annotáció**: Rajzolja a szinteket (ha az exchange támogatja)

### 2. Fibonacci Kalkulátor (Web UI)

Az `index.html` dashboard egy interaktív **Fibonacci Kalkulátor** panelt tartalmaz:

#### Használat:
1. Töltsd ki a beviteli mezőket:
   - **Swing High**: Az utolsó swing magasságpontja
   - **Swing Low**: Az utolsó swing alacsonypontja
   - **Jelenlegi ár**: A jelenlegi piaci ár
   - **Irány**: LONG (vásárlás) vagy SHORT (eladás)

2. Válaszd ki a **TP extension** és **SL retracement** szinteket

3. Kattints a **"Fibonacci szintek kalkulálása"** gombra

#### Kimenet:
- **TP ár és %**: Az expected take profit ár és az entry-ből számított percentá
- **SL ár és %**: A stop loss ár és percentá
- **Risk/Reward ratio**: Az ár-bevételési relácó
- **Összes Fibonacci szintek**: Teljes táblázat az összes standard szintről

### 3. Beállítások (config.py)

```python
# Fibonacci TP/SL (PRIMARY)
USE_FIBONACCI_TP_SL = True              # Fibonacci-t használd (True)
FIB_TP_EXTENSION = 1.272                # TP extension szint (default: 1.272)
FIB_SL_RETRACEMENT = 0.618              # SL retracement szint (default: 0.618)
FIB_LOOKBACK_PERIODS = 24               # Hány candlet nézz vissza swing-hez

# Fallback (ha Fibonacci fails)
TAKE_PROFIT_DECIMAL = 0.20              # 20% (only if Fibonacci fails)
STOP_LOSS_DECIMAL = 0.30                # 30% (only if Fibonacci fails)
```

#### Ajánlott konfigurációk:

**Konzervatív (kisebb nyereség, kisebb kockázat):**
```python
FIB_TP_EXTENSION = 1.0                  # Szintig
FIB_SL_RETRACEMENT = 0.786              # 78.6%
```

**Kiegyensúlyozott (alapértelmezett):**
```python
FIB_TP_EXTENSION = 1.272                # 127.2%
FIB_SL_RETRACEMENT = 0.618              # 61.8%
```

**Agresszív (nagyobb nyereség, nagyobb kockázat):**
```python
FIB_TP_EXTENSION = 1.618                # Golden Ratio
FIB_SL_RETRACEMENT = 0.382              # 38.2%
```

## Technikai implementáció

### Fibonacci szintek számítása (utils/fib.py)

```python
from utils.fib import compute_fibonacci_levels

# Swing pontok közül számítsd ki az összes szintet
swing_high = 88000.0  # BTC all-time high in period
swing_low = 86000.0   # BTC all-time low in period

levels = compute_fibonacci_levels(swing_high, swing_low)
# Eredmény: {0.0: 86000.0, 0.236: 86468.0, 0.618: 87220.0, 1.272: 88568.0, ...}
```

### TP/SL automatikus kalkuláció

```python
from utils.fib import compute_tp_sl_from_fib

tp_dec, sl_dec = compute_tp_sl_from_fib(
    current_price=87500.0,
    side="BUY",
    swing_high=88000.0,
    swing_low=86000.0,
    tp_extension=1.272,
    sl_retracement=0.618
)
# Returns: tp_dec (0-1), sl_dec (0-1) decimals
```

## Fibonacci kalkulátor tool integrációja

A web UI kalkulátor segít a kereskedőknek manuálisan tesztelni a Fibonacci szinteket:

1. **Analitikus segítség**: Gyorsan ellenőrizd, milyen szintek könnyen elérhetőek
2. **Risk/Reward optimalizálás**: Lásd a risk/reward ratiót entry előtt
3. **Tanulás**: Megértsd, hogyan működnek a Fibonacci szintek a valós kereskedésben
4. **Backtesting**: Manuálisan teszteld a különböző extension/retracement kombinációkat

## Előnyök

✅ **Matematikai alapon**: Fibonacci szintek széleskörűen használt, véletlenszerűtlen alapok  
✅ **Eltávolítja a szubjektivitást**: Nem kell manuálisan TP/SL-t állítani  
✅ **Rugalmas**: Könnyen konfigurálható extension/retracement szintekhez  
✅ **Chart integráció**: Automatikus rajzolás az exchange chart-ra (ha támogatott)  
✅ **Fallback mód**: Ha Fibonacci fails, visszavált fix TP/SL-re  

## Tippek a sikeres használathoz

1. **Backtest**: Teszteld a különböző Fibonacci konfigurációkat históriás adaton
2. **Trend felismerés**: Fibonacci legjobban akkor működik, ha tiszta trend van
3. **Szintek kombinálása**: Több Fibonacci szint egy magasabb szinten lehet support/resistance
4. **Volatilitás figyelése**: Nagyobb volatilitásnál nagyobb extension célok lehetnek hatékonyabbak
5. **Risk management**: Mindig őrizd meg a 1:1-nél jobb risk/reward ratiót

## Hivatkozások

- **Investopedia - Fibonacci Retracement**: https://www.investopedia.com/articles/active-trading/091615/how-set-fibonacci-retracement-levels.asp
- **Investing.com Fibonacci Calculator**: https://www.investing.com/tools/fibonacci-calculator

## Támogatott Fibonacci szintek

| Szint | Típus | Ár | Felhasználás |
|-------|-------|-----|------------|
| 0.0% | Retracement | Swing Low | Támogatás |
| 23.6% | Retracement | - | Gyenge R/S |
| 38.2% | Retracement | - | Közepes R/S |
| 50% | Retracement | - | Pszichológiai |
| 61.8% | Retracement | - | Erős R/S ⭐ |
| 78.6% | Retracement | - | Nagyon erős |
| 100% | Base | Swing High | Ellenállás |
| 127.2% | Extension | - | TP szint ⭐ |
| 161.8% | Extension | - | Golden Ratio |
| 200% | Extension | - | Duális ext. |
| 261.8% | Extension | - | Erős ext. |

---

**Megjegyzés**: A Fibonacci szintek önmagukban nem garantálnak sikert. Használd a bot ensemble Strategy-jában a többi jelzéssel együtt (AI, trend, breakout, sentiment) a legpontosabb bejegyzésekhez.
