"""Обробка фото: перевірка, поворот за EXIF, зменшення і стиснення у WebP."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024    # 10 МБ на один файл до стиснення
MAX_SIDE = 1600                         # найбільша сторона після зменшення, px
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = 40_000_000     # захист від «бомб» з гігантською роздільністю


class ImageError(ValueError):
    pass


def process_image(file_storage):
    """Приймає файл з форми, повертає (bytes, width, height) у форматі WebP."""
    raw = file_storage.read(MAX_UPLOAD_BYTES + 1)
    name = file_storage.filename or "файл"
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError(f"«{name}» більший за 10 МБ")
    try:
        img = Image.open(io.BytesIO(raw))
        fmt = img.format
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError(f"«{name}» не схожий на фото. Підходять JPG, PNG або WebP")
    if fmt not in ALLOWED_FORMATS:
        raise ImageError(f"«{name}»: формат {fmt} не підтримується. Підходять JPG, PNG або WebP")

    img = ImageOps.exif_transpose(img)      # фото з телефону не будуть лежати на боці
    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, "WEBP", quality=82, method=6)
    return out.getvalue(), img.width, img.height
