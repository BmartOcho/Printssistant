import os
import shutil
import zipfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from duplexer import make_duplex
from cropper_logic import process_auto_crop
from insert_logic import insert_pages
from even_odd_logic import generate_even_odd
from vectorizer import engine as vectorizer_engine
from presets import get_preset

app = FastAPI(title="Printssistant API")

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
    # Sanitize filename to prevent path traversal
    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Define output path
    output_filename = f"duplex_{safe_name}"
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
    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if rows < 1 or cols < 1:
        return JSONResponse(status_code=400, content={"status": "error", "message": "rows and cols must be at least 1"})

    # Process
    cropped_files = process_auto_crop(file_path, PROCESSED_DIR, rows, cols)

    if not cropped_files:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Crop produced no output"})

    # If multiple files, zip them
    if len(cropped_files) > 1:
        zip_filename = f"cropped_{safe_name}.zip"
        zip_path = PROCESSED_DIR / zip_filename
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for f in cropped_files:
                zipf.write(PROCESSED_DIR / f, arcname=f)
        return {"status": "success", "filename": zip_filename}

    return {"status": "success", "filename": cropped_files[0]}

@app.post("/insert")
async def insert_pdf(
    base_file: UploadFile = File(...),
    insert_file: UploadFile = File(...),
    interval: int = Form(...)
):
    base_path = UPLOAD_DIR / Path(base_file.filename).name
    with open(base_path, "wb") as buffer:
        shutil.copyfileobj(base_file.file, buffer)

    insert_path = UPLOAD_DIR / Path(insert_file.filename).name
    with open(insert_path, "wb") as buffer:
        shutil.copyfileobj(insert_file.file, buffer)

    output_filename = f"inserted_{Path(base_file.filename).name}"
    output_path = PROCESSED_DIR / output_filename
    
    success = insert_pages(base_path, insert_path, output_path, interval=interval, positions=[])
    
    if success:
        return {"status": "success", "filename": output_filename}
    else:
        return {"status": "error", "message": "Failed to process PDF"}

@app.post("/evenodd")
async def get_even_odd(
    start: int = Form(...),
    end: int = Form(...),
    type: str = Form(...)
):
    is_even = True if type == "even" else False
    result_string = generate_even_odd(start, end, is_even)
    
    return {"status": "success", "result": result_string}

@app.post("/vectorize")
async def vectorize_image(
    file: UploadFile = File(...),
    preset: str = Form("laser_bw")
):
    preset_config = get_preset(preset)
    if not preset_config:
        return {"status": "error", "message": f"Unknown preset: {preset}"}
    
    image_bytes = await file.read()
    
    try:
        result = vectorizer_engine.vectorize(image_bytes, preset_config)
        import time
        timestamp = int(time.time())
        basename = os.path.splitext(Path(file.filename).name)[0]
        svg_filename = f"{basename}_{preset}_{timestamp}.svg"
        svg_path = PROCESSED_DIR / svg_filename
        
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(result["svg"])
            
        return {
            "status": "success", 
            "filename": svg_filename,
            "preview_bw": result.get("preview_bw"),
            "stats": result.get("stats")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/download/{filename}")
async def download_file(filename: str):
    safe_name = Path(filename).name
    file_path = PROCESSED_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=safe_name)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
