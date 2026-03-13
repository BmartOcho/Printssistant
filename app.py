import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from duplexer import make_duplex
from cropper_logic import process_auto_crop
from insert_logic import insert_pages
from even_odd_logic import generate_even_odd
from vectorizer import engine as vectorizer_engine
from presets import get_preset
from swatchset_logic import generate_swatchset

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

@app.post("/insert")
async def insert_pdf(
    base_file: UploadFile = File(...),
    insert_file: UploadFile = File(...),
    interval: int = Form(...)
):
    base_path = UPLOAD_DIR / base_file.filename
    with open(base_path, "wb") as buffer:
        shutil.copyfileobj(base_file.file, buffer)
        
    insert_path = UPLOAD_DIR / insert_file.filename
    with open(insert_path, "wb") as buffer:
        shutil.copyfileobj(insert_file.file, buffer)
        
    output_filename = f"inserted_{base_file.filename}"
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
        basename = os.path.splitext(file.filename)[0]
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

@app.post("/swatchset")
async def create_swatchset(
    base_c: int = Form(...),
    base_m: int = Form(...),
    base_y: int = Form(...),
    base_k: int = Form(...),
    goal_type: str = Form(...),
    goal_r: int = Form(0),
    goal_g: int = Form(0),
    goal_b: int = Form(0),
    goal_hex: str = Form(""),
    goal_pantone: str = Form(""),
    output_format: str = Form("pdf"),
    reference_image: Optional[UploadFile] = File(None)
):
    import time
    ref_bytes = None
    if reference_image and reference_image.filename:
        ref_bytes = await reference_image.read()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    ext = "eps" if output_format == "eps" else "pdf"
    output_path = PROCESSED_DIR / f"swatchset_{timestamp}.{ext}"

    success = generate_swatchset(
        output_path=output_path,
        base_c=base_c, base_m=base_m, base_y=base_y, base_k=base_k,
        goal_type=goal_type,
        goal_r=goal_r, goal_g=goal_g, goal_b=goal_b,
        goal_hex=goal_hex,
        goal_pantone=goal_pantone,
        reference_image_bytes=ref_bytes,
        output_format=output_format,
    )

    if success:
        return {"status": "success", "filename": output_path.name}
    fmt_label = "EPS" if output_format == "eps" else "PDF"
    return {"status": "error", "message": f"Failed to generate swatch set {fmt_label}"}


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = PROCESSED_DIR / filename
    if file_path.exists():
        return FileResponse(file_path, filename=filename)
    return {"error": "File not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
