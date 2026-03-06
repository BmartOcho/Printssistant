import os
import shutil
import zipfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from duplexer import make_duplex
from cropper_logic import process_auto_crop

app = FastAPI(title="Print Productivity Hub API")

# Setup directories
import tempfile
BASE_DIR = Path(__file__).parent
TEMP_DIR = Path(tempfile.gettempdir())

UPLOAD_DIR = TEMP_DIR / "uploads"
PROCESSED_DIR = TEMP_DIR / "processed_web"

UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.post("/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # Save uploaded file
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Define output path
    output_filename = f"duplex_{file.filename}"
    output_path = PROCESSED_DIR / output_filename
    
    # Process the file
    success = make_duplex(file_path, output_path)
    
    if success:
        return {"status": "success", "filename": output_filename}
    else:
        return {"status": "error", "message": "Failed to process PDF"}

@app.post("/crop")
async def crop_pdf(
    file: UploadFile = File(...), 
    rows: int = Form(...), 
    cols: int = Form(...)
):
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Process
    cropped_files = process_auto_crop(file_path, PROCESSED_DIR, rows, cols)
    
    # If multiple files, zip them
    if len(cropped_files) > 1:
        zip_filename = f"cropped_{file.filename}.zip"
        zip_path = PROCESSED_DIR / zip_filename
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for f in cropped_files:
                zipf.write(PROCESSED_DIR / f, arcname=f)
        return {"status": "success", "filename": zip_filename}
    
    return {"status": "success", "filename": cropped_files[0]}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = PROCESSED_DIR / filename
    if file_path.exists():
        return FileResponse(file_path, filename=filename)
    return {"error": "File not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
