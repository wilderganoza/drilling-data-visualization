from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.core.security import verify_password, create_access_token
from app.schemas.auth import LoginRequest, TokenResponse, UserInfo
from app.core.deps import get_current_user
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/login", response_model=TokenResponse, summary="Login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token = create_access_token(data={"sub": user.username})
    logger.info(f"User logged in: {user.username}")
    return TokenResponse(
        access_token=access_token,
        user=UserInfo.model_validate(user)
    )


@router.get("/me", response_model=UserInfo, summary="Get current user")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserInfo.model_validate(current_user)
