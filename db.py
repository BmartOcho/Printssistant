import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError(
        "Missing required environment variables: "
        "SUPABASE_URL and SUPABASE_SERVICE_KEY must both be set."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_user_record(user_id: str) -> dict | None:
    """Fetch a user row from the public.users table."""
    result = supabase.table("users").select("*").eq("id", user_id).single().execute()
    return result.data if result.data else None


def upsert_user(user_id: str, email: str) -> None:
    """Create or update a user record (called after login/signup)."""
    supabase.table("users").upsert({
        "id": user_id,
        "email": email,
    }, on_conflict="id").execute()


def increment_job_count(user_id: str) -> int:
    """Increment monthly job counter. Returns new count."""
    import datetime
    user = get_user_record(user_id)
    if not user:
        return 0

    # Reset counter if it's a new month
    reset_at = user.get("monthly_jobs_reset")
    now = datetime.datetime.now(datetime.timezone.utc)
    if reset_at:
        reset_dt = datetime.datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
        if now.month != reset_dt.month or now.year != reset_dt.year:
            supabase.table("users").update({
                "monthly_jobs": 1,
                "monthly_jobs_reset": now.isoformat()
            }).eq("id", user_id).execute()
            return 1

    new_count = (user.get("monthly_jobs") or 0) + 1
    supabase.table("users").update({"monthly_jobs": new_count}).eq("id", user_id).execute()
    return new_count


# ── User Profiles ─────────────────────────────────────────────────────────────

def update_user_profile(user_id: str, fields: dict) -> None:
    """Update profile fields on the users table. Only writes provided keys."""
    import datetime
    fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Whitelist editable fields
    allowed = {"user_type", "company_name", "bio", "profile_image_url", "location", "social_links", "updated_at"}
    safe = {k: v for k, v in fields.items() if k in allowed}
    if safe:
        supabase.table("users").update(safe).eq("id", user_id).execute()


def get_public_profile(user_id: str) -> dict | None:
    """Fetch public-safe profile fields for a user."""
    result = (
        supabase.table("users")
        .select("id, email, user_type, company_name, bio, profile_image_url, location, social_links, is_verified, created_at")
        .eq("id", user_id)
        .single()
        .execute()
    )
    return result.data if result.data else None


# ── Preflight Jobs ─────────────────────────────────────────────────────────────

def create_preflight_job(user_id: str | None, ip_address: str, filename: str, file_size: int) -> str:
    """Insert a new preflight job with status='processing'. Returns the job id."""
    import datetime
    import uuid
    now = datetime.datetime.now(datetime.timezone.utc)
    job_id = str(uuid.uuid4())
    supabase.table("preflight_jobs").insert({
        "id": job_id,
        "user_id": user_id,
        "ip_address": ip_address,
        "filename": filename,
        "file_size": file_size,
        "status": "processing",
        "created_at": now.isoformat(),
        "expires_at": (now + datetime.timedelta(days=30)).isoformat(),
    }).execute()
    return job_id


def complete_preflight_job(job_id: str, results: dict) -> None:
    """Write check results and mark the job as completed."""
    import json
    supabase.table("preflight_jobs").update({
        "results": results,
        "status": "completed",
    }).eq("id", job_id).execute()


def fail_preflight_job(job_id: str, error: str) -> None:
    supabase.table("preflight_jobs").update({
        "status": "failed",
        "results": {"error": error},
    }).eq("id", job_id).execute()


def get_preflight_job(job_id: str, retries: int = 3) -> dict | None:
    """
    Fetch a preflight job by ID with retry logic for race conditions.

    When a share link is opened while the job is still processing,
    we retry up to `retries` times with 100ms delays to give the
    background task time to complete. Returns None if the job doesn't
    exist, or the job dict (which may include expired status).
    """
    import time
    import datetime

    for attempt in range(retries):
        result = (
            supabase.table("preflight_jobs")
            .select("id, user_id, filename, file_size, results, status, created_at, expires_at")
            .eq("id", job_id)
            .single()
            .execute()
        )
        if not result.data:
            return None

        job = result.data

        # Check expiry
        expires_at = job.get("expires_at")
        if expires_at:
            now = datetime.datetime.now(datetime.timezone.utc)
            exp_dt = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if now > exp_dt:
                job["status"] = "expired"
                return job

        # If still processing and we have retries left, wait and retry
        if job["status"] == "processing" and attempt < retries - 1:
            time.sleep(0.1)  # 100ms delay between retries
            continue

        return job

    return result.data if result.data else None


# ── Preflight Quota ────────────────────────────────────────────────────────────

def get_preflight_count_today(ip_address: str) -> int:
    """Returns how many preflight checks this IP has run today (UTC)."""
    import datetime
    today = datetime.date.today().isoformat()
    result = (
        supabase.table("preflight_checks")
        .select("check_count")
        .eq("ip_address", ip_address)
        .eq("check_date", today)
        .execute()
    )
    if result.data:
        return result.data[0]["check_count"]
    return 0


def get_preflight_count_month(user_id: str) -> int:
    """Returns how many preflight checks this user has run this calendar month."""
    import datetime
    # All rows for this user this month
    now = datetime.datetime.now(datetime.timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    result = (
        supabase.table("preflight_jobs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", month_start)
        .neq("status", "failed")
        .execute()
    )
    return result.count or 0


def increment_preflight_ip(ip_address: str) -> None:
    """Upsert daily IP-based preflight counter."""
    import datetime
    today = datetime.date.today().isoformat()
    existing = (
        supabase.table("preflight_checks")
        .select("id, check_count")
        .eq("ip_address", ip_address)
        .eq("check_date", today)
        .execute()
    )
    if existing.data:
        row_id = existing.data[0]["id"]
        new_count = existing.data[0]["check_count"] + 1
        supabase.table("preflight_checks").update({"check_count": new_count}).eq("id", row_id).execute()
    else:
        import uuid
        supabase.table("preflight_checks").insert({
            "id": str(uuid.uuid4()),
            "ip_address": ip_address,
            "check_date": today,
            "check_count": 1,
        }).execute()


def log_job_history(user_id: str, tool_name: str, file_size: int = 0, processing_ms: int = 0) -> None:
    """
    Log tool usage to job_history table for analytics.
    Non-blocking; errors are logged but don't raise exceptions.
    """
    try:
        import datetime
        supabase.table("job_history").insert({
            "user_id": user_id,
            "tool_name": tool_name,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "file_size": file_size,
            "processing_ms": processing_ms,
        }).execute()
    except Exception as e:
        # Silently log errors; don't crash the tool if logging fails
        print(f"⚠️  Failed to log job history: {e}")
