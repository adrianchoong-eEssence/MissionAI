"""Programme-neutral AI service interface used by participant and facilitator flows."""

from __future__ import annotations

from dataclasses import dataclass

from ai.aura import ask_aura
from ai.client import get_openai_client


@dataclass(frozen=True)
class AIServiceResult:
    """Container for non-blocking AI responses."""

    text: str
    ok: bool = True
    fallback: bool = False


class PlatformAIService:
    """Interface for AI-backed operations with fail-open behavior."""

    def __init__(self, enabled=True):
        self.enabled = bool(enabled)

    def _ask(self, fallback: str, **kwargs) -> AIServiceResult:
        if not self.enabled:
            return AIServiceResult(fallback, ok=True, fallback=True)
        try:
            _ = get_openai_client()
        except Exception as error:
            return AIServiceResult(
                text=f"{fallback}\n\n{str(error)}".strip(),
                ok=False,
                fallback=True,
            )
        try:
            return AIServiceResult(text=ask_aura(**kwargs), ok=True, fallback=False)
        except Exception as error:
            return AIServiceResult(
                text=f"{fallback}\n\n{str(error)}".strip(),
                ok=False,
                fallback=True,
            )

    def facilitator_insights(
        self,
        *,
        facilitator_name,
        personality,
        greeting,
        mission,
        user_message,
        assistance_mode="COACH",
        allowed_hint="",
    ) -> AIServiceResult:
        return self._ask(
            "The AI assistant is currently unavailable. Please continue with facilitator guidance.",
            facilitator_name=facilitator_name,
            personality=personality,
            greeting=greeting,
            mission=mission,
            user_message=user_message,
            assistance_mode=assistance_mode,
            allowed_hint=allowed_hint,
        )

    def evaluate_submission(self, *, submission, mission):
        return self._ask(
            "Submission evaluation is currently offline.",
            facilitator_name="EXOS AI Coach",
            personality="Supportive",
            greeting="Hi team",
            mission=mission,
            user_message=f"Evaluate this submission for {mission.get('Title', 'activity')}: {submission}",
            assistance_mode="EVALUATION",
        )

    def mission_generation(self, *, event_context, constraints=""):
        return self._ask(
            "Mission generation is currently unavailable.",
            facilitator_name="EXOS Mission Architect",
            personality="Collaborative",
            greeting="Ready when you are",
            mission={"EventContext": event_context, "Constraints": constraints},
            user_message="Generate a mission plan.",
            assistance_mode="GENERATION",
        )

    def programme_generation(self, *, event_context, constraints=""):
        return self._ask(
            "Programme generation is currently unavailable.",
            facilitator_name="EXOS Programme Architect",
            personality="Collaborative",
            greeting="Ready when you are",
            mission={"EventContext": event_context, "Constraints": constraints},
            user_message="Generate a programme blueprint.",
            assistance_mode="GENERATION",
        )

    def reflection_synthesis(self, *, mission, response):
        return self._ask(
            "Reflection synthesis is currently unavailable.",
            facilitator_name="EXOS Reflection Coach",
            personality="Reflective",
            greeting="Great effort",
            mission=mission,
            user_message=f"Summarise this reflection: {response}",
            assistance_mode="SYNTHESIS",
        )


def get_platform_ai_service():
    return PlatformAIService(enabled=True)
