import fitz
import os
from pathlib import Path

def process_auto_crop(input_path: Path, output_dir: Path, rows: int, cols: int):
    """
    Core logic for Auto-Cropper (extracted from auto-cropper.py)
    Exports all segments from the grid.
    """
    doc = fitz.open(str(input_path))
    page = doc[0]
    pw, ph = page.rect.width, page.rect.height
    
    stem = input_path.stem
    output_files = []

    for r in range(rows):
        for c in range(cols):
            x0 = c * (pw / cols)
            y0 = r * (ph / rows)
            rect = fitz.Rect(x0, y0, x0 + (pw / cols), y0 + (ph / rows))
            
            new_doc = fitz.open()
            new_page = new_doc.new_page(width=rect.width, height=rect.height)
            new_page.show_pdf_page(fitz.Rect(0, 0, rect.width, rect.height), doc, 0, clip=rect)
            
            filename = f"{stem}_r{r}c{c}_cropped.pdf"
            save_path = output_dir / filename
            new_doc.save(str(save_path))
            new_doc.close()
            output_files.append(filename)
            
    doc.close()
    return output_files
