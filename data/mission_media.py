import re
import uuid

import streamlit as st

from data.runtime_database import RuntimeDatabaseError, get_runtime_database
from data.upload_safety import validate_image_content, validate_upload


BUCKET = "exos-mission-media"
REFERENCE_PREFIX = f"supabase://{BUCKET}/"
RACE_STATION_REFERENCE_ROOT = "formula-race/stations"

MEDIA_LIMITS = {
    "image": 10 * 1024 * 1024,
    "video": 200 * 1024 * 1024,
    "document": 25 * 1024 * 1024,
}

MEDIA_FORMATS = {
    "image": (
        {"jpg", "jpeg", "png", "webp", "heic"},
        {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"},
    ),
    "video": (
        {"mp4", "mov", "m4v", "webm"},
        {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"},
    ),
    "document": (
        {"pdf", "doc", "docx", "ppt", "pptx"},
        {"application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ),
}


def _safe_segment(value, fallback="file"):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return cleaned.strip("-.") or fallback


def _storage_path(reference):
    value = str(reference or "").strip()
    if value.startswith(REFERENCE_PREFIX):
        return value[len(REFERENCE_PREFIX):]
    return ""


def _race_station_reference_prefix(event_id, activity_id):
    """Return the private, exact scope for one R.A.C.E. station reference."""
    return (
        f"{RACE_STATION_REFERENCE_ROOT}/"
        f"{_safe_segment(event_id, 'unassigned-event')}/"
        f"{_safe_segment(activity_id, 'unassigned-station')}/reference/"
    )


def upload_formula_race_station_reference(runtime, uploaded_file, event_id, activity_id):
    """Validate and store one facilitator-only station reference image privately.

    The supplied runtime keeps this helper usable by the Core-v2 adapter and
    avoids routing a R.A.C.E. asset through the generic global runtime.
    """
    if uploaded_file is None:
        return ""
    extensions, mime_types = MEDIA_FORMATS["image"]
    image_bytes = validate_upload(
        uploaded_file, extensions, mime_types, MEDIA_LIMITS["image"],
        "station reference image",
    )
    validate_image_content(image_bytes, "station reference image")
    storage_path = (
        _race_station_reference_prefix(event_id, activity_id)
        +
        f"{uuid.uuid4().hex[:12]}-"
        f"{_safe_segment(getattr(uploaded_file, 'name', ''), 'reference-image')}"
    )
    runtime.upload_mission_media(
        storage_path=storage_path,
        media_bytes=image_bytes,
        content_type=str(getattr(uploaded_file, "type", "") or "application/octet-stream"),
    )
    return REFERENCE_PREFIX + storage_path


def get_formula_race_station_reference_url(runtime, reference, expires_in=1800):
    """Resolve a private reference image without exposing its storage path."""
    storage_path = _storage_path(reference)
    if not storage_path:
        return str(reference or "").strip()
    try:
        return runtime.create_mission_media_url(storage_path, expires_in=expires_in)
    except RuntimeDatabaseError:
        return ""


def delete_formula_race_station_reference(runtime, event_id, activity_id, reference):
    """Delete only an image owned by this exact event/station scope."""
    storage_path = _storage_path(reference)
    expected_prefix = _race_station_reference_prefix(event_id, activity_id)
    if not storage_path or not storage_path.startswith(expected_prefix):
        return []
    return runtime.delete_mission_media([storage_path])


def upload_mission_media(uploaded_file, template_id, media_kind):
    if uploaded_file is None:
        return ""

    kind = str(media_kind).strip().lower()
    if kind not in MEDIA_LIMITS:
        raise ValueError(f"Unsupported mission media type: {media_kind}")

    extensions, mime_types = MEDIA_FORMATS[kind]
    file_bytes = validate_upload(
        uploaded_file, extensions, mime_types, MEDIA_LIMITS[kind], kind,
    )
    if kind == "image":
        validate_image_content(file_bytes, "image")

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


def upload_character_portrait(uploaded_file, character_source):
    """Upsert one reusable portrait object for a named character."""
    if uploaded_file is None:
        return ""
    extensions, mime_types = MEDIA_FORMATS["image"]
    file_bytes = validate_upload(
        uploaded_file, extensions, mime_types,
        MEDIA_LIMITS["image"], "portrait image",
    )
    validate_image_content(file_bytes, "portrait image")

    character_segment = _safe_segment(
        str(character_source).lower(),
        "unassigned-character",
    )
    storage_path = f"characters/{character_segment}/portrait"
    content_type = str(
        getattr(uploaded_file, "type", "") or "application/octet-stream"
    )
    get_runtime_database().upload_mission_media(
        storage_path=storage_path,
        media_bytes=file_bytes,
        content_type=content_type,
    )
    get_mission_media_url.clear()
    return REFERENCE_PREFIX + storage_path


def upload_library_asset(uploaded_file, asset_id, current_reference=""):
    """Store or replace one reusable Asset Library object."""
    if uploaded_file is None:
        return ""
    extensions, mime_types = MEDIA_FORMATS["image"]
    file_bytes = validate_upload(
        uploaded_file, extensions, mime_types, MEDIA_LIMITS["image"], "asset image",
    )
    validate_image_content(file_bytes, "asset image")

    asset_segment = _safe_segment(str(asset_id).lower(), "unassigned-asset")
    storage_path = (
        _storage_path(current_reference)
        or f"assets/{asset_segment}/file"
    )
    content_type = str(
        getattr(uploaded_file, "type", "") or "application/octet-stream"
    )
    get_runtime_database().upload_mission_media(
        storage_path=storage_path,
        media_bytes=file_bytes,
        content_type=content_type,
    )
    get_mission_media_url.clear()
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
