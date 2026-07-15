import io
import unittest
from unittest.mock import patch

from PIL import Image

from data.google_drive import get_photo_url, upload_photo


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


if __name__ == "__main__":
    unittest.main()
