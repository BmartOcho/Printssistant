"""
Auto-Enhancement Engine — intelligent image preprocessing for vectorization.

Classifies images by type (logo, text, illustration, photograph) using
OpenCV heuristics, then applies a tailored preprocessing chain and selects
optimal tracing parameters. No ML dependencies — pure OpenCV + numpy.
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Image Classification
# ═══════════════════════════════════════════════════════════════════════

def classify_image(img_bgr, has_alpha):
    """
    Classify a BGR image into one of four types using heuristic analysis.

    Returns:
        dict with "type", "confidence", and "metrics"
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # --- Edge density (Canny) ---
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / (h * w)

    # --- Saturation ---
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    avg_saturation = float(hsv[:, :, 1].mean())

    # --- Contrast ratio ---
    p5 = float(np.percentile(gray, 5))
    p95 = float(np.percentile(gray, 95))
    contrast_ratio = (p95 - p5) / 255.0

    # --- Unique color count (K-means on small sample) ---
    unique_colors = _estimate_color_count(img_bgr)

    is_high_contrast = contrast_ratio > 0.6

    metrics = {
        "edge_density": round(edge_density, 4),
        "avg_saturation": round(avg_saturation, 1),
        "unique_color_count": unique_colors,
        "contrast_ratio": round(contrast_ratio, 3),
        "has_alpha": has_alpha,
        "is_high_contrast": is_high_contrast,
    }

    # --- Decision tree ---
    img_type = "photograph"
    confidence = 0.5

    if edge_density > 0.15 and avg_saturation < 40 and unique_colors <= 4:
        img_type = "text"
        confidence = min(1.0, edge_density / 0.2)
    elif unique_colors <= 8 and is_high_contrast:
        img_type = "logo"
        confidence = min(1.0, contrast_ratio)
    elif has_alpha and unique_colors <= 12 and avg_saturation < 80:
        img_type = "logo"
        confidence = 0.7
    elif 5 <= unique_colors <= 64 and avg_saturation >= 30:
        if 0.03 <= edge_density <= 0.15:
            img_type = "illustration"
            confidence = 0.7
        elif avg_saturation >= 50:
            img_type = "illustration"
            confidence = 0.6

    logger.info(f"Classified as '{img_type}' (confidence={confidence:.2f}, colors={unique_colors}, edges={edge_density:.3f}, sat={avg_saturation:.0f})")

    return {"type": img_type, "confidence": round(confidence, 2), "metrics": metrics}


def _estimate_color_count(img_bgr, sample_size=100):
    """Estimate perceptually distinct color count via K-means on a small sample."""
    h, w = img_bgr.shape[:2]
    small = cv2.resize(img_bgr, (sample_size, sample_size), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2Lab)
    data = lab.reshape(-1, 3).astype(np.float32)

    k = 32
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 2.0)
    _, labels, _ = cv2.kmeans(data, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

    # Count clusters with >0.5% of pixels
    total = labels.shape[0]
    threshold = total * 0.005
    _, counts = np.unique(labels, return_counts=True)
    significant = int(np.sum(counts > threshold))

    return significant


# ═══════════════════════════════════════════════════════════════════════
#  Auto-Enhancement Pipeline
# ═══════════════════════════════════════════════════════════════════════

def auto_enhance(img_bgr, classification):
    """
    Apply the optimal preprocessing chain for the classified image type.
    Returns the enhanced BGR image ready for tracing.
    """
    img_type = classification["type"]

    if img_type == "logo":
        return _enhance_logo(img_bgr)
    elif img_type == "text":
        return _enhance_text(img_bgr)
    elif img_type == "illustration":
        return _enhance_illustration(img_bgr)
    else:
        return _enhance_photograph(img_bgr)


def _enhance_logo(img):
    """Logo: auto levels → background removal → quantize K=8 → bilateral."""
    img = _auto_levels(img)
    img = _remove_background(img)
    img = _color_quantize(img, k=8)
    img = cv2.bilateralFilter(img, d=9, sigmaColor=50, sigmaSpace=50)
    return img


def _enhance_text(img):
    """Text: auto levels → grayscale → adaptive threshold → morph close → BGR."""
    img = _auto_levels(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = _adaptive_threshold(gray)
    binary = _morphological_cleanup(binary)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def _enhance_illustration(img):
    """Illustration: auto levels → quantize K=16 → bilateral → unsharp."""
    img = _auto_levels(img)
    img = _color_quantize(img, k=16)
    img = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
    img = _unsharp_mask(img, strength=0.3)
    return img


def _enhance_photograph(img):
    """Photo: auto levels → bilateral → quantize K=32 → unsharp."""
    img = _auto_levels(img)
    img = cv2.bilateralFilter(img, d=9, sigmaColor=100, sigmaSpace=100)
    img = _color_quantize(img, k=32)
    img = _unsharp_mask(img, strength=0.3)
    return img


# ═══════════════════════════════════════════════════════════════════════
#  Preprocessing Helpers
# ═══════════════════════════════════════════════════════════════════════

def _auto_levels(img_bgr):
    """
    Histogram stretching on L channel in Lab space.
    Maps p2 brightness → 0 and p98 → 255. Skips if already well-distributed.
    """
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2Lab)
    l_channel = lab[:, :, 0].astype(np.float32)

    p2 = np.percentile(l_channel, 2)
    p98 = np.percentile(l_channel, 98)

    # Skip if already well-distributed
    if p98 - p2 > 230:
        return img_bgr

    # Avoid division by zero
    if p98 - p2 < 1:
        return img_bgr

    l_stretched = np.clip((l_channel - p2) * (255.0 / (p98 - p2)), 0, 255)
    lab[:, :, 0] = l_stretched.astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_Lab2BGR)


def _remove_background(img_bgr):
    """
    Detect solid background via flood fill from four corners.
    If >40% of image is one color, replace with white.
    Skip if foreground would be <5%.
    """
    h, w = img_bgr.shape[:2]
    total_pixels = h * w
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    best_mask = None
    best_count = 0

    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]

    for cx, cy in corners:
        mask = np.zeros((h + 2, w + 2), np.uint8)
        flood_img = gray.copy()
        num_filled, _, _, _ = cv2.floodFill(
            flood_img, mask, (cx, cy), 255,
            loDiff=20, upDiff=20,
            flags=cv2.FLOODFILL_MASK_ONLY | (255 << 8)
        )
        filled_count = np.count_nonzero(mask[1:-1, 1:-1])
        if filled_count > best_count:
            best_count = filled_count
            best_mask = mask[1:-1, 1:-1]

    bg_ratio = best_count / total_pixels
    fg_ratio = 1.0 - bg_ratio

    if bg_ratio < 0.40 or fg_ratio < 0.05:
        return img_bgr

    # Replace background with white
    result = img_bgr.copy()
    result[best_mask > 0] = [255, 255, 255]
    return result


def _color_quantize(img_bgr, k):
    """
    K-means color quantization in Lab space.
    Downsamples to 800x800 for speed, maps palette back to full resolution.
    """
    h, w = img_bgr.shape[:2]

    # Downsample for K-means speed
    max_dim = 800
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        small = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = img_bgr

    lab_small = cv2.cvtColor(small, cv2.COLOR_BGR2Lab)
    data = lab_small.reshape(-1, 3).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels_small, centers = cv2.kmeans(data, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
    centers = centers.astype(np.uint8)

    # Map palette back to full-resolution image
    lab_full = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2Lab)
    data_full = lab_full.reshape(-1, 3).astype(np.float32)
    centers_f = centers.astype(np.float32)

    # Nearest-neighbor assignment: for each pixel find closest center
    # Use batch processing to avoid memory explosion
    n = data_full.shape[0]
    labels_full = np.empty(n, dtype=np.int32)
    batch_size = 500_000
    for i in range(0, n, batch_size):
        batch = data_full[i:i + batch_size]
        dists = np.linalg.norm(batch[:, None, :] - centers_f[None, :, :], axis=2)
        labels_full[i:i + batch_size] = np.argmin(dists, axis=1)

    quantized_lab = centers[labels_full].reshape(h, w, 3)
    return cv2.cvtColor(quantized_lab, cv2.COLOR_Lab2BGR)


def _adaptive_threshold(gray):
    """Adaptive threshold for B&W — handles uneven lighting from scans."""
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=21,
        C=10,
    )


def _morphological_cleanup(binary, kernel_size=2):
    """Close small gaps and remove isolated noise in binary image."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


def _unsharp_mask(img_bgr, strength=0.3):
    """Light unsharp mask to restore edge definition after quantization."""
    blurred = cv2.GaussianBlur(img_bgr, (0, 0), 2)
    return cv2.addWeighted(img_bgr, 1.0 + strength, blurred, -strength, 0)


def upscale_small(img_bgr, min_dim=1500):
    """Lanczos upscale if longest side < min_dim. Small images produce poor traces."""
    h, w = img_bgr.shape[:2]
    longest = max(h, w)
    if longest >= min_dim:
        return img_bgr
    scale = min_dim / longest
    new_w = int(w * scale)
    new_h = int(h * scale)
    logger.info(f"Upscaling {w}x{h} -> {new_w}x{new_h} for better tracing")
    return cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)


# ═══════════════════════════════════════════════════════════════════════
#  Auto Config Generation
# ═══════════════════════════════════════════════════════════════════════

# Potrace availability (mirrors check in vectorizer.py)
try:
    import potrace as _potrace_check
    _HAS_POTRACE = True
except ImportError:
    _HAS_POTRACE = False


def get_auto_config(classification, width, height, has_alpha):
    """
    Generate a complete vectorizer config dict based on image classification.
    Returns a config compatible with VectorizerEngine's engine methods.
    """
    img_type = classification["type"]

    if img_type == "logo":
        return _config_logo(has_alpha)
    elif img_type == "text":
        return _config_text(has_alpha)
    elif img_type == "illustration":
        return _config_illustration()
    else:
        return _config_photograph()


def _config_logo(has_alpha):
    use_potrace = _HAS_POTRACE
    return {
        "mode": "bw",
        "use_potrace": use_potrace,
        "auto_mode": True,
        "alpha_handling": {"invert": "auto"},
        "vtracer": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 4,
            "corner_threshold": 60,
            "length_threshold": 4.0,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 3,
        },
        "potrace": {
            "turd_size": 5,
            "alphamax": 1.0,
            "opttolerance": 0.5,
        },
        "preprocessing": {},
    }


def _config_text(has_alpha):
    use_potrace = _HAS_POTRACE
    return {
        "mode": "bw",
        "use_potrace": use_potrace,
        "auto_mode": True,
        "alpha_handling": {"invert": "auto"},
        "vtracer": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 2,
            "corner_threshold": 90,
            "length_threshold": 4.0,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 3,
        },
        "potrace": {
            "turd_size": 3,
            "alphamax": 1.0,
            "opttolerance": 0.3,
        },
        "preprocessing": {},
    }


def _config_illustration():
    return {
        "mode": "color",
        "use_potrace": False,
        "auto_mode": True,
        "alpha_handling": {"invert": False},
        "vtracer": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 4,
            "color_precision": 5,
            "layer_difference": 12,
            "corner_threshold": 60,
            "length_threshold": 4.0,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 3,
        },
        "preprocessing": {},
    }


def _config_photograph():
    return {
        "mode": "color",
        "use_potrace": False,
        "auto_mode": True,
        "alpha_handling": {"invert": False},
        "vtracer": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 10,
            "color_precision": 6,
            "layer_difference": 20,
            "corner_threshold": 45,
            "length_threshold": 5.0,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 3,
        },
        "preprocessing": {},
    }
