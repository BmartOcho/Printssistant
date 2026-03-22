import os
import shutil
import zipfile
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from duplexer import make_duplex
from cropper_logic import process_auto_crop
from insert_logic import insert_pages
from even_odd_logic import generate_even_odd
from vectorizer import engine as vectorizer_engine
from presets import get_preset
from swatchset_logic import generate_swatchset
from auth import get_current_user, require_pro, check_free_limit, create_access_token
from db import supabase, increment_job_count
from passlib.context import CryptContext

try:
    from resend import Resend
    resend_available = True
except ImportError:
    resend_available = False

app = FastAPI(title="Printssistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password Reset Setup ─────────────────────────────────────────────────────

def initialize_password_resets_table():
    """Create password_resets table if it doesn't exist."""
    try:
        supabase.table("password_resets").select("id").limit(1).execute()
    except Exception as e:
        # Table doesn't exist, create it
        try:
            # Note: This uses the Supabase REST API directly via supabase.postgrest
            # You may need to create this table manually in Supabase if this fails
            supabase.postgrest.from_("password_resets").select("*").execute()
        except:
            print(
                "⚠️  password_resets table not found. Create it manually in Supabase with:\n"
                "  - email (text, unique)\n"
                "  - token (text, unique)\n"
                "  - expires_at (timestamp)\n"
                "  - used (boolean, default false)\n"
                "  - created_at (timestamp, default now())"
            )


# Call on startup
@app.on_event("startup")
async def startup():
    initialize_password_resets_table()


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


# ── Root ────────────────────────────────────────────────────────────────────

@app.get("/")
async def read_index():
    return FileResponse(BASE_DIR / "static" / "index.html")


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/auth/signup")
async def signup(request: Request):
    """Create a new account with email + password."""
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Check if already exists
    existing = supabase.table("users").select("id").eq("email", email).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    import uuid
    user_id = str(uuid.uuid4())
    password_hash = pwd_context.hash(password)

    supabase.table("users").insert({
        "id": user_id,
        "email": email,
        "password_hash": password_hash,
        "is_pro": False,
        "monthly_jobs": 0,
    }).execute()

    token = create_access_token(user_id, email)
    return {"access_token": token, "email": email, "is_pro": False, "monthly_jobs": 0}


@app.post("/auth/signin")
async def signin(request: Request):
    """Sign in with email + password, returns a JWT."""
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    result = supabase.table("users").select("id, email, password_hash, is_pro, monthly_jobs").eq("email", email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = result.data[0]
    verify_result = pwd_context.verify(password, user["password_hash"]) if user.get("password_hash") else False
    print(f"[DEBUG] Password verify result for {email}: {verify_result}")
    if not user.get("password_hash") or not verify_result:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user["id"], email)
    return {
        "access_token": token,
        "email": email,
        "is_pro": user.get("is_pro", False),
        "monthly_jobs": user.get("monthly_jobs", 0),
    }


# ── Password Reset ───────────────────────────────────────────────────────────

@app.post("/auth/forgot-password")
async def forgot_password(request: Request):
    """Send a password reset email to the user."""
    body = await request.json()
    email = body.get("email", "").strip().lower()

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    # Check if user exists
    result = supabase.table("users").select("id, email").eq("email", email).execute()
    if not result.data:
        # Don't leak whether email exists — return success anyway
        return {"message": "If an account with that email exists, a reset link has been sent."}

    # Generate a secure token (32 bytes = 64 hex chars)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    # Store the token in the password_resets table
    try:
        supabase.table("password_resets").insert({
            "email": email,
            "token": token,
            "expires_at": expires_at.isoformat(),
            "used": False,
        }).execute()
    except Exception as e:
        print(f"Error storing password reset token: {e}")
        return {"message": "If an account with that email exists, a reset link has been sent."}

    # Send email via Resend (if API key is available)
    reset_url = f"https://printssistant.com/reset-password?token={token}"
    
    if resend_available and os.environ.get("RESEND_API_KEY"):
        try:
            client = Resend(api_key=os.environ.get("RESEND_API_KEY"))
            client.emails.send({
                "from": "noreply@printssistant.com",
                "to": email,
                "subject": "Reset Your Printssistant Password",
                "html": f"""
                <p>Hi,</p>
                <p>You requested a password reset for your Printssistant account. Click the link below to set a new password:</p>
                <p><a href="{reset_url}">Reset Password</a></p>
                <p>This link expires in 1 hour.</p>
                <p>If you didn't request this, you can ignore this email.</p>
                <p>—<br>Printssistant Team</p>
                """,
            })
        except Exception as e:
            print(f"Error sending reset email: {e}")
    else:
        print(f"⚠️  Reset token for {email}: {reset_url}")
        print("(Resend not configured. Copy the link above to test.)")

    return {"message": "If an account with that email exists, a reset link has been sent."}


@app.get("/auth/reset-password/{token}")
async def validate_reset_token(token: str):
    """Validate that a reset token exists and hasn't expired."""
    try:
        result = supabase.table("password_resets").select("email, expires_at, used").eq("token", token).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link")
        
        reset = result.data[0]
        
        if reset.get("used"):
            raise HTTPException(status_code=400, detail="This reset link has already been used")
        
        expires_at = datetime.fromisoformat(reset["expires_at"].replace("Z", "+00:00"))
        if datetime.utcnow() > expires_at:
            raise HTTPException(status_code=400, detail="This reset link has expired")
        
        return {"valid": True, "email": reset["email"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error validating reset token: {e}")
        raise HTTPException(status_code=400, detail="Invalid reset link")


@app.post("/auth/reset-password")
async def reset_password(request: Request):
    """Update the user's password using a valid reset token."""
    body = await request.json()
    token = body.get("token", "")
    new_password = body.get("password", "")

    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and password are required")
    
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Validate the token
    try:
        result = supabase.table("password_resets").select("email, expires_at, used").eq("token", token).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Invalid reset token")
        
        reset = result.data[0]
        
        if reset.get("used"):
            raise HTTPException(status_code=400, detail="This reset link has already been used")
        
        expires_at = datetime.fromisoformat(reset["expires_at"].replace("Z", "+00:00"))
        if datetime.utcnow() > expires_at:
            raise HTTPException(status_code=400, detail="This reset link has expired")
        
        email = reset["email"]
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error validating reset token: {e}")
        raise HTTPException(status_code=400, detail="Invalid reset token")

    # Update the user's password
    try:
        new_hash = pwd_context.hash(new_password[:72])
        supabase.table("users").update({
            "password_hash": new_hash,
        }).eq("email", email).execute()

        # Mark the token as used
        supabase.table("password_resets").update({
            "used": True,
        }).eq("token", token).execute()

        return {"message": "Password updated successfully"}
    except Exception as e:
        print(f"Error updating password: {e}")
        raise HTTPException(status_code=500, detail="Error updating password")


@app.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Returns current user info. Frontend uses this to check auth state."""
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "is_pro": user.get("is_pro", False),
        "monthly_jobs": user.get("monthly_jobs", 0),
    }


# ── Stripe Webhook ────────────────────────────────────────────────────────────

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Receives payment events from Stripe.
    On successful checkout, flips the user's is_pro flag.
    Set STRIPE_WEBHOOK_SECRET in Railway env vars (from Stripe Dashboard → Webhooks).
    """
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_details", {}).get("email") or session.get("customer_email")
        stripe_customer_id = session.get("customer")

        if customer_email:
            # Find user by email and flip is_pro
            result = supabase.table("users").select("id").eq("email", customer_email).execute()
            if result.data:
                import datetime
                supabase.table("users").update({
                    "is_pro": True,
                    "stripe_customer_id": stripe_customer_id,
                    "pro_activated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }).eq("email", customer_email).execute()

    return {"status": "ok"}


# ── Free Tools (require login + monthly limit) ────────────────────────────────

@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(check_free_limit),
):
    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    output_filename = f"duplex_{safe_name}"
    output_path = PROCESSED_DIR / output_filename

    success = make_duplex(file_path, output_path)

    if success:
        increment_job_count(user["id"])
        return {"status": "success", "filename": output_filename}
    else:
        return {"status": "error", "message": "Failed to process PDF"}


@app.post("/crop")
async def crop_pdf(
    file: UploadFile = File(...),
    rows: int = Form(...),
    cols: int = Form(...),
    user: dict = Depends(check_free_limit),
):
    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if rows < 1 or cols < 1:
        return JSONResponse(status_code=400, content={"status": "error", "message": "rows and cols must be at least 1"})

    cropped_files = process_auto_crop(file_path, PROCESSED_DIR, rows, cols)

    if not cropped_files:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Crop produced no output"})

    if len(cropped_files) > 1:
        zip_filename = f"cropped_{safe_name}.zip"
        zip_path = PROCESSED_DIR / zip_filename
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for f in cropped_files:
                zipf.write(PROCESSED_DIR / f, arcname=f)
        increment_job_count(user["id"])
        return {"status": "success", "filename": zip_filename}

    increment_job_count(user["id"])
    return {"status": "success", "filename": cropped_files[0]}


@app.post("/insert")
async def insert_pdf(
    base_file: UploadFile = File(...),
    insert_file: UploadFile = File(...),
    interval: int = Form(...),
    user: dict = Depends(check_free_limit),
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
        increment_job_count(user["id"])
        return {"status": "success", "filename": output_filename}
    else:
        return {"status": "error", "message": "Failed to process PDF"}


# ── Free / Open Tools ─────────────────────────────────────────────────────────

@app.post("/evenodd")
async def get_even_odd(
    start: int = Form(...),
    end: int = Form(...),
    type: str = Form(...),
):
    """Even/Odd generator — open to all, no auth required."""
    is_even = True if type == "even" else False
    result_string = generate_even_odd(start, end, is_even)
    return {"status": "success", "result": result_string}


# ── Pro-Only Tools ────────────────────────────────────────────────────────────

@app.post("/vectorize")
async def vectorize_image(
    file: UploadFile = File(...),
    preset: str = Form("laser_bw"),
    user: dict = Depends(require_pro),
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
            "stats": result.get("stats"),
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
    reference_image: Optional[UploadFile] = File(None),
    user: dict = Depends(require_pro),
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


# ── Downloads ─────────────────────────────────────────────────────────────────

@app.get("/download/{filename}")
async def download_file(
    filename: str,
):
    safe_name = Path(filename).name
    file_path = PROCESSED_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=safe_name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
