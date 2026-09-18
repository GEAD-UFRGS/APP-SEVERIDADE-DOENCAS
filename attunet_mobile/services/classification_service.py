import cv2
import numpy as np

from config import DAMAGE_MODE_NECROTIC, DEFAULT_DAMAGE_MODE


class ClassificationService:
    HEALTHY_COLOR = np.array([0, 200, 0, 255], dtype=np.uint8)
    SEVERITY_COLOR = np.array([255, 165, 0, 255], dtype=np.uint8)
    MAX_ANALYSIS_SIDE = 1600

    def classify_image(
        self,
        original_rgb: np.ndarray,
        leaf_mask: np.ndarray,
        damage_mode: str = DEFAULT_DAMAGE_MODE,
        cleanup: bool = True,
    ):
        folha_mask = leaf_mask > 0
        analysis_rgb, analysis_leaf_mask = self._analysis_image(original_rgb, folha_mask)
        severidade_mask = self._severity_mask(analysis_rgb, analysis_leaf_mask, damage_mode, cleanup)
        if severidade_mask.shape != folha_mask.shape:
            height, width = folha_mask.shape
            severidade_mask = cv2.resize(
                severidade_mask.astype(np.uint8),
                (width, height),
                interpolation=cv2.INTER_NEAREST,
            ) > 0
        severidade_mask &= folha_mask
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

    def _analysis_image(self, original_rgb, leaf_mask):
        height, width = leaf_mask.shape
        largest_side = max(height, width)
        if largest_side <= self.MAX_ANALYSIS_SIDE:
            return original_rgb, leaf_mask
        scale = self.MAX_ANALYSIS_SIDE / largest_side
        analysis_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        resized_rgb = cv2.resize(original_rgb, analysis_size, interpolation=cv2.INTER_AREA)
        resized_mask = cv2.resize(leaf_mask.astype(np.uint8), analysis_size, interpolation=cv2.INTER_NEAREST) > 0
        return resized_rgb, resized_mask

    def _severity_mask(self, original_rgb, leaf_mask, damage_mode, cleanup):
        if not np.any(leaf_mask):
            return np.zeros_like(leaf_mask, dtype=bool)

        features = self._color_features(original_rgb)
        reference = self._healthy_reference(features, leaf_mask)
        necrotic = self._necrotic_mask(features, leaf_mask, reference)

        if damage_mode == DAMAGE_MODE_NECROTIC:
            severity = necrotic
        else:
            severity = necrotic | self._chlorotic_mask(features, leaf_mask, reference)

        return self._clean_mask(severity, leaf_mask) if cleanup else severity

    def _color_features(self, original_rgb):
        rgb = original_rgb.astype(np.float32)
        r, g, b = cv2.split(rgb)
        total = r + g + b + 1.0
        normalized_exg = (2.0 * g - r - b) / total

        hsv = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2HSV)
        h, s, v = cv2.split(hsv.astype(np.float32))
        lab = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2LAB)
        _, lab_a, lab_b = cv2.split(lab.astype(np.float32))
        return {
            "r": r,
            "g": g,
            "b": b,
            "h": h,
            "s": s,
            "v": v,
            "lab_a": lab_a,
            "lab_b": lab_b,
            "exg": normalized_exg,
        }

    def _healthy_reference(self, features, leaf_mask):
        h = features["h"]
        s = features["s"]
        exg = features["exg"]
        green_candidates = leaf_mask & (h >= 28.0) & (h <= 90.0) & (s >= 22.0)

        if np.count_nonzero(green_candidates) >= 32:
            candidate_exg = exg[green_candidates]
            cutoff = float(np.percentile(candidate_exg, 65.0))
            reference_mask = green_candidates & (exg >= cutoff)
        else:
            cutoff = float(np.percentile(exg[leaf_mask], 75.0))
            reference_mask = leaf_mask & (exg >= cutoff)

        return {
            "exg": float(np.median(exg[reference_mask])),
            "a": float(np.median(features["lab_a"][reference_mask])),
            "b": float(np.median(features["lab_b"][reference_mask])),
            "s": float(np.median(s[reference_mask])),
            "v": float(np.median(features["v"][reference_mask])),
            "dark_v": float(np.percentile(features["v"][leaf_mask], 18.0)),
        }

    def _necrotic_mask(self, features, leaf_mask, reference):
        r = features["r"]
        g = features["g"]
        b = features["b"]
        h = features["h"]
        s = features["s"]
        v = features["v"]
        lab_a = features["lab_a"]
        lab_b = features["lab_b"]
        exg = features["exg"]

        lost_green = (lab_a >= max(reference["a"] + 7.0, 120.0)) & (exg <= reference["exg"] - 0.055)
        brown = (
            (h <= 27.0)
            & (s >= 32.0)
            & (r >= g * 0.93)
            & (b <= np.maximum(r, g) * 0.92)
            & (v <= 238.0)
        )
        deep_brown = (lab_a >= 134.0) & (lab_b >= 126.0) & (exg <= 0.035)
        dark_non_green = (
            (v <= min(reference["dark_v"] + 8.0, reference["v"] * 0.62))
            & (exg <= reference["exg"] - 0.07)
            & ((s >= 24.0) | (r >= g))
        )
        neutral_damage = (v <= 92.0) & (s <= 55.0) & (exg <= 0.01) & (r >= g * 0.94)

        return leaf_mask & ((lost_green & brown) | deep_brown | dark_non_green | neutral_damage)

    def _chlorotic_mask(self, features, leaf_mask, reference):
        h = features["h"]
        s = features["s"]
        v = features["v"]
        lab_a = features["lab_a"]
        lab_b = features["lab_b"]
        exg = features["exg"]

        green_loss = (lab_a >= reference["a"] + 4.0) & (exg <= reference["exg"] - 0.045)
        yellow = (
            (h >= 17.0)
            & (h <= 47.0)
            & (s >= 20.0)
            & (lab_b >= max(reference["b"] + 5.0, 135.0))
            & (lab_a >= reference["a"] + 3.0)
        )
        pale_green = (
            (h >= 25.0)
            & (h <= 65.0)
            & green_loss
            & (lab_b >= reference["b"] + 2.0)
            & (v >= reference["v"] * 0.55)
        )
        absolute_chlorosis = (
            (h >= 18.0)
            & (h <= 43.0)
            & (lab_a >= 116.0)
            & (lab_b >= 143.0)
            & (exg <= 0.10)
        )

        return leaf_mask & (yellow | pale_green | absolute_chlorosis)

    def _clean_mask(self, severity, leaf_mask):
        severity_u8 = severity.astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        closed = cv2.morphologyEx(severity_u8, cv2.MORPH_CLOSE, kernel)
        return (closed > 0) & leaf_mask

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
