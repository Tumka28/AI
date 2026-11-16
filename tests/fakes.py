"""Test doubles shared by the test modules."""

from typing import Any, Dict, List, Optional

from bot_v.llm.client import ERROR_PREFIX


class FakeLLM:
    backend = "fake"
    host = "fake://"
    models = {"general": "fake-model"}

    def __init__(self, reply: str = "local reply"):
        self.reply = reply
        self.calls: List[Dict[str, Any]] = []

    def query(self, model: str, prompt: str, system: Optional[str] = None) -> str:
        self.calls.append({"model": model, "prompt": prompt, "system": system})
        return self.reply


class FailingLLM(FakeLLM):
    def __init__(self):
        super().__init__(reply=f"{ERROR_PREFIX} cannot reach server")


class FakeMemory:
    def __init__(self):
        self.indexed: List[str] = []

    def index(self, path: str) -> Dict[str, Any]:
        self.indexed.append(path)
        return {"chunks": 1, "path": path}

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return [{"content": f"hit for {query}", "score": 1.0}][:top_k]


class FakeJarvis:
    """Mimics openjarvis.Jarvis.ask_full / memory / close."""

    def __init__(self, raise_exc: Optional[Exception] = None):
        self.calls: List[Dict[str, Any]] = []
        self.closed = False
        self.memory = FakeMemory()
        self.raise_exc = raise_exc

    def ask_full(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append({"query": query, **kwargs})
        if self.raise_exc:
            raise self.raise_exc
        result: Dict[str, Any] = {
            "content": f"oj: {query}",
            "model": "oj-model",
            "engine": "llamacpp",
        }
        if kwargs.get("agent"):
            result["turns"] = 2
            result["tool_results"] = [
                {"tool_name": t, "content": "42", "success": True}
                for t in (kwargs.get("tools") or [])
            ]
        return result

    def close(self) -> None:
        self.closed = True
