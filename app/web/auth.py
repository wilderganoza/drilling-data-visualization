# Importamos las clases de FastAPI para el router, inyección de dependencias, formularios y la request
from fastapi import APIRouter, Depends, Form, Request
# Importamos la respuesta de redirección para después del login/logout
from fastapi.responses import RedirectResponse
# Importamos Session para tipar la sesión de base de datos
from sqlalchemy.orm import Session

# Importamos la configuración de la app (entorno, tiempo de expiración del token, etc.)
from app.core.config import settings
# Importamos el nombre de la cookie de sesión y la dependencia que resuelve el usuario autenticado
from app.core.deps import WEB_COOKIE_NAME, get_current_user_web
# Importamos las funciones para crear el token de acceso y verificar la contraseña
from app.core.security import create_access_token, verify_password
# Importamos el logger de la app
from app.core.logging import get_logger
# Importamos el modelo User para consultar las credenciales
from app.models.legacy import User
# Importamos la dependencia que nos entrega una sesión de base de datos
from app.db.session import get_db
# Importamos las plantillas Jinja2 para renderizar la página de login
from app.web.templating import templates

# Creamos el logger específico de este módulo
logger = get_logger(__name__)
# Creamos el router de autenticación
router = APIRouter()


def _safe_next(next: str) -> str:
    """Solo permitimos redirigir a una ruta relativa del propio sitio (empieza con
    "/" pero no con "//" o "/\\", que el navegador podría interpretar como
    protocol-relative hacia otro host) — evita un open redirect vía ?next=."""
    if next and next.startswith("/") and not next.startswith("//") and not next.startswith("/\\"):
        return next
    return "/wells"


def _is_authenticated(request: Request, db: Session) -> bool:
    try:
        # Intentamos resolver el usuario actual a partir de la cookie de sesión
        get_current_user_web(request, db)
        # Si no lanzó excepción, el usuario está autenticado
        return True
    except Exception:
        # Cualquier excepción (token ausente, inválido, usuario inactivo, etc.) significa que no está autenticado
        return False


# Definimos la ruta que muestra el formulario de login
@router.get("/login")
async def login_form(request: Request, next: str = "/wells", db: Session = Depends(get_db)):
    # Si el usuario ya tiene sesión iniciada, lo redirigimos directo al destino
    if _is_authenticated(request, db):
        return RedirectResponse(url=_safe_next(next), status_code=302)
    # Renderizamos el formulario de login sin error, guardando el destino para después de iniciar sesión
    return templates.TemplateResponse(
        request, "pages/login.html", {"error": None, "next": next}
    )


# Definimos la ruta que procesa el envío del formulario de login
@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/wells"),
    db: Session = Depends(get_db),
):
    # Buscamos al usuario por su username
    user = db.query(User).filter(User.username == username).first()
    # Validamos que exista, que la contraseña sea correcta y que esté activo
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        # Si falla cualquiera de las validaciones, volvemos a mostrar el formulario con un error
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {"error": "Invalid username or password", "next": next},
            status_code=401,
        )

    # Creamos el token de acceso con el username como claim "sub"
    token = create_access_token(data={"sub": user.username})
    # Registramos en el log que el usuario inició sesión
    logger.info(f"[web] User logged in: {user.username}")

    # Preparamos la redirección hacia el destino solicitado (o /wells por defecto)
    response = RedirectResponse(url=_safe_next(next), status_code=302)
    # Guardamos el token en una cookie httponly para mantener la sesión
    response.set_cookie(
        key=WEB_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    # Devolvemos la respuesta de redirección con la cookie ya configurada
    return response


# Definimos la ruta que cierra la sesión del usuario
@router.post("/logout")
async def logout():
    # Redirigimos a la página de login
    response = RedirectResponse(url="/login", status_code=302)
    # Eliminamos la cookie de sesión
    response.delete_cookie(WEB_COOKIE_NAME, path="/")
    return response
