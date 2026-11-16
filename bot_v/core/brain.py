"""Bot V — the master controller.

Bot V owns the decisions; backends do the work:

    user -> BotV -> local LLM              Bot V's own answers (+ approved skills)
                 -> Teacher                a stronger model, when the local one fails
                                           or to grade local answers (review mode)
                 -> PermissionGate -> OpenJarvisAdapter -> OpenJarvis agents/tools

Everything Bot V does is written to the ExperienceLog; what it learns from
the teacher goes to the TrainingStore (fine-tuning data).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from bot_v.config import settings
from bot_v.core.permissions import PermissionGate
from bot_v.integrations.openjarvis_adapter import OpenJarvisAdapter, OpenJarvisUnavailable
from bot_v.learning.dataset import TrainingStore
from bot_v.llm.client import LLMClient, is_error
from bot_v.memory.experience_log import ExperienceLog
from bot_v.skills.library import SkillLibrary
from bot_v.teacher import Teacher, TeacherError, load_teacher

SYSTEM_PROMPT = (
    "You are Bot V, a personal AI assistant. Answer clearly and concisely, "
    "in the same language the user writes in."
)

BACKENDS = ("auto", "local", "openjarvis", "teacher")
GOOD_SCORE = 8  # review score at or above which a "good" local answer is kept

_FROM_SETTINGS: Any = object()


class BotV:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        openjarvis: Optional[OpenJarvisAdapter] = None,
        gate: Optional[PermissionGate] = None,
        log: Optional[ExperienceLog] = None,
        on_event: Optional[Callable[[str], None]] = None,
        teacher: Any = _FROM_SETTINGS,
        teacher_mode: Optional[str] = None,
        training: Optional[TrainingStore] = None,
        skills: Optional[SkillLibrary] = None,
    ):
        self.llm = llm or LLMClient()
        self.openjarvis = openjarvis or OpenJarvisAdapter()
        self.gate = gate or PermissionGate()
        self.log = log or ExperienceLog()
        self._on_event = on_event
        self.teacher: Optional[Teacher] = load_teacher() if teacher is _FROM_SETTINGS else teacher
        self.teacher_mode = teacher_mode or settings.teacher_mode
        self.training = training or TrainingStore()
        self.skills = skills or SkillLibrary()

    def _event(self, text: str) -> None:
        if self._on_event is not None:
            try:
                self._on_event(text)
            except Exception:
                pass

    def _skill_context(self, text: str) -> Tuple[List[str], str]:
        try:
            return self.skills.context_for(text)
        except Exception:  # a broken skill must never break answering
            return [], ""

    # ------------------------------------------------------------ actions
    def chat(self, message: str) -> Dict[str, Any]:
        """Answer with Bot V's own local model (plus any relevant approved skills)."""
        names, context = self._skill_context(message)
        system = f"{SYSTEM_PROMPT}\n\n{context}" if context else SYSTEM_PROMPT
        self._event(f"local: thinking (skills: {names})" if names else "local: thinking")
        reply = self.llm.query("general", message, system=system)
        status = "error" if is_error(reply) else "ok"
        self.log.record(
            "chat", backend="local", input=message, output=reply, status=status, skills=names or None
        )
        out = {"status": status, "backend": "local", "reply": reply}
        if names:
            out["skills"] = names
        return out

    def delegate(
        self,
        task: str,
        *,
        agent: Optional[str] = None,
        tools: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Hand a task to OpenJarvis, after Bot V's permission check."""
        tools = list(tools or [])
        decision = self.gate.check(task, tools)
        if not decision.allowed:
            self._event(f"openjarvis: denied {decision.denied}")
            self.log.record(
                "delegate", backend="openjarvis", input=task, agent=agent, tools=tools,
                status="denied", denied=decision.denied, reason=decision.reason,
            )
            return {
                "status": "denied",
                "backend": "openjarvis",
                "reply": f"Bot V blocked tools {decision.denied}: {decision.reason}",
                "denied": decision.denied,
            }

        # OpenJarvis's SDK does not load skills itself, so Bot V passes along
        # the instructions of the approved skills that fit this task.
        names, context = self._skill_context(task)
        oj_task = f"{context}\n\n<task>\n{task}\n</task>" if context else task

        self._event(f"openjarvis: running (agent={agent}, tools={tools})")
        try:
            result = self.openjarvis.ask(oj_task, agent=agent, tools=tools)
        except OpenJarvisUnavailable as exc:
            self.log.record("delegate", backend="openjarvis", input=task, status="unavailable")
            return {"status": "unavailable", "backend": "openjarvis", "reply": str(exc)}
        except Exception as exc:
            self.log.record(
                "delegate", backend="openjarvis", input=task, agent=agent, tools=tools,
                status="error", error=str(exc),
            )
            return {"status": "error", "backend": "openjarvis", "reply": f"OpenJarvis error: {exc}"}

        self.log.record(
            "delegate", backend="openjarvis", input=task, agent=agent, tools=tools,
            approved=decision.approved, output=result.content,
            tool_results=result.tool_results, model=result.model, status="ok",
            skills=names or None,
        )
        self._event("openjarvis: done")
        out = {
            "status": "ok",
            "backend": "openjarvis",
            "reply": result.content,
            "result": result.to_dict(),
        }
        if names:
            out["skills"] = names
        return out

    # ------------------------------------------------------------- teacher
    def ask_teacher(self, message: str) -> Dict[str, Any]:
        """Ask the teacher directly and keep its answer as a training example."""
        if self.teacher is None:
            return {
                "status": "unavailable",
                "backend": "teacher",
                "reply": "No teacher is configured. Set BOTV_TEACHER (claude, openai or ollama).",
            }
        self._event(f"teacher: asking {self.teacher.provider}/{self.teacher.model}")
        try:
            answer = self.teacher.answer(message)
        except TeacherError as exc:
            self.log.record("teacher", backend="teacher", input=message, status="error", error=str(exc))
            return {"status": "error", "backend": "teacher", "reply": f"Teacher error: {exc}"}

        example_id = None
        if not answer.truncated:
            example_id = self.training.add(
                message, answer.text, source="teacher_answer",
                teacher=answer.provider, model=answer.model,
            )["id"]
        self.log.record(
            "teacher", backend="teacher", input=message, output=answer.text, status="ok",
            model=answer.model, truncated=answer.truncated, usage=answer.usage, example_id=example_id,
        )
        self._event("teacher: done")
        return {
            "status": "ok",
            "backend": "teacher",
            "reply": answer.text,
            "teacher": {"provider": answer.provider, "model": answer.model},
            "learned": example_id is not None,
        }

    def _review(self, message: str, local: Dict[str, Any]) -> Dict[str, Any]:
        """Let the teacher grade a local answer; use its correction if needed."""
        self._event("teacher: reviewing the local answer")
        try:
            review = self.teacher.review(message, local["reply"])
        except TeacherError as exc:
            self.log.record("review", backend="teacher", input=message, status="error", error=str(exc))
            return {**local, "review_error": str(exc)}

        info = {"provider": review.provider, "model": review.model,
                "score": review.score, "verdict": review.verdict, "problems": review.problems}
        if review.verdict == "good" and review.score >= GOOD_SCORE:
            self.training.add(message, local["reply"], source="local_verified",
                              teacher=review.provider, model=review.model, score=review.score)
            self.log.record("review", backend="teacher", input=message, status="ok", **info)
            return {**local, "review": info}

        self.training.add(message, review.improved_answer, source="teacher_correction",
                          rejected=local["reply"], teacher=review.provider, model=review.model,
                          score=review.score)
        self.log.record("review", backend="teacher", input=message, status="ok",
                        output=review.improved_answer, **info)
        out = {
            "status": "ok",
            "backend": "teacher",
            "reply": review.improved_answer,
            "review": info,
            "local_reply": local["reply"],
            "learned": True,
        }
        if local.get("skills"):
            out["skills"] = local["skills"]
        return out

    # -------------------------------------------------------------- router
    def handle(self, message: str, backend: str = "auto") -> Dict[str, Any]:
        """Entry point for a user message.

        ``auto``: the local model answers. If it fails, Bot V asks the teacher
        (unless the teacher mode is "manual"), then OpenJarvis. In "review"
        mode the teacher also grades every local answer.
        """
        if backend not in BACKENDS:
            raise ValueError(f"backend must be one of {BACKENDS}, got {backend!r}")
        if backend == "openjarvis":
            return self.delegate(message)
        if backend == "teacher":
            return self.ask_teacher(message)

        local = self.chat(message)
        if backend == "local":
            return local
        if local["status"] == "ok":
            if self.teacher is not None and self.teacher_mode == "review":
                return self._review(message, local)
            return local

        if self.teacher is not None and self.teacher_mode != "manual":
            self._event("local model failed, asking the teacher")
            answer = self.ask_teacher(message)
            if answer["status"] == "ok":
                return {**answer, "fallback_from": "local", "local_error": local["reply"]}

        if self.openjarvis.is_installed():
            self._event("local model failed, falling back to OpenJarvis")
            fallback = self.delegate(message)
            fallback["fallback_from"] = "local"
            fallback["local_error"] = local["reply"]
            return fallback
        return local

    # ------------------------------------------------------------- status
    def status(self) -> Dict[str, Any]:
        teacher = None
        if self.teacher is not None:
            teacher = {"provider": self.teacher.provider, "model": self.teacher.model,
                       "mode": self.teacher_mode}
        try:
            skills = self.skills.list()
            skills_summary = {"installed": [s["name"] for s in skills["installed"]],
                              "quarantined": [s["name"] for s in skills["quarantined"]]}
        except Exception as exc:
            skills_summary = {"error": str(exc)}
        return {
            "llm": {
                "backend": self.llm.backend,
                "host": self.llm.host,
                "models": self.llm.models,
            },
            "openjarvis": self.openjarvis.status(),
            "teacher": teacher,
            "learning": self.training.stats(),
            "skills": skills_summary,
            "safe_tools": sorted(self.gate.safe_tools),
            "approver": self.gate.approver is not None,
        }

    def close(self) -> None:
        self.openjarvis.close()
