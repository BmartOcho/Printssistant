# Printssistant 📄📄

A simple Python utility to duplex PDF files. It takes each page of a PDF and duplicates it (Front and Back), which is useful for certain printing workflows.

## Features

- **Automatic Duplexing**: Duplicates every page in a PDF.
- **Batch Processing**: Processes all PDFs in the `Add_PDF` folder.
- **Clean Output**: Saves processed files to a `Processed` subfolder.

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/BmartOcho/Duplexer.git
   cd Duplexer
   ```

2. **Set up a virtual environment (optional but recommended)**:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Place your PDF files in the `Add_PDF` folder.
2. Run the script:
   ```bash
   python duplexer.py
   ```
3. Your duplexed PDFs will be in the `Add_PDF/Processed` folder.

## Author

**Benjamin (BmartOcho)**
