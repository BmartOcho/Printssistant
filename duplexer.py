#!/usr/bin/env python3
import os
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter

def make_duplex(input_path: Path, output_path: Path) -> None:
    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)    # front (original page)
        writer.add_page(page)    # back (duplicate)
    with open(output_path, "wb") as f:
        writer.write(f)
    print(f"✔ Processed {input_path.name} → {output_path.name}")

def main():
    input_dir  = Path("Add_PDF")
    if not input_dir.is_dir():
        print(f"Folder not found: {input_dir!r}")
        return

    # create an output folder (you can change this as you like)
    output_dir = input_dir / "Processed"
    output_dir.mkdir(exist_ok=True)

    # find all PDFs and duplex them
    for pdf_file in input_dir.glob("*.pdf"):
        out_file = output_dir / f"duplex_{pdf_file.name}"
        make_duplex(pdf_file, out_file)

if __name__ == "__main__":
    main()
