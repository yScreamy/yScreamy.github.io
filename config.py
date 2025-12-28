import os
from hyperliquid.utils import constants
from dotenv import load_dotenv

load_dotenv(override=True)

# -----------------------------
# HÁLÓZAT
# -----------------------------
IS_TESTNET = False
BASE_URL = constants.TESTNET_API_URL if IS_TESTNET else constants.MAINNET_API_URL

# -----------------------------
WALLET_ADDRESS = os.getenv("HL_AGENT_WALLET_ADDRESS", "").strip()
PRIVATE_KEY = os.getenv("HL_AGENT_PRIVATE_KEY", "").strip()
CRYPTO_PANIC_KEY = os.getenv("CRYPTO_PANIC_KEY", "").strip()
TRADING_ADDRESS = os.getenv("HL_TRADING_ADDRESS", "").strip()


NEWS_SENTIMENT_MODEL = "ElKulako/cryptobert"
CRYPTO_PANIC_PLAN = "developer"  # ha ezt használod a URL-hez
NEWS_FETCH_LIMIT = 10
NEWS_REGION = "en"
NEWS_CURRENCIES = "BTC"



OLLAMA_URL = "http://127.0.0.1:11434"
LLM_MODEL = "llama3.1:8b"   # példa
AI_MIN_CONFIDENCE = 0.65

# Backwards-compatible env names used in main.py
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", OLLAMA_URL))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", LLM_MODEL))

# Ensemble weights (tweakable via env/config)
ENSEMBLE_WEIGHT_ARTIFICIAL_INTELLIGENCE = float(os.getenv("ENSEMBLE_WEIGHT_ARTIFICIAL_INTELLIGENCE", 0.40))
ENSEMBLE_WEIGHT_TREND_FOLLOWING = float(os.getenv("ENSEMBLE_WEIGHT_TREND_FOLLOWING", 0.20))
ENSEMBLE_WEIGHT_BREAKOUT = float(os.getenv("ENSEMBLE_WEIGHT_BREAKOUT", 0.20))
ENSEMBLE_WEIGHT_MEAN_REVERSION = float(os.getenv("ENSEMBLE_WEIGHT_MEAN_REVERSION", 0.20))
ENSEMBLE_WEIGHT_TREND_ANALYSIS = float(os.getenv("ENSEMBLE_WEIGHT_TREND_ANALYSIS", 0.10))
ENSEMBLE_WEIGHT_REINFORCEMENT_LEARNING = float(os.getenv("ENSEMBLE_WEIGHT_REINFORCEMENT_LEARNING", 0.10))

# Default candle interval
CANDLE_INTERVAL = os.getenv("CANDLE_INTERVAL", "15m")

# ====================================================
# TP/SL MANAGEMENT
# ====================================================
# Fibonacci-based TP/SL is PRIMARY (automatic calculation based on swing points)
# Fixed TP/SL below are FALLBACK ONLY (used if Fibonacci fails or is disabled)
USE_FIBONACCI_TP_SL = True  # Use Fibonacci retracement/extension for TP/SL
FIB_TP_EXTENSION = float(os.getenv("FIB_TP_EXTENSION", 1.272))      # Take profit at Fib extension (27.2%)
FIB_SL_RETRACEMENT = float(os.getenv("FIB_SL_RETRACEMENT", 0.382))  # Stop loss at Fib retracement (38.2% - lent az entry alatt)
FIB_LOOKBACK_PERIODS = int(os.getenv("FIB_LOOKBACK_PERIODS", 24))   # Bars to find swing high/low

# Trailing stop: used to manage open position when TP not yet hit
USE_TRAILING_STOP_LOSS = True  # True = trailing stop, False = static TP/SL
TRAILING_STEP_PERCENT = 0.05   # 5% steps for trailing stop (gyorsabb védelem)

# Minimum elvárt Risk/Reward arány (TP/SL százalékokból)
MIN_RISK_REWARD = float(os.getenv("MIN_RISK_REWARD", 1.5))

# Breakeven aktiválása: ha az aktuális PnL eléri ezt a decimált (pl. 0.005 = 0.5%),
# húzzuk fel az első védelmi stopot az entry szintre
BREAKEVEN_ACTIVATE_DECIMAL = float(os.getenv("BREAKEVEN_ACTIVATE_DECIMAL", 0.005))

# Fallback: if Fibonacci fails or is disabled, use these fixed levels
TAKE_PROFIT_DECIMAL = 0.20     # 20% (fallback only)
STOP_LOSS_DECIMAL = 0.30       # 30% (fallback only)

SYMBOL = "BTC"

# Ha True: executor meta-ból lekéri a MAX tőkeáttétet és azt állítja be + 100% equity-t használ.
USE_MAX_LEVERAGE = False

# Fallback (ha valamiért nem tudja lekérni a max leverage-et)
DEFAULT_LEVERAGE = 20

# Market order csúszás (0.01 = 1%)
SLIPPAGE = 0.01

# ====================================================
# IDŐZÍTÉS / BOT LOGIKA
# ====================================================
# 60 = 1 perc
LOOP_INTERVAL = 10

# hány ciklusonként retrain (ha 60 mp a ciklus, akkor 5 = 5 perc)
RETRAIN_INTERVAL = 5

# hírek frissítése (másodperc)
NEWS_REFRESH_RATE = 3600

# ====================================================
# LOG
# ====================================================
LOG_FILE = "bot_log.txt"
