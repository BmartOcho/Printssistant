import fitz
from pathlib import Path


def process_auto_crop(input_path: Path, output_dir: Path, rows: int, cols: int):
    """
    Grid-based crop: splits each page into rows × cols segments,
    then combines all segments into a single multi-page PDF.
    """
    doc = fitz.open(str(input_path))
    stem = input_path.stem
    out_doc = fitz.open()

    for page_num in range(len(doc)):
        page = doc[page_num]
        pw, ph = page.rect.width, page.rect.height

        for r in range(rows):
            for c in range(cols):
                x0 = c * (pw / cols)
                y0 = r * (ph / rows)
                w = pw / cols
                h = ph / rows
                rect = fitz.Rect(x0, y0, x0 + w, y0 + h)

                new_page = out_doc.new_page(width=rect.width, height=rect.height)
                new_page.show_pdf_page(fitz.Rect(0, 0, rect.width, rect.height), doc, page_num, clip=rect)

    filename = f"{stem}_cropped.pdf"
    save_path = output_dir / filename
    out_doc.save(str(save_path))
    out_doc.close()
    doc.close()
    return filename


def process_reader_spreads(input_path: Path, output_dir: Path):
    """
    Reader spreads: first and last pages kept as-is,
    middle pages split into left/right halves (2 cols, 1 row).
    All combined into a single multi-page PDF in reading order.
    """
    doc = fitz.open(str(input_path))
    stem = input_path.stem
    out_doc = fitz.open()
    page_count = len(doc)

    for page_num in range(page_count):
        page = doc[page_num]
        pw, ph = page.rect.width, page.rect.height

        if page_num == 0 or page_num == page_count - 1:
            # First and last page: keep as-is
            new_page = out_doc.new_page(width=pw, height=ph)
            new_page.show_pdf_page(fitz.Rect(0, 0, pw, ph), doc, page_num)
        else:
            # Middle pages: split into left and right halves
            half_w = pw / 2
            for side in range(2):
                x0 = side * half_w
                rect = fitz.Rect(x0, 0, x0 + half_w, ph)
                new_page = out_doc.new_page(width=half_w, height=ph)
                new_page.show_pdf_page(fitz.Rect(0, 0, half_w, ph), doc, page_num, clip=rect)

    filename = f"{stem}_reader_spreads.pdf"
    save_path = output_dir / filename
    out_doc.save(str(save_path))
    out_doc.close()
    doc.close()
    return filename
