import os
import sys

# Ensure stdout handles Unicode (emoji etc.) on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Load .env for local development (no-op if file absent or dotenv not installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import asyncio
import shutil
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException, Depends, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from duplexer import make_duplex
from cropper_logic import process_auto_crop, process_reader_spreads
from insert_logic import insert_pages
from even_odd_logic import generate_even_odd
from vectorizer import engine as vectorizer_engine
from presets import get_preset
from swatchset_logic import generate_swatchset
from auth import get_current_user, get_optional_user, require_pro, check_free_limit, create_access_token, security
from db import (
    supabase, increment_job_count, log_job_history,
    update_user_profile, get_public_profile,
    create_preflight_job, complete_preflight_job, fail_preflight_job, get_preflight_job,
    get_preflight_count_today, get_preflight_count_month, increment_preflight_ip,
)
from preflight_logic import run_preflight
from passlib.context import CryptContext

resend_client = None
try:
    import resend
    resend_available = True
    print("✅ Resend library imported successfully")
except ImportError as e:
    resend_available = False
    print(f"❌ Failed to import resend: {e}")

# Debug: Check if RESEND_API_KEY is available
print(f"[STARTUP] RESEND_API_KEY loaded: {bool(os.environ.get('RESEND_API_KEY'))}")
print(f"[STARTUP] Checking variable name: RESEND_API_KEY")

app = FastAPI(title="Printssistant API")

# ── CORS Configuration ────────────────────────────────────────────────────────
# Allow production domain + localhost for development/testing
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ALLOWED_ORIGINS = [
    "https://printssistant.com",
    "https://www.printssistant.com",
]
# Allow localhost in dev/staging environments
if ENVIRONMENT in ["development", "staging"]:
    ALLOWED_ORIGINS.extend([
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Cache Control Middleware ──────────────────────────────────────────────────
@app.middleware("http")
async def add_cache_control(request: Request, call_next):
    """Add Cache-Control headers to static assets for optimal edge caching."""
    response = await call_next(request)
    path = request.url.path

    # Cache images and fonts for 1 year (truly static assets)
    if path.startswith("/static/") and any(path.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf"]):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    # CSS and JS: always revalidate — ensures users get updated scripts/styles after each deploy
    elif path.startswith("/static/") and any(path.endswith(ext) for ext in [".css", ".js"]):
        response.headers["Cache-Control"] = "no-cache"
    # HTML pages: always revalidate — ensures the correct script tags are loaded
    elif path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-cache"

    return response


# Rate limiter for brute-force protection
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Import and add slowapi error handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={"status": "error", "message": "Too many authentication attempts. Please try again later."}
    )

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint for Railway and load balancer monitoring."""
    return {"status": "ok"}


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
DOWNLOAD_RETENTION_SECONDS = 600

UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# File size limits (in bytes)
MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB for PDFs
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB for images


# ── Cleanup Helper ──────────────────────────────────────────────────────────

def cleanup_files(*file_paths: Path):
    """Delete temporary files after response is sent."""
    for file_path in file_paths:
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            print(f"⚠️  Failed to delete {file_path}: {e}")


async def cleanup_files_later(delay_seconds: int, *file_paths: Path):
    """Delete temporary files after a delay to allow follow-up download requests."""
    await asyncio.sleep(delay_seconds)
    cleanup_files(*file_paths)


# ── Root ────────────────────────────────────────────────────────────────────

@app.get("/")
async def read_index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/forgot-password")
async def forgot_password_page():
    return FileResponse(BASE_DIR / "static" / "forgot-password.html")


@app.get("/reset-password")
async def reset_password_page():
    return FileResponse(BASE_DIR / "static" / "reset-password.html")


@app.get("/suggest-idea")
async def suggest_idea_page():
    return FileResponse(BASE_DIR / "static" / "suggest-idea.html")


# ── Suggestions API ──────────────────────────────────────────────────────────

@app.post("/api/suggestions")
async def submit_suggestion(request: Request):
    """Submit a feature suggestion or tool idea."""
    try:
        body = await request.json()
        
        # Validate required fields
        required_fields = ['email', 'title', 'description', 'impact']
        if not all(field in body for field in required_fields):
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Store in Supabase
        suggestion_data = {
            "name": body.get("name", "Anonymous"),
            "email": body.get("email", "").strip().lower(),
            "title": body.get("title", ""),
            "description": body.get("description", ""),
            "impact": body.get("impact", ""),
            "submitted_at": body.get("submittedAt", datetime.utcnow().isoformat()),
            "status": "new",
        }
        
        # Try to insert into suggestions table
        try:
            supabase.table("suggestions").insert(suggestion_data).execute()
        except Exception as e:
            print(f"Error storing suggestion: {e}")
            # Table might not exist, but don't fail the request
            print(f"💡 Suggestion received: {suggestion_data['title']} from {suggestion_data['email']}")
        
        # Send confirmation email
        reset_url = f"https://printssistant.com"
        
        if resend_available and os.environ.get("RESEND_API_KEY"):
            try:
                resend.api_key = os.environ.get("RESEND_API_KEY")
                resend.Emails.send({
                    "from": "dev@printssistant.com",
                    "to": body.get("email", ""),
                    "subject": "We got your idea! ⚡",
                    "html": f"""
                    <p>Hey {body.get('name', 'there')},</p>
                    <p>Thanks for suggesting <strong>{body.get('title')}</strong>. We read every idea and build based on what matters most to our users.</p>
                    <p>We'll be in touch if we move forward with this one.</p>
                    <p>—<br>The Printssistant Team</p>
                    """,
                })
                print(f"Confirmation email sent to {body.get('email', '')}")
            except Exception as e:
                print(f"Error sending confirmation email: {e}")

            # Notify admin
            try:
                resend.Emails.send({
                    "from": "dev@printssistant.com",
                    "to": "ben.martinec@gmail.com",
                    "subject": f"💡 New idea: {body.get('title', '')}",
                    "html": f"""
                    <p><strong>From:</strong> {body.get('name', 'Anonymous')} ({body.get('email', '')})</p>
                    <p><strong>Title:</strong> {body.get('title', '')}</p>
                    <p><strong>Frequency:</strong> {body.get('impact', '')}</p>
                    <p><strong>Description:</strong><br>{body.get('description', '')}</p>
                    """,
                })
            except Exception as e:
                print(f"Error sending admin notification: {e}")

        return {
            "message": "Thank you! Your idea has been submitted.",
            "title": body.get("title", "")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing suggestion: {e}")
        raise HTTPException(status_code=500, detail="Error processing suggestion")


@app.post("/api/suggest-idea")
async def suggest_idea(request: Request, current_user: Optional[dict] = Depends(get_optional_user)):
    """Submit a quick idea suggestion (from modal popup)."""
    try:
        body = await request.json()
        idea = body.get("idea", "").strip()

        if not idea:
            raise HTTPException(status_code=400, detail="Idea cannot be empty")

        # Get email from logged-in user or use Anonymous
        email = current_user.get("email", "anonymous@printssistant.com") if current_user else "anonymous@printssistant.com"

        # Store in Supabase
        idea_data = {
            "name": "Anonymous",
            "email": email,
            "title": idea[:100],  # First 100 chars as title
            "description": idea,
            "impact": "not specified",
            "submitted_at": datetime.utcnow().isoformat(),
            "status": "new",
        }

        try:
            supabase.table("suggestions").insert(idea_data).execute()
        except Exception as e:
            print(f"Error storing idea: {e}")
            print(f"💡 Quick idea received: {idea[:100]} from {email}")

        if resend_available and os.environ.get("RESEND_API_KEY"):
            try:
                resend.api_key = os.environ.get("RESEND_API_KEY")
                resend.Emails.send({
                    "from": "dev@printssistant.com",
                    "to": "ben.martinec@gmail.com",
                    "subject": "💡 New quick idea submitted",
                    "html": f"""
                    <p><strong>From:</strong> {email}</p>
                    <p><strong>Idea:</strong><br>{idea}</p>
                    """,
                })
            except Exception as e:
                print(f"Error sending admin notification: {e}")

        return {"status": "success", "message": "Thanks! Your idea has been submitted."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing idea: {e}")
        raise HTTPException(status_code=500, detail="Error processing idea")


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/auth/signup")
@limiter.limit("10/minute")
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

    user_type = body.get("user_type", "").strip().lower()
    if user_type not in ("og", "dg"):
        user_type = None  # will be set during onboarding

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    supabase.table("users").insert({
        "id": user_id,
        "email": email,
        "password_hash": password_hash,
        "is_pro": False,
        "monthly_jobs": 0,
        "user_type": user_type,
        "created_at": now,
        "updated_at": now,
    }).execute()

    token = create_access_token(user_id, email)
    return {
        "access_token": token,
        "email": email,
        "is_pro": False,
        "monthly_jobs": 0,
        "user_type": user_type,
    }


@app.post("/auth/signin")
@limiter.limit("10/minute")
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
    
    print(f"[DEBUG] resend_available: {resend_available}, RESEND_API_KEY set: {bool(os.environ.get('RESEND_API_KEY'))}")
    
    if resend_available and os.environ.get("RESEND_API_KEY"):
        try:
            print(f"[DEBUG] Attempting to send reset email to {email}")
            resend.api_key = os.environ.get("RESEND_API_KEY")
            result = resend.Emails.send({
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
            print(f"[DEBUG] Email sent successfully: {result}")
        except Exception as e:
            print(f"❌ Error sending reset email: {type(e).__name__}: {e}")
    else:
        print(f"⚠️  Resend not configured (available={resend_available}, has_key={bool(os.environ.get('RESEND_API_KEY'))})")
        print(f"⚠️  Reset token for {email}: {reset_url}")
        print("(Copy the link above to test.)")

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
    """Returns current user info including profile fields."""
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "is_pro": user.get("is_pro", False),
        "monthly_jobs": user.get("monthly_jobs", 0),
        "user_type": user.get("user_type"),
        "company_name": user.get("company_name"),
        "bio": user.get("bio"),
        "profile_image_url": user.get("profile_image_url"),
        "location": user.get("location"),
        "social_links": user.get("social_links") or {},
        "is_verified": user.get("is_verified", False),
    }


# ── Profile ───────────────────────────────────────────────────────────────────

@app.get("/profile")
async def profile_page():
    return FileResponse(BASE_DIR / "static" / "profile.html")


@app.get("/profile/{user_id}")
async def public_profile_page(user_id: str):
    return FileResponse(BASE_DIR / "static" / "profile.html")


@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    """Public profile — safe fields only."""
    profile = get_public_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@app.put("/api/profile")
async def update_profile(request: Request, user: dict = Depends(get_current_user)):
    """Update the logged-in user's profile fields."""
    body = await request.json()

    # Validate user_type if provided
    user_type = body.get("user_type")
    if user_type is not None and user_type not in ("og", "dg"):
        raise HTTPException(status_code=400, detail="user_type must be 'og' or 'dg'")

    # Enforce bio length
    bio = body.get("bio")
    if bio and len(bio) > 250:
        raise HTTPException(status_code=400, detail="Bio must be 250 characters or fewer")

    # Validate social_links shape if provided
    social_links = body.get("social_links")
    if social_links is not None:
        allowed_keys = {"linkedin", "twitter", "website"}
        if not isinstance(social_links, dict) or not set(social_links.keys()).issubset(allowed_keys):
            raise HTTPException(status_code=400, detail="social_links must contain only: linkedin, twitter, website")

    fields = {}
    for key in ("user_type", "company_name", "bio", "profile_image_url", "location", "social_links"):
        if key in body:
            fields[key] = body[key]

    if not fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    update_user_profile(user["id"], fields)
    return {"status": "ok"}


# ── DG Preflight ──────────────────────────────────────────────────────────────

PREFLIGHT_FREE_LIMIT_MONTH = 5
PREFLIGHT_ANON_LIMIT_DAY = 1
PREFLIGHT_MAX_SIZE_FREE = 10 * 1024 * 1024   # 10 MB
PREFLIGHT_MAX_SIZE_PRO  = 50 * 1024 * 1024   # 50 MB


@app.get("/preflight")
async def preflight_page():
    return FileResponse(BASE_DIR / "static" / "preflight.html")


@app.get("/preflight/{job_id}")
async def preflight_result_page(job_id: str):
    """Serve the same preflight page; JS reads job_id from the URL."""
    return FileResponse(BASE_DIR / "static" / "preflight.html")


@app.post("/api/preflight")
async def run_preflight_check(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    credentials = Depends(security),
):
    """
    Upload a PDF and run all 5 preflight checks.
    Returns {job_id, results, overall, page_count} immediately.
    PDF bytes are discarded right after processing.

    Rate limits:
      - Anonymous (no token):  1 check / IP / day
      - Free user:             5 checks / month
      - Pro user:              unlimited
    """
    ip = request.client.host if request.client else "unknown"

    # Resolve auth (optional — anonymous is allowed)
    user = None
    is_pro = False
    if credentials:
        try:
            from auth import SECRET_KEY, ALGORITHM
            from jose import jwt as jose_jwt
            payload = jose_jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                from db import get_user_record
                user = get_user_record(user_id)
                is_pro = (user or {}).get("is_pro", False)
        except Exception:
            pass  # treat as anonymous if token is bad

    max_size = PREFLIGHT_MAX_SIZE_PRO if is_pro else PREFLIGHT_MAX_SIZE_FREE

    # ── File size gate ────────────────────────────────────────────────────────
    pdf_bytes = await file.read()
    file_size = len(pdf_bytes)

    # ── PDF magic byte validation ─────────────────────────────────────────────
    if pdf_bytes[:4] != b'%PDF':
        raise HTTPException(status_code=400, detail="Invalid PDF file. File does not appear to be a valid PDF.")

    if file_size > max_size:
        limit_mb = max_size // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Limit is {limit_mb} MB {'for Pro' if is_pro else '— upgrade to Pro for 50 MB'}.",
        )

    if file.content_type and "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # ── Quota check ───────────────────────────────────────────────────────────
    if not is_pro:
        if user:
            month_count = get_preflight_count_month(user["id"])
            if month_count >= PREFLIGHT_FREE_LIMIT_MONTH:
                raise HTTPException(
                    status_code=429,
                    detail=f"Free tier allows {PREFLIGHT_FREE_LIMIT_MONTH} preflight checks per month. Upgrade to Pro for unlimited.",
                )
        else:
            day_count = get_preflight_count_today(ip)
            if day_count >= PREFLIGHT_ANON_LIMIT_DAY:
                raise HTTPException(
                    status_code=429,
                    detail="Anonymous users get 1 free preflight check per day. Sign up for more.",
                )

    # ── Create job record ─────────────────────────────────────────────────────
    user_id = (user or {}).get("id")
    job_id = create_preflight_job(
        user_id=user_id,
        ip_address=ip,
        filename=file.filename or "upload.pdf",
        file_size=file_size,
    )

    # ── Run checks (synchronous but fast enough for request cycle) ─────────
    try:
        preflight_result = await asyncio.to_thread(run_preflight, pdf_bytes, file_size)
    except Exception as exc:
        fail_preflight_job(job_id, str(exc))
        raise HTTPException(status_code=500, detail="Preflight processing failed.")
    finally:
        del pdf_bytes  # discard immediately — GDPR compliance

    if "error" in preflight_result:
        fail_preflight_job(job_id, preflight_result["error"])
        raise HTTPException(status_code=422, detail=preflight_result["error"])

    # Store page_count in results for display
    complete_preflight_job(job_id, preflight_result)

    # Increment quota counters
    if not is_pro:
        if not user:
            background_tasks.add_task(increment_preflight_ip, ip)

    return {
        "job_id": job_id,
        "filename": file.filename,
        **preflight_result,
    }


@app.get("/api/preflight/{job_id}")
async def get_preflight_result(job_id: str):
    """Fetch a completed preflight result by job ID (shareable link)."""
    job = get_preflight_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Preflight result not found.")
    if job.get("status") == "expired":
        raise HTTPException(status_code=410, detail="This preflight result has expired.")
    return job


@app.get("/api/preflight/quota")
async def get_preflight_quota(request: Request, credentials = Depends(security)):
    """
    Get remaining preflight checks for current user/IP.
    Returns: {tier, remaining, limit}
    """
    ip = request.client.host if request.client else "unknown"
    
    # Resolve auth (optional — anonymous is allowed)
    user = None
    is_pro = False
    if credentials:
        try:
            from auth import SECRET_KEY, ALGORITHM
            from jose import jwt as jose_jwt
            payload = jose_jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                from db import get_user_record
                user = get_user_record(user_id)
                is_pro = (user or {}).get("is_pro", False)
        except Exception:
            pass  # treat as anonymous if token is bad
    
    if user and is_pro:
        # Pro users: unlimited
        return {
            "tier": "pro",
            "remaining": 999999,  # effectively unlimited
            "limit": 999999
        }
    elif user:
        # Free users: 5 per month
        used = get_preflight_count_month(user["id"])
        remaining = max(0, PREFLIGHT_FREE_LIMIT_MONTH - used)
        return {
            "tier": "free",
            "remaining": remaining,
            "limit": PREFLIGHT_FREE_LIMIT_MONTH
        }
    else:
        # Anonymous: 1 per day per IP
        used = get_preflight_count_today(ip)
        remaining = max(0, PREFLIGHT_ANON_LIMIT_DAY - used)
        return {
            "tier": "anonymous",
            "remaining": remaining,
            "limit": PREFLIGHT_ANON_LIMIT_DAY
        }


@app.post("/api/preflight/{job_id}/report")
async def generate_preflight_report(job_id: str):
    """
    Generate and return a PDF report of preflight check results.
    Report includes: filename, check date, all 5 check results with status.
    """
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    
    job = get_preflight_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Preflight job not found")
    if job.get("status") == "expired":
        raise HTTPException(status_code=410, detail="This preflight result has expired")
    
    # Try to generate PDF with reportlab (graceful fallback if not installed)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib import colors
        
        buffer = BytesIO()
        c = pdf_canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "Printssistant Preflight Report")
        
        # Filename
        c.setFont("Helvetica", 10)
        c.drawString(50, height - 80, f"File: {job.get('filename', 'unknown')}")
        
        # Date
        created_at = job.get('created_at', 'unknown')
        c.drawString(50, height - 100, f"Date: {created_at}")
        
        # Results section
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, height - 130, "Validation Results:")
        
        y = height - 160
        results = job.get('results', {})
        for check_name, check_result in results.items():
            status = check_result.get('status', 'unknown').upper()
            message = check_result.get('message', '')
            
            # Status color coding (text only, no actual colors in this basic impl)
            status_text = f"[{status}] {check_name}: {message}"
            c.setFont("Helvetica", 10)
            c.drawString(70, y, status_text)
            y -= 20
        
        # Footer
        c.setFont("Helvetica", 8)
        c.drawString(50, 30, "Generated by Printssistant | https://printssistant.com")
        
        c.save()
        buffer.seek(0)
        
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=preflight_report_{job_id}.pdf"}
        )
    
    except ImportError:
        # reportlab not available, return JSON fallback
        return JSONResponse({
            "filename": job.get('filename'),
            "created_at": job.get('created_at'),
            "results": job.get('results'),
            "note": "PDF generation unavailable. Download JSON report above."
        })


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
    import time
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_PDF_SIZE // (1024*1024)} MB."
        )

    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as buffer:
        buffer.write(file_content)

    output_filename = f"duplex_{safe_name}"
    output_path = PROCESSED_DIR / output_filename

    # Run CPU-intensive duplexer in thread pool to avoid blocking event loop
    start_time = time.time()
    success = await asyncio.to_thread(make_duplex, file_path, output_path)
    processing_ms = int((time.time() - start_time) * 1000)

    if success:
        increment_job_count(user["id"])
        # Log job history in background (non-blocking)
        background_tasks.add_task(log_job_history, user["id"], "duplexer", file_size, processing_ms)
        # Clean up original upload after response
        background_tasks.add_task(cleanup_files, file_path)
        # Keep processed file briefly so /download/{filename} can fetch it.
        background_tasks.add_task(cleanup_files_later, DOWNLOAD_RETENTION_SECONDS, output_path)
        return {"status": "success", "filename": output_filename}
    else:
        # Clean up on error too
        background_tasks.add_task(cleanup_files, file_path)
        return {"status": "error", "message": "Failed to process PDF"}


@app.post("/crop")
async def crop_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("grid"),
    rows: int = Form(2, ge=1, le=100),
    cols: int = Form(2, ge=1, le=100),
    user: dict = Depends(check_free_limit),
):
    import time
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_PDF_SIZE // (1024*1024)} MB."
        )

    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as buffer:
        buffer.write(file_content)

    start_time = time.time()
    if mode == "reader_spreads":
        output_filename = await asyncio.to_thread(process_reader_spreads, file_path, PROCESSED_DIR)
    else:
        output_filename = await asyncio.to_thread(process_auto_crop, file_path, PROCESSED_DIR, rows, cols)
    processing_ms = int((time.time() - start_time) * 1000)

    if not output_filename:
        background_tasks.add_task(cleanup_files, file_path)
        return JSONResponse(status_code=500, content={"status": "error", "message": "Crop produced no output"})

    increment_job_count(user["id"])
    background_tasks.add_task(log_job_history, user["id"], "cropper", file_size, processing_ms)
    background_tasks.add_task(cleanup_files, file_path)
    background_tasks.add_task(
        cleanup_files_later, DOWNLOAD_RETENTION_SECONDS, PROCESSED_DIR / output_filename
    )
    return {"status": "success", "filename": output_filename}


@app.post("/insert")
async def insert_pdf(
    background_tasks: BackgroundTasks,
    base_file: UploadFile = File(...),
    insert_file: UploadFile = File(...),
    interval: int = Form(..., ge=1),
    user: dict = Depends(check_free_limit),
):
    import time
    # Read and validate base file size
    base_content = await base_file.read()
    if len(base_content) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Base file too large. Maximum size is {MAX_PDF_SIZE // (1024*1024)} MB."
        )

    # Read and validate insert file size
    insert_content = await insert_file.read()
    if len(insert_content) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Insert file too large. Maximum size is {MAX_PDF_SIZE // (1024*1024)} MB."
        )

    base_path = UPLOAD_DIR / Path(base_file.filename).name
    with open(base_path, "wb") as buffer:
        buffer.write(base_content)

    insert_path = UPLOAD_DIR / Path(insert_file.filename).name
    with open(insert_path, "wb") as buffer:
        buffer.write(insert_content)

    output_filename = f"inserted_{Path(base_file.filename).name}"
    output_path = PROCESSED_DIR / output_filename

    total_file_size = len(base_content) + len(insert_content)
    start_time = time.time()
    success = await asyncio.to_thread(insert_pages, base_path, insert_path, output_path, interval=interval, positions=[])
    processing_ms = int((time.time() - start_time) * 1000)

    if success:
        increment_job_count(user["id"])
        # Log job history in background
        background_tasks.add_task(log_job_history, user["id"], "insert", total_file_size, processing_ms)
        # Clean up original upload files after response
        background_tasks.add_task(cleanup_files, base_path, insert_path)
        # Keep processed file briefly so /download/{filename} can fetch it.
        background_tasks.add_task(cleanup_files_later, DOWNLOAD_RETENTION_SECONDS, output_path)
        return {"status": "success", "filename": output_filename}
    else:
        # Clean up on error too
        background_tasks.add_task(cleanup_files, base_path, insert_path)
        return {"status": "error", "message": "Failed to process PDF"}


# ── Free / Open Tools ─────────────────────────────────────────────────────────

@app.post("/evenodd")
async def get_even_odd(
    start: int = Form(..., ge=0, le=1000000),
    end: int = Form(..., ge=0, le=1000000),
    type: str = Form(...),
):
    """Even/Odd generator — open to all, no auth required."""
    if start > end:
        raise HTTPException(status_code=400, detail="start must be less than or equal to end")

    is_even = True if type == "even" else False
    result_string = generate_even_odd(start, end, is_even)
    return {"status": "success", "result": result_string}


# ── Pro-Only Tools ────────────────────────────────────────────────────────────

@app.post("/vectorize")
async def vectorize_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    preset: str = Form("laser_bw"),
    user: dict = Depends(require_pro),
):
    import time
    preset_config = get_preset(preset)
    if not preset_config:
        return {"status": "error", "message": f"Unknown preset: {preset}"}

    image_bytes = await file.read()
    file_size = len(image_bytes)
    if file_size > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Image file too large. Maximum size is {MAX_IMAGE_SIZE // (1024*1024)} MB."
        )

    try:
        start_time = time.time()
        result = await asyncio.to_thread(vectorizer_engine.vectorize, image_bytes, preset_config)
        processing_ms = int((time.time() - start_time) * 1000)

        timestamp = int(time.time())
        basename = os.path.splitext(Path(file.filename).name)[0]
        svg_filename = f"{basename}_{preset}_{timestamp}.svg"
        svg_path = PROCESSED_DIR / svg_filename

        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(result["svg"])

        # Log job history in background
        background_tasks.add_task(log_job_history, user["id"], "vectorizer", file_size, processing_ms)
        # Keep file briefly so /download/{filename} can fetch it.
        background_tasks.add_task(cleanup_files_later, DOWNLOAD_RETENTION_SECONDS, svg_path)

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
    background_tasks: BackgroundTasks,
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
    ref_size = 0
    if reference_image and reference_image.filename:
        ref_bytes = await reference_image.read()
        ref_size = len(ref_bytes)
        if ref_size > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Reference image too large. Maximum size is {MAX_IMAGE_SIZE // (1024*1024)} MB."
            )

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    ext = "eps" if output_format == "eps" else "pdf"
    output_path = PROCESSED_DIR / f"swatchset_{timestamp}.{ext}"

    start_time = time.time()
    success = await asyncio.to_thread(
        generate_swatchset,
        output_path=output_path,
        base_c=base_c, base_m=base_m, base_y=base_y, base_k=base_k,
        goal_type=goal_type,
        goal_r=goal_r, goal_g=goal_g, goal_b=goal_b,
        goal_hex=goal_hex,
        goal_pantone=goal_pantone,
        reference_image_bytes=ref_bytes,
        output_format=output_format,
    )
    processing_ms = int((time.time() - start_time) * 1000)


    if success:
        # Log job history in background
        background_tasks.add_task(log_job_history, user["id"], "swatchset", ref_size, processing_ms)
        # Keep processed file briefly so /download/{filename} can fetch it.
        background_tasks.add_task(cleanup_files_later, DOWNLOAD_RETENTION_SECONDS, output_path)
        return {"status": "success", "filename": output_path.name}
    fmt_label = "EPS" if output_format == "eps" else "PDF"
    return {"status": "error", "message": f"Failed to generate swatch set {fmt_label}"}


# ── Health & Monitoring ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint for Railway and load balancers."""
    return {"status": "ok"}


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


# ── Global Exception Handler ─────────────────────────────────────────────────
import logging
import traceback

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler that sanitizes stack traces from HTTP responses
    while logging the full trace internally for debugging.
    """
    # Log full exception server-side
    logger.error(f"Unhandled exception: {traceback.format_exc()}")
    
    # Return sanitized response to client (no stack trace)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "An internal error occurred. Please try again later."}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
