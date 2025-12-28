# ai/advisor.py
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from ai.llm_client import LLMClient

SYSTEM = """You are a trading assistant for a live trading bot.
Rules:
- Output ONLY valid JSON. No markdown, no explanations outside JSON.
- You do NOT execute trades. You only propose.
- Always respect risk: never propose increasing risk when volatility/news is extreme.
- If uncertain, set bias=NEUTRAL and confidence low.
"""

def _safe_json_load(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        # Néha a model “szemetel”. Meg lehet próbálni egy tisztítást, de
        # élő botnál inkább legyen FAIL SAFE.
        return None

@dataclass
class Advice:
    raw: Dict[str, Any]

    @property
    def confidence(self) -> float:
        try:
            return float(self.raw.get("confidence", 0.0))
        except Exception:
            return 0.0

class TradingAdvisor:
    def __init__(self, client: LLMClient):
        self.client = client

    def get_advice(self, context: Dict[str, Any]) -> Optional[Advice]:
        user = json.dumps(context, ensure_ascii=False)
        out = self.client.generate(system=SYSTEM, user=user)
        parsed = _safe_json_load(out)
        if not parsed:
            return None
        return Advice(parsed)
