"""Test doubles shared by the test modules."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from bot_v.llm.client import ERROR_PREFIX
from bot_v.teacher.base import TeacherAnswer, TeacherError, TeacherReview


class FakeTeacher:
    provider = "fake"
    model = "fake-teacher"

    def __init__(self, answer="teacher answer", review=None, error=None, truncated=False):
        self._answer = answer
        self._review = review
        self._error = error
        self._truncated = truncated
        self.answer_calls: List[str] = []
        self.review_calls: List[tuple] = []

    def answer(self, question: str) -> TeacherAnswer:
        self.answer_calls.append(question)
        if self._error:
            raise TeacherError(self._error)
        return TeacherAnswer(self._answer, self.provider, self.model, truncated=self._truncated)

    def review(self, question: str, local_answer: str) -> TeacherReview:
        self.review_calls.append((question, local_answer))
        if self._error:
            raise TeacherError(self._error)
        return self._review


def write_skill(root: Path, name: str, description: str, body: str = "Do the thing.", extra=None) -> Path:
    """Create a skill folder with a SKILL.md (and optional extra files)."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8"
    )
    for rel, content in (extra or {}).items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return folder


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


class ScriptedLLM(FakeLLM):
    """chat() returns the scripted replies in order (for the JSON tool loop)."""

    def __init__(self, *replies: str, reply: str = "local reply"):
        super().__init__(reply=reply)
        self.replies = list(replies)
        self.chats: List[List[Dict[str, Any]]] = []

    def chat(self, model: str, messages: List[Dict[str, Any]]) -> str:
        self.chats.append([dict(m) for m in messages])
        if not self.replies:
            return '{"answer": "done"}'
        return self.replies.pop(0)


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

    def list_models(self) -> List[str]:
        return ["oj-model"]

    def close(self) -> None:
        self.closed = True
