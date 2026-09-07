# Importamos las librerias necesarias
from fastapi import Depends, HTTPException, Request # Dependencias de FastAPI para inyectar la sesión de BD y lanzar errores HTTP
from sqlalchemy import func # Para comparar el correo sin distinguir mayúsculas
from sqlalchemy.orm import Session # Tipado de la sesión de SQLAlchemy que recibimos por inyección
from app.db.session import get_db # Dependencia que nos entrega una sesión de base de datos por request
from app.models.legacy import User # Modelo User para tipar el usuario autenticado
from app.core.config import settings # Nombre de la cookie de sesión
from app.core.logging import get_logger # Para registrar el enlace con Supabase
from app.core.supabase_auth import decode_claims # Leer los claims del token de Supabase Auth

# Creamos el logger de este módulo
logger = get_logger(__name__)

# Mantenemos el nombre histórico apuntando al valor configurable, para no romper
# los módulos que ya lo importaban.
WEB_COOKIE_NAME = settings.SESSION_COOKIE_NAME

# Declaramos esta excepción para señalar que el usuario no está autenticado (o dejó de estarlo)
class NotAuthenticatedException(Exception):
    # Excepción personalizada para indicar que el usuario no está autenticado
    pass

# Resolvemos la fila local de users que corresponde a un usuario de Supabase Auth
def resolve_local_user(db: Session, claims: dict) -> User:
    # El claim "sub" es el uuid del usuario en auth.users
    auth_user_id = claims.get("sub")

    # Sin identificador no podemos resolver a nadie
    if not auth_user_id:
        raise NotAuthenticatedException()

    # Buscamos primero por el enlace ya establecido, que es el camino normal
    user = db.query(User).filter(User.auth_user_id == auth_user_id).first()

    # La primera vez que alguien entra con una cuenta anterior a Supabase el
    # enlace todavía no existe: lo establecemos por correo, que es único.
    if user is None:
        # Leemos el correo del token
        email = (claims.get("email") or "").strip()

        # Sin correo no hay forma de identificar la fila local
        if not email:
            raise NotAuthenticatedException()

        # Comparamos en minúsculas, igual que el índice único de la tabla
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()

        # Un usuario de Supabase sin fila local no tiene perfil en esta app
        if user is None:
            raise NotAuthenticatedException()

        # Dejamos el enlace hecho para que las siguientes peticiones no repitan la búsqueda
        user.auth_user_id = auth_user_id
        db.commit()

        # Registramos el enlace, que ocurre una sola vez por usuario
        logger.info(f"[auth] Linked local user {user.username} to Supabase auth id")

    # Verificamos que el usuario siga activo en esta app
    if not user.is_active:
        raise NotAuthenticatedException()

    # Devolvemos la fila local, que es lo que espera el resto de la aplicación
    return user

# Definimos la dependencia que obtiene el usuario autenticado a partir de la cookie de sesión
def get_current_user_web(request: Request, db: Session = Depends(get_db)) -> User:
    # Leemos el token de Supabase desde la cookie httpOnly
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)

    # Si no hay token, consideramos que no hay sesión iniciada
    if not token:
        # Lanzamos la excepción para que el handler global redirija al login
        raise NotAuthenticatedException()

    # Leemos los claims; devuelve None si el token venció o está malformado
    claims = decode_claims(token)

    # Si el token no es válido, la sesión terminó
    if claims is None:
        # Lanzamos la excepción porque el token no es válido
        raise NotAuthenticatedException()

    # Traducimos la identidad de Supabase a la fila local de users
    return resolve_local_user(db, claims)

# Definimos la dependencia que exige que el usuario autenticado sea administrador
def get_current_admin_web(current_user: User = Depends(get_current_user_web)) -> User:
    # Verificamos que el usuario tenga el flag de administrador
    if not current_user.is_admin:
        # Rechazamos el acceso con un 403 si no es administrador
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Devolvemos el usuario porque ya confirmamos que es administrador
    return current_user


# Nombre comun con el que las cinco aplicaciones resuelven el perfil local
def _perfil_local(claims: dict):
    """El perfil local de esa sesion, o None si no lo hay.

    DDV lo resuelve con `resolve_local_user`, que ademas enlaza la cuenta de
    Supabase la primera vez y devuelve la fila del modelo. Las otras cuatro lo
    hacen con `_perfil_local`, que devuelve un diccionario.

    Este alias existe para que el patron se llame igual en las cinco: mismo
    trabajo con dos nombres es lo que hace que alguien nuevo no lo encuentre, y
    lo que hizo que el comparador de diferencias se equivocara al medirlo.

    Aqui no se lanza si no hay perfil: quien quiera el comportamiento estricto
    —cortar la sesion— sigue llamando a `resolve_local_user` directamente.
    """
    # La sesion se abre aqui, para respetar el contrato comun de las cinco:
    # todas reciben solo los claims. La version estricta —que ademas enlaza la
    # cuenta y corta si no hay perfil— sigue siendo resolve_local_user(db, claims).
    from app.db.session import db_manager

    try:
        with db_manager.session() as db:
            fila = resolve_local_user(db, claims)

            # Se devuelve un diccionario, no la fila: la sesión se cierra al
            # salir del `with` y una instancia desligada estallaría al leerla
            return {"id": fila.id, "full_name": fila.full_name,
                    "role": "admin" if fila.is_admin else "operador",
                    "is_admin": fila.is_admin}

    # Sin perfil, se devuelve None en vez de cortar, que es lo que hacen las
    # otras cuatro
    except Exception:
        return None
