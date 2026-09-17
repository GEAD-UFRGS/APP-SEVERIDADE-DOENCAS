import json
import uuid
from dataclasses import dataclass, field

from config import DEFAULT_SETTINGS, EXPERIMENTS_PATH, PARCELS_PATH, SETTINGS_PATH, ensure_app_files


def _new_id():
    return uuid.uuid4().hex


def _read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path, data):
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(path)


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
class Reading:
    id: str
    date: str
    target_images: int
    description: str = ""
    images: list[ParcelImage] = field(default_factory=list)
    result_images: list[dict] = field(default_factory=list)
    current_index: int = 0
    processed: bool = False
    validation_mode: bool = False

    @property
    def name(self):
        return "Teste unitário" if self.validation_mode else f"Leitura de {self.date}"

    @property
    def culture(self):
        return "Validação"

    def current_image(self):
        if not self.images:
            return None
        self.current_index = min(max(self.current_index, 0), len(self.images) - 1)
        return self.images[self.current_index]

    def next_image(self):
        if self.current_index < len(self.images) - 1:
            self.current_index += 1

    def previous_image(self):
        if self.current_index > 0:
            self.current_index -= 1

    def is_ready_to_process(self):
        if self.validation_mode:
            return bool(self.images) and all(image.path for image in self.images)
        return (
            not self.processed
            and self.target_images > 0
            and len(self.images) == self.target_images
            and all(image.path for image in self.images)
        )

    def remaining_images(self):
        if self.validation_mode:
            return None
        return max(self.target_images - len(self.images), 0)

    def all_results(self):
        current = [
            {"healthy_pct": image.healthy_pct, "severity_pct": image.severity_pct}
            for image in self.images
            if image.processed
        ]
        return current or self.result_images

    def average_healthy_pct(self):
        results = self.all_results()
        return round(sum(item["healthy_pct"] for item in results) / len(results), 2) if results else 0.0

    def average_severity_pct(self):
        results = self.all_results()
        return round(sum(item["severity_pct"] for item in results) / len(results), 2) if results else 0.0

    def finish_processing(self):
        self.result_images = [
            {
                "healthy_pct": round(float(image.healthy_pct), 4),
                "severity_pct": round(float(image.severity_pct), 4),
            }
            for image in self.images
            if image.processed
        ]
        self.processed = len(self.result_images) == len(self.images) and bool(self.images)

    def invalidate_results(self):
        self.result_images = []
        self.processed = False
        for image in self.images:
            image.processed = False
            image.healthy_pct = 0.0
            image.severity_pct = 0.0
            image.view_sources = {}

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date,
            "target_images": self.target_images,
            "description": self.description,
            "processed": self.processed,
            "result_images": self.result_images,
        }

    @classmethod
    def from_dict(cls, data):
        results = data.get("result_images", [])
        return cls(
            id=data.get("id", _new_id()),
            date=data.get("date", ""),
            target_images=max(int(data.get("target_images", 0)), 0),
            description=data.get("description", ""),
            result_images=[
                {
                    "healthy_pct": float(item.get("healthy_pct", 0.0)),
                    "severity_pct": float(item.get("severity_pct", 0.0)),
                }
                for item in results
                if isinstance(item, dict)
            ],
            processed=bool(data.get("processed", False) and results),
        )


@dataclass
class Parcel:
    id: str
    name: str
    description: str = ""
    readings: list[Reading] = field(default_factory=list)

    def processed_results(self):
        return [result for reading in self.readings if reading.processed for result in reading.all_results()]

    def average_healthy_pct(self):
        results = self.processed_results()
        return round(sum(item["healthy_pct"] for item in results) / len(results), 2) if results else 0.0

    def average_severity_pct(self):
        results = self.processed_results()
        return round(sum(item["severity_pct"] for item in results) / len(results), 2) if results else 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "readings": [reading.to_dict() for reading in self.readings],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id", _new_id()),
            name=data.get("name", "Parcela"),
            description=data.get("description", ""),
            readings=[Reading.from_dict(item) for item in data.get("readings", []) if isinstance(item, dict)],
        )


@dataclass
class Block:
    id: str
    name: str
    description: str = ""
    parcels: list[Parcel] = field(default_factory=list)

    def processed_results(self):
        return [result for parcel in self.parcels for result in parcel.processed_results()]

    def average_healthy_pct(self):
        results = self.processed_results()
        return round(sum(item["healthy_pct"] for item in results) / len(results), 2) if results else 0.0

    def average_severity_pct(self):
        results = self.processed_results()
        return round(sum(item["severity_pct"] for item in results) / len(results), 2) if results else 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parcels": [parcel.to_dict() for parcel in self.parcels],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id", _new_id()),
            name=data.get("name", "Bloco"),
            description=data.get("description", ""),
            parcels=[Parcel.from_dict(item) for item in data.get("parcels", []) if isinstance(item, dict)],
        )


@dataclass
class Experiment:
    id: str
    name: str
    start_date: str
    culture: str
    description: str = ""
    blocks: list[Block] = field(default_factory=list)

    def counts(self):
        parcels = sum(len(block.parcels) for block in self.blocks)
        readings = sum(len(parcel.readings) for block in self.blocks for parcel in block.parcels)
        return len(self.blocks), parcels, readings

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date,
            "culture": self.culture,
            "description": self.description,
            "blocks": [block.to_dict() for block in self.blocks],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id", _new_id()),
            name=data.get("name", "Experimento"),
            start_date=data.get("start_date", ""),
            culture=data.get("culture", "Trigo"),
            description=data.get("description", ""),
            blocks=[Block.from_dict(item) for item in data.get("blocks", []) if isinstance(item, dict)],
        )


@dataclass
class AppSettings:
    confidence: float = 0.6
    sensitivity: float = 0.5
    use_hybrid_threshold: bool = False


@dataclass
class AppState:
    settings: AppSettings = field(default_factory=AppSettings)
    experiments: list[Experiment] = field(default_factory=list)
    active_level: str = "home"
    active_experiment_id: str | None = None
    active_block_id: str | None = None
    active_plot_id: str | None = None
    active_reading_id: str | None = None
    unit_test: Reading | None = None

    @classmethod
    def load(cls):
        ensure_app_files()
        settings_data = DEFAULT_SETTINGS.copy()
        loaded_settings = _read_json(SETTINGS_PATH, {})
        if isinstance(loaded_settings, dict):
            settings_data.update(loaded_settings)
        experiments = []
        if EXPERIMENTS_PATH.exists():
            loaded = _read_json(EXPERIMENTS_PATH, [])
            if isinstance(loaded, list):
                experiments = [Experiment.from_dict(item) for item in loaded if isinstance(item, dict)]
        elif PARCELS_PATH.exists():
            experiments = cls._migrate_legacy_parcels()
        state = cls(
            settings=AppSettings(
                confidence=float(settings_data.get("confidence", 0.6)),
                sensitivity=float(settings_data.get("sensitivity", 0.5)),
                use_hybrid_threshold=bool(settings_data.get("use_hybrid_threshold", False)),
            ),
            experiments=experiments,
        )
        if experiments and not EXPERIMENTS_PATH.exists():
            state.persist_experiments()
        return state

    @staticmethod
    def _migrate_legacy_parcels():
        loaded = _read_json(PARCELS_PATH, [])
        if not isinstance(loaded, list) or not loaded:
            return []
        plots = []
        for item in loaded:
            if not isinstance(item, dict) or item.get("validation_mode"):
                continue
            results = [
                {
                    "healthy_pct": float(image.get("healthy_pct", 0.0)),
                    "severity_pct": float(image.get("severity_pct", 0.0)),
                }
                for image in item.get("images", [])
                if image.get("processed")
            ]
            reading = Reading(
                id=_new_id(),
                date=item.get("date", ""),
                target_images=int(item.get("target_images", len(results))),
                description=item.get("description", ""),
                result_images=results,
                processed=bool(results),
            )
            plots.append(Parcel(id=item.get("id", _new_id()), name=item.get("name", "Parcela"), readings=[reading]))
        if not plots:
            return []
        culture = next((item.get("culture") for item in loaded if isinstance(item, dict)), "Trigo")
        start_date = next((item.get("date") for item in loaded if isinstance(item, dict)), "")
        return [
            Experiment(
                id=_new_id(),
                name="Amostragens anteriores",
                start_date=start_date,
                culture=culture or "Trigo",
                blocks=[Block(id=_new_id(), name="Bloco importado", parcels=plots)],
            )
        ]

    def save_settings(self):
        ensure_app_files()
        _write_json(
            SETTINGS_PATH,
            {
                "confidence": round(float(self.settings.confidence), 4),
                "sensitivity": round(float(self.settings.sensitivity), 4),
                "use_hybrid_threshold": bool(self.settings.use_hybrid_threshold),
            },
        )

    def persist_experiments(self):
        ensure_app_files()
        _write_json(EXPERIMENTS_PATH, [experiment.to_dict() for experiment in self.experiments])

    def add_experiment(self, name, start_date, culture, description=""):
        experiment = Experiment(_new_id(), name, start_date, culture, description)
        self.experiments.append(experiment)
        self.persist_experiments()
        return experiment

    def add_block(self, name, description=""):
        experiment = self.get_active_experiment()
        if experiment is None:
            return None
        block = Block(_new_id(), name, description)
        experiment.blocks.append(block)
        self.persist_experiments()
        return block

    def add_plot(self, name, description=""):
        block = self.get_active_block()
        if block is None:
            return None
        plot = Parcel(_new_id(), name, description)
        block.parcels.append(plot)
        self.persist_experiments()
        return plot

    def add_reading(self, reading_date, target_images, description=""):
        plot = self.get_active_plot()
        if plot is None:
            return None
        reading = Reading(_new_id(), reading_date, target_images, description)
        plot.readings.append(reading)
        self.persist_experiments()
        return reading

    def get_active_experiment(self):
        return next((item for item in self.experiments if item.id == self.active_experiment_id), None)

    def get_active_block(self):
        experiment = self.get_active_experiment()
        return next((item for item in experiment.blocks if item.id == self.active_block_id), None) if experiment else None

    def get_active_plot(self):
        block = self.get_active_block()
        return next((item for item in block.parcels if item.id == self.active_plot_id), None) if block else None

    def get_active_reading(self):
        plot = self.get_active_plot()
        return next((item for item in plot.readings if item.id == self.active_reading_id), None) if plot else None

    def get_active_parcel(self):
        return self.unit_test if self.active_level == "test" else self.get_active_reading()

    def open_experiment(self, item_id):
        self.active_experiment_id = item_id
        self.active_level = "experiment"

    def open_block(self, item_id):
        self.active_block_id = item_id
        self.active_level = "block"

    def open_plot(self, item_id):
        self.active_plot_id = item_id
        self.active_level = "plot"

    def open_reading(self, item_id):
        self.active_reading_id = item_id
        self.active_level = "reading"

    def start_unit_test(self):
        self.unit_test = Reading(_new_id(), "", 0, validation_mode=True)
        self.active_level = "test"

    def navigate_back(self):
        levels = {"experiment": "home", "block": "experiment", "plot": "block", "reading": "plot", "test": "home"}
        previous = self.active_level
        self.active_level = levels.get(previous, "home")
        if previous == "test":
            self.unit_test = None
