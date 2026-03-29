#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path
from pypdf import PdfReader, PdfWriter

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def make_duplex(input_path: Path, output_path: Path, group_size: int = 1) -> bool:
    """
    Creates a duplex version of a PDF by duplicating groups of pages.
    group_size=1: 1,1,2,2,3,3,...
    group_size=3: 1-2-3,1-2-3,4-5-6,4-5-6,...
    """
    try:
        reader = PdfReader(str(input_path))
        writer = PdfWriter()
        pages = reader.pages

        for i in range(0, len(pages), group_size):
            group = pages[i:i + group_size]
            for _ in range(2):          # Front pass + Back pass
                for page in group:
                    writer.add_page(page)
            
        with open(output_path, "wb") as f:
            writer.write(f)
        
        logger.info(f"✔ Processed: {input_path.name} -> {output_path.name}")
        return True
    except Exception as e:
        logger.error(f"✘ Failed to process {input_path.name}: {e}")
        return False

def main():
    # Base directory logic
    base_dir = Path(__file__).parent
    input_dir = base_dir / "Add_PDF"
    
    if not input_dir.is_dir():
        logger.warning(f"Input directory 'Add_PDF' not found. Creating it...")
        input_dir.mkdir(parents=True, exist_ok=True)
        print(f"Please place your PDF files in: {input_dir.absolute()}")
        return

    output_dir = input_dir / "Processed"
    output_dir.mkdir(exist_ok=True)

    pdf_files = list(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.info("No PDF files found in 'Add_PDF' folder.")
        return

    success_count = 0
    for pdf_file in pdf_files:
        # Avoid processing already processed files if they are in the same folder
        if pdf_file.name.startswith("duplex_"):
            continue
            
        out_file = output_dir / f"duplex_{pdf_file.name}"
        if make_duplex(pdf_file, out_file):
            success_count += 1

    logger.info(f"Summary: Successfully processed {success_count}/{len(pdf_files)} files.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nProcess interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
