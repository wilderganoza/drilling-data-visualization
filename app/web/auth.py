# Importamos las clases de FastAPI para el router, inyección de dependencias, formularios y la request
from fastapi import APIRouter, Depends, Form, Request, Response
# Importamos la respuesta de redirección para después del login/logout
from fastapi.responses import RedirectResponse
# Importamos Session para tipar la sesión de base de datos
from sqlalchemy.orm import Session

# Importamos la configuración de la app (nombres de cookies, flags de seguridad)
from app.core.config import settings
# Importamos la dependencia que resuelve el usuario autenticado
from app.core.deps import get_current_user_web
# Importamos las operaciones contra Supabase Auth
from app.core.supabase_auth import AuthError, sign_in, sign_out
# Importamos el logger de la app
from app.core.logging import get_logger
# Importamos la dependencia que nos entrega una sesión de base de datos
from app.db.session import get_db
# Importamos las plantillas Jinja2 para renderizar la página de login
from app.web.templating import templates

# Creamos el logger específico de este módulo
logger = get_logger(__name__)
# Creamos el router de autenticación
router = APIRouter()

# Definimos cuánto dura la cookie de refresh, en segundos (30 días)
REFRESH_MAX_AGE = 30 * 24 * 60 * 60


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


def _set_session_cookies(response: Response, access_token: str, refresh_token: str, expires_in: int) -> None:
    """Guardamos los tokens de Supabase en cookies httpOnly: el navegador los envía
    solo, y JavaScript no puede leerlos."""
    # El access token dura lo que diga Supabase (típicamente una hora)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=access_token,
        max_age=expires_in,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

    # El refresh token dura mucho más y sirve para renovar la sesión
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_MAX_AGE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    # Eliminamos ambas cookies con el mismo path con que se crearon
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")


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
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/wells"),
):
    # Intentamos autenticar contra Supabase Auth, que es el proveedor de identidad
    try:
        # Pedimos el par de tokens
        session = await sign_in(email.strip(), password)
    # Credenciales inválidas: volvemos a mostrar el formulario con el error
    except AuthError as exc:
        # Devolvemos 401 para que quede registrado en los logs de acceso
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {"error": str(exc), "next": next},
            status_code=401,
        )

    # Registramos en el log que el usuario inició sesión
    logger.info(f"[web] User logged in: {email.strip()}")

    # Preparamos la redirección hacia el destino solicitado (o /wells por defecto)
    response = RedirectResponse(url=_safe_next(next), status_code=302)

    # Guardamos los tokens en cookies httpOnly
    _set_session_cookies(
        response,
        session["access_token"],
        session["refresh_token"],
        session.get("expires_in", 3600),
    )

    # Devolvemos la respuesta de redirección con las cookies ya configuradas
    return response


# Definimos la ruta que cierra la sesión del usuario
@router.post("/logout")
async def logout(request: Request):
    # Recuperamos el access token para avisarle a Supabase
    token = request.cookies.get(settings.SESSION_COOKIE_NAME, "")

    # Invalidamos el refresh token del lado del servidor si había sesión
    if token:
        await sign_out(token)

    # Redirigimos a la página de login
    response = RedirectResponse(url="/login", status_code=302)

    # Borramos las cookies locales pase lo que pase
    _clear_session_cookies(response)

    return response
