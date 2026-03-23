"""
Vectorizer Presets - Three engine-native presets with learned settings support.
1. Laser Engraving (B&W) - VTracer binary mode for general B&W vectorization
2. Full Color - VTracer color mode with stacked hierarchical layering
3. High Precision B&W - Potrace for sharp edges on logos, text, laser/vinyl

Includes smart preset suggestion based on image analysis.
"""

import copy
import json
import os
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "learned_settings.json")


# ─── Default Configurations ────────────────────────────────────────

DEFAULT_LASER_BW = {
    "name": "Laser Engraving (B&W)",
    "description": "General-purpose black-and-white vectorization using VTracer. "
                   "Fast and clean results for most B&W artwork.",
    "icon": "\u26a1",
    "category": "Laser",
    "mode": "bw",
    "alpha_handling": {
        "invert": "auto",
    },
    "vtracer": {
        "colormode": "binary",
        "hierarchical": "stacked",
        "mode": "spline",
        "filter_speckle": 4,
        "corner_threshold": 60,
        "length_threshold": 4.0,
        "max_iterations": 10,
        "splice_threshold": 45,
        "path_precision": 8,
    },
}

DEFAULT_FULL_COLOR = {
    "name": "Full Color",
    "description": "Color-accurate vectorization that preserves the original palette. "
                   "Uses VTracer's native color quantization and stacked layering.",
    "icon": "\U0001f3a8",
    "category": "Color",
    "mode": "color",
    "alpha_handling": {
        "invert": False,
    },
    "vtracer": {
        "colormode": "color",
        "hierarchical": "stacked",
        "mode": "spline",
        "filter_speckle": 4,
        "color_precision": 6,
        "layer_difference": 16,
        "corner_threshold": 60,
        "length_threshold": 4.0,
        "max_iterations": 10,
        "splice_threshold": 45,
        "path_precision": 6,
    },
}

DEFAULT_HIGH_PRECISION_BW = {
    "name": "High Precision B&W",
    "description": "Potrace-powered precision tracing for logos, text, and lettering. "
                   "Produces mathematically optimal curves with sharp, clean edges.",
    "icon": "\U0001f3af",
    "category": "Precision",
    "mode": "bw",
    "high_precision_bw": True,
    "alpha_handling": {
        "invert": "auto",
    },
    "potrace": {
        "turd_size": 5,
        "alphamax": 1.0,
        "opttolerance": 0.5,
    },
    "preprocessing": {
        "denoise": True,
        "denoise_strength": 5,
    },
}


def _load_learned():
    """Load learned settings from JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _apply_learned(preset, learned_settings):
    """Apply learned parameter settings onto a preset's defaults."""
    result = copy.deepcopy(preset)
    if not learned_settings:
        return result

    for section_key, section_vals in learned_settings.items():
        if section_key in result and isinstance(section_vals, dict):
            result[section_key].update(section_vals)

    return result


_PRESET_MAP = {
    "laser_bw": DEFAULT_LASER_BW,
    "full_color": DEFAULT_FULL_COLOR,
    "high_precision_bw": DEFAULT_HIGH_PRECISION_BW,
}


def get_preset(name):
    """Get a preset by name with learned settings applied."""
    default = _PRESET_MAP.get(name)
    if default is None:
        return None

    learned = _load_learned()
    preset = copy.deepcopy(default)

    if name in learned and learned[name].get("sample_count", 0) > 0:
        preset = _apply_learned(preset, learned[name].get("settings", {}))

    return preset


def list_presets():
    """Return summary info for all available presets."""
    learned = _load_learned()

    presets = []
    for key, default in _PRESET_MAP.items():
        info = {
            "key": key,
            "name": default["name"],
            "description": default["description"],
            "icon": default["icon"],
            "category": default["category"],
        }
        if key in learned:
            info["sample_count"] = learned[key].get("sample_count", 0)
            info["best_score"] = learned[key].get("best_score", 0)
            info["last_updated"] = learned[key].get("last_updated", "")
        else:
            info["sample_count"] = 0
            info["best_score"] = 0
            info["last_updated"] = ""

        presets.append(info)

    return presets


# ─── Smart Preset Routing ──────────────────────────────────────────

def suggest_preset(image_analysis: Dict[str, Any]) -> List[str]:
    """
    Suggest optimal preset(s) based on image characteristics.

    Uses image analysis (saturation, transparency, content brightness) to recommend
    the best vectorization preset. Returns presets ranked by recommendation.

    Args:
        image_analysis: Dict with keys:
            - has_alpha: bool, whether image has transparency
            - content_is_light: bool, whether opaque content is predominantly light
            - width: int, image width in pixels
            - height: int, image height in pixels
            - detected_mode_suggestion: str, initial suggestion ("bw", "color", "high_precision_bw")

    Returns:
        List[str]: Preset keys ranked by recommendation priority.
                   Example: ["high_precision_bw", "laser_bw", "full_color"]
    """
    suggestions = []
    width = image_analysis.get("width", 0)
    height = image_analysis.get("height", 0)
    has_alpha = image_analysis.get("has_alpha", False)
    suggested_mode = image_analysis.get("detected_mode_suggestion", "bw")

    # Primary logic: transparent + B&W = high_precision_bw is ideal
    if has_alpha and suggested_mode in ("bw", "high_precision_bw"):
        suggestions.append("high_precision_bw")

    # If mode suggestion is color-rich, recommend full_color
    if suggested_mode == "color":
        suggestions.append("full_color")

    # Always include B&W options for fallback
    if "high_precision_bw" not in suggestions:
        suggestions.append("high_precision_bw")

    if "laser_bw" not in suggestions:
        suggestions.append("laser_bw")

    # Add full_color if not already present
    if "full_color" not in suggestions:
        suggestions.append("full_color")

    # Trim to top 3 suggestions
    return suggestions[:3]


def analyze_image_characteristics(
    image_bytes: bytes,
) -> Dict[str, Any]:
    """
    Analyze image bytes to extract vectorization-relevant characteristics.

    Examines color saturation, transparency, and brightness to determine
    the best preset and provide user guidance.

    Args:
        image_bytes: Raw image data as bytes (PNG or JPEG)

    Returns:
        Dict with keys:
            - has_alpha: bool
            - content_is_light: bool
            - detected_saturation: float (0-255 scale)
            - color_count_estimate: int
            - suggested_mode: str ("bw", "color", "high_precision_bw")
    """
    try:
        import cv2
        import numpy as np

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)

        if img is None:
            logger.warning("Could not decode image for analysis")
            return _default_image_analysis()

        has_alpha = len(img.shape) == 3 and img.shape[2] == 4
        content_is_light = False

        # Analyze brightness if alpha channel exists
        if has_alpha:
            alpha = img[:, :, 3]
            bgr = img[:, :, :3]
            opaque_mask = alpha > 128
            if opaque_mask.any():
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                content_is_light = gray[opaque_mask].mean() > 170
        else:
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
            content_is_light = gray.mean() > 170

        # Analyze saturation and color count
        if len(img.shape) == 3 and img.shape[2] >= 3:
            bgr = img[:, :, :3]
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            saturation = hsv[:, :, 1]
            avg_saturation = saturation.mean()

            # Estimate distinct colors by downsampling and clustering
            small = cv2.resize(hsv, (50, 50))
            reshaped = small.reshape(-1, 3)
            unique_colors = len(np.unique(reshaped, axis=0))
        else:
            avg_saturation = 0.0
            unique_colors = 2

        # Determine suggested mode based on saturation and colors
        if avg_saturation < 30:  # Low saturation = mostly B&W
            suggested_mode = "high_precision_bw" if has_alpha else "bw"
        elif unique_colors > 10:  # Rich colors
            suggested_mode = "color"
        else:
            suggested_mode = "bw"

        return {
            "has_alpha": has_alpha,
            "content_is_light": content_is_light,
            "detected_saturation": round(avg_saturation, 1),
            "color_count_estimate": unique_colors,
            "suggested_mode": suggested_mode,
        }

    except ImportError:
        logger.warning("OpenCV or NumPy not available for image analysis")
        return _default_image_analysis()
    except Exception as e:
        logger.warning(f"Image analysis failed: {str(e)}")
        return _default_image_analysis()


def _default_image_analysis() -> Dict[str, Any]:
    """Return safe default analysis when analysis fails."""
    return {
        "has_alpha": False,
        "content_is_light": False,
        "detected_saturation": 0.0,
        "color_count_estimate": 0,
        "suggested_mode": "bw",
    }
