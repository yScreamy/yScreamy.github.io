# ai/llm_client.py
import requests

class LLMClient:
    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }
        try:
            r = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            # Be permissive with response shape
            msg = data.get("message") or {}
            return str(msg.get("content") or "").strip()
        except Exception:
            return ""
