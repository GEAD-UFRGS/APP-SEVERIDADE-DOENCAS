import json
from pathlib import Path

APP_TITLE = "ATTUNet Mobile"
WEB_UPLOAD_SECRET = "attunet-mobile-local-upload-key"
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
ASSETS_DIR = APP_DIR / "assets"
MODELS_DIR = ASSETS_DIR / "models"
MODEL_METADATA_PATH = MODELS_DIR / "model_metadata.json"
STATE_DIR = APP_DIR / "state"
SETTINGS_PATH = STATE_DIR / "settings.json"
PARCELS_PATH = STATE_DIR / "saved_parcels.json"
TEMP_IMAGES_DIR = STATE_DIR / "temp_images"
UPLOAD_DIR = STATE_DIR
TEST_IMAGES_DIR = PROJECT_ROOT / "imagens_teste"
INPUT_WIDTH = 512
INPUT_HEIGHT = 512
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_SETTINGS = {
    "confidence": 0.6,
    "sensitivity": 0.5,
}
WEB_IMAGE_BATCH_LIMIT = 4
WEB_IMAGE_COMPRESSION_QUALITY = 40
WEB_MAX_IMAGE_SIDE = 1600
CULTURE_OPTIONS = ["Trigo"]


def ensure_app_files():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(
            json.dumps(DEFAULT_SETTINGS, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    if not MODEL_METADATA_PATH.exists():
        MODEL_METADATA_PATH.write_text(
            json.dumps(
                {
                    "model_file": "attunet.onnx",
                    "input_name": "input",
                    "output_name": "output",
                    "input_width": INPUT_WIDTH,
                    "input_height": INPUT_HEIGHT,
                    "threshold": 0.6,
                    "apply_sigmoid": True,
                },
                indent=2,
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )


def load_model_metadata():
    ensure_app_files()
    return json.loads(MODEL_METADATA_PATH.read_text(encoding="utf-8"))


def get_model_path():
    metadata = load_model_metadata()
    model_file = metadata.get("model_file", "attunet.onnx")
    return MODELS_DIR / model_file
