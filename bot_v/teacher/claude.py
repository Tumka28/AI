"""Claude as Bot V's teacher, through the official Anthropic Python SDK.

Install with ``pip install -r requirements-teacher.txt`` and provide credentials
the way the SDK resolves them (``ANTHROPIC_API_KEY``, or an ``ant auth login``
profile). Prompts sent here leave the machine: only enable this teacher if
that is acceptable for what you ask Bot V.

Requests go to ``client.beta.messages.create`` with server-side refusal
fallbacks (``fallbacks="default"``): if Claude's safety classifiers decline a
request, the API retries it on the model Anthropic recommends for that case.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from bot_v.teacher.base import (
    ANSWER_SYSTEM,
    REVIEW_INSTRUCTIONS,
    REVIEW_SCHEMA,
    REVIEW_SYSTEM,
    TeacherAnswer,
    TeacherError,
    TeacherReview,
    review_from_dict,
)

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000  # non-streaming default; leaves room for long answers


class ClaudeTeacher:
    provider = "claude"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        effort: str = "high",
        client: Any = None,
        max_tokens: int = MAX_TOKENS,
    ):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client

    # ------------------------------------------------------------- plumbing
    def _sdk(self):
        try:
            import anthropic
        except ImportError as exc:
            raise TeacherError(
                "the 'anthropic' package is not installed: pip install -r requirements-teacher.txt"
            ) from exc
        return anthropic

    def _get_client(self) -> Any:
        if self._client is None:
            anthropic = self._sdk()
            try:
                self._client = anthropic.Anthropic()
            except anthropic.AnthropicError as exc:
                raise TeacherError(f"cannot create Claude client: {exc}") from exc
        return self._client

    def _create(self, *, system: str, prompt: str, output_config: Dict[str, Any]) -> Any:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": output_config,
        }
        # Haiku has no server-side fallback; every other current model does.
        if not self.model.startswith("claude-haiku"):
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"

        client = self._get_client()
        try:
            return client.beta.messages.create(**kwargs)
        except Exception as exc:
            raise self._translate(exc) from exc

    def _translate(self, exc: Exception) -> TeacherError:
        try:
            import anthropic
        except ImportError:
            return TeacherError(str(exc))
        # Most specific first.
        if isinstance(exc, anthropic.AuthenticationError):
            return TeacherError("Claude rejected the credentials: set ANTHROPIC_API_KEY or run `ant auth login`")
        if isinstance(exc, anthropic.PermissionDeniedError):
            return TeacherError(f"this API key may not use {self.model}")
        if isinstance(exc, anthropic.NotFoundError):
            return TeacherError(f"model {self.model!r} was not found")
        if isinstance(exc, anthropic.RateLimitError):
            return TeacherError("Claude rate limit reached; try again later")
        if isinstance(exc, anthropic.BadRequestError):
            return TeacherError(f"Claude rejected the request: {exc.message}")
        if isinstance(exc, anthropic.APIStatusError):
            return TeacherError(f"Claude API error {exc.status_code}: {exc.message}")
        if isinstance(exc, anthropic.APIConnectionError):
            return TeacherError("cannot reach the Claude API (network error)")
        if isinstance(exc, anthropic.AnthropicError):
            return TeacherError(f"Claude client error: {exc}")
        if isinstance(exc, TypeError) and "authentication" in str(exc).lower():
            # Raised by the SDK at request time when it finds no credentials.
            return TeacherError("no Claude credentials: set ANTHROPIC_API_KEY or run `ant auth login`")
        return TeacherError(f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _text(response: Any) -> str:
        return "".join(
            block.text for block in (response.content or []) if getattr(block, "type", "") == "text"
        )

    def _check_refusal(self, response: Any) -> None:
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise TeacherError(f"Claude declined this request (category: {category or 'unknown'})")

    @staticmethod
    def _usage(response: Any) -> Dict[str, Any]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        return {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }

    # ------------------------------------------------------------ teaching
    def answer(self, question: str) -> TeacherAnswer:
        response = self._create(
            system=ANSWER_SYSTEM,
            prompt=question,
            output_config={"effort": self.effort},
        )
        self._check_refusal(response)
        text = self._text(response)
        if not text.strip():
            raise TeacherError("Claude returned an empty answer")
        return TeacherAnswer(
            text=text,
            provider=self.provider,
            # The model that actually answered (differs if a fallback served it).
            model=getattr(response, "model", None) or self.model,
            stop_reason=getattr(response, "stop_reason", "") or "",
            truncated=getattr(response, "stop_reason", None) == "max_tokens",
            usage=self._usage(response),
        )

    def review(self, question: str, local_answer: str) -> TeacherReview:
        response = self._create(
            system=REVIEW_SYSTEM,
            prompt=REVIEW_INSTRUCTIONS.format(question=question, answer=local_answer),
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": REVIEW_SCHEMA},
            },
        )
        self._check_refusal(response)
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise TeacherError("Claude's review was cut off (max_tokens)")
        text = self._text(response)
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise TeacherError(f"Claude's review was not valid JSON: {text[:200]}") from exc
        return review_from_dict(data, self.provider, getattr(response, "model", None) or self.model)


def make_claude_teacher(model: Optional[str] = None, effort: str = "high") -> ClaudeTeacher:
    return ClaudeTeacher(model=model or DEFAULT_MODEL, effort=effort)
