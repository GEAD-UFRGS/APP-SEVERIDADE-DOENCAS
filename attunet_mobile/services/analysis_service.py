from pathlib import Path

from PIL import Image

from services.classification_service import ClassificationService
from services.image_service import pil_image_to_base64, zoom_rgba_to_mask
from services.segmentation_service import SegmentationService


class AnalysisService:
    def __init__(self):
        self.segmentation_service = SegmentationService()
        self.classification_service = ClassificationService()

    def process_image(self, image_path: Path, confidence: float, sensitivity: float):
        segmentation = self.segmentation_service.segment_image(image_path, confidence)
        classification = self.classification_service.classify_image(
            original_rgb=segmentation["original_rgb"],
            leaf_mask=segmentation["leaf_mask"],
            sensitivity=sensitivity,
        )

        original_view = zoom_rgba_to_mask(
            segmentation["segmented_rgba"],
            segmentation["leaf_mask"],
        )
        overlay_rgba = self.classification_service.build_overlay_rgba(
            segmentation["segmented_rgba"],
            classification["healthy_mask"],
            classification["severity_mask"],
        )
        overlay_view = zoom_rgba_to_mask(overlay_rgba, segmentation["leaf_mask"])

        map_rgba = self.classification_service.build_map_rgba(
            classification["healthy_mask"],
            classification["severity_mask"],
        )
        map_view = zoom_rgba_to_mask(map_rgba, segmentation["leaf_mask"])

        return {
            "view_sources": {
                "original": pil_image_to_base64(Image.fromarray(original_view, mode="RGBA")),
                "sobreposicao": pil_image_to_base64(Image.fromarray(overlay_view, mode="RGBA")),
                "mapa": pil_image_to_base64(Image.fromarray(map_view, mode="RGBA")),
            },
            "healthy_pct": classification["healthy_pct"],
            "severity_pct": classification["severity_pct"],
        }
