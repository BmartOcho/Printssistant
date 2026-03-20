from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from db import supabase, get_user_record, upsert_user

FREE_TIER_LIMIT = 20  # jobs per month for free users

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Validates the Bearer token from Supabase Auth.
    Returns the user dict (id, email, is_pro, monthly_jobs, etc.)
    Raises 401 if token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )

    token = credentials.credentials
    try:
        auth_response = supabase.auth.get_user(token)
        auth_user = auth_response.user
        if not auth_user:
            raise ValueError("No user in response")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
        )

    # Ensure user exists in our public.users table
    upsert_user(auth_user.id, auth_user.email)
    user_record = get_user_record(auth_user.id)

    return user_record or {"id": auth_user.id, "email": auth_user.email, "is_pro": False, "monthly_jobs": 0}


async def require_pro(user: dict = Depends(get_current_user)) -> dict:
    """Dependency for Pro-only endpoints. Raises 403 if not Pro."""
    if not user.get("is_pro"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires Printssistant Pro.",
        )
    return user


async def check_free_limit(user: dict = Depends(get_current_user)) -> dict:
    """Dependency for free-tier endpoints. Raises 429 if over monthly limit."""
    if user.get("is_pro"):
        return user  # Pro users have no limits
    if (user.get("monthly_jobs") or 0) >= FREE_TIER_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Free tier limit reached ({FREE_TIER_LIMIT} jobs/month). Upgrade to Pro for unlimited access.",
        )
    return user
