from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.core.security import get_password_hash
from app.core.deps import get_current_user, get_current_admin
from app.schemas.user import (
    UserCreate, UserUpdate, UserPasswordUpdate, UserResponse, UserListResponse
)
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=UserListResponse, summary="List all users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all users (requires authentication)."""
    users = db.query(User).offset(skip).limit(limit).all()
    total = db.query(User).count()
    return UserListResponse(
        total=total,
        users=[UserResponse.model_validate(u) for u in users]
    )


@router.post("/", response_model=UserResponse, summary="Create user")
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new user (admin only)."""
    existing = db.query(User).filter(User.username == user_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        email=user_data.email,
        is_admin=user_data.is_admin,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info(f"User created: {new_user.username}")
    return UserResponse.model_validate(new_user)


@router.get("/{user_id}", response_model=UserResponse, summary="Get user")
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse, summary="Update user")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    logger.info(f"User updated: {user.username}")
    return UserResponse.model_validate(user)


@router.put("/{user_id}/password", summary="Update user password")
async def update_user_password(
    user_id: int,
    password_data: UserPasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update user password (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    logger.info(f"Password updated for user: {user.username}")
    return {"message": "Password updated successfully"}


@router.delete("/{user_id}", summary="Delete user")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db.delete(user)
    db.commit()
    logger.info(f"User deleted: {user.username}")
    return {"message": "User deleted successfully"}
