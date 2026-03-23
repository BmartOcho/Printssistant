"""
Vectorizer Engine - Dual-engine image-to-vector conversion.

Primary engine: VTracer (all color + general B&W)
Secondary engine: Potrace (high-precision B&W for logos, text, laser/vinyl)
"""

import base64
import copy
import io
import logging
import re
import time
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import vtracer
from PIL import Image

logger = logging.getLogger(__name__)

# Potrace is optional — only needed for high-precision B&W mode
try:
    import potrace
    HAS_POTRACE = True
    logger.info("Potrace available — high-precision B&W mode enabled")
except ImportError:
    HAS_POTRACE = False
    logger.warning("Potrace not available — high-precision B&W mode disabled, VTracer will be used for all modes")

# cairosvg is optional — used for SVG preview rendering
try:
    import cairosvg
    HAS_CAIROSVG = True
except (ImportError, OSError):
    HAS_CAIROSVG = False
    logger.warning("cairosvg not available — previews will use source image instead of rendered SVG")


class VectorizerEngine:
    """Dual-engine vectorizer: VTracer (primary) + Potrace (precision B&W)."""

    def vectorize(self, image_bytes, preset, custom_overrides=None, test_mode=False):
        """
        Vectorize a raster image to SVG.

        Args:
            image_bytes: Raw image file bytes (PNG/JPEG)
            preset: Preset configuration dict
            custom_overrides: Optional parameter overrides
            test_mode: If True, return detailed diagnostics (processing times per engine,
                      engine selection info, color palette, transparency decisions)

        Returns:
            dict with 'svg', 'preview_bw' (base64 PNG), 'stats', and optionally 'diagnostics'
        """
        config = self._merge_config(preset, custom_overrides)
        start_time = time.time()
        stages = ["image_load", "analysis", "engine_execution", "svg_validation", "preview_generation"]
        current_stage = "image_load"

        try:
            # 1. Load and prepare image (handle alpha/transparency)
            png_bytes, has_alpha, content_is_light, width, height = self._prepare_image(
                image_bytes, config
            )
            current_stage = "analysis"

            # 2. Perform image analysis for diagnostics
            image_analysis = {
                "has_alpha": has_alpha,
                "content_is_light": content_is_light,
                "width": width,
                "height": height,
                "detected_mode_suggestion": self._suggest_mode_from_image(
                    png_bytes, has_alpha, content_is_light
                ),
            }

            # 3. Route to engine with fallback chain
            current_stage = "engine_execution"
            vtracer_time = None
            potrace_time = None
            engine_name = None
            svg_content = None

            # Try VTracer first (primary engine)
            vtracer_start = time.time()
            try:
                svg_content = self._run_vtracer(png_bytes, config)
                vtracer_time = round(time.time() - vtracer_start, 3)
                engine_name = "vtracer"

                # Validate SVG output
                if not svg_content or not self._is_valid_svg(svg_content):
                    logger.warning("VTracer returned invalid SVG, attempting fallback to Potrace")
                    svg_content = None
            except Exception as e:
                logger.error(f"VTracer failed: {str(e)}", exc_info=True)
                svg_content = None

            # Fallback to Potrace if VTracer failed and high-precision is desired or required
            if svg_content is None and HAS_POTRACE:
                potrace_start = time.time()
                try:
                    svg_content = self._run_potrace(png_bytes, config, width, height)
                    potrace_time = round(time.time() - potrace_start, 3)
                    engine_name = "potrace"

                    if not self._is_valid_svg(svg_content):
                        logger.error("Potrace also returned invalid SVG")
                        svg_content = None
                except Exception as e:
                    logger.error(f"Potrace fallback failed: {str(e)}", exc_info=True)
                    svg_content = None

            # If both engines failed, raise user-friendly error
            if svg_content is None:
                error_msg = self._build_engine_error_message()
                raise RuntimeError(error_msg)

            current_stage = "svg_validation"

            # 4. Extract stats from SVG
            stats = self._extract_stats(svg_content)

            # 5. Generate warnings and recommendations
            warnings = self._generate_warnings(width, height, config, image_analysis)
            recommendations = self._generate_recommendations(
                image_analysis, config, stats
            )

            current_stage = "preview_generation"

            # 6. Generate preview
            preview = self._generate_preview(svg_content, png_bytes)

            # 7. Assemble result
            elapsed = time.time() - start_time
            stats.update({
                "processing_time": round(elapsed, 2),
                "image_width": width,
                "image_height": height,
                "engine": engine_name,
                "has_transparency": has_alpha,
                "auto_inverted": content_is_light and config.get("alpha_handling", {}).get("invert") == "auto",
                "mode": config.get("mode", "bw"),
                "warnings": warnings,
                "recommendations": recommendations,
                "processing_info": {
                    "stages": stages,
                    "current_stage": "complete",
                    "total_time_seconds": round(elapsed, 2),
                },
            })

            result = {"svg": svg_content, "preview_bw": preview, "stats": stats}

            # 8. Add detailed diagnostics if test_mode is enabled
            if test_mode:
                color_palette = self._extract_color_palette(svg_content) if engine_name == "vtracer" else []
                transparency_decision = self._get_transparency_handling_decision(has_alpha, content_is_light, config)

                result["diagnostics"] = {
                    "processing_time_vtracer": vtracer_time,
                    "processing_time_potrace": potrace_time,
                    "engine_actually_used": engine_name,
                    "color_palette_detected": color_palette,
                    "transparency_handling_decision": transparency_decision,
                    "image_analysis": image_analysis,
                }

            return result

        except Exception as e:
            logger.error(f"Vectorization failed at stage '{current_stage}': {str(e)}", exc_info=True)
            error_response = {
                "svg": None,
                "preview_bw": None,
                "stats": {
                    "error": str(e),
                    "processing_stage_failed": current_stage,
                    "processing_info": {
                        "stages": stages,
                        "current_stage": current_stage,
                    },
                }
            }
            if test_mode:
                error_response["diagnostics"] = {
                    "processing_time_vtracer": vtracer_time,
                    "processing_time_potrace": potrace_time,
                    "engine_actually_used": engine_name,
                }
            return error_response

    # ═══════════════════════════════════════════════════════════════════
    #  Image Preparation
    # ═══════════════════════════════════════════════════════════════════

    def _prepare_image(self, image_bytes, config):
        """Load image, handle alpha compositing, return PNG bytes for engines.

        Returns:
            (png_bytes, has_alpha, content_is_light, width, height)
        """
        img, has_alpha, content_is_light = self._load_image(image_bytes)
        height, width = img.shape[:2]

        # Re-encode composited image to PNG bytes for engine consumption
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        return png_bytes, has_alpha, content_is_light, width, height

    def _load_image(self, image_bytes):
        """Load image from bytes, handling alpha/transparency.

        Returns:
            (img_bgr, has_alpha, content_is_light)
        """
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError("Failed to decode image. Ensure it's a valid PNG or JPEG file.")

        if len(img.shape) == 3 and img.shape[2] == 4:
            has_alpha = True
            alpha = img[:, :, 3]
            bgr = img[:, :, :3]

            # Detect content brightness
            opaque_mask = alpha > 128
            if opaque_mask.any():
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                content_is_light = gray[opaque_mask].mean() > 170
            else:
                content_is_light = False

            # Composite onto contrasting background
            alpha_f = alpha.astype(np.float32) / 255.0
            alpha_3ch = np.stack([alpha_f] * 3, axis=-1)
            bg_color = 0 if content_is_light else 255
            solid_bg = np.full_like(bgr, bg_color, dtype=np.uint8)
            composited = (
                bgr.astype(np.float32) * alpha_3ch
                + solid_bg.astype(np.float32) * (1 - alpha_3ch)
            )
            img = composited.astype(np.uint8)
        else:
            has_alpha = False
            content_is_light = False
            if len(img.shape) == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        return img, has_alpha, content_is_light

    # ═══════════════════════════════════════════════════════════════════
    #  VTracer Engine (Primary)
    # ═══════════════════════════════════════════════════════════════════

    def _run_vtracer(self, png_bytes, config):
        """Run VTracer on PNG bytes with parameters from config."""
        params = config.get("vtracer", {})

        svg_content = vtracer.convert_raw_image_to_svg(
            png_bytes,
            img_format="png",
            colormode=params.get("colormode", "color"),
            hierarchical=params.get("hierarchical", "stacked"),
            mode=params.get("mode", "spline"),
            filter_speckle=params.get("filter_speckle", 4),
            color_precision=params.get("color_precision", 6),
            layer_difference=params.get("layer_difference", 16),
            corner_threshold=params.get("corner_threshold", 60),
            length_threshold=params.get("length_threshold", 4.0),
            max_iterations=params.get("max_iterations", 10),
            splice_threshold=params.get("splice_threshold", 45),
            path_precision=params.get("path_precision", 8),
        )

        return svg_content

    # ═══════════════════════════════════════════════════════════════════
    #  Potrace Engine (High-Precision B&W)
    # ═══════════════════════════════════════════════════════════════════

    def _run_potrace(self, png_bytes, config, width, height):
        """Minimal Potrace pipeline: grayscale → denoise (optional) → threshold → trace."""
        # Decode PNG to grayscale
        nparr = np.frombuffer(png_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

        # Optional light denoise (conservative)
        preprocess = config.get("preprocessing", {})
        if preprocess.get("denoise", False):
            strength = preprocess.get("denoise_strength", 5)
            img = cv2.fastNlMeansDenoising(img, None, h=strength, templateWindowSize=7, searchWindowSize=21)

        # Simple Otsu threshold — no CLAHE, no morphology
        _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Trace with Potrace
        bitmap_data = binary < 128  # Potrace: True = foreground
        bmp = potrace.Bitmap(bitmap_data)

        potrace_config = config.get("potrace", {})
        path = bmp.trace(
            turdsize=potrace_config.get("turd_size", 5),
            alphamax=potrace_config.get("alphamax", 1.0),
            opticurve=True,
            opttolerance=potrace_config.get("opttolerance", 0.5),
        )

        # Build SVG
        svg_paths = []
        for curve in path:
            path_d = self._potrace_curve_to_svg_d(curve)
            if path_d:
                svg_paths.append(path_d)

        combined = " ".join(svg_paths)
        svg_content = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">\n'
            f'  <path d="{combined}" fill="#000000" stroke="none" fill-rule="evenodd"/>\n'
            f'</svg>'
        )

        return svg_content

    def _potrace_curve_to_svg_d(self, curve):
        """Convert a Potrace curve to an SVG path data string."""
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
    #  Validation & Error Handling
    # ═══════════════════════════════════════════════════════════════════

    def _is_valid_svg(self, svg_string):
        """
        Validate that SVG content is well-formed and contains path data.

        Args:
            svg_string: SVG content as string

        Returns:
            True if SVG is valid, False otherwise
        """
        if not svg_string or not isinstance(svg_string, str):
            return False

        try:
            root = ET.fromstring(svg_string)
            # Check for paths or other drawing elements
            ns = {"svg": "http://www.w3.org/2000/svg"}
            paths = (
                root.findall(".//svg:path", ns)
                or root.findall(".//{http://www.w3.org/2000/svg}path")
                or root.findall(".//path")
            )
            return len(paths) > 0
        except ET.ParseError:
            return False

    def _build_engine_error_message(self):
        """
        Build a user-friendly error message with installation instructions.

        Returns:
            str: Formatted error message
        """
        msg = "Vectorization failed: Both VTracer and fallback engines encountered errors.\n"
        msg += "To resolve this:\n"
        msg += "1. VTracer should be installed. Check: `pip list | grep vtracer`\n"

        if not HAS_POTRACE:
            msg += "2. Potrace is not installed. Install it: `pip install pypotrace`\n"
        else:
            msg += "2. Potrace is available but also failed. Check image format and try another preset.\n"

        msg += "3. Ensure your image is a valid PNG or JPEG file.\n"
        msg += "4. If this persists, contact support with your image file."

        return msg

    # ═══════════════════════════════════════════════════════════════════
    #  Image Analysis & Diagnostics
    # ═══════════════════════════════════════════════════════════════════

    def _suggest_mode_from_image(self, png_bytes, has_alpha, content_is_light):
        """
        Analyze image and suggest the most appropriate vectorization mode.

        Args:
            png_bytes: Image as PNG bytes
            has_alpha: Whether image has alpha channel
            content_is_light: Whether opaque content is predominantly light

        Returns:
            str: Suggested mode ("bw", "color", or "high_precision_bw")
        """
        try:
            nparr = np.frombuffer(png_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return "bw"

            # Convert to HSV for saturation analysis
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            saturation = hsv[:, :, 1]

            # Low saturation = mostly B&W
            avg_saturation = saturation.mean()
            has_rich_colors = avg_saturation > 50  # Arbitrary but reasonable threshold

            # For transparent images with low saturation, high_precision_bw is ideal
            if has_alpha and not has_rich_colors:
                return "high_precision_bw"

            # For color-rich images, suggest full_color
            if has_rich_colors:
                return "color"

            # Default to B&W for low-saturation images
            return "bw"

        except Exception as e:
            logger.warning(f"Image analysis failed: {str(e)}, defaulting to 'bw'")
            return "bw"

    def _extract_color_palette(self, svg_string):
        """
        Extract detected color palette from SVG (relevant for color mode).

        Args:
            svg_string: SVG content as string

        Returns:
            list: Array of hex color strings (e.g., ["#FF0000", "#00FF00"])
        """
        colors = set()
        try:
            root = ET.fromstring(svg_string)
            ns = {"svg": "http://www.w3.org/2000/svg"}

            # Find all elements with fill or stroke attributes
            for elem in root.iter():
                fill = elem.get("fill", "")
                stroke = elem.get("stroke", "")

                for color_attr in [fill, stroke]:
                    if color_attr and color_attr not in ("none", "black", "white"):
                        # Try to normalize to hex format
                        if color_attr.startswith("#"):
                            colors.add(color_attr.upper())

            return sorted(list(colors))
        except Exception as e:
            logger.warning(f"Color palette extraction failed: {str(e)}")
            return []

    def _get_transparency_handling_decision(self, has_alpha, content_is_light, config):
        """
        Describe how transparency was handled in this vectorization.

        Args:
            has_alpha: Whether original image had alpha channel
            content_is_light: Whether opaque content is predominantly light
            config: Configuration dict

        Returns:
            str: Decision description
        """
        if not has_alpha:
            return "none"

        invert_mode = config.get("alpha_handling", {}).get("invert", False)

        if invert_mode == "auto":
            if content_is_light:
                return "composited_on_dark"
            else:
                return "composited_on_light"
        elif invert_mode:
            return "auto_inverted"
        else:
            return "composited_on_light"

    # ═══════════════════════════════════════════════════════════════════
    #  Warnings & Recommendations
    # ═══════════════════════════════════════════════════════════════════

    def _generate_warnings(self, width, height, config, image_analysis):
        """
        Generate user-facing warnings about image or processing.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            config: Configuration dict
            image_analysis: Image analysis results

        Returns:
            list: Array of warning strings
        """
        warnings = []

        # Large image warning
        total_pixels = width * height
        if total_pixels > 4_000_000:  # >2000x2000
            warnings.append(
                f"Image is very large ({width}x{height}), processing may be slow"
            )

        # High-precision mode warning
        if config.get("high_precision_bw", False):
            warnings.append(
                "High-precision B&W mode will spend extra time on edge optimization"
            )

        # Transparent image warning
        if image_analysis.get("has_alpha"):
            warnings.append(
                "Image has transparency; it will be composited onto a solid background"
            )

        return warnings

    def _generate_recommendations(self, image_analysis, config, stats):
        """
        Generate preset recommendations based on detected image characteristics.

        Args:
            image_analysis: Image analysis results
            config: Current configuration dict
            stats: Vectorization stats

        Returns:
            dict: Recommendations including suggested presets and reasoning
        """
        recommendations = {
            "current_mode": config.get("mode", "unknown"),
            "suggested_modes": [],
            "reason": "",
        }

        # Use the suggest_preset function from presets module
        try:
            from presets import suggest_preset

            suggestions = suggest_preset(image_analysis)
            if suggestions:
                recommendations["suggested_modes"] = suggestions
                recommendations["reason"] = self._build_recommendation_reason(suggestions, image_analysis)
        except (ImportError, Exception) as e:
            logger.warning(f"Could not generate preset recommendations: {str(e)}")

        return recommendations

    def _build_recommendation_reason(self, suggestions, image_analysis):
        """Build a human-readable explanation for preset suggestions."""
        reasons = []

        if "high_precision_bw" in suggestions:
            reasons.append("Image detected as sharp B&W content (optimal for precision)")
        if "laser_bw" in suggestions:
            reasons.append("Image suitable for general B&W engraving")
        if "full_color" in suggestions:
            reasons.append("Image detected as color-rich")

        if image_analysis.get("has_alpha"):
            reasons.append("Transparent background detected")

        return "; ".join(reasons) if reasons else "See suggested presets"

    # ═══════════════════════════════════════════════════════════════════
    #  Stats & Preview
    # ═══════════════════════════════════════════════════════════════════

    def _extract_stats(self, svg_string):
        """Parse SVG to extract path count, point count, and color count."""
        try:
            root = ET.fromstring(svg_string)
            ns = {"svg": "http://www.w3.org/2000/svg"}

            paths = root.findall(".//svg:path", ns) or root.findall(".//{http://www.w3.org/2000/svg}path")
            if not paths:
                # Try without namespace (VTracer may omit namespace)
                paths = root.findall(".//path")

            path_count = len(paths)
            point_count = 0
            colors = set()

            for p in paths:
                d = p.get("d", "")
                # Count path commands as proxy for point count
                point_count += len(re.findall(r"[MLCQASZ]", d, re.IGNORECASE))
                fill = p.get("fill", "")
                if fill and fill != "none":
                    colors.add(fill)

            return {
                "path_count": path_count,
                "point_count": point_count,
                "color_count": len(colors),
            }
        except ET.ParseError:
            logger.warning("Failed to parse SVG for stats extraction")
            return {"path_count": 0, "point_count": 0, "color_count": 0}

    def _generate_preview(self, svg_string, fallback_png_bytes):
        """Generate a base64 PNG preview of the SVG output."""
        if HAS_CAIROSVG:
            try:
                png_data = cairosvg.svg2png(
                    bytestring=svg_string.encode("utf-8"),
                    output_width=1200,
                )
                return base64.b64encode(png_data).decode("utf-8")
            except Exception:
                logger.warning("cairosvg rendering failed, falling back to source image")

        # Fallback: use the composited source image as preview
        pil_img = Image.open(io.BytesIO(fallback_png_bytes))
        max_dim = 1200
        if pil_img.width > max_dim or pil_img.height > max_dim:
            pil_img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # ═══════════════════════════════════════════════════════════════════
    #  Config
    # ═══════════════════════════════════════════════════════════════════

    def _merge_config(self, preset, overrides):
        """Deep merge custom overrides into preset config."""
        config = copy.deepcopy(preset)
        if not overrides:
            return config

        for section_key, section_val in overrides.items():
            if section_key in config and isinstance(section_val, dict):
                config[section_key].update(section_val)
            else:
                config[section_key] = section_val

        return config


# Singleton engine instance
engine = VectorizerEngine()
