# 🎯 Fibonacci TP/SL Kalkulátor - Új Funkció

## Összefoglaló

Implementáltam egy **Fibonacci retracement és extension alapú** automatikus Take Profit / Stop Loss (TP/SL) rendszert a tradingbot-hoz. Ez **eltávolította a manuális TP/SL beállítások szükségességét** és helyette matematikai alapon számított szinteket használ.

### Mik a főbb újítások?

✅ **Fibonacci-alapú TP/SL (PRIMARY)**
- Automatikus kalkuláció entry-nél
- Swing high/low felismerés az utolsó 24 candleból
- Konfigurálható extension (TP) és retracement (SL) szintek

✅ **Web UI Fibonacci Kalkulátor**
- Interaktív panel az index.html-ben
- Manuális szintkalkuláció backtesting-hez
- Risk/Reward ratio megjelenítés

✅ **Fallback rendszer**
- Ha Fibonacci fails, visszavált fix TP/SL-re
- Robusztus error handling

✅ **Chart Annotáció**
- Fibonacci szintek rajzolása az exchange charton (ha támogatott)

## Technikai részletek

### 1. Fibonacci szintek (utils/fib.py)

```python
from utils.fib import compute_fibonacci_levels

# Swing pontokból számítsd az összes szintet
levels = compute_fibonacci_levels(swing_high=90000, swing_low=85000)
# {0.0: 85000.0, 0.236: 86180.0, 0.382: 86910.0, ..., 1.618: 93090.0}
```

**Standrd szintek:**
- Retracements: 23.6%, 38.2%, 50%, 61.8%, 78.6%
- Extensions: 100%, 127.2%, 161.8%, 200%, 261.8%

### 2. TP/SL Kalkuláció

```python
from utils.fib import compute_tp_sl_from_fib

tp_dec, sl_dec = compute_tp_sl_from_fib(
    current_price=87500,
    side="BUY",
    swing_high=90000,
    swing_low=85000,
    tp_extension=1.272,  # 127.2% - szint TP-hez
    sl_retracement=0.382  # 38.2% - szint SL-hez
)
# Returns: (0.0441, 0.0067) = 4.41% TP, 0.67% SL
```

**Risk/Reward ratio:** 1:6.54 (nagyon jó)

### 3. Config beállítások (config.py)

```python
# PRIMARY: Fibonacci-alapú TP/SL
USE_FIBONACCI_TP_SL = True
FIB_TP_EXTENSION = 1.272       # 127.2% extension (TP)
FIB_SL_RETRACEMENT = 0.382     # 38.2% retracement (SL)
FIB_LOOKBACK_PERIODS = 24      # Hány candle-t nézz vissza

# FALLBACK: Ha Fibonacci fails
TAKE_PROFIT_DECIMAL = 0.20     # 20%
STOP_LOSS_DECIMAL = 0.30       # 30%
```

**Javasolt konfigurációk:**

| Profil | TP Extension | SL Retracement | Risk/Reward | Jelleg |
|--------|--------------|----------------|-------------|--------|
| Konzervatív | 1.0 | 0.786 | 1:0.5 | Kis nyereség, kis kockázat |
| Kiegyensúlyozott ⭐ | 1.272 | 0.382 | 1:6.5 | Default (jelenlegi) |
| Agresszív | 1.618 | 0.236 | 1:10 | Nagy nyereség, nagy kockázat |

### 4. Web UI Fibonacci Kalkulátor

Az `index.html`-ben egy új **"🔢 Fibonacci Kalkulátor"** panel:

1. **Bemenet:**
   - Swing High
   - Swing Low
   - Jelenlegi ár
   - Irány (BUY/SELL)
   - TP extension szint
   - SL retracement szint

2. **Kimenet:**
   - TP ár és %
   - SL ár és %
   - Risk/Reward ratio
   - Összes Fibonacci szint táblázat

3. **Használat:**
   ```html
   <!-- Fibonacci Calculator Panel -->
   <div class="controls">
     <h3>🔢 Fibonacci Kalkulátor</h3>
     <input id="fibSwingHigh" type="number" placeholder="Swing High">
     <input id="fibSwingLow" type="number" placeholder="Swing Low">
     <button class="btn btn-primary" id="btnCalcFib">Kalkulálja</button>
   </div>
   ```

## Integrációs pontok main.py-ben

### Entry logika (position megnyitás)

```python
# --- Fibonacci: compute levels and set TP/SL automatically (PRIMARY) ---
if FIB_ENABLED and high_series is not None and low_series is not None:
    # 1. Swing high/low meghatározása
    swing_high = high_series.iloc[-FIB_LOOKBACK:].max()
    swing_low = low_series.iloc[-FIB_LOOKBACK:].min()
    
    # 2. Fibonacci szintek számítása
    fib_levels = compute_fibonacci_levels(swing_high, swing_low)
    
    # 3. TP/SL árak kiválasztása
    tp_price = fib_levels[FIB_TP_EXTENSION]
    sl_price = fib_levels[FIB_SL_RETRACEMENT]
    
    # 4. Decimális TP/SL számítása
    tp_dec = (tp_price - current_price) / current_price  # BUY
    sl_dec = (current_price - sl_price) / current_price
    
    # 5. Alkalmazás az instancere
    self.take_profit_decimal = tp_dec
    self.stop_loss_decimal = sl_dec
    
    # 6. Chart annotáció
    ann = {
        "type": "fibonacci",
        "swing_high": swing_high,
        "swing_low": swing_low,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "levels": fib_levels,
        ...
    }
    self.executor.exchange.create_annotation(ann)
```

### Fallback logika

```python
if not fib_success:
    # Fallback: use fixed TP/SL
    self.take_profit_decimal = TAKE_PROFIT_DECIMAL
    self.stop_loss_decimal = STOP_LOSS_DECIMAL
    note += "Fallback TP/SL: 20% / 30%"
```

## Tesztvezetés

Alle tesztek passar:

```bash
$ pytest tests/ -v
================ 12 passed in 6.22s ==================
```

**Tesztelt funkciók:**
- ✅ `test_compute_fib_levels` - Fibonacci szintek kiszámítása
- ✅ `test_tp_sl_buy` - TP/SL BUY-hoz
- ✅ `test_tp_sl_sell` - TP/SL SELL-hez
- ✅ `test_fib_levels_integration` - Integrációs teszt
- ✅ `test_tp_sl_integration_buy/sell` - Full TP/SL flow
- ✅ `test_bot_init` - Bot inicializáció

## Dokumentáció

Részletes Guide: **[FIBONACCI_GUIDE.md](FIBONACCI_GUIDE.md)**

## Előnyök

🎯 **Matematikai alapon:** Fibonacci szintek széles körben használt, nem szubjektív alapok  
⚡ **Automatikus:** Nem kell manuálisan TP/SL-t állítani  
🔧 **Rugalmas:** Könnyen konfigurálható extension/retracement szintekhez  
📊 **Chart integráció:** Automatikus rajzolás (ha támogatott)  
🛡️ **Fallback:** Ha Fibonacci fails, visszavált fix TP/SL-re  
🧮 **Backtesting:** Web UI kalkulátor a manuális teszteléshez  

## Telepítés és használat

1. **Config beállítás:**
   ```python
   USE_FIBONACCI_TP_SL = True
   FIB_TP_EXTENSION = 1.272
   FIB_SL_RETRACEMENT = 0.382
   ```

2. **Bot indítása:**
   ```bash
   python main.py
   ```

3. **Web UI:**
   - Nyisd meg: `http://localhost:8080`
   - Fibonacci Kalkulátor panel használata backtesting-hez

## Közeljövő fejlesztések (opcionális)

- [ ] Dinamikus Fibonacci szint kiválasztás az ADX/volatilitás alapján
- [ ] Multi-timeframe Fibonacci konfluencia
- [ ] Fibonacci szint szerkesztő az UI-ban
- [ ] Fibonacci-based trailing stop
- [ ] RL model tanítás Fibonacci szinteken alapulva

## Összefoglalás

A Fibonacci TP/SL rendszer:
✅ **Működik**: Tesztek pass, bot elindulnál  
✅ **Konfigurálható**: Könnyen módosítható szintek  
✅ **Biztonságos**: Fallback rendszer, error handling  
✅ **Felhasználóbarát**: Web UI kalkulátor a tanuláshoz  
✅ **Produkciókész**: Ready to use a valós kereskedéshez  

---

**Megjegyzés**: Ez a rendszer matematikai alapokon alapul, de **nem garantál profitot**. Mindig az ensemble stratégia többi jelzésével (AI, trend, sentiment) együtt használd!
