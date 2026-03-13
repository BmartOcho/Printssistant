import difflib
import logging
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pantone Solid Coated → CMYK lookup (values are 0–100 per channel)
# ---------------------------------------------------------------------------
PANTONE_CMYK = {
    # Reds and oranges
    "485 C":          (0,   95,  100, 0),
    "032 C":          (0,   90,  86,  0),
    "021 C":          (0,   52,  100, 0),
    "1505 C":         (0,   50,  100, 0),
    "WARM RED C":     (0,   75,  95,  0),
    "179 C":          (0,   82,  79,  0),
    "1795 C":         (0,   91,  87,  0),
    "1815 C":         (22,  100, 97,  14),
    "186 C":          (7,   100, 82,  26),
    "1865 C":         (0,   89,  76,  0),
    "1875 C":         (0,   79,  73,  0),
    "193 C":          (0,   92,  57,  0),
    "199 C":          (0,   100, 77,  6),
    "200 C":          (8,   100, 73,  28),
    # Magentas and pinks
    "RHODAMINE RED C":(0,   100, 0,   0),
    "206 C":          (0,   100, 33,  2),
    "212 C":          (0,   74,  13,  0),
    "219 C":          (0,   97,  25,  0),
    "226 C":          (0,   92,  0,   0),
    "232 C":          (0,   60,  0,   0),
    "238 C":          (0,   49,  0,   0),
    # Purples and violets
    "VIOLET C":       (64,  84,  0,   0),
    "2607 C":         (85,  97,  0,   0),
    "265 C":          (55,  67,  0,   0),
    "266 C":          (77,  86,  0,   0),
    "267 C":          (90,  100, 0,   0),
    "268 C":          (78,  93,  0,   22),
    "2685 C":         (93,  100, 0,   4),
    # Blues
    "REFLEX BLUE C":  (100, 72,  0,   18),
    "PROCESS BLUE C": (100, 4,   0,   0),
    "286 C":          (100, 75,  0,   2),
    "287 C":          (100, 64,  0,   16),
    "293 C":          (100, 55,  0,   15),
    "294 C":          (100, 53,  0,   36),
    "300 C":          (91,  53,  0,   0),
    "301 C":          (100, 41,  0,   22),
    "072 C":          (100, 78,  0,   9),
    "279 C":          (64,  25,  0,   0),
    "2925 C":         (80,  12,  0,   0),
    "306 C":          (74,  0,   4,   0),
    "3005 C":         (100, 30,  0,   0),
    "3015 C":         (100, 26,  0,   16),
    # Cyans and teals
    "CYAN C":         (100, 0,   0,   0),
    "313 C":          (80,  3,   14,  0),
    "3145 C":         (100, 1,   33,  13),
    "3155 C":         (100, 6,   32,  0),
    "320 C":          (94,  0,   32,  0),
    "3255 C":         (55,  0,   22,  0),
    "326 C":          (72,  0,   28,  0),
    "327 C":          (100, 0,   43,  21),
    # Greens
    "GREEN C":        (100, 0,   100, 0),
    "348 C":          (100, 0,   91,  42),
    "349 C":          (100, 0,   78,  56),
    "355 C":          (93,  0,   100, 0),
    "362 C":          (68,  0,   100, 15),
    "369 C":          (57,  0,   100, 0),
    "375 C":          (38,  0,   100, 0),
    "376 C":          (39,  0,   98,  0),
    "382 C":          (20,  0,   100, 0),
    "390 C":          (12,  0,   100, 9),
    # Yellows and golds
    "YELLOW C":       (0,   0,   100, 0),
    "012 C":          (0,   6,   100, 0),
    "116 C":          (0,   18,  100, 0),
    "123 C":          (0,   27,  100, 0),
    "130 C":          (0,   37,  100, 0),
    "137 C":          (0,   37,  89,  0),
    "143 C":          (0,   30,  78,  0),
    "144 C":          (0,   53,  97,  0),
    "150 C":          (0,   47,  95,  0),
    "1235 C":         (0,   30,  100, 0),
    "1245 C":         (0,   31,  100, 6),
    "1255 C":         (0,   37,  100, 7),
    # Browns and earth tones
    "470 C":          (0,   60,  85,  0),
    "476 C":          (38,  59,  72,  42),
    "483 C":          (29,  73,  75,  42),
    "4975 C":         (42,  77,  77,  68),
    "4625 C":         (12,  68,  88,  57),
    "7526 C":         (12,  42,  58,  18),
    "7527 C":         (3,   14,  21,  5),
    # Blacks and grays
    "BLACK C":        (0,   0,   0,   100),
    "BLACK 2 C":      (0,   0,   0,   100),
    "COOL GRAY 1 C":  (0,   0,   0,   12),
    "COOL GRAY 3 C":  (0,   0,   0,   20),
    "COOL GRAY 5 C":  (0,   0,   0,   31),
    "COOL GRAY 7 C":  (0,   0,   0,   43),
    "COOL GRAY 9 C":  (0,   0,   0,   56),
    "COOL GRAY 11 C": (0,   0,   0,   72),
    "WARM GRAY 1 C":  (2,   2,   5,   7),
    "WARM GRAY 3 C":  (3,   4,   8,   14),
    "WARM GRAY 6 C":  (8,   9,   14,  30),
    "WARM GRAY 9 C":  (15,  16,  21,  50),
    "WARM GRAY 11 C": (22,  22,  30,  65),
    # Special / metallic process approximations
    "877 C":          (25,  18,  17,  53),
    "871 C":          (20,  30,  65,  20),
    # White
    "WHITE":          (0,   0,   0,   0),
}


# ---------------------------------------------------------------------------
# Color conversion helpers
# ---------------------------------------------------------------------------

def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def hex_to_rgb(hex_str: str) -> tuple:
    """Parse '#FF5733' or 'FF5733' → (255, 87, 51)."""
    h = hex_str.strip().lstrip('#')
    if len(h) != 6:
        raise ValueError(f"Invalid hex color '{hex_str}' — expected 6 hex digits (e.g. #FF5733)")
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f"Invalid hex color '{hex_str}' — contains non-hex characters")


def rgb_to_cmyk(r: int, g: int, b: int) -> tuple:
    """Standard RGB (0–255) → CMYK (0–100 each)."""
    r = _clamp(r, 0, 255)
    g = _clamp(g, 0, 255)
    b = _clamp(b, 0, 255)
    r_n, g_n, b_n = r / 255.0, g / 255.0, b / 255.0
    k = 1.0 - max(r_n, g_n, b_n)
    if k >= 1.0:
        return (0, 0, 0, 100)
    denom = 1.0 - k
    c = (1.0 - r_n - k) / denom
    m = (1.0 - g_n - k) / denom
    y = (1.0 - b_n - k) / denom
    return (round(c * 100), round(m * 100), round(y * 100), round(k * 100))


def pantone_to_cmyk(pantone_str: str) -> tuple:
    """Look up a Pantone color name → CMYK (0–100 each)."""
    key = pantone_str.strip().upper()

    # Exact match
    if key in PANTONE_CMYK:
        return PANTONE_CMYK[key]

    # Try appending " C" (user typed "485" instead of "485 C")
    key_c = key + " C"
    if key_c in PANTONE_CMYK:
        return PANTONE_CMYK[key_c]

    # Fuzzy fallback
    matches = difflib.get_close_matches(key, PANTONE_CMYK.keys(), n=1, cutoff=0.5)
    if matches:
        logger.warning(f"Pantone '{pantone_str}' not found — using closest match '{matches[0]}'")
        return PANTONE_CMYK[matches[0]]

    raise ValueError(
        f"Pantone '{pantone_str}' not found in lookup table and no close match available. "
        "Try formats like '485 C', 'Reflex Blue C', or 'Cool Gray 5 C'."
    )


def lerp_cmyk(base: tuple, goal: tuple, t: float) -> tuple:
    """Linear interpolation between two CMYK tuples. Values clamped to 0–100."""
    return tuple(_clamp(round(base[i] + t * (goal[i] - base[i])), 0, 100) for i in range(4))


# ---------------------------------------------------------------------------
# Swatch variation algorithm
# ---------------------------------------------------------------------------

def build_swatches(base: tuple, goal: tuple) -> list:
    """
    Generate 9 swatch dicts for a 3×3 grid.
    Center [1,1] is the original base. The 8 surrounding swatches
    explore different paths toward the goal CMYK.
    """
    bc, bm, by, bk = base
    gc, gm, gy, gk = goal

    return [
        # Row 0
        {"cmyk": lerp_cmyk(base, goal, 0.25),   "label": "25% Shift", "row": 0, "col": 0},
        {"cmyk": (gc, bm, by, bk),               "label": "C Push",    "row": 0, "col": 1},
        {"cmyk": (bc, gm, by, bk),               "label": "M Push",    "row": 0, "col": 2},
        # Row 1
        {"cmyk": lerp_cmyk(base, goal, 0.50),   "label": "50% Shift", "row": 1, "col": 0},
        {"cmyk": base,                            "label": "Original",  "row": 1, "col": 1},
        {"cmyk": lerp_cmyk(base, goal, 0.75),   "label": "75% Shift", "row": 1, "col": 2},
        # Row 2
        {"cmyk": (bc, bm, gy, bk),               "label": "Y Push",    "row": 2, "col": 0},
        {"cmyk": goal,                            "label": "Goal",      "row": 2, "col": 1},
        {"cmyk": (gc, gm, gy, _clamp(gk - 10, 0, 100)), "label": "Goal +", "row": 2, "col": 2},
    ]


# ---------------------------------------------------------------------------
# Layout constants (72 pt = 1 inch)
# ---------------------------------------------------------------------------
_PAGE_SIZE   = 864   # 12"
_SWATCH_SIZE = 216   # 3"
_GRID_ORIGIN = 108   # 1.5" margin
_COLOR_H     = 180   # colored area height within each cell
_LABEL_H     = 36    # label strip height (bottom of cell)

# Y coordinate of the title band base in ReportLab/PostScript (bottom-up)
_TITLE_Y     = _PAGE_SIZE - _GRID_ORIGIN   # 756


# ---------------------------------------------------------------------------
# PDF generation — ReportLab canvas (vector, CMYK-native, Illustrator-editable)
# ---------------------------------------------------------------------------

def _generate_pdf(output_path: Path, swatches: list, goal_desc: str,
                  ref_bytes: Optional[bytes]) -> None:
    """
    Write a 12"×12" vector PDF using ReportLab.
    All color values are emitted as DeviceCMYK — no RGB conversion.
    The resulting file opens in Illustrator with individually selectable paths.
    """
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader

    date_str = datetime.now().strftime("%B %d, %Y")
    c = rl_canvas.Canvas(str(output_path), pagesize=(_PAGE_SIZE, _PAGE_SIZE))

    # ── White background ────────────────────────────────────────────────────
    c.setFillColorCMYK(0, 0, 0, 0)
    c.rect(0, 0, _PAGE_SIZE, _PAGE_SIZE, fill=1, stroke=0)

    # ── Title band (top strip) ───────────────────────────────────────────────
    c.setFillColorCMYK(0, 0, 0, 0.82)
    c.rect(0, _TITLE_Y, _PAGE_SIZE, _GRID_ORIGIN, fill=1, stroke=0)

    # Title text (white in CMYK = 0,0,0,0)
    c.setFillColorCMYK(0, 0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20, _TITLE_Y + 73, "SWATCH SET CREATOR")

    c.setFillColorCMYK(0, 0, 0, 0.4)
    c.setFont("Helvetica", 10)
    c.drawString(20, _TITLE_Y + 50, f"Original vs. {goal_desc}")

    c.setFillColorCMYK(0, 0, 0, 0.5)
    c.setFont("Helvetica", 8)
    c.drawRightString(_PAGE_SIZE - 165, _TITLE_Y + 83, date_str)

    # Optional reference image thumbnail
    if ref_bytes:
        try:
            c.drawImage(
                ImageReader(BytesIO(ref_bytes)),
                _PAGE_SIZE - 95, _TITLE_Y + 8,
                width=85, height=92,
                preserveAspectRatio=True, mask='auto'
            )
            c.setFillColorCMYK(0, 0, 0, 0.5)
            c.setFont("Helvetica", 7)
            c.drawCentredString(_PAGE_SIZE - 52, _TITLE_Y + 3, "Ref.")
        except Exception as e:
            logger.warning(f"Could not embed reference image: {e} — skipping thumbnail")

    # ── Swatch cells ─────────────────────────────────────────────────────────
    # ReportLab Y-axis is bottom-up; row 0 is the top visual row.
    # rl_y = bottom edge of the swatch cell in ReportLab coordinates.
    for s in swatches:
        col, row = s["col"], s["row"]
        cmyk = s["cmyk"]
        cv, mv, yv, kv = [v / 100.0 for v in cmyk]

        x    = _GRID_ORIGIN + col * _SWATCH_SIZE
        rl_y = _PAGE_SIZE - _GRID_ORIGIN - (row + 1) * _SWATCH_SIZE
        cx   = x + _SWATCH_SIZE / 2

        # Colored fill (upper portion of cell)
        c.setFillColorCMYK(cv, mv, yv, kv)
        c.rect(x, rl_y + _LABEL_H, _SWATCH_SIZE, _COLOR_H, fill=1, stroke=0)

        # Dark label strip (lower portion)
        c.setFillColorCMYK(0, 0, 0, 0.7)
        c.rect(x, rl_y, _SWATCH_SIZE, _LABEL_H, fill=1, stroke=0)

        # Cell border
        c.setStrokeColorCMYK(0, 0, 0, 0.15)
        c.setLineWidth(0.75)
        c.rect(x, rl_y, _SWATCH_SIZE, _SWATCH_SIZE, fill=0, stroke=1)

        # Swatch name (white text)
        c.setFillColorCMYK(0, 0, 0, 0)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(cx, rl_y + _LABEL_H - 14, s["label"])

        # CMYK values
        cmyk_str = f"C:{cmyk[0]}  M:{cmyk[1]}  Y:{cmyk[2]}  K:{cmyk[3]}"
        c.setFont("Helvetica", 7)
        c.drawCentredString(cx, rl_y + 5, cmyk_str)

    c.save()


# ---------------------------------------------------------------------------
# EPS generation — raw DSC-compliant PostScript (no extra dependencies)
# ---------------------------------------------------------------------------

def _generate_eps(output_path: Path, swatches: list, goal_desc: str) -> None:
    """
    Write a DSC 3.0 Encapsulated PostScript file.
    Uses native PS operators (setcmykcolor / rectfill / rectstroke) so every
    swatch is a discrete, selectable object when opened in Illustrator.
    Note: reference image thumbnails are omitted in EPS output.
    """
    date_str = datetime.now().strftime("%B %d, %Y")

    # Escape parentheses for PS string literals
    def ps_str(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = [
        "%!PS-Adobe-3.0 EPSF-3.0",
        f"%%BoundingBox: 0 0 {_PAGE_SIZE} {_PAGE_SIZE}",
        f"%%HiResBoundingBox: 0.0 0.0 {float(_PAGE_SIZE)} {float(_PAGE_SIZE)}",
        "%%DocumentProcessColors: Cyan Magenta Yellow Black",
        "%%LanguageLevel: 2",
        f"%%Title: ({ps_str('Swatch Set - ' + goal_desc)})",
        f"%%CreationDate: ({date_str})",
        "%%EndComments",
        "%%BeginProlog",
        "% ctext: (string) cx cy  →  center the string horizontally at (cx, cy)",
        "/ctext { moveto dup stringwidth pop 2 div neg 0 rmoveto show } def",
        "%%EndProlog",
        "%%Page: 1 1",
        "",
        "% ── Background ──────────────────────────────────────────────────────",
        "0 0 0 0 setcmykcolor",
        f"0 0 {_PAGE_SIZE} {_PAGE_SIZE} rectfill",
        "",
        "% ── Title band ──────────────────────────────────────────────────────",
        "0 0 0 0.82 setcmykcolor",
        f"0 {_TITLE_Y} {_PAGE_SIZE} {_GRID_ORIGIN} rectfill",
        "",
        "% ── Title text ──────────────────────────────────────────────────────",
        "0 0 0 0 setcmykcolor",
        "/Helvetica-Bold findfont 16 scalefont setfont",
        f"20 {_TITLE_Y + 73} moveto (SWATCH SET CREATOR) show",
        "",
        "0 0 0 0.4 setcmykcolor",
        "/Helvetica findfont 10 scalefont setfont",
        f"20 {_TITLE_Y + 50} moveto ({ps_str('Original vs. ' + goal_desc)}) show",
        "",
        "0 0 0 0.5 setcmykcolor",
        "/Helvetica findfont 8 scalefont setfont",
        f"({ps_str(date_str)}) dup stringwidth pop neg {_PAGE_SIZE - 165} add "
        f"{_TITLE_Y + 83} moveto show",
        "",
        "% ── Swatch cells ────────────────────────────────────────────────────",
    ]

    for s in swatches:
        col, row = s["col"], s["row"]
        cmyk = s["cmyk"]
        cv, mv, yv, kv = [v / 100.0 for v in cmyk]

        x    = _GRID_ORIGIN + col * _SWATCH_SIZE
        rl_y = _PAGE_SIZE - _GRID_ORIGIN - (row + 1) * _SWATCH_SIZE
        cx   = x + _SWATCH_SIZE / 2

        cmyk_label = f"C:{cmyk[0]}  M:{cmyk[1]}  Y:{cmyk[2]}  K:{cmyk[3]}"

        lines += [
            f"% -- {s['label']} ({cmyk_label}) --",
            # Colored fill
            f"{cv:.4f} {mv:.4f} {yv:.4f} {kv:.4f} setcmykcolor",
            f"{x} {rl_y + _LABEL_H} {_SWATCH_SIZE} {_COLOR_H} rectfill",
            # Label strip
            f"0 0 0 0.70 setcmykcolor",
            f"{x} {rl_y} {_SWATCH_SIZE} {_LABEL_H} rectfill",
            # Cell border
            f"0 0 0 0.15 setcmykcolor",
            "0.75 setlinewidth",
            f"{x} {rl_y} {_SWATCH_SIZE} {_SWATCH_SIZE} rectstroke",
            # Swatch name (white)
            "0 0 0 0 setcmykcolor",
            "/Helvetica-Bold findfont 8 scalefont setfont",
            f"({ps_str(s['label'])}) {cx} {rl_y + _LABEL_H - 14} ctext",
            # CMYK values
            "/Helvetica findfont 7 scalefont setfont",
            f"({cmyk_label}) {cx} {rl_y + 5} ctext",
            "",
        ]

    lines += [
        "showpage",
        "%%EOF",
    ]

    with open(str(output_path), "w", encoding="latin-1") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_swatchset(
    output_path: Path,
    base_c: int, base_m: int, base_y: int, base_k: int,
    goal_type: str,
    goal_r: int = 0, goal_g: int = 0, goal_b: int = 0,
    goal_hex: str = "",
    goal_pantone: str = "",
    reference_image_bytes: Optional[bytes] = None,
    output_format: str = "pdf",
) -> bool:
    """
    Generate a 12"×12" swatch comparison sheet.

    output_format:
      "pdf" — ReportLab vector PDF, editable in Illustrator (default)
      "eps" — DSC-compliant EPS, natively editable in Illustrator
    """
    try:
        base = tuple(_clamp(v, 0, 100) for v in (base_c, base_m, base_y, base_k))

        if goal_type == "rgb":
            goal_cmyk = rgb_to_cmyk(goal_r, goal_g, goal_b)
            goal_desc = f"RGB ({goal_r}, {goal_g}, {goal_b})"
        elif goal_type == "hex":
            r, g, b = hex_to_rgb(goal_hex)
            goal_cmyk = rgb_to_cmyk(r, g, b)
            goal_desc = f"Hex {goal_hex.upper() if not goal_hex.startswith('#') else goal_hex.upper()}"
        elif goal_type == "pantone":
            goal_cmyk = pantone_to_cmyk(goal_pantone)
            goal_desc = f"Pantone {goal_pantone}"
        else:
            raise ValueError(f"Unknown goal_type: '{goal_type}'")

        logger.info(f"Base CMYK: {base}  |  Goal CMYK ({goal_desc}): {goal_cmyk}")

        swatches = build_swatches(base, goal_cmyk)

        if output_format == "eps":
            _generate_eps(output_path, swatches, goal_desc)
        else:
            _generate_pdf(output_path, swatches, goal_desc, reference_image_bytes)

        logger.info(f"✔ Swatchset saved: {output_path.name}")
        return True

    except Exception as e:
        logger.error(f"✘ Failed to generate swatchset: {e}")
        return False
