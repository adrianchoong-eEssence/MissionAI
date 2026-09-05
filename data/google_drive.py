import io
import os
import re
import uuid
from datetime import datetime

import streamlit as st
from PIL import Image, ImageOps

from data.runtime_database import RuntimeDatabaseError, get_runtime_database
from data.upload_safety import validate_upload


SUBMISSION_BUCKET = "exos-submissions"
STORAGE_REFERENCE_PREFIX = f"supabase://{SUBMISSION_BUCKET}/"
DEFAULT_VIDEO_EVIDENCE_MAX_BYTES = 50 * 1024 * 1024


def video_evidence_max_bytes() -> int:
    """Return the bounded per-file video limit for the Theme Park UAT.

    An operator may lower the limit with ``EXOS_THEME_PARK_VIDEO_MAX_BYTES``
    for a constrained event connection.  It can never be raised above the
    conservative 50 MB UAT ceiling without a deliberate source change.
    """
    value = os.getenv("EXOS_THEME_PARK_VIDEO_MAX_BYTES", "")
    try:
        configured = int(value) if value else DEFAULT_VIDEO_EVIDENCE_MAX_BYTES
    except ValueError:
        configured = DEFAULT_VIDEO_EVIDENCE_MAX_BYTES
    return max(1 * 1024 * 1024, min(configured, DEFAULT_VIDEO_EVIDENCE_MAX_BYTES))


def _safe_path_part(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return cleaned.strip("-._")[:80] or fallback


def _prepare_image(uploaded_file):
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        image.thumbnail((1600, 1600))
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception as error:
        raise ValueError(f"The selected image could not be processed: {error}")

    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=78,
        optimize=True,
    )
    return buffer.getvalue()


def upload_photo(
    event_id,
    mission_id,
    team_name,
    participant_name,
    uploaded_file,
):
    runtime = get_runtime_database()
    if not runtime.can_publish:
        raise RuntimeDatabaseError(
            "Photo storage is not configured for this app. Add "
            "SUPABASE_SECRET_KEY to its Streamlit secrets."
        )

    raw_bytes = validate_upload(
        uploaded_file,
        {"jpg", "jpeg", "png"},
        {"image/jpeg", "image/png"},
        10 * 1024 * 1024,
        "photo evidence",
    )
    prepared_file = io.BytesIO(raw_bytes)
    prepared_file.name = str(getattr(uploaded_file, "name", "photo"))
    image_bytes = _prepare_image(prepared_file)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}-{uuid.uuid4().hex}.jpg"
    storage_path = "/".join([
        _safe_path_part(event_id, "event"),
        _safe_path_part(mission_id, "mission"),
        _safe_path_part(team_name, "team"),
        _safe_path_part(participant_name, "participant"),
        filename,
    ])

    runtime.upload_submission_image(
        storage_path,
        image_bytes,
        content_type="image/jpeg",
    )

    return {
        "file_id": storage_path,
        "url": f"{STORAGE_REFERENCE_PREFIX}{storage_path}",
        "filename": filename,
        "content_type": "image/jpeg",
    }


def upload_evidence_file(
    event_id,
    mission_id,
    team_name,
    participant_name,
    uploaded_file,
    evidence_type,
    maximum_bytes=None,
):
    """Store participant video/audio evidence in the existing private bucket."""
    runtime = get_runtime_database()
    if not runtime.can_publish:
        raise RuntimeDatabaseError(
            "Evidence storage is not configured for this app. Add "
            "SUPABASE_SECRET_KEY to its Streamlit secrets."
        )

    kind = str(evidence_type or "file").strip().lower()
    maximum = (
        video_evidence_max_bytes() if kind == "video" else 25 * 1024 * 1024
    )
    if maximum_bytes is not None:
        try:
            maximum = min(maximum, max(int(maximum_bytes), 1))
        except (TypeError, ValueError):
            pass
    formats = {
        "video": (
            {"mp4", "mov", "m4v", "webm"},
            {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"},
        ),
        "audio": (
            {"mp3", "m4a", "wav", "aac", "ogg"},
            {"audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/wav", "audio/x-wav", "audio/aac", "audio/ogg"},
        ),
    }
    if kind not in formats:
        raise ValueError("The selected evidence type is not supported.")
    file_bytes = validate_upload(
        uploaded_file, *formats[kind], maximum, f"{kind} evidence",
    )

    original_name = _safe_path_part(getattr(uploaded_file, "name", ""), kind)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}-{uuid.uuid4().hex}-{original_name}"
    storage_path = "/".join([
        _safe_path_part(event_id, "event"),
        _safe_path_part(mission_id, "mission"),
        _safe_path_part(team_name, "team"),
        _safe_path_part(participant_name, "participant"),
        filename,
    ])
    content_type = str(
        getattr(uploaded_file, "type", "") or "application/octet-stream"
    )
    runtime.upload_submission_image(storage_path, file_bytes, content_type=content_type)
    return {
        "file_id": storage_path,
        "url": f"{STORAGE_REFERENCE_PREFIX}{storage_path}",
        "filename": filename,
        "content_type": content_type,
    }


def delete_evidence_file(storage_path):
    """Compensate a failed metadata write without touching existing evidence."""
    path = str(storage_path or "").strip().lstrip("/")
    if path:
        get_runtime_database().delete_submission_images([path])


@st.cache_data(ttl=300, show_spinner=False)
def _private_submission_bytes(storage_path):
    return get_runtime_database().download_submission_image(storage_path)


# Compatibility seam for existing photo callers/tests.  New callers should
# use ``get_private_evidence_bytes`` because a private submission object can
# be an image or a video.
def _private_photo_bytes(storage_path):
    return _private_submission_bytes(storage_path)


def get_private_evidence_bytes(image_url="", file_id=""):
    """Read a private submission object server-side without creating a URL."""
    reference = str(image_url or "").strip()
    storage_path = ""
    if reference.startswith(STORAGE_REFERENCE_PREFIX):
        storage_path = reference[len(STORAGE_REFERENCE_PREFIX):]
    elif file_id and not str(file_id).startswith("TEMP-"):
        storage_path = str(file_id).strip().lstrip("/")
    if not storage_path:
        return b""
    try:
        return _private_submission_bytes(storage_path)
    except RuntimeDatabaseError:
        return b""


def get_photo_url(image_url="", file_id=""):
    reference = str(image_url or "").strip()
    if reference.startswith(("https://", "http://", "data:image")):
        return reference

    storage_path = ""
    if reference.startswith(STORAGE_REFERENCE_PREFIX):
        storage_path = reference[len(STORAGE_REFERENCE_PREFIX):]
    elif file_id and not str(file_id).startswith("TEMP-"):
        storage_path = str(file_id).strip().lstrip("/")
    if not storage_path:
        return ""
    try:
        return _private_photo_bytes(storage_path)
    except RuntimeDatabaseError:
        return ""
