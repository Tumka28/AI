import requests
import json

class LLMClient:
    def __init__(self, host="http://localhost:11434"):
        self.host = host

    def query(self, model, prompt):
        url = f"{self.host}/api/generate"

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }

        try:
            res = requests.post(url, json=payload)
            data = res.json()

            if "response" in data:
                return data["response"]
            else:
                return "[LLM ERROR] No response from model"

        except Exception as e:
            return f"[LLM ERROR] {str(e)}"

