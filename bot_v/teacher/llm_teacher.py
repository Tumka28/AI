"""A bigger self-hosted model as Bot V's teacher.

Any server Bot V's LLM client can talk to works: Ollama, or an
OpenAI-compatible server (llama-server, LM Studio, vLLM) on a stronger machine.
Nothing leaves your own network unless that server is remote.
"""

from __future__ import annotations

from typing import Any, Optional

from bot_v.llm.client import LLMClient, LLMError
from bot_v.llm.parsing import extract_json
from bot_v.teacher.base import (
    ANSWER_SYSTEM,
    REVIEW_INSTRUCTIONS,
    REVIEW_SYSTEM,
    TeacherAnswer,
    TeacherError,
    TeacherReview,
    review_from_dict,
)

JSON_REPLY_HINT = (
    '\n\nReply with only a JSON object with the keys "score", "verdict", '
    '"problems" and "improved_answer".'
)


class LLMTeacher:
    def __init__(self, backend: str, host: str, model: str, client: Optional[Any] = None):
        if not model:
            raise ValueError("BOTV_TEACHER_MODEL is required for an openai/ollama teacher")
        self.provider = backend
        self.model = model
        self.client = client or LLMClient(host=host, backend=backend, models={"teacher": model})

    def _chat(self, system: str, prompt: str) -> str:
        try:
            return self.client.chat(
                "teacher",
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
        except LLMError as exc:
            raise TeacherError(f"teacher model failed: {exc}") from exc

    def answer(self, question: str) -> TeacherAnswer:
        text = self._chat(ANSWER_SYSTEM, question)
        if not text.strip():
            raise TeacherError("teacher returned an empty answer")
        return TeacherAnswer(text=text, provider=self.provider, model=self.model)

    def review(self, question: str, local_answer: str) -> TeacherReview:
        prompt = REVIEW_INSTRUCTIONS.format(question=question, answer=local_answer) + JSON_REPLY_HINT
        reply = self._chat(REVIEW_SYSTEM, prompt)
        try:
            data = extract_json(reply)
        except (ValueError, LLMError) as exc:
            raise TeacherError(f"teacher review was not valid JSON: {reply[:200]}") from exc
        return review_from_dict(data, self.provider, self.model)
