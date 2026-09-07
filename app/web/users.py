# Importamos json para armar la cabecera HX-Trigger que dispara los toasts en el cliente
import json

# Importamos las clases de FastAPI para el router, inyección de dependencias, forms y requests
from fastapi import APIRouter, Depends, Form, Request
# Importamos las respuestas HTML (fragmentos renderizados) y de redirección (ruta legacy /users)
from fastapi.responses import HTMLResponse, RedirectResponse
# Importamos el tipo de sesión de SQLAlchemy
from sqlalchemy.orm import Session

# Importamos las dependencias de autenticación: usuario admin y usuario autenticado
from app.core.deps import get_current_admin_web, get_current_user_web
# Importamos la función para hashear contraseñas
from app.core.security import get_password_hash
# Importamos el modelo User
from app.models.legacy import User
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos el objeto de templates Jinja de la app
from app.web.templating import templates, toast_header

# Creamos el router sin prefijo (se monta directamente en /users)
router = APIRouter()


def _users_context(db: Session, current_user: User, form_error: str | None = None) -> dict:
    # Obtenemos todos los usuarios ordenados por id
    users = db.query(User).order_by(User.id).all()
    # Devolvemos el contexto base para renderizar la sección de usuarios
    return {"users": users, "current_user": current_user, "form_error": form_error}


def _render_section(request: Request, db: Session, current_user: User, **extra):
    # Armamos el contexto de usuarios (con posible error de formulario)
    ctx = _users_context(db, current_user, **extra)
    # Agregamos el request, requerido por Jinja2Templates
    ctx["request"] = request
    # Renderizamos el fragmento parcial de la sección de usuarios
    return templates.TemplateResponse(request, "partials/users_section.html", ctx)


@router.get("/users")
async def users_page(current_user: User = Depends(get_current_user_web)):
    """Relocated into Ops Admin (Users). Redirect keeps old links working; the
    create/toggle/delete/password actions below (POST /users*) are unchanged."""
    # Redirigimos a la nueva ubicación de la página de usuarios
    return RedirectResponse(url="/admin/ops/users", status_code=307)


@router.post("/users", response_class=HTMLResponse)
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    email: str = Form(""),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_web),
):
    # Verificamos si ya existe un usuario con ese username
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        # Si ya existe, re-renderizamos la sección mostrando el error
        return _render_section(request, db, current_user, form_error="Username already exists")

    # Construimos el nuevo usuario, hasheando la contraseña antes de guardarla
    new_user = User(
        username=username,
        hashed_password=get_password_hash(password),
        full_name=full_name or None,
        email=email or None,
        is_admin=is_admin,
    )
    # Agregamos el usuario a la sesión y confirmamos
    db.add(new_user)
    db.commit()

    # Re-renderizamos la sección con la lista de usuarios actualizada
    response = _render_section(request, db, current_user)
    # Disparamos un toast de éxito en el cliente vía HX-Trigger
    response.headers["HX-Trigger"] = toast_header("User created successfully")
    return response


@router.post("/users/{user_id}/toggle-active", response_class=HTMLResponse)
async def toggle_active(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_web),
):
    # Buscamos el usuario por id
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # Invertimos el flag de activo/inactivo
        user.is_active = not user.is_active
        db.commit()
    # Re-renderizamos la sección con el estado actualizado
    response = _render_section(request, db, current_user)
    # Disparamos el toast indicando si quedó activado o desactivado
    response.headers["HX-Trigger"] = json.dumps(
        {"toast": {"message": f"User {'activated' if user and user.is_active else 'deactivated'}"}}
    )
    return response


@router.post("/users/{user_id}/toggle-admin", response_class=HTMLResponse)
async def toggle_admin(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_web),
):
    # Buscamos el usuario por id
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # Invertimos el flag de administrador
        user.is_admin = not user.is_admin
        db.commit()
    # Re-renderizamos la sección con el estado actualizado
    response = _render_section(request, db, current_user)
    # Disparamos el toast indicando si se otorgó o quitó el rol admin
    response.headers["HX-Trigger"] = json.dumps(
        {"toast": {"message": f"Admin {'granted' if user and user.is_admin else 'removed'}"}}
    )
    return response


@router.post("/users/{user_id}/password", response_class=HTMLResponse)
async def update_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_web),
):
    # Buscamos el usuario por id
    user = db.query(User).filter(User.id == user_id).first()
    # Preparamos el mensaje de éxito por defecto
    toast_message = "Password updated"
    if not user:
        # Si el usuario no existe, avisamos en el toast
        toast_message = "User not found"
    elif len(new_password) < 6:
        # Validamos el largo mínimo de la contraseña
        toast_message = "Password must be at least 6 characters"
    else:
        # Actualizamos el hash de la contraseña y confirmamos
        user.hashed_password = get_password_hash(new_password)
        db.commit()

    # Re-renderizamos la sección de usuarios
    response = _render_section(request, db, current_user)
    # Disparamos el toast con el resultado de la operación
    response.headers["HX-Trigger"] = toast_header(toast_message)
    return response


@router.delete("/users/{user_id}", response_class=HTMLResponse)
async def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_web),
):
    # Preparamos el toast de éxito por defecto
    toast = {"message": "User deleted"}
    if user_id == current_user.id:
        # Evitamos que un admin se elimine a sí mismo
        toast = {"message": "Cannot delete yourself", "type": "error"}
    else:
        # Buscamos el usuario a eliminar
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            # Lo eliminamos y confirmamos
            db.delete(user)
            db.commit()
        else:
            # Si no existe, avisamos con un toast de error
            toast = {"message": "User not found", "type": "error"}

    # Re-renderizamos la sección de usuarios
    response = _render_section(request, db, current_user)
    # Disparamos el toast con el resultado de la operación
    response.headers["HX-Trigger"] = json.dumps({"toast": toast})
    return response
