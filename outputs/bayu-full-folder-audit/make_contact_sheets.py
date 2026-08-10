from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

source = Path("outputs/bayu-full-folder-audit/thumbnails")
destination = Path("outputs/bayu-full-folder-audit/contact-sheets")
destination.mkdir(parents=True, exist_ok=True)

files = sorted(source.glob("*.jpg"))
font = ImageFont.load_default(size=20)
columns = 4
rows = 4
cell_width = 360
cell_height = 320
label_height = 32

for sheet_index, start in enumerate(range(0, len(files), columns * rows), start=1):
    page = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(page)
    for offset, path in enumerate(files[start:start + columns * rows]):
        row, column = divmod(offset, columns)
        with Image.open(path) as image:
            image.thumbnail((cell_width - 12, cell_height - label_height - 12))
            x = column * cell_width + (cell_width - image.width) // 2
            y = row * cell_height + label_height + (cell_height - label_height - image.height) // 2
            page.paste(image, (x, y))
        draw.text((column * cell_width + 8, row * cell_height + 6), path.stem, fill="black", font=font)
    page.save(destination / f"bayu-contact-{sheet_index:02d}.jpg", quality=90)
