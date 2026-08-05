import json
import uuid
from dataclasses import asdict, dataclass, field

from config import DEFAULT_SETTINGS, PARCELS_PATH, SETTINGS_PATH, ensure_app_files


@dataclass
class ParcelImage:
    id: str
    path: str | None = None
    healthy_pct: float = 0.0
    severity_pct: float = 0.0
    view_sources: dict[str, str] = field(default_factory=dict)
    processed: bool = False
    view_mode: str = "mapa"

    @property
    def has_visualization(self):
        return bool(self.view_sources)


@dataclass
class Parcel:
    id: str
    name: str
    target_images: int
    date: str
    culture: str
    description: str = ""
    images: list[ParcelImage] = field(default_factory=list)
    current_index: int = 0
    saved: bool = False

    def current_image(self):
        if not self.images:
            return None
        if self.current_index < 0:
            self.current_index = 0
        if self.current_index >= len(self.images):
            self.current_index = len(self.images) - 1
        return self.images[self.current_index]

    def next_image(self):
        if self.images and self.current_index < len(self.images) - 1:
            self.current_index += 1

    def previous_image(self):
        if self.images and self.current_index > 0:
            self.current_index -= 1

    def is_ready_to_process(self):
        return (
            len(self.images) == self.target_images
            and self.target_images > 0
            and all(image.path for image in self.images)
        )

    def average_healthy_pct(self):
        processed = [image.healthy_pct for image in self.images if image.processed]
        return round(sum(processed) / len(processed), 2) if processed else 0.0

    def average_severity_pct(self):
        processed = [image.severity_pct for image in self.images if image.processed]
        return round(sum(processed) / len(processed), 2) if processed else 0.0

    def to_saved_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "target_images": self.target_images,
            "date": self.date,
            "culture": self.culture,
            "description": self.description,
            "saved": True,
            "images": [
                {
                    "id": image.id,
                    "healthy_pct": image.healthy_pct,
                    "severity_pct": image.severity_pct,
                    "processed": image.processed,
                    "view_mode": image.view_mode,
                }
                for image in self.images
            ],
        }

    @classmethod
    def from_saved_dict(cls, data: dict):
        images = [
            ParcelImage(
                id=image.get("id", uuid.uuid4().hex),
                healthy_pct=float(image.get("healthy_pct", 0.0)),
                severity_pct=float(image.get("severity_pct", 0.0)),
                processed=bool(image.get("processed", False)),
                view_mode=image.get("view_mode", "mapa"),
            )
            for image in data.get("images", [])
        ]
        return cls(
            id=data.get("id", uuid.uuid4().hex),
            name=data.get("name", ""),
            target_images=int(data.get("target_images", 0)),
            date=data.get("date", ""),
            culture=data.get("culture", "Trigo"),
            description=data.get("description", ""),
            images=images,
            saved=bool(data.get("saved", True)),
        )


@dataclass
class AppSettings:
    confidence: float = 0.6
    sensitivity: float = 0.5
    use_hybrid_threshold: bool = False


@dataclass
class AppState:
    settings: AppSettings = field(default_factory=AppSettings)
    parcels: list[Parcel] = field(default_factory=list)
    active_parcel_id: str | None = None

    @classmethod
    def load(cls):
        ensure_app_files()
        settings_data = DEFAULT_SETTINGS.copy()
        if SETTINGS_PATH.exists():
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings_data.update(loaded)

        parcels: list[Parcel] = []
        if PARCELS_PATH.exists():
            loaded_parcels = json.loads(PARCELS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded_parcels, list):
                parcels = [Parcel.from_saved_dict(item) for item in loaded_parcels if isinstance(item, dict)]

        settings = AppSettings(
            confidence=float(settings_data.get("confidence", 0.6)),
            sensitivity=float(settings_data.get("sensitivity", 0.5)),
            use_hybrid_threshold=bool(settings_data.get("use_hybrid_threshold", False)),
        )
        return cls(settings=settings, parcels=parcels)

    def save_settings(self):
        ensure_app_files()
        SETTINGS_PATH.write_text(
            json.dumps(
                {
                    "confidence": round(float(self.settings.confidence), 4),
                    "sensitivity": round(float(self.settings.sensitivity), 4),
                    "use_hybrid_threshold": bool(self.settings.use_hybrid_threshold),
                },
                indent=2,
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )

    def persist_saved_parcels(self):
        ensure_app_files()
        saved_data = [parcel.to_saved_dict() for parcel in self.parcels if parcel.saved]
        PARCELS_PATH.write_text(
            json.dumps(saved_data, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    def add_parcel(self, name: str, target_images: int, date: str, culture: str, description: str = ""):
        parcel = Parcel(
            id=uuid.uuid4().hex,
            name=name,
            target_images=target_images,
            date=date,
            culture=culture,
            description=description,
        )
        self.parcels.append(parcel)
        return parcel

    def get_active_parcel(self):
        if self.active_parcel_id is None:
            return None
        for parcel in self.parcels:
            if parcel.id == self.active_parcel_id:
                return parcel
        return None

    def open_parcel(self, parcel_id: str):
        self.active_parcel_id = parcel_id

    def close_parcel(self):
        self.active_parcel_id = None

    def delete_parcel(self, parcel_id: str):
        self.parcels = [parcel for parcel in self.parcels if parcel.id != parcel_id]
        if self.active_parcel_id == parcel_id:
            self.active_parcel_id = None
        self.persist_saved_parcels()

    def save_parcel(self, parcel_id: str):
        parcel = next((item for item in self.parcels if item.id == parcel_id), None)
        if parcel is None:
            return
        parcel.saved = True
        self.persist_saved_parcels()
