from unittest.mock import patch

from services.platform_ai_service import PlatformAIService



def test_ai_fallback_does_not_raise_and_returns_default():
    with patch("services.platform_ai_service.get_openai_client", side_effect=RuntimeError("no key")):
        service = PlatformAIService(enabled=True)
        result = service.facilitator_insights(
            facilitator_name="EXOS",
            personality="Friendly",
            greeting="Hello",
            mission={},
            user_message="Where do we go?",
            assistance_mode="COACH",
        )

    assert result.ok is False
    assert result.fallback is True
    assert "AI assistant is currently unavailable" in result.text


def test_ai_success_path_maps_to_result_text():
    with patch("services.platform_ai_service.get_openai_client", return_value=object()):
        with patch("services.platform_ai_service.ask_aura", return_value="Use nearby signs."):
            service = PlatformAIService(enabled=True)
            result = service.facilitator_insights(
                facilitator_name="EXOS",
                personality="Friendly",
                greeting="Hello",
                mission={},
                user_message="Where do we go?",
                assistance_mode="COACH",
            )

    assert result.ok is True
    assert result.fallback is False
    assert result.text == "Use nearby signs."


def test_service_off_does_not_call_openai():
    with patch("services.platform_ai_service.get_openai_client") as openai_client:
        service = PlatformAIService(enabled=False)
        result = service.reflection_synthesis(mission={}, response="Great job")

    openai_client.assert_not_called()
    assert result.ok is True
    assert result.fallback is True
