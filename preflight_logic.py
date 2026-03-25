"""
DG Preflight — PDF validation for print readiness.

Checks:
  1. Bleeds       — pages missing ≥ 0.125" bleed
  2. Color Mode   — RGB images that should be CMYK
  3. File Size    — warns if > 25 MB
  4. Safe Margins — text within 0.5" of trim edge
  5. Resolution   — images below 300 DPI effective

All measurements use PDF points (1 pt = 1/72 inch).
Uses PyMuPDF (fitz) which is already in requirements.txt.
"""
from __future__ import annotations

from typing import Any

import fitz  # PyMuPDF

# ── Constants ─────────────────────────────────────────────────────────────────
BLEED_MIN_PT = 0.125 * 72        # 9 pts  = 0.125"
SAFE_MARGIN_PT = 0.5 * 72        # 36 pts = 0.5"
MIN_DPI = 300
WARN_FILE_SIZE = 25 * 1024 * 1024   # 25 MB


# ── Helpers ───────────────────────────────────────────────────────────────────

def _result(status: str, message: str, detail: str = "") -> dict[str, str]:
    return {"status": status, "message": message, "detail": detail}


def _page_list(pages: list[int]) -> str:
    unique = sorted(set(pages))
    shown = ", ".join(str(p) for p in unique[:5])
    extra = f" (+{len(unique) - 5} more)" if len(unique) > 5 else ""
    return shown + extra


# ── Check 1: File Size ────────────────────────────────────────────────────────

def check_file_size(file_size: int) -> dict[str, str]:
    mb = file_size / (1024 * 1024)
    if file_size >= WARN_FILE_SIZE:
        return _result(
            "warn",
            f"Large file ({mb:.1f} MB)",
            "Files over 25 MB may be rejected by some print providers. Consider optimising images.",
        )
    return _result("pass", f"File size OK ({mb:.1f} MB)")


# ── Check 2: Bleeds ───────────────────────────────────────────────────────────

def check_bleeds(doc: fitz.Document) -> dict[str, str]:
    """
    Compares each page's TrimBox to its MediaBox.
    If TrimBox == MediaBox the PDF has no bleed defined at all.
    If the gap between MediaBox and TrimBox is < 0.125" on any side, bleed is insufficient.
    """
    missing: list[int] = []
    thin: list[int] = []

    for i, page in enumerate(doc):
        mb = page.mediabox
        tb = page.trimbox  # falls back to MediaBox if not set

        same_w = abs(mb.width - tb.width) < 0.5
        same_h = abs(mb.height - tb.height) < 0.5

        if same_w and same_h:
            missing.append(i + 1)
            continue

        # Bleed margins: how much MediaBox extends beyond TrimBox
        left   = tb.x0 - mb.x0
        bottom = tb.y0 - mb.y0
        right  = mb.x1 - tb.x1
        top    = mb.y1 - tb.y1

        if min(left, bottom, right, top) < BLEED_MIN_PT:
            thin.append(i + 1)

    if missing:
        return _result(
            "fail",
            "Missing bleeds",
            f"No bleed on page(s) {_page_list(missing)}. Add 0.125\" (3 mm) bleed before sending to print.",
        )
    if thin:
        return _result(
            "warn",
            "Insufficient bleed",
            f"Bleed < 0.125\" on page(s) {_page_list(thin)}. Standard print bleed is 0.125\" (3 mm).",
        )
    return _result("pass", "Bleeds OK", "All pages have ≥ 0.125\" bleed on every side.")


# ── Check 3: Color Mode ───────────────────────────────────────────────────────

def check_color_mode(doc: fitz.Document) -> dict[str, str]:
    """
    Extracts embedded images from each page and checks their colorspace.
    fitz reports: colorspace components 1=Gray, 3=RGB, 4=CMYK.
    """
    rgb_pages: list[int] = []
    unknown_pages: list[int] = []

    for i, page in enumerate(doc):
        page_flagged = False
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                img = doc.extract_image(xref)
                cs_components = img.get("colorspace", 0)
                cs_name = (img.get("cs-name") or "").lower()

                if cs_components == 3 or "rgb" in cs_name:
                    rgb_pages.append(i + 1)
                    page_flagged = True
                    break
                elif cs_components == 0 and not page_flagged:
                    unknown_pages.append(i + 1)
            except Exception:
                pass

    if rgb_pages:
        return _result(
            "fail",
            "RGB images detected",
            f"Page(s) {_page_list(rgb_pages)} contain RGB images. Convert to CMYK before printing.",
        )
    if unknown_pages:
        return _result(
            "warn",
            "Unrecognised color profile",
            f"Page(s) {_page_list(unknown_pages)} have images with unknown colorspaces. Verify CMYK output with your print provider.",
        )
    return _result("pass", "Color mode OK", "All images appear to be CMYK or grayscale.")


# ── Check 4: Safe Margins ─────────────────────────────────────────────────────

def check_safe_margins(doc: fitz.Document) -> dict[str, str]:
    """
    Flags pages where text blocks fall within 0.5\" of the TrimBox edge.
    Checks text blocks only (vector elements excluded — too expensive without rendering).
    """
    at_risk: list[int] = []

    for i, page in enumerate(doc):
        tb = page.trimbox
        safe_x0 = tb.x0 + SAFE_MARGIN_PT
        safe_y0 = tb.y0 + SAFE_MARGIN_PT
        safe_x1 = tb.x1 - SAFE_MARGIN_PT
        safe_y1 = tb.y1 - SAFE_MARGIN_PT

        for block in page.get_text("blocks"):
            bx0, by0, bx1, by1 = block[:4]
            if bx0 < safe_x0 or by0 < safe_y0 or bx1 > safe_x1 or by1 > safe_y1:
                at_risk.append(i + 1)
                break

    if at_risk:
        return _result(
            "warn",
            "Content near trim edge",
            f"Text within 0.5\" of trim on page(s) {_page_list(at_risk)}. Content may be cut off during finishing.",
        )
    return _result("pass", "Safe margins OK", "No text detected within 0.5\" of the trim edge.")


# ── Check 5: Image Resolution ─────────────────────────────────────────────────

def check_resolution(doc: fitz.Document) -> dict[str, str]:
    """
    Calculates effective DPI for each embedded image:
        effective_dpi = pixel_width / (rendered_width_in_pts / 72)
    Images below 300 DPI will appear pixelated at print size.
    """
    low_res: list[tuple[int, int]] = []   # (page_number, effective_dpi)

    for i, page in enumerate(doc):
        for img_info in page.get_images(full=True):
            xref    = img_info[0]
            pix_w   = img_info[2]  # pixel width
            pix_h   = img_info[3]  # pixel height

            if pix_w == 0 or pix_h == 0:
                continue

            try:
                rects = page.get_image_rects(xref)
            except Exception:
                continue

            for rect in rects:
                if rect.width <= 0 or rect.height <= 0:
                    continue
                dpi_x = pix_w / (rect.width / 72)
                dpi_y = pix_h / (rect.height / 72)
                eff_dpi = int(min(dpi_x, dpi_y))
                if eff_dpi < MIN_DPI:
                    low_res.append((i + 1, eff_dpi))
                    break   # one low-res image per page is enough to flag it

    if low_res:
        pages = [p for p, _ in low_res]
        min_dpi = min(d for _, d in low_res)
        return _result(
            "fail",
            f"Low-resolution images (min {min_dpi} DPI)",
            f"Images below 300 DPI on page(s) {_page_list(pages)}. These will appear pixelated at print size.",
        )
    return _result("pass", "Resolution OK", "All images are ≥ 300 DPI at their rendered print size.")


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_preflight(pdf_bytes: bytes, file_size: int) -> dict[str, Any]:
    """
    Runs all 5 preflight checks and returns structured results.

    Returns:
        {
          "page_count": int,
          "overall":    "pass" | "warn" | "fail",
          "checks": {
            "file_size":    {status, message, detail},
            "bleeds":       {status, message, detail},
            "color_mode":   {status, message, detail},
            "safe_margins": {status, message, detail},
            "resolution":   {status, message, detail},
          }
        }
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        return {"error": f"Could not open PDF: {exc}"}

    page_count = len(doc)

    checks = {
        "file_size":    check_file_size(file_size),
        "bleeds":       check_bleeds(doc),
        "color_mode":   check_color_mode(doc),
        "safe_margins": check_safe_margins(doc),
        "resolution":   check_resolution(doc),
    }

    doc.close()

    statuses = [c["status"] for c in checks.values()]
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "pass"

    return {"page_count": page_count, "overall": overall, "checks": checks}
