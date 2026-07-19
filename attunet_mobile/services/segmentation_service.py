import json
import re
import shutil
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from config import (
    INPUT_HEIGHT,
    INPUT_WIDTH,
    MODEL_METADATA_PATH,
    MODELS_DIR,
    ensure_app_files,
    get_model_path,
)


class SegmentationService:
    def __init__(self):
        self.session = None
        self.metadata = self._load_metadata()

    def _load_metadata(self):
        ensure_app_files()
        return json.loads(MODEL_METADATA_PATH.read_text(encoding="utf-8"))

    def _get_session(self):
        if self.session is not None:
            return self.session
        model_path = get_model_path()
        if not model_path.exists():
            raise FileNotFoundError(
                f"Modelo ONNX nao encontrado em: {model_path}"
            )
        self._ensure_external_data_file(model_path)
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        return self.session

    def segment_image(self, image_path: Path, confidence: float):
        image = Image.open(image_path).convert("RGB")
        original = np.array(image)
        input_tensor = self._preprocess_image(image)
        session = self._get_session()
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        raw_output = session.run([output_name], {input_name: input_tensor})[0]
        logits = raw_output[0, 0]
        probs = self._sigmoid(logits)
        mask = (probs >= confidence).astype(np.uint8) * 255
        mask_image = Image.fromarray(mask, mode="L").resize(
            image.size,
            Image.Resampling.NEAREST,
        )
        leaf_mask = np.array(mask_image)
        segmented_rgba = self._apply_transparent_background(original, leaf_mask)

        return {
            "original_rgb": original,
            "leaf_mask": leaf_mask,
            "segmented_rgba": segmented_rgba,
        }

    def _preprocess_image(self, image: Image.Image):
        resized = image.resize((INPUT_WIDTH, INPUT_HEIGHT), Image.Resampling.BILINEAR)
        array = np.asarray(resized).astype(np.float32) / 255.0
        chw = np.transpose(array, (2, 0, 1))
        return np.expand_dims(chw, axis=0).astype(np.float32)

    def _sigmoid(self, x):
        return 1.0 / (1.0 + np.exp(-x))

    def _apply_transparent_background(self, original: np.ndarray, mask: np.ndarray):
        alpha = np.where(mask > 0, 255, 0).astype(np.uint8)
        return np.dstack((original, alpha))

    def _ensure_external_data_file(self, model_path: Path):
        expected_files = self._extract_external_data_names(model_path)
        if not expected_files:
            return

        available_data_files = sorted(MODELS_DIR.glob("*.onnx.data"))
        if not available_data_files:
            return

        source_file = model_path.with_name(f"{model_path.name}.data")
        if not source_file.exists():
            source_file = available_data_files[0]

        for expected_name in expected_files:
            target_file = model_path.with_name(expected_name)
            if target_file.exists():
                continue
            if source_file.resolve() == target_file.resolve():
                continue
            shutil.copyfile(source_file, target_file)

    def _extract_external_data_names(self, model_path: Path):
        content = model_path.read_bytes()
        matches = re.findall(rb"([A-Za-z0-9_.-]+\.onnx\.data)", content)
        names = []
        for match in matches:
            name = match.decode("utf-8", errors="ignore")
            if name not in names:
                names.append(name)
        return names
