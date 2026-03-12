"""
Vectorizer Engine - Core image-to-vector conversion pipeline.
Supports two modes:
  1. B&W: OpenCV preprocessing + Potrace tracing → single-path black SVG
  2. Color: K-means color quantization → per-layer Potrace tracing → multi-path color SVG
"""

import cv2
import numpy as np
from PIL import Image
import io
import logging
import time

logger = logging.getLogger(__name__)

# Try to import potrace
try:
    import potrace
    HAS_POTRACE = True
    logger.info("Potrace available - using high-quality tracing")
except ImportError:
    HAS_POTRACE = False
    logger.warning("Potrace not available - falling back to OpenCV contour tracing")


class VectorizerEngine:
    """Main vectorization engine that converts raster images to SVG."""

    def __init__(self):
        self.last_preprocessed = None
        self.last_thresholded = None

    def vectorize(self, image_bytes, preset, custom_overrides=None):
        """
        Full vectorization pipeline. Routes to B&W or Color based on preset mode.

        Args:
            image_bytes: Raw image file bytes
            preset: Preset configuration dict
            custom_overrides: Optional dict of parameter overrides

        Returns:
            dict with 'svg' (string), 'preview_bw' (base64 png),
            'stats' (dict with path count, point count, etc.)
        """
        config = self._merge_config(preset, custom_overrides)
        mode = config.get("mode", "bw")

        if mode == "color":
            return self._vectorize_color(image_bytes, config)
        else:
            return self._vectorize_bw(image_bytes, config)

    # ═══════════════════════════════════════════════════════════════════
    #  B&W PIPELINE
    # ═══════════════════════════════════════════════════════════════════

    def _vectorize_bw(self, image_bytes, config):
        """Black and white vectorization pipeline."""
        start_time = time.time()

        # 1. Load image (handles alpha/transparency)
        img, has_alpha, content_is_light = self._load_image(image_bytes)
        original_h, original_w = img.shape[:2]

        # 2. Preprocess
        processed = self._preprocess(img, config["preprocessing"])
        self.last_preprocessed = processed.copy()

        # 3. Threshold to binary
        binary = self._threshold(processed, config["threshold"])

        # Handle inversion — support "auto" mode for transparent images
        invert_setting = config["preprocessing"].get("invert", False)
        should_invert = False
        if invert_setting == "auto":
            should_invert = has_alpha and content_is_light
            if should_invert:
                logger.info("Auto-invert: detected light content on transparent background")
        elif invert_setting:
            should_invert = True

        if should_invert:
            binary = cv2.bitwise_not(binary)

        self.last_thresholded = binary.copy()

        # 4. Trace to vector paths
        if HAS_POTRACE:
            svg_content, stats = self._trace_potrace(
                binary, original_w, original_h, config["tracing"], config["output"]
            )
        else:
            svg_content, stats = self._trace_opencv(
                binary, original_w, original_h, config["tracing"], config["output"]
            )

        # 5. Generate B&W preview
        preview = self._generate_preview(binary)

        elapsed = time.time() - start_time
        stats["processing_time"] = round(elapsed, 2)
        stats["image_width"] = original_w
        stats["image_height"] = original_h
        stats["engine"] = "potrace" if HAS_POTRACE else "opencv"
        stats["has_transparency"] = has_alpha
        stats["auto_inverted"] = should_invert and invert_setting == "auto"
        stats["mode"] = "bw"

        return {
            "svg": svg_content,
            "preview_bw": preview,
            "stats": stats,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  FULL COLOR PIPELINE
    # ═══════════════════════════════════════════════════════════════════

    def _vectorize_color(self, image_bytes, config):
        """Full color vectorization: quantize → layer → trace each color."""
        start_time = time.time()

        # 1. Load image
        img, has_alpha, _ = self._load_image(image_bytes)
        original_h, original_w = img.shape[:2]

        # 2. Light preprocessing (preserve colors, just reduce noise)
        preprocessed = self._preprocess_color(img, config.get("preprocessing", {}))

        # 3. Color quantization
        color_config = config.get("color", {})
        num_colors = color_config.get("num_colors", 12)
        edge_margin = color_config.get("edge_margin", 1)
        min_fraction = color_config.get("min_cluster_fraction", 0.01)

        colors, labels, quantized = self._quantize_colors(
            preprocessed, num_colors, edge_margin, min_fraction
        )

        # 4. Trace each color layer
        trace_config = config.get("tracing", {})
        svg_paths = []
        total_paths = 0
        total_points = 0

        for i, color_bgr in enumerate(colors):
            # Create binary mask for this color
            mask = (labels == i).astype(np.uint8) * 255

            # Skip tiny clusters
            if np.sum(mask > 0) < (original_w * original_h * min_fraction):
                continue

            # Optional morphological cleanup on the mask
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            # Trace this color layer
            if HAS_POTRACE:
                paths, layer_stats = self._trace_color_layer_potrace(
                    mask, color_bgr, trace_config
                )
            else:
                paths, layer_stats = self._trace_color_layer_opencv(
                    mask, color_bgr, trace_config
                )

            svg_paths.extend(paths)
            total_paths += layer_stats["path_count"]
            total_points += layer_stats["point_count"]

        # 5. Build final color SVG
        svg_content = self._build_color_svg(svg_paths, original_w, original_h, config.get("output", {}))

        # 6. Generate preview (quantized image)
        preview = self._generate_preview(cv2.cvtColor(quantized, cv2.COLOR_BGR2GRAY))

        elapsed = time.time() - start_time
        stats = {
            "processing_time": round(elapsed, 2),
            "image_width": original_w,
            "image_height": original_h,
            "path_count": total_paths,
            "point_count": total_points,
            "color_count": len(colors),
            "engine": "potrace" if HAS_POTRACE else "opencv",
            "has_transparency": has_alpha,
            "auto_inverted": False,
            "mode": "color",
        }

        return {
            "svg": svg_content,
            "preview_bw": preview,
            "stats": stats,
        }

    def _preprocess_color(self, img, config):
        """Light preprocessing for color mode — preserve colors, reduce noise."""
        result = img.copy()

        # Denoise (bilateral filter preserves edges + colors better than NLM)
        if config.get("denoise", True):
            strength = config.get("denoise_strength", 5)
            result = cv2.bilateralFilter(result, d=9, sigmaColor=strength * 7, sigmaSpace=strength * 7)

        return result

    def _quantize_colors(self, img, num_colors, edge_margin=1, min_fraction=0.01):
        """
        Reduce image to num_colors dominant colors using K-means.
        Samples colors away from edges to avoid anti-aliasing noise.

        Returns:
            colors: list of BGR color tuples
            labels: 2D array of cluster assignments
            quantized: the quantized image
        """
        h, w = img.shape[:2]

        # Create edge mask to sample colors from interior regions
        if edge_margin > 0:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            # Dilate edges to create a margin
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (edge_margin * 2 + 1, edge_margin * 2 + 1)
            )
            edge_zone = cv2.dilate(edges, kernel, iterations=1)
            interior_mask = (edge_zone == 0)
        else:
            interior_mask = np.ones((h, w), dtype=bool)

        # Reshape for K-means
        pixels = img.reshape(-1, 3).astype(np.float32)

        # Use interior pixels for finding cluster centers
        interior_pixels = img[interior_mask].reshape(-1, 3).astype(np.float32)

        if len(interior_pixels) < num_colors:
            interior_pixels = pixels  # Fallback

        # K-means clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 1.0)
        _, labels_interior, centers = cv2.kmeans(
            interior_pixels, num_colors, None, criteria, 5, cv2.KMEANS_PP_CENTERS
        )

        # Assign ALL pixels to nearest center
        centers_f = centers.astype(np.float32)
        # Vectorized distance computation
        dists = np.sqrt(((pixels[:, np.newaxis, :] - centers_f[np.newaxis, :, :]) ** 2).sum(axis=2))
        labels_all = dists.argmin(axis=1).reshape(h, w)

        # Filter out tiny clusters
        valid_colors = []
        label_map = {}
        total_pixels = h * w
        new_idx = 0

        for i in range(num_colors):
            cluster_size = np.sum(labels_all == i)
            fraction = cluster_size / total_pixels
            if fraction >= min_fraction:
                label_map[i] = new_idx
                valid_colors.append(tuple(centers[i].astype(np.uint8).tolist()))
                new_idx += 1

        # Remap labels, assigning filtered clusters to nearest valid color
        final_labels = np.zeros((h, w), dtype=np.int32)
        valid_centers = np.array([list(c) for c in valid_colors], dtype=np.float32)

        for orig_idx in range(num_colors):
            mask = labels_all == orig_idx
            if orig_idx in label_map:
                final_labels[mask] = label_map[orig_idx]
            else:
                # Map to nearest valid color
                center = centers[orig_idx].astype(np.float32)
                dists_to_valid = np.sqrt(((valid_centers - center) ** 2).sum(axis=1))
                nearest = dists_to_valid.argmin()
                final_labels[mask] = nearest

        # Build quantized image
        quantized = np.zeros_like(img)
        for i, color in enumerate(valid_colors):
            mask = final_labels == i
            quantized[mask] = color

        return valid_colors, final_labels, quantized

    def _trace_color_layer_potrace(self, mask, color_bgr, trace_config):
        """Trace a single color layer mask using Potrace."""
        # Potrace: True = foreground
        bitmap_data = (mask > 128)
        bmp = potrace.Bitmap(bitmap_data)

        turd_size = trace_config.get("turd_size", 3)
        alphamax = trace_config.get("corner_threshold", 1.0)
        opttolerance = trace_config.get("optimize_tolerance", 0.2)

        path = bmp.trace(
            turdsize=turd_size,
            alphamax=alphamax,
            opticurve=True,
            opttolerance=opttolerance,
        )

        # Convert BGR to hex color
        b, g, r = color_bgr
        hex_color = f"#{r:02x}{g:02x}{b:02x}"

        svg_paths = []
        path_count = 0
        point_count = 0

        for curve in path:
            path_d = self._potrace_curve_to_svg_path(curve)
            if path_d:
                svg_paths.append({"d": path_d, "color": hex_color})
                path_count += 1
                point_count += path_d.count(" ")

        return svg_paths, {"path_count": path_count, "point_count": point_count}

    def _trace_color_layer_opencv(self, mask, color_bgr, trace_config):
        """Trace a single color layer mask using OpenCV contours."""
        min_area = trace_config.get("min_contour_area", 30)
        simplify = trace_config.get("simplify_tolerance", 1.0)

        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_L1)

        b, g, r = color_bgr
        hex_color = f"#{r:02x}{g:02x}{b:02x}"

        svg_paths = []
        point_count = 0

        for contour in contours:
            if cv2.contourArea(contour) < min_area:
                continue

            epsilon = simplify * cv2.arcLength(contour, True) / 1000.0
            simplified = cv2.approxPolyDP(contour, epsilon, True)

            if len(simplified) < 3:
                continue

            if trace_config.get("smooth", True) and len(simplified) >= 4:
                path_d = self._contour_to_smooth_path(simplified)
            else:
                path_d = self._contour_to_path(simplified)

            if path_d:
                svg_paths.append({"d": path_d, "color": hex_color})
                point_count += len(simplified)

        return svg_paths, {"path_count": len(svg_paths), "point_count": point_count}

    def _build_color_svg(self, color_paths, width, height, output_config):
        """Build a multi-color SVG from colored path data."""
        background = output_config.get("background", "transparent")

        svg_parts = [
            f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">',
        ]

        if background != "transparent":
            svg_parts.append(
                f'  <rect width="{width}" height="{height}" fill="{background}"/>'
            )

        # Group paths by color for cleaner SVG
        by_color = {}
        for p in color_paths:
            color = p["color"]
            if color not in by_color:
                by_color[color] = []
            by_color[color].append(p["d"])

        for color, paths in by_color.items():
            combined = " ".join(paths)
            svg_parts.append(
                f'  <path d="{combined}" fill="{color}" stroke="none" fill-rule="evenodd"/>'
            )

        svg_parts.append("</svg>")
        return "\n".join(svg_parts)

    # ═══════════════════════════════════════════════════════════════════
    #  SHARED: Image Loading
    # ═══════════════════════════════════════════════════════════════════

    def _load_image(self, image_bytes):
        """Load image from bytes into OpenCV format, handling alpha/transparency.

        Returns:
            (img, has_alpha, content_is_light) — all call-local, never stored on self.
        """
        nparr = np.frombuffer(image_bytes, np.uint8)

        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError("Failed to decode image. Ensure it's a valid PNG or JPEG file.")

        # Check if image has an alpha channel
        if len(img.shape) == 3 and img.shape[2] == 4:
            has_alpha = True
            logger.info("Detected alpha channel (transparent image)")

            alpha = img[:, :, 3]
            bgr = img[:, :, :3]

            # Analyze content brightness
            opaque_mask = alpha > 128
            if opaque_mask.any():
                gray_full = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                opaque_brightness = gray_full[opaque_mask].mean()
                content_is_light = opaque_brightness > 170
                logger.info(
                    f"Content brightness: {opaque_brightness:.0f}/255 "
                    f"({'light' if content_is_light else 'dark'})"
                )
            else:
                content_is_light = False

            # Composite onto contrasting background
            alpha_f = alpha.astype(np.float32) / 255.0
            alpha_3ch = np.stack([alpha_f] * 3, axis=-1)
            if content_is_light:
                bg_color = 0
                logger.info("Compositing onto BLACK background (light content)")
            else:
                bg_color = 255
                logger.info("Compositing onto WHITE background (dark content)")
            solid_bg = np.full_like(bgr, bg_color, dtype=np.uint8)
            composited = (bgr.astype(np.float32) * alpha_3ch +
                         solid_bg.astype(np.float32) * (1 - alpha_3ch))
            img = composited.astype(np.uint8)
        else:
            has_alpha = False
            content_is_light = False
            if len(img.shape) == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        return img, has_alpha, content_is_light

    # ═══════════════════════════════════════════════════════════════════
    #  SHARED: Preprocessing
    # ═══════════════════════════════════════════════════════════════════

    def _preprocess(self, img, config):
        """Apply preprocessing pipeline (for B&W mode)."""
        result = img.copy()

        # Convert to grayscale
        if len(result.shape) == 3:
            result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)

        # Denoise
        if config.get("denoise", False):
            strength = config.get("denoise_strength", 10)
            result = cv2.fastNlMeansDenoising(
                result, None, h=strength, templateWindowSize=7, searchWindowSize=21
            )

        # Contrast enhancement (CLAHE)
        if config.get("contrast_enhance", False):
            clip_limit = config.get("contrast_clip_limit", 3.0)
            grid_size = config.get("contrast_grid_size", 8)
            clahe = cv2.createCLAHE(
                clipLimit=clip_limit,
                tileGridSize=(grid_size, grid_size)
            )
            result = clahe.apply(result)

        # Sharpen (Unsharp Mask)
        if config.get("sharpen", False):
            amount = config.get("sharpen_amount", 1.5)
            blurred = cv2.GaussianBlur(result, (0, 0), 3)
            result = cv2.addWeighted(result, 1.0 + amount, blurred, -amount, 0)

        # Morphological operations
        morph = config.get("morphology", "none")
        if morph != "none":
            kernel_size = config.get("morphology_kernel", 2)
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
            )
            if morph == "close":
                result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, kernel)
            elif morph == "open":
                result = cv2.morphologyEx(result, cv2.MORPH_OPEN, kernel)
            elif morph == "dilate":
                result = cv2.dilate(result, kernel, iterations=1)
            elif morph == "erode":
                result = cv2.erode(result, kernel, iterations=1)

        return result

    # ═══════════════════════════════════════════════════════════════════
    #  SHARED: Thresholding
    # ═══════════════════════════════════════════════════════════════════

    def _threshold(self, img, config):
        """Apply thresholding to create binary image."""
        method = config.get("method", "otsu")

        if method == "otsu":
            _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif method == "simple":
            value = config.get("value", 128)
            _, binary = cv2.threshold(img, value, 255, cv2.THRESH_BINARY)
        elif method == "adaptive_mean":
            block_size = config.get("adaptive_block_size", 15)
            c = config.get("adaptive_c", 5)
            if block_size % 2 == 0:
                block_size += 1
            binary = cv2.adaptiveThreshold(
                img, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY, block_size, c
            )
        elif method == "adaptive_gaussian":
            block_size = config.get("adaptive_block_size", 15)
            c = config.get("adaptive_c", 5)
            if block_size % 2 == 0:
                block_size += 1
            binary = cv2.adaptiveThreshold(
                img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, block_size, c
            )
        else:
            raise ValueError(f"Unknown threshold method: {method}")

        return binary

    # ═══════════════════════════════════════════════════════════════════
    #  SHARED: Potrace Tracing (B&W)
    # ═══════════════════════════════════════════════════════════════════

    def _trace_potrace(self, binary, width, height, trace_config, output_config):
        """Trace binary image using Potrace for high-quality B&W vectorization."""
        bitmap_data = (binary < 128)
        bmp = potrace.Bitmap(bitmap_data)

        turd_size = trace_config.get("turd_size", 2)
        alphamax = trace_config.get("corner_threshold", 1.0)
        opttolerance = trace_config.get("optimize_tolerance", 0.2)

        path = bmp.trace(
            turdsize=turd_size,
            alphamax=alphamax,
            opticurve=True,
            opttolerance=opttolerance,
        )

        svg_paths = []
        path_count = 0
        point_count = 0

        for curve in path:
            path_d = self._potrace_curve_to_svg_path(curve)
            if path_d:
                svg_paths.append(path_d)
                path_count += 1
                point_count += path_d.count(" ")

        svg_content = self._build_svg(svg_paths, width, height, output_config)

        return svg_content, {"path_count": path_count, "point_count": point_count}

    def _potrace_curve_to_svg_path(self, curve):
        """Convert a potrace curve to an SVG path data string."""
        parts = []
        start = curve.start_point
        parts.append(f"M {start.x:.2f},{start.y:.2f}")

        for segment in curve.segments:
            if segment.is_corner:
                c = segment.c
                ep = segment.end_point
                parts.append(f"L {c.x:.2f},{c.y:.2f}")
                parts.append(f"L {ep.x:.2f},{ep.y:.2f}")
            else:
                c1 = segment.c1
                c2 = segment.c2
                ep = segment.end_point
                parts.append(
                    f"C {c1.x:.2f},{c1.y:.2f} {c2.x:.2f},{c2.y:.2f} {ep.x:.2f},{ep.y:.2f}"
                )

        parts.append("Z")
        return " ".join(parts)

    # ═══════════════════════════════════════════════════════════════════
    #  SHARED: OpenCV Contour Tracing (Fallback)
    # ═══════════════════════════════════════════════════════════════════

    def _trace_opencv(self, binary, width, height, trace_config, output_config):
        """Trace binary image using OpenCV contours as fallback."""
        min_area = trace_config.get("min_contour_area", 50)
        simplify = trace_config.get("simplify_tolerance", 1.5)

        contours, hierarchy = cv2.findContours(
            cv2.bitwise_not(binary),
            cv2.RETR_TREE,
            cv2.CHAIN_APPROX_TC89_L1
        )

        if hierarchy is None:
            return self._build_svg([], width, height, output_config), {
                "path_count": 0, "point_count": 0
            }

        hierarchy = hierarchy[0]
        svg_paths = []
        point_count = 0

        for i, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            epsilon = simplify * cv2.arcLength(contour, True) / 1000.0
            simplified = cv2.approxPolyDP(contour, epsilon, True)

            if len(simplified) < 3:
                continue

            if trace_config.get("smooth", True) and len(simplified) >= 4:
                path_d = self._contour_to_smooth_path(simplified)
            else:
                path_d = self._contour_to_path(simplified)

            if path_d:
                svg_paths.append(path_d)
                point_count += len(simplified)

        svg_content = self._build_svg(svg_paths, width, height, output_config)

        return svg_content, {"path_count": len(svg_paths), "point_count": point_count}

    def _contour_to_path(self, contour):
        """Convert an OpenCV contour to a simple SVG path (lines only)."""
        points = contour.reshape(-1, 2)
        if len(points) < 3:
            return None

        parts = [f"M {points[0][0]:.1f},{points[0][1]:.1f}"]
        for p in points[1:]:
            parts.append(f"L {p[0]:.1f},{p[1]:.1f}")
        parts.append("Z")

        return " ".join(parts)

    def _contour_to_smooth_path(self, contour):
        """Convert an OpenCV contour to a smooth SVG path using cubic beziers."""
        points = contour.reshape(-1, 2).astype(float)
        n = len(points)
        if n < 3:
            return None

        parts = [f"M {points[0][0]:.2f},{points[0][1]:.2f}"]

        for i in range(n):
            p0 = points[(i - 1) % n]
            p1 = points[i]
            p2 = points[(i + 1) % n]
            p3 = points[(i + 2) % n]

            tension = 0.35
            c1x = p1[0] + (p2[0] - p0[0]) * tension
            c1y = p1[1] + (p2[1] - p0[1]) * tension
            c2x = p2[0] - (p3[0] - p1[0]) * tension
            c2y = p2[1] - (p3[1] - p1[1]) * tension

            parts.append(
                f"C {c1x:.2f},{c1y:.2f} {c2x:.2f},{c2y:.2f} {p2[0]:.2f},{p2[1]:.2f}"
            )

        parts.append("Z")
        return " ".join(parts)

    # ═══════════════════════════════════════════════════════════════════
    #  SHARED: SVG Building (B&W)
    # ═══════════════════════════════════════════════════════════════════

    def _build_svg(self, paths, width, height, output_config):
        """Build complete SVG document from B&W path data."""
        fill_mode = output_config.get("fill_mode", "fill")
        fill_color = output_config.get("fill_color", "#000000")
        stroke_color = output_config.get("stroke_color", "#000000")
        stroke_width = output_config.get("stroke_width", 0.5)
        background = output_config.get("background", "transparent")

        svg_parts = [
            f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">',
        ]

        if background != "transparent":
            svg_parts.append(
                f'  <rect width="{width}" height="{height}" fill="{background}"/>'
            )

        if fill_mode == "fill":
            style = f'fill="{fill_color}" stroke="none"'
        elif fill_mode == "stroke":
            style = f'fill="none" stroke="{stroke_color}" stroke-width="{stroke_width}"'
        elif fill_mode == "both":
            style = (
                f'fill="{fill_color}" '
                f'stroke="{stroke_color}" stroke-width="{stroke_width}"'
            )
        else:
            style = f'fill="{fill_color}" stroke="none"'

        if paths:
            combined = " ".join(paths)
            svg_parts.append(
                f'  <path d="{combined}" {style} fill-rule="evenodd"/>'
            )

        svg_parts.append("</svg>")
        return "\n".join(svg_parts)

    # ═══════════════════════════════════════════════════════════════════
    #  SHARED: Preview & Config
    # ═══════════════════════════════════════════════════════════════════

    def _generate_preview(self, binary):
        """Generate a base64-encoded PNG preview."""
        import base64
        pil_img = Image.fromarray(binary)

        max_dim = 1200
        if pil_img.width > max_dim or pil_img.height > max_dim:
            pil_img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buf = io.BytesIO()
        pil_img.save(buf, format="PNG", optimize=True)
        buf.seek(0)

        return base64.b64encode(buf.read()).decode("utf-8")

    def _merge_config(self, preset, overrides):
        """Deep merge custom overrides into preset config."""
        import copy
        config = copy.deepcopy(preset)
        if not overrides:
            return config

        for section_key, section_val in overrides.items():
            if section_key in config and isinstance(section_val, dict):
                config[section_key].update(section_val)
            else:
                config[section_key] = section_val

        return config

    def get_preview(self, image_bytes, preset, custom_overrides=None):
        """Generate only the B&W threshold preview (faster than full vectorization)."""
        config = self._merge_config(preset, custom_overrides)
        img, has_alpha, content_is_light = self._load_image(image_bytes)
        processed = self._preprocess(img, config["preprocessing"])
        binary = self._threshold(processed, config["threshold"])

        invert_setting = config["preprocessing"].get("invert", False)
        should_invert = False
        if invert_setting == "auto":
            should_invert = has_alpha and content_is_light
        elif invert_setting:
            should_invert = True

        if should_invert:
            binary = cv2.bitwise_not(binary)

        return self._generate_preview(binary)


# Singleton engine instance
engine = VectorizerEngine()
