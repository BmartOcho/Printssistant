import os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from db import supabase, get_user_record

FREE_TIER_LIMIT = 20  # jobs per month for free users

SECRET_KEY = os.environ.get("JWT_SECRET", "printssistant-secret-please-set-jwt-secret-env-var")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Validates our own JWT token (issued by /auth/signup or /auth/signin).
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        if not user_id or not email:
            raise ValueError("Invalid token payload")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
        )

    user_record = get_user_record(user_id)
    return user_record or {"id": user_id, "email": email, "is_pro": False, "monthly_jobs": 0}


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
