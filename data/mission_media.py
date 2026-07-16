import re
import uuid

import streamlit as st

from data.runtime_database import RuntimeDatabaseError, get_runtime_database


BUCKET = "exos-mission-media"
REFERENCE_PREFIX = f"supabase://{BUCKET}/"

MEDIA_LIMITS = {
    "image": 10 * 1024 * 1024,
    "video": 200 * 1024 * 1024,
    "document": 25 * 1024 * 1024,
}


def _safe_segment(value, fallback="file"):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return cleaned.strip("-.") or fallback


def _storage_path(reference):
    value = str(reference or "").strip()
    if value.startswith(REFERENCE_PREFIX):
        return value[len(REFERENCE_PREFIX):]
    return ""


def upload_mission_media(uploaded_file, template_id, media_kind):
    if uploaded_file is None:
        return ""

    kind = str(media_kind).strip().lower()
    if kind not in MEDIA_LIMITS:
        raise ValueError(f"Unsupported mission media type: {media_kind}")

    file_bytes = uploaded_file.getvalue()
    if not file_bytes:
        raise ValueError("The selected media file is empty.")
    if len(file_bytes) > MEDIA_LIMITS[kind]:
        limit_mb = MEDIA_LIMITS[kind] // (1024 * 1024)
        raise ValueError(f"The {kind} file exceeds the {limit_mb} MB limit.")

    template_segment = _safe_segment(str(template_id).upper(), "UNASSIGNED")
    filename = _safe_segment(uploaded_file.name, f"{kind}-file")
    storage_path = (
        f"templates/{template_segment}/{kind}/"
        f"{uuid.uuid4().hex[:12]}-{filename}"
    )
    content_type = str(
        getattr(uploaded_file, "type", "") or "application/octet-stream"
    )
    get_runtime_database().upload_mission_media(
        storage_path=storage_path,
        media_bytes=file_bytes,
        content_type=content_type,
    )
    return REFERENCE_PREFIX + storage_path


@st.cache_data(ttl=300, show_spinner=False)
def get_mission_media_url(reference, expires_in=1800):
    value = str(reference or "").strip()
    if not value:
        return ""
    storage_path = _storage_path(value)
    if not storage_path:
        return value
    try:
        return get_runtime_database().create_mission_media_url(
            storage_path,
            expires_in=expires_in,
        )
    except RuntimeDatabaseError:
        return ""


def delete_mission_media_references(references):
    paths = [
        _storage_path(reference)
        for reference in references
        if _storage_path(reference)
    ]
    if not paths:
        return []
    result = get_runtime_database().delete_mission_media(paths)
    get_mission_media_url.clear()
    return result
