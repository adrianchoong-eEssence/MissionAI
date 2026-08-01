import logging
import uuid


LOGGER = logging.getLogger(__name__)


def upload_error_message(action, saved=False, retry=True, error=None):
    """Return a safe user-facing upload failure with a traceable reference."""
    reference = uuid.uuid4().hex[:8].upper()
    if error is not None:
        LOGGER.error("Upload failure %s during %s: %r", reference, action, error)
    saved_text = "The file was saved." if saved else "The file was not saved."
    retry_text = "Please retry." if retry else "Please contact a facilitator."
    return f"{action} failed. {saved_text} {retry_text} Reference: {reference}."


def validate_upload(uploaded_file, allowed_extensions, allowed_mime_types, max_bytes, label):
    """Validate server-side name, MIME, and size before storage is called."""
    if uploaded_file is None:
        raise ValueError(f"Choose a {label.lower()} to upload.")
    name = str(getattr(uploaded_file, "name", "") or "").strip()
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in {value.lower().lstrip(".") for value in allowed_extensions}:
        raise ValueError(f"The selected {label.lower()} format is not supported.")
    content_type = str(getattr(uploaded_file, "type", "") or "").lower()
    if content_type and content_type not in {value.lower() for value in allowed_mime_types}:
        raise ValueError(f"The selected {label.lower()} MIME type is not supported.")
    file_bytes = uploaded_file.getvalue()
    if not file_bytes:
        raise ValueError(f"The selected {label.lower()} is empty.")
    if len(file_bytes) > max_bytes:
        raise ValueError(f"The {label.lower()} exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    return file_bytes
