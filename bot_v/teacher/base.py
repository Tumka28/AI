"""Shared types for Bot V's teachers.

A teacher is a stronger model Bot V asks when its own local model fails, or
that grades and corrects local answers. Every teacher answer can become a
training example (see ``bot_v.learning``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Protocol

VERDICTS = ("good", "needs_fix", "wrong")

ANSWER_SYSTEM = (
    "You are the teacher of Bot V, a small assistant that runs on a local model. "
    "Answer the user's question directly and correctly, in the same language the "
    "question is written in. Your answer will also be used as a training example "
    "for the small model, so make it complete and self-contained: no references to "
    "yourself, to Bot V, or to this conversation."
)

REVIEW_SYSTEM = (
    "You are the teacher of Bot V, a small assistant that runs on a local model. "
    "You check its answers. Be strict about correctness and fair about style."
)

REVIEW_INSTRUCTIONS = """Grade the local model's answer to the question below.

Return:
- score: an integer from 1 (useless) to 10 (fully correct and helpful)
- verdict: "good" if the answer can be shown to the user as is, "needs_fix" if it is
  partly right, "wrong" if it is incorrect or does not answer the question
- problems: short descriptions of what is wrong or missing (empty if none)
- improved_answer: the best answer to the question, in the question's language. If the
  local answer is already good, return it with only small corrections.

<question>
{question}
</question>

<local_answer>
{answer}
</local_answer>"""

# JSON schema for review results (used for structured output where supported).
REVIEW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "problems": {"type": "array", "items": {"type": "string"}},
        "improved_answer": {"type": "string"},
    },
    "required": ["score", "verdict", "problems", "improved_answer"],
    "additionalProperties": False,
}


class TeacherError(RuntimeError):
    """The teacher could not produce a usable answer."""


@dataclass
class TeacherAnswer:
    text: str
    provider: str
    model: str
    stop_reason: str = ""
    truncated: bool = False
    usage: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TeacherReview:
    score: int
    verdict: str
    problems: List[str]
    improved_answer: str
    provider: str
    model: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def review_from_dict(data: Any, provider: str, model: str) -> TeacherReview:
    """Validate a review dict from a model and coerce it into a TeacherReview."""
    if not isinstance(data, dict):
        raise TeacherError(f"review is not a JSON object: {str(data)[:200]}")
    try:
        score = int(data["score"])
        verdict = str(data["verdict"]).strip().lower()
        improved = str(data["improved_answer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TeacherError(f"review is missing fields: {exc}") from exc
    if verdict not in VERDICTS:
        raise TeacherError(f"unknown verdict {verdict!r}")
    problems = data.get("problems") or []
    if not isinstance(problems, list):
        problems = [str(problems)]
    return TeacherReview(
        score=max(1, min(10, score)),
        verdict=verdict,
        problems=[str(p) for p in problems],
        improved_answer=improved,
        provider=provider,
        model=model,
    )


class Teacher(Protocol):
    provider: str
    model: str

    def answer(self, question: str) -> TeacherAnswer: ...

    def review(self, question: str, local_answer: str) -> TeacherReview: ...
