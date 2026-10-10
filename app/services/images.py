from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from app.config import COMPONENT_IMAGES_DIR, IMAGE_MAX_SIZE, IMAGE_QUALITY, THUMBNAIL_IMAGES_DIR, THUMBNAIL_MAX_SIZE


def ensure_dirs():
    COMPONENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    (COMPONENT_IMAGES_DIR.parent / 'locations').mkdir(parents=True, exist_ok=True)
    (THUMBNAIL_IMAGES_DIR / 'locations').mkdir(parents=True, exist_ok=True)
    (COMPONENT_IMAGES_DIR.parent / 'branding').mkdir(parents=True, exist_ok=True)
    (THUMBNAIL_IMAGES_DIR / 'branding').mkdir(parents=True, exist_ok=True)


def _save_webp(image: Image.Image, destination: Path, max_size: tuple[int, int]):
    processed = ImageOps.exif_transpose(image)
    if processed.mode not in ('RGB', 'RGBA'):
        processed = processed.convert('RGB')
    if processed.mode == 'RGBA':
        background = Image.new('RGB', processed.size, (255, 255, 255))
        background.paste(processed, mask=processed.split()[-1])
        processed = background
    processed.thumbnail(max_size)
    processed.save(destination, format='WEBP', quality=IMAGE_QUALITY, method=6)


def save_uploaded_image(upload_file, image_dir: str = 'components', thumb_dir: str = 'thumbnails'):
    ensure_dirs()
    suffix = '.webp'
    filename = f'{uuid4().hex}{suffix}'
    thumb_filename = f'{uuid4().hex}{suffix}'
    image_root = COMPONENT_IMAGES_DIR.parent / image_dir
    thumb_root = THUMBNAIL_IMAGES_DIR.parent / thumb_dir
    image_root.mkdir(parents=True, exist_ok=True)
    thumb_root.mkdir(parents=True, exist_ok=True)
    image_path = image_root / filename
    thumb_path = thumb_root / thumb_filename

    raw = upload_file.file.read()
    image = Image.open(BytesIO(raw))
    _save_webp(image, image_path, IMAGE_MAX_SIZE)
    image = Image.open(BytesIO(raw))
    _save_webp(image, thumb_path, THUMBNAIL_MAX_SIZE)
    return f'images/{image_dir}/{filename}', f'images/{thumb_dir}/{thumb_filename}'


def save_component_image(upload_file):
    return save_uploaded_image(upload_file, image_dir='components', thumb_dir='thumbnails')


def save_location_image(upload_file):
    return save_uploaded_image(upload_file, image_dir='locations', thumb_dir='thumbnails/locations')


def save_brand_logo(upload_file):
    image_path, _ = save_uploaded_image(upload_file, image_dir='branding', thumb_dir='thumbnails/branding')
    return image_path


def delete_relative_file(data_dir: Path, relative_path: str | None):
    if not relative_path:
        return
    path = data_dir / relative_path
    if path.exists() and path.is_file():
        path.unlink(missing_ok=True)
