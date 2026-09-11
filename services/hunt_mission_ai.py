"""Read-only, event-grounded Mission AI for Hunt participants."""
from __future__ import annotations

from base64 import b64encode
import json
import os
import urllib.error
import urllib.request


def _visible_missions(workspace: dict) -> list[dict]:
    return [{
        "name": mission.get("Name", "Mission"), "type": mission.get("MissionType", ""),
        "state": mission.get("MissionState", ""), "instructions": mission.get("Instructions", ""),
        "checkpoint": mission.get("CheckpointID", ""), "points": mission.get("MaximumScore", 0),
        "evidence": mission.get("EvidenceType", "NONE"),
    } for mission in list(workspace.get("Missions") or []) if mission.get("Visible", True)]


def _context(workspace: dict) -> dict:
    return {
        "event": workspace.get("EventName", "Mission AI Walk Hunt"),
        "team": workspace.get("TeamName") or workspace.get("TeamID", ""),
        "operational_state": workspace.get("OperationalState", "READY"),
        "progress": workspace.get("Progress", {}),
        "missions": _visible_missions(workspace),
        "rules": [
            "Use only the supplied event, team, mission and checkpoint context.",
            "Do not infer, guess or claim the participant's GPS location.",
            "Do not award points, mark a mission complete, change a Captain, or alter the Hunt state.",
        ],
    }


def _fallback(question: str, context: dict) -> str:
    query = str(question or "").casefold()
    missions = list(context.get("missions") or [])
    if "near" in query or "location" in query or "where" in query:
        return "I cannot infer your location. Check the LIVE LOCATION status and the canonical checkpoint proximity shown in Mission AI."
    if "score" in query or "point" in query:
        ranked = sorted(missions, key=lambda item: float(item.get("points") or 0), reverse=True)
        return "Visible mission values: " + "; ".join(f"{row['name']} — {int(float(row['points'] or 0))} pts" for row in ranked[:4]) + ". Scores require the configured evidence and review."
    if "next" in query or "consider" in query or "clue" in query:
        available = [item for item in missions if str(item.get("state", "")).upper() == "AVAILABLE"]
        if available:
            choice = max(available, key=lambda item: float(item.get("points") or 0))
            return f"A visible option is {choice['name']}. {choice['instructions']} Choose based on your team, safety, and the return window."
    return "I can explain a visible mission, its required evidence, or help your team think through a clue. I cannot verify location, score work, or complete a mission."


def ask_hunt_mission_ai(question: str, workspace: dict, image_bytes: bytes | None = None,
                        image_content_type: str = "") -> str:
    """Request a short advisory answer, with deterministic safe fallback."""
    context = _context(workspace)
    key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return _fallback(question, context)
    prompt = "CANONICAL HUNT CONTEXT:\n" + json.dumps(context, ensure_ascii=False) + "\n\nQUESTION:\n" + str(question or "")
    content = [{"type": "input_text", "text": prompt}]
    if image_bytes and image_content_type in {"image/jpeg", "image/png", "image/webp"}:
        content.append({"type": "input_image", "image_url": "data:" + image_content_type + ";base64," + b64encode(image_bytes).decode("ascii")})
    payload = json.dumps({
        "model": "gpt-4.1-mini",
        "instructions": (
            "You are Mission AI for a Walk Hunt. Use only the supplied canonical context. "
            "Never infer GPS location, make up checkpoint facts, award points, submit evidence, mark a mission complete, "
            "or alter Captain/Hunt state. If context does not answer it, say to check with a facilitator. Keep under 120 words."
        ),
        "input": [{"role": "user", "content": content}], "max_output_tokens": 250,
    }).encode("utf-8")
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=payload, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return _fallback(question, context)
    answer = str(response_body.get("output_text") or "").strip()
    return answer or _fallback(question, context)
