"""
Vectorizer Presets - Two simplified presets that load from learned_settings.json.
1. Laser Engraving (B&W) - Precise black-and-white vector tracing
2. Full Color - Color-accurate image trace with multi-layer SVG output
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
    "description": "Precise black-and-white vectorization optimized for laser engraving. "
                   "Produces sharp, accurate letter forms and clean paths.",
    "icon": "⚡",
    "category": "Laser",
    "mode": "bw",
    "preprocessing": {
        "grayscale": True,
        "denoise": True,
        "denoise_strength": 10,
        "sharpen": True,
        "sharpen_amount": 1.5,
        "contrast_enhance": True,
        "contrast_clip_limit": 3.0,
        "contrast_grid_size": 8,
        "morphology": "close",
        "morphology_kernel": 2,
        "invert": "auto",
    },
    "threshold": {
        "method": "otsu",
        "value": 128,
        "adaptive_block_size": 15,
        "adaptive_c": 5,
    },
    "tracing": {
        "turd_size": 2,
        "corner_threshold": 1.0,
        "optimize_tolerance": 0.2,
        "smooth": True,
        "min_contour_area": 50,
        "simplify_tolerance": 1.5,
    },
    "output": {
        "stroke_color": "#000000",
        "stroke_width": 0.5,
        "fill_color": "#000000",
        "fill_mode": "fill",
        "background": "transparent",
    }
}

DEFAULT_FULL_COLOR = {
    "name": "Full Color",
    "description": "Color-accurate vectorization that preserves the original palette. "
                   "Eye-droppers colors away from edges to avoid raster noise.",
    "icon": "🎨",
    "category": "Color",
    "mode": "color",
    "preprocessing": {
        "denoise": True,
        "denoise_strength": 5,
        "sharpen": False,
        "sharpen_amount": 1.0,
        "contrast_enhance": False,
        "contrast_clip_limit": 2.0,
        "contrast_grid_size": 8,
        "invert": False,
    },
    "color": {
        "num_colors": 12,
        "edge_margin": 1,
        "min_cluster_fraction": 0.01,
    },
    "threshold": {
        "method": "simple",
        "value": 128,
    },
    "tracing": {
        "turd_size": 3,
        "corner_threshold": 1.0,
        "optimize_tolerance": 0.2,
        "smooth": True,
        "min_contour_area": 30,
        "simplify_tolerance": 1.0,
    },
    "output": {
        "stroke_color": "none",
        "stroke_width": 0,
        "fill_color": "#000000",
        "fill_mode": "fill",
        "background": "transparent",
    }
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


def get_preset(name):
    """Get a preset by name with learned settings applied."""
    learned = _load_learned()

    if name == "laser_bw":
        preset = copy.deepcopy(DEFAULT_LASER_BW)
        if "laser_bw" in learned and learned["laser_bw"].get("sample_count", 0) > 0:
            preset = _apply_learned(preset, learned["laser_bw"].get("settings", {}))
        return preset

    elif name == "full_color":
        preset = copy.deepcopy(DEFAULT_FULL_COLOR)
        if "full_color" in learned and learned["full_color"].get("sample_count", 0) > 0:
            preset = _apply_learned(preset, learned["full_color"].get("settings", {}))
        return preset

    return None


def list_presets():
    """Return summary info for all available presets."""
    learned = _load_learned()

    presets = []
    for key, default in [("laser_bw", DEFAULT_LASER_BW), ("full_color", DEFAULT_FULL_COLOR)]:
        info = {
            "key": key,
            "name": default["name"],
            "description": default["description"],
            "icon": default["icon"],
            "category": default["category"],
        }
        # Add learning stats if available
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
