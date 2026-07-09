import base64
import io
import uuid
from PIL import Image


def upload_photo(event_id, mission_id, team_name, participant_name, uploaded_file):
    image = Image.open(uploaded_file)

    image.thumbnail((600, 600))

    buffer = io.BytesIO()
    image.convert("RGB").save(
        buffer,
        format="JPEG",
        quality=55,
        optimize=True,
    )

    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    data_url = f"data:image/jpeg;base64,{encoded}"

    return {
        "file_id": f"TEMP-{uuid.uuid4()}",
        "url": data_url,
        "filename": uploaded_file.name,
    }