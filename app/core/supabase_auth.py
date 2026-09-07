"""Autenticación contra Supabase Auth (GoTrue).

A diferencia de la versión React, el token no vive en localStorage sino en una
cookie httpOnly: el navegador no puede leerlo desde JavaScript, y HTMX lo envía
solo porque el navegador adjunta cookies automáticamente.
"""

# Importamos las librerias necesarias
from typing import Any, Dict, Optional  # Para tipar respuestas y claims

import httpx  # Cliente HTTP para hablar con GoTrue
import jwt  # Para leer los claims del access token sin ir a la red

from app.core.config import settings  # URL y clave publicable del proyecto
from app.core.logging import get_logger  # Para registrar fallos de autenticación

# Creamos el logger de este módulo
logger = get_logger(__name__)


# Definimos el error que lanzamos cuando las credenciales no son válidas
class AuthError(Exception):
    """Credenciales inválidas o sesión no renovable."""


# Construimos la URL base del servicio de autenticación
def _auth_url(path: str) -> str:
    # Concatenamos el endpoint sobre la ruta /auth/v1 del proyecto
    return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1{path}"


# Armamos las cabeceras que GoTrue exige en toda llamada
def _headers() -> Dict[str, str]:
    # La clave publicable identifica al proyecto; no autoriza por sí sola
    return {
        "apikey": settings.SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
    }


# Intercambiamos usuario y contraseña por un par de tokens
async def sign_in(email: str, password: str) -> Dict[str, Any]:
    # Abrimos un cliente con timeout acotado para no colgar el request
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Pedimos el grant de tipo password
        response = await client.post(
            _auth_url("/token?grant_type=password"),
            headers=_headers(),
            json={"email": email, "password": password},
        )

    # Cualquier respuesta no exitosa la tratamos como credenciales inválidas
    if response.status_code != 200:
        # Registramos el motivo real para poder depurar, sin exponerlo al usuario
        logger.warning(f"Supabase sign_in failed ({response.status_code}): {response.text[:200]}")

        # Lanzamos un error genérico: no revelamos si el correo existe o no
        raise AuthError("Usuario o contraseña incorrectos")

    # Devolvemos el cuerpo con access_token, refresh_token y user
    return response.json()


# Canjeamos un refresh token por un access token nuevo
async def refresh_session(refresh_token: str) -> Dict[str, Any]:
    # Abrimos un cliente con timeout acotado
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Pedimos el grant de tipo refresh_token
        response = await client.post(
            _auth_url("/token?grant_type=refresh_token"),
            headers=_headers(),
            json={"refresh_token": refresh_token},
        )

    # Si el refresh no sirve, la sesión terminó y hay que volver a entrar
    if response.status_code != 200:
        # Registramos el motivo para depuración
        logger.info(f"Supabase refresh failed ({response.status_code})")

        # Lanzamos el error para que el llamador limpie las cookies
        raise AuthError("La sesión expiró")

    # Devolvemos el cuerpo con los tokens renovados
    return response.json()


# Cerramos la sesión del lado de Supabase para invalidar el refresh token
async def sign_out(access_token: str) -> None:
    # Abrimos un cliente con timeout acotado
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Avisamos a GoTrue; si falla, igual borraremos las cookies localmente
        try:
            # Enviamos el logout autenticado con el propio access token
            await client.post(
                _auth_url("/logout"),
                headers={**_headers(), "Authorization": f"Bearer {access_token}"},
            )
        # Un logout fallido no debe impedir que el usuario salga
        except httpx.HTTPError as exc:
            # Registramos el problema y seguimos
            logger.info(f"Supabase logout call failed, clearing cookies anyway: {exc}")


# Leemos los claims de un access token sin validar la firma contra la red
def decode_claims(access_token: str) -> Optional[Dict[str, Any]]:
    # Un token vacío no tiene claims que leer
    if not access_token:
        return None

    # Intentamos decodificar comprobando solo la expiración
    try:
        # Supabase firma con HS256 usando un secreto que el servidor de la app no
        # tiene; validamos vigencia aquí y dejamos la validación criptográfica real
        # a PostgREST/RLS, que sí verifica la firma en cada consulta.
        return jwt.decode(
            access_token,
            options={"verify_signature": False, "verify_exp": True},
            algorithms=["HS256"],
        )
    # Un token vencido o malformado se trata como ausencia de sesión
    except jwt.PyJWTError:
        # Devolvemos None para que el llamador intente refrescar
        return None
