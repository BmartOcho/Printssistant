import os
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter
from typing import List, Optional

def insert_pages(base_pdf: Path, insert_pdf: Path, output_pdf: Path, interval: Optional[int], positions: List[int]) -> bool:
    """
    Core logic to insert one PDF into another at specified intervals or positions.
    """
    try:
        base_reader = PdfReader(str(base_pdf))
        insert_reader = PdfReader(str(insert_pdf))
        writer = PdfWriter()

        total_pages = len(base_reader.pages)
        
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
                for insert_page in insert_reader.pages:
                    writer.add_page(insert_page)

        with open(output_pdf, "wb") as f:
            writer.write(f)
            
        return True
    except Exception as e:
        print(f"Error inserting pages: {e}")
        return False
