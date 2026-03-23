"""
Vectorizer Presets - Three engine-native presets with learned settings support.
1. Laser Engraving (B&W) - VTracer binary mode for general B&W vectorization
2. Full Color - VTracer color mode with stacked hierarchical layering
3. High Precision B&W - Potrace for sharp edges on logos, text, laser/vinyl
"""

import copy
import json
import os
import logging

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
