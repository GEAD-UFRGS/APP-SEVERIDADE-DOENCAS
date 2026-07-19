import base64
import io
import shutil
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from config import (
    TEMP_IMAGES_DIR,
    TEST_IMAGES_DIR,
    VALID_EXTENSIONS,
    WEB_MAX_IMAGE_SIDE,
    ensure_app_files,
)


def list_image_paths(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS
        ]
    )


def list_test_images() -> list[Path]:
    return list_image_paths(TEST_IMAGES_DIR)


def image_file_to_bytes(image_path: Path) -> bytes:
    image = Image.open(image_path).convert("RGB")
    return pil_image_to_bytes(image)


def pil_image_to_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def pil_image_to_base64(image: Image.Image) -> str:
    return base64.b64encode(pil_image_to_bytes(image)).decode("ascii")


def zoom_rgba_to_mask(image_rgba: np.ndarray, mask: np.ndarray, margin_ratio: float = 0.06):
    points = np.argwhere(mask > 0)
    if points.size == 0:
        return image_rgba

    top, left = points.min(axis=0)
    bottom, right = points.max(axis=0)

    height = max(bottom - top + 1, 1)
    width = max(right - left + 1, 1)
    margin = int(max(height, width) * margin_ratio)

    top = max(int(top) - margin, 0)
    left = max(int(left) - margin, 0)
    bottom = min(int(bottom) + margin + 1, mask.shape[0])
    right = min(int(right) + margin + 1, mask.shape[1])

    cropped = image_rgba[top:bottom, left:right]
    crop_height, crop_width = cropped.shape[:2]
    square_side = max(crop_width, crop_height)

    canvas = np.zeros((square_side, square_side, 4), dtype=np.uint8)
    offset_x = (square_side - crop_width) // 2
    offset_y = (square_side - crop_height) // 2
    canvas[offset_y : offset_y + crop_height, offset_x : offset_x + crop_width] = cropped
    return canvas


def prepare_selected_images(files, optimize_for_web: bool = False) -> list[Path]:
    ensure_app_files()
    selected_paths: list[Path] = []

    for index, file in enumerate(files):
        file_path = getattr(file, "path", None)
        if file_path:
            selected_paths.append(Path(file_path))
            continue

        file_bytes = getattr(file, "bytes", None)
        file_name = getattr(file, "name", f"imagem_{index}.png")
        if not file_bytes:
            continue

        target_path = save_temp_image_bytes(
            file_bytes=file_bytes,
            file_name=file_name,
            index=index,
            optimize=optimize_for_web,
        )
        selected_paths.append(target_path)

    return selected_paths


def save_temp_image_bytes(
    file_bytes: bytes,
    file_name: str = "imagem.png",
    index: int = 0,
    optimize: bool = False,
) -> Path:
    ensure_app_files()
    safe_name = Path(file_name).name
    suffix = Path(safe_name).suffix.lower() or ".png"
    if optimize:
        suffix = ".jpg"
    target_name = f"{index:03d}_{uuid.uuid4().hex[:8]}{suffix}"
    target_path = TEMP_IMAGES_DIR / target_name
    if optimize:
        _save_optimized_temp_image(file_bytes, target_path)
    else:
        target_path.write_bytes(file_bytes)
    return target_path


def build_temp_image_path(file_name: str, index: int) -> tuple[str, Path]:
    ensure_app_files()
    safe_name = Path(file_name).name
    suffix = Path(safe_name).suffix.lower() or ".png"
    target_name = f"{index:03d}_{uuid.uuid4().hex[:8]}{suffix}"
    relative_path = f"temp_images/{target_name}"
    return relative_path, TEMP_IMAGES_DIR / target_name


def clear_temp_images():
    if not TEMP_IMAGES_DIR.exists():
        return
    for item in TEMP_IMAGES_DIR.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)


def _save_optimized_temp_image(file_bytes: bytes, target_path: Path):
    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    image.thumbnail((WEB_MAX_IMAGE_SIDE, WEB_MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    image.save(target_path, format="JPEG", quality=88, optimize=True)
