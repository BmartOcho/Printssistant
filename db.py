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
