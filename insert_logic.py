import os
from pathlib import Path
from pypdf import PdfReader, PdfWriter, PageObject
from typing import List, Optional

def insert_pages(
    base_pdf: Path,
    insert_pdf: Optional[Path],
    output_pdf: Path,
    interval: Optional[int],
    positions: List[int],
    blank_mode: Optional[str] = None,
) -> bool:
    """
    Insert pages into a PDF at specified intervals or positions.
    Supports inserting from another PDF, blank pages, or both.
    blank_mode: None (no blanks), "interval" (blank at each interval), "cover" (front/back padding).
    """
    try:
        base_reader = PdfReader(str(base_pdf))
        insert_reader = PdfReader(str(insert_pdf)) if insert_pdf else None
        writer = PdfWriter()

        total_pages = len(base_reader.pages)

        # Read page dimensions from first page for blank creation
        media_box = base_reader.pages[0].mediabox
        page_width = float(media_box.width)
        page_height = float(media_box.height)

        def add_blank():
            writer.add_page(PageObject.create_blank_page(width=page_width, height=page_height))

        def add_insert_pages():
            if insert_reader:
                for insert_page in insert_reader.pages:
                    writer.add_page(insert_page)

        # ── Cover mode ────────────────────────────────────────────────────
        if blank_mode == "cover":
            # First 2 pages (or fewer if doc is short)
            front_count = min(2, total_pages)
            for i in range(front_count):
                writer.add_page(base_reader.pages[i])

            # 2 blanks after front pages
            add_blank()
            add_blank()

            # Middle pages
            middle_start = front_count
            middle_end = max(front_count, total_pages - 2)
            for i in range(middle_start, middle_end):
                writer.add_page(base_reader.pages[i])

            # 2 blanks before back pages (only if doc has >4 pages)
            if total_pages > 4:
                add_blank()
                add_blank()

            # Last 2 pages (skip if already covered by front)
            back_start = max(front_count, total_pages - 2)
            for i in range(back_start, total_pages):
                writer.add_page(base_reader.pages[i])

        # ── Interval mode (blank and/or insert PDF) ──────────────────────
        else:
            # Build insertion points (1-based index)
            points = set()
            if interval and interval > 0:
                points.update(range(interval, total_pages + 1, interval))
            for pos in positions:
                if 1 <= pos <= total_pages:
                    points.add(pos)

            insertion_points = sorted(points)

            for index in range(total_pages):
                writer.add_page(base_reader.pages[index])
                page_number = index + 1
                if page_number in insertion_points:
                    if blank_mode == "interval":
                        add_blank()
                    add_insert_pages()

        with open(output_pdf, "wb") as f:
            writer.write(f)

        return True
    except Exception as e:
        print(f"Error inserting pages: {e}")
        return False
