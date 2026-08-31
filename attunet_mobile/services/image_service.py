import base64
import io
import subprocess
import shutil
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog
from urllib.parse import unquote, urlparse

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


def list_test_images_from_folder(folder: Path) -> tuple[list[Path], str | None]:
    if not folder.exists() or not folder.is_dir():
        return [], "A pasta selecionada nao existe."
    subfolders = [item for item in folder.iterdir() if item.is_dir()]
    if subfolders:
        return [], "A pasta selecionada possui subpastas. Escolha uma pasta apenas com imagens."
    images = list_image_paths(folder)
    if not images:
        return [], "Nenhuma imagem valida foi encontrada na pasta selecionada."
    return images, None


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


def prepare_selected_images(
    files,
    optimize_for_web: bool = False,
    copy_local_files: bool = True,
) -> list[Path]:
    ensure_app_files()
    selected_paths: list[Path] = []

    for index, file in enumerate(files):
        if isinstance(file, Path):
            if file.exists():
                if copy_local_files:
                    target_path = save_temp_image_file(
                        source_path=file,
                        file_name=file.name,
                        index=index,
                        optimize=optimize_for_web,
                    )
                    selected_paths.append(target_path)
                else:
                    selected_paths.append(file)
            continue

        file_path = _normalize_selected_file_path(getattr(file, "path", None))
        if file_path and file_path.exists():
            if copy_local_files:
                target_path = save_temp_image_file(
                    source_path=file_path,
                    file_name=getattr(file, "name", file_path.name),
                    index=index,
                    optimize=optimize_for_web,
                )
                selected_paths.append(target_path)
            else:
                selected_paths.append(file_path)
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


def pick_linux_image_paths(max_files: int | None = None) -> list[Path]:
    ensure_app_files()
    command = [
        "zenity",
        "--file-selection",
        "--multiple",
        "--separator=|",
        "--title=Selecionar imagens da parcela",
        "--file-filter=Imagens | *.jpg *.jpeg *.png *.bmp *.webp",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    raw_output = result.stdout.strip()
    if not raw_output:
        return []

    selected_paths: list[Path] = []
    for raw_path in raw_output.split("|"):
        path = Path(raw_path)
        if path.exists() and path.suffix.lower() in VALID_EXTENSIONS:
            selected_paths.append(path)

    if max_files is not None:
        return selected_paths[:max_files]
    return selected_paths


def pick_linux_directory_path() -> Path | None:
    ensure_app_files()
    command = [
        "zenity",
        "--file-selection",
        "--directory",
        "--title=Selecionar pasta com imagens de teste",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    raw_output = result.stdout.strip()
    if not raw_output:
        return None
    return Path(raw_output)


def pick_desktop_image_paths() -> list[Path]:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilenames(
            title="Selecionar imagens da parcela",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp")],
        )
    finally:
        root.destroy()
    return [Path(path) for path in selected if Path(path).exists()]


def pick_desktop_directory_path() -> Path | None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="Selecionar pasta com imagens de teste")
    finally:
        root.destroy()
    if not selected:
        return None
    return Path(selected)


def save_temp_image_file(
    source_path: Path,
    file_name: str | None = None,
    index: int = 0,
    optimize: bool = False,
) -> Path:
    ensure_app_files()
    safe_name = Path(file_name or source_path.name).name
    suffix = Path(safe_name).suffix.lower() or source_path.suffix.lower() or ".png"
    if optimize:
        suffix = ".jpg"
    target_name = f"{index:03d}_{uuid.uuid4().hex[:8]}{suffix}"
    target_path = TEMP_IMAGES_DIR / target_name
    if optimize:
        _save_optimized_temp_image(source_path.read_bytes(), target_path)
    else:
        shutil.copy2(source_path, target_path)
    return target_path


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


def _normalize_selected_file_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    if raw_path.startswith("file://"):
        parsed = urlparse(raw_path)
        return Path(unquote(parsed.path))
    return Path(raw_path)
