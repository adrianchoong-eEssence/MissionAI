import io

from PIL import Image

from screens.mission_setup import crop_reference_image


def _png(width=200, height=100):
    image = Image.new("RGB", (width, height), "#cc3300")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_crop_reference_image_uses_requested_box():
    cropped = crop_reference_image(_png(), (50, 10, 150, 90))
    result = Image.open(io.BytesIO(cropped))

    assert result.size == (100, 80)
    assert result.format == "PNG"


def test_crop_reference_image_clamps_box_to_source_bounds():
    cropped = crop_reference_image(_png(40, 30), (-20, -10, 100, 100))
    result = Image.open(io.BytesIO(cropped))

    assert result.size == (40, 30)
