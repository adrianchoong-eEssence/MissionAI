import io
import unittest
from unittest.mock import patch

from PIL import Image

from data.google_drive import get_photo_url, upload_evidence_file, upload_photo
from data.upload_safety import upload_error_message


class FakeRuntime:
    can_publish = True

    def __init__(self):
        self.uploads = []

    def upload_submission_image(
        self,
        storage_path,
        image_bytes,
        content_type="image/jpeg",
    ):
        self.uploads.append({
            "Path": storage_path,
            "Bytes": image_bytes,
            "ContentType": content_type,
        })


class SubmissionStorageTests(unittest.TestCase):
    def make_image(self):
        uploaded = io.BytesIO()
        Image.new("RGB", (32, 24), color="blue").save(
            uploaded,
            format="PNG",
        )
        uploaded.seek(0)
        uploaded.name = "evidence.png"
        return uploaded

    def test_photo_upload_returns_stable_private_storage_reference(self):
        runtime = FakeRuntime()
        with patch(
            "data.google_drive.get_runtime_database",
            return_value=runtime,
        ):
            result = upload_photo(
                "EVT-TEST",
                "M01",
                "Team Alpha",
                "Participant One",
                self.make_image(),
            )

        self.assertTrue(result["url"].startswith(
            "supabase://exos-submissions/EVT-TEST/M01/Team-Alpha/"
        ))
        self.assertEqual(result["file_id"], runtime.uploads[0]["Path"])
        self.assertEqual(runtime.uploads[0]["ContentType"], "image/jpeg")
        self.assertGreater(len(runtime.uploads[0]["Bytes"]), 0)

    def test_photo_url_preserves_existing_and_loads_private_storage_bytes(self):
        self.assertEqual(
            get_photo_url("https://example.com/photo.jpg"),
            "https://example.com/photo.jpg",
        )
        with patch(
            "data.google_drive._private_photo_bytes",
            return_value=b"private-image-bytes",
        ):
            result = get_photo_url(
                "supabase://exos-submissions/EVT/M01/photo.jpg"
            )
        self.assertEqual(result, b"private-image-bytes")

    def test_video_and_audio_formats_are_validated_server_side(self):
        runtime = FakeRuntime()
        with patch("data.google_drive.get_runtime_database", return_value=runtime):
            for filename, mime, kind in (
                ("LOADTEST-video.mp4", "video/mp4", "VIDEO"),
                ("LOADTEST-video.mov", "video/quicktime", "VIDEO"),
                ("LOADTEST-audio.m4a", "audio/mp4", "AUDIO"),
                ("LOADTEST-audio.mp3", "audio/mpeg", "AUDIO"),
            ):
                uploaded = io.BytesIO(b"small-test-media")
                uploaded.name, uploaded.type = filename, mime
                upload_evidence_file(
                    "EVT-0004", "M01", "LOADTEST", "LOADTEST",
                    uploaded, kind,
                )
        self.assertEqual(len(runtime.uploads), 4)

    def test_invalid_video_is_rejected_before_storage(self):
        runtime = FakeRuntime()
        uploaded = io.BytesIO(b"not-video")
        uploaded.name, uploaded.type = "LOADTEST-video.exe", "application/octet-stream"
        with patch("data.google_drive.get_runtime_database", return_value=runtime):
            with self.assertRaisesRegex(ValueError, "format is not supported"):
                upload_evidence_file(
                    "EVT-0004", "M01", "LOADTEST", "LOADTEST",
                    uploaded, "VIDEO",
                )
        self.assertEqual(runtime.uploads, [])

    def test_public_failure_message_has_reference_and_no_backend_detail(self):
        message = upload_error_message(
            "Photo upload", error=RuntimeError("/tmp/private secret-token"),
        )
        self.assertIn("Photo upload failed", message)
        self.assertIn("The file was not saved", message)
        self.assertIn("Please retry", message)
        self.assertRegex(message, r"Reference: [A-F0-9]{8}")
        self.assertNotIn("/tmp", message)
        self.assertNotIn("secret-token", message)


if __name__ == "__main__":
    unittest.main()
