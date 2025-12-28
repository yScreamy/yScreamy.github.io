# Hyperliquid Trading Bot

Ez a repo egy élő kereskedőbot, amely ensemble + ML + LLM alapú advisorral működik.

## Új funkciók
- **Fibonacci integráció**: Automatikus TP/SL számítás Fibonacci szintek alapján, web UI megjelenítés Plotly-val.
- **Hyperparaméter tuning**: RandomizedSearchCV a modell tréningben legjobb paraméterek kereséséhez.
- **Logger integráció**: Strukturált logging `utils/logger.py`-val, fájlba és konzolra.
- **CI/CD**: GitHub Actions workflow lint (flake8, black), unit tesztek és smoke tesztek futtatására.
- **Integrációs tesztek**: Mockolt tesztek az Exchange API-ra és bot komponensekre.

Gyors indítás (fejlesztés):

1. Telepítsd a függőségeket (ajánlott virtuális környezet):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r Requirements.txt
```

2. Állítsd be a környezeti változókat vagy `config.py`-t (lásd a fájl elején lévő példákat):
- `PRIVATE_KEY`, `HL_AGENT_WALLET_ADDRESS`, `HL_TRADING_ADDRESS` stb.
- (Opcionális) `OLLAMA_BASE_URL`, `OLLAMA_MODEL` ha az advisor-hoz használod az Ollama-t.

3. Indítás (lokálisan):

```bash
python main.py
```

## Fejlesztési információk
- **Fibonacci segédfüggvények**: `utils/fib.py` és web UI megjelenítés a `wwwroot/index.html`-ben (`last_fibonacci`).
- **Modell tréning**: `train_ai.py` elmenti a modellt `ai/trading_model.pkl` és a feature-listát `ai/trading_model_features.pkl`. Most hyperparaméter tuninggal.
- **AI modell**: `ai/model.py` betölti a modelt és a feature-listát, biztonságos fallback viselkedéssel.
- **Tesztek**: Unit tesztek `tests/test_fib.py`, integrációs tesztek `tests/test_integration.py`.
- **Logging**: `utils/logger.py` használata minden log üzenethez.

## További javaslatok
- Telemetria/logging külső szolgáltatásba (Sentry/Prometheus) éles környezethez.
- Frontend bővítés további chart-okkal vagy interaktív elemekkel.