import os
from hyperliquid.utils import constants
from dotenv import load_dotenv

load_dotenv(override=True)

# -----------------------------
# HÁLÓZAT
# -----------------------------
IS_TESTNET = True
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

# -----------------------------
# KERESKEDÉS
# -----------------------------
SYMBOL = "BTC"

# Ha True: executor meta-ból lekéri a MAX tőkeáttétet és azt állítja be + 100% equity-t használ.
USE_MAX_LEVERAGE = False

# Fallback (ha valamiért nem tudja lekérni a max leverage-et)
DEFAULT_LEVERAGE = 20

# Market order csúszás (0.01 = 1%)
SLIPPAGE = 0.01

# -----------------------------
# IDŐZÍTÉS / BOT LOGIKA
# -----------------------------
# 60 = 1 perc
LOOP_INTERVAL = 10

# hány ciklusonként retrain (ha 60 mp a ciklus, akkor 5 = 5 perc)
RETRAIN_INTERVAL = 5

# hírek frissítése (másodperc)
NEWS_REFRESH_RATE = 3600

# -----------------------------
# LOG
# -----------------------------
LOG_FILE = "bot_log.txt"
