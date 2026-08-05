import cv2
import numpy as np


class ClassificationService:
    HEALTHY_COLOR = np.array([0, 200, 0, 255], dtype=np.uint8)
    SEVERITY_COLOR = np.array([255, 165, 0, 255], dtype=np.uint8)
    ABSOLUTE_EXG_THRESHOLD = 53.5
    HYBRID_ADAPTIVE_WEIGHT = 0.2
    HYBRID_SENSITIVITY_RANGE = 12.0

    def classify_image(
        self,
        original_rgb: np.ndarray,
        leaf_mask: np.ndarray,
        sensitivity: float,
        use_hybrid_threshold: bool = False,
        cleanup: int = 1,
    ):
        folha_mask = leaf_mask > 0
        severidade_mask = self._severity_mask(
            original_rgb=original_rgb,
            leaf_mask=folha_mask,
            sensitivity=sensitivity,
            use_hybrid_threshold=use_hybrid_threshold,
            cleanup=cleanup,
        )
        sadia_mask = folha_mask & (~severidade_mask)

        folha_px = int(np.count_nonzero(folha_mask))
        severidade_px = int(np.count_nonzero(severidade_mask))
        sadia_px = int(np.count_nonzero(sadia_mask))

        if folha_px > 0:
            severity_pct = 100.0 * severidade_px / folha_px
            healthy_pct = 100.0 * sadia_px / folha_px
        else:
            severity_pct = 0.0
            healthy_pct = 0.0

        return {
            "leaf_mask": folha_mask,
            "healthy_mask": sadia_mask,
            "severity_mask": severidade_mask,
            "healthy_pct": round(healthy_pct, 2),
            "severity_pct": round(severity_pct, 2),
        }

    def _severity_mask(
        self,
        original_rgb: np.ndarray,
        leaf_mask: np.ndarray,
        sensitivity: float,
        use_hybrid_threshold: bool,
        cleanup: int,
    ):
        sensitivity = float(np.clip(sensitivity, 0.0, 1.0))

        img_bgr = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2BGR)
        b, g, r = cv2.split(img_bgr.astype(np.float32))

        exg = 2.0 * g - r - b
        exg_leaf = exg[leaf_mask]
        if exg_leaf.size == 0:
            return np.zeros_like(leaf_mask, dtype=bool)

        adaptive_threshold = self._adaptive_threshold(exg_leaf, sensitivity)
        exg_threshold = adaptive_threshold
        if use_hybrid_threshold:
            exg_threshold = self._hybrid_threshold(adaptive_threshold, sensitivity)

        hsv = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2HSV)
        h, s, v = cv2.split(hsv)

        green_hsv = (h >= 25) & (h <= 110) & (s >= 18)
        dominant_green = (g >= (r * 1.03)) & (g >= (b * 0.92))
        light_green = (g >= (r + 8.0)) & (g >= (b + 2.0)) & (v >= 60)
        healthy_green = leaf_mask & ((green_hsv & dominant_green) | light_green)

        low_vegetation = exg <= exg_threshold
        yellow_or_necrotic = ((h < 25) | (h > 110) | (s < 28)) & (g <= (r * 1.08))

        severity = leaf_mask & low_vegetation & (~healthy_green) & yellow_or_necrotic

        kernel_size = 2 * max(1, int(cleanup)) + 1
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        severity_u8 = severity.astype(np.uint8) * 255
        severity_u8 = cv2.morphologyEx(severity_u8, cv2.MORPH_OPEN, kernel)
        severity_u8 = cv2.morphologyEx(severity_u8, cv2.MORPH_CLOSE, kernel)
        return severity_u8 > 0

    def _adaptive_threshold(self, exg_leaf: np.ndarray, sensitivity: float):
        percentile = 6.0 + (sensitivity * 24.0)
        percentile_threshold = float(np.percentile(exg_leaf, percentile))
        median_exg = float(np.median(exg_leaf))
        std_exg = float(np.std(exg_leaf))
        return min(percentile_threshold, median_exg - (0.18 * std_exg))

    def _hybrid_threshold(self, adaptive_threshold: float, sensitivity: float):
        sensitivity_offset = (sensitivity - 0.5) * self.HYBRID_SENSITIVITY_RANGE
        absolute_threshold = self.ABSOLUTE_EXG_THRESHOLD + sensitivity_offset
        blended_threshold = (
            ((1.0 - self.HYBRID_ADAPTIVE_WEIGHT) * absolute_threshold)
            + (self.HYBRID_ADAPTIVE_WEIGHT * adaptive_threshold)
        )
        lower_bound = absolute_threshold - 10.0
        upper_bound = absolute_threshold + 10.0
        return float(np.clip(blended_threshold, lower_bound, upper_bound))

    def build_map_rgba(self, healthy_mask: np.ndarray, severity_mask: np.ndarray):
        height, width = healthy_mask.shape
        result = np.zeros((height, width, 4), dtype=np.uint8)
        result[healthy_mask] = self.HEALTHY_COLOR
        result[severity_mask] = self.SEVERITY_COLOR
        return result

    def build_overlay_rgba(
        self,
        original_rgba: np.ndarray,
        healthy_mask: np.ndarray,
        severity_mask: np.ndarray,
        alpha: float = 0.45,
    ):
        overlay = original_rgba.copy()
        overlay[..., 3] = np.where((healthy_mask | severity_mask), 255, 0).astype(np.uint8)

        healthy_color = np.array([0, 200, 0], dtype=np.float32)
        severity_color = np.array([255, 165, 0], dtype=np.float32)

        healthy_pixels = overlay[..., :3][healthy_mask].astype(np.float32)
        severity_pixels = overlay[..., :3][severity_mask].astype(np.float32)

        overlay[..., :3][healthy_mask] = ((1.0 - alpha) * healthy_pixels + alpha * healthy_color).astype(np.uint8)
        overlay[..., :3][severity_mask] = ((1.0 - alpha) * severity_pixels + alpha * severity_color).astype(np.uint8)
        return overlay
