from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_web
from app.models.legacy import User
from app.db.session import get_db
from app.core.ops_roles import OpsRole
from app.models.roles import OpsUserRole


def _get_ops_role(db: Session, user_id: int) -> OpsRole | None:
    row = db.get(OpsUserRole, user_id)
    if row is None:
        return None
    try:
        return OpsRole(row.role)
    except ValueError:
        return None


def has_ops_role(db: Session, current_user: User, *allowed: OpsRole) -> bool:
    """Non-raising counterpart to require_ops_role(), for GET routes that must
    stay viewable by everyone but need to know whether to show edit/delete/
    approve controls at all — those were previously rendered unconditionally
    for every role (including READ_ONLY), 403-ing silently on click."""
    if current_user.is_admin:
        return True
    return _get_ops_role(db, current_user.id) in allowed


def require_ops_role(*allowed: OpsRole):
    """Dependency factory mirroring get_current_admin_web: gate a route to
    users holding one of `allowed` ops roles. A global admin (User.is_admin)
    always passes, without needing an ops role row of their own."""

    def _dep(current_user: User = Depends(get_current_user_web), db: Session = Depends(get_db)) -> User:
        if current_user.is_admin:
            return current_user
        role = _get_ops_role(db, current_user.id)
        if role not in allowed:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user

    return _dep
