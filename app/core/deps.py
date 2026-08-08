# Importamos las librerias necesarias
from fastapi import Depends, HTTPException, Request # Dependencias de FastAPI para inyectar la sesión de BD y lanzar errores HTTP
from sqlalchemy.orm import Session # Tipado de la sesión de SQLAlchemy que recibimos por inyección
from app.db.session import get_db # Dependencia que nos entrega una sesión de base de datos por request
from app.models.legacy import User # Modelo User para tipar el usuario autenticado
from app.core.security import decode_access_token # Validar y leer el JWT guardado en la cookie

# Definimos el nombre de la cookie donde guardamos el token de acceso
WEB_COOKIE_NAME = "access_token"

# Declaramos esta excepción para señalar que el usuario no está autenticado (o dejó de estarlo)
class NotAuthenticatedException(Exception):
    # Excepción personalizada para indicar que el usuario no está autenticado
    pass

# Definimos la dependencia que obtiene el usuario autenticado a partir de la cookie de sesión
def get_current_user_web(request: Request, db: Session = Depends(get_db)) -> User:
    # Leemos el token desde la cookie de la request
    token = request.cookies.get(WEB_COOKIE_NAME)

    # Si no hay token, consideramos que no hay sesión iniciada
    if not token:
        # Lanzamos la excepción para que el handler global redirija al login
        raise NotAuthenticatedException()

    # Decodificamos el token para obtener su contenido (payload)
    payload = decode_access_token(token)

    # Si el token es inválido o expiró, decode_access_token nos devuelve None
    if payload is None:
        # Lanzamos la excepción porque el token no es válido
        raise NotAuthenticatedException()

    # Extraemos el username desde el claim "sub" del payload
    username = payload.get("sub")

    # Si el payload no trae username, el token está mal formado
    if username is None:
        # Lanzamos la excepción porque no podemos identificar al usuario
        raise NotAuthenticatedException()

    # Buscamos al usuario en la base de datos por su username
    user = db.query(User).filter(User.username == username).first()

    # Verificamos que el usuario exista y esté activo
    if user is None or not user.is_active:
        # Lanzamos la excepción porque el usuario no existe o fue desactivado
        raise NotAuthenticatedException()

    # Devolvemos el usuario autenticado para que la ruta lo reciba por inyección
    return user

# Definimos la dependencia que exige que el usuario autenticado sea administrador
def get_current_admin_web(current_user: User = Depends(get_current_user_web)) -> User:
    # Verificamos que el usuario tenga el flag de administrador
    if not current_user.is_admin:
        # Rechazamos el acceso con un 403 si no es administrador
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Devolvemos el usuario porque ya confirmamos que es administrador
    return current_user
