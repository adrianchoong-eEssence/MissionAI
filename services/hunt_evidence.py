"""Private evidence upload helpers for event-scoped Hunt missions."""
from __future__ import annotations

import re
import uuid

from data.mission_media import REFERENCE_PREFIX
from data.runtime_database import get_runtime_database
from data.upload_safety import validate_image_content, validate_upload


_MEDIA = {
    "PHOTO": ({"jpg", "jpeg", "png", "webp", "heic"}, {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}),
    "VIDEO": ({"mp4", "mov", "m4v", "webm"}, {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"}),
}
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _segment(value: object, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    return cleaned.strip(".-") or fallback


def upload_hunt_evidence(uploaded_file, *, event_id: str, team_id: str, mission_id: str, evidence_type: str) -> dict:
    """Validate and upload a private evidence object; never return a public URL."""
    kind = str(evidence_type or "").upper()
    if kind not in _MEDIA or uploaded_file is None:
        raise ValueError("Choose the required photo or video evidence.")
    extensions, mime_types = _MEDIA[kind]
    maximum = MAX_VIDEO_BYTES if kind == "VIDEO" else MAX_PHOTO_BYTES
    payload = validate_upload(uploaded_file, extensions, mime_types, maximum, kind.lower())
    if kind == "PHOTO":
        validate_image_content(payload, "photo evidence")
    filename = _segment(getattr(uploaded_file, "name", ""), f"{kind.lower()}-evidence")
    storage_path = "/".join((
        "hunt", _segment(event_id, "event"), _segment(team_id, "team"),
        _segment(mission_id, "mission"), f"{uuid.uuid4().hex[:16]}-{filename}",
    ))
    get_runtime_database().upload_mission_media(
        storage_path=storage_path, media_bytes=payload,
        content_type=str(getattr(uploaded_file, "type", "") or "application/octet-stream"),
    )
    return {
        "EvidenceType": kind,
        "StorageReference": REFERENCE_PREFIX + storage_path,
        "FileSizeBytes": len(payload),
        # Client-side media-duration extraction is inconsistent across mobile
        # browsers, so the 5–10 second guidance is visible in the UX; the hard
        # private 50 MB ceiling is validated here and again in the RPC.
        "DurationGuidance": "5–10 seconds recommended" if kind == "VIDEO" else "",
    }
