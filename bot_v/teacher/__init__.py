"""Bot V's teachers: stronger models Bot V learns from."""

from __future__ import annotations

from typing import Optional

from bot_v.config import Settings, settings as default_settings
from bot_v.teacher.base import Teacher, TeacherAnswer, TeacherError, TeacherReview


def load_teacher(s: Optional[Settings] = None) -> Optional[Teacher]:
    """Build the teacher configured in settings, or None if none is set."""
    s = s or default_settings
    if s.teacher_provider == "claude":
        from bot_v.teacher.claude import ClaudeTeacher

        return ClaudeTeacher(model=s.teacher_model, effort=s.teacher_effort)
    if s.teacher_provider in ("openai", "ollama"):
        from bot_v.teacher.llm_teacher import LLMTeacher

        return LLMTeacher(backend=s.teacher_provider, host=s.teacher_host, model=s.teacher_model)
    return None


__all__ = ["Teacher", "TeacherAnswer", "TeacherError", "TeacherReview", "load_teacher"]
