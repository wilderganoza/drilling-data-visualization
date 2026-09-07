# Importamos las librerias necesarias
from datetime import datetime, timedelta, timezone # Para calcular la fecha de expiración del token
from typing import Optional # Para tipar el token/expiración opcionales
import jwt # Para codificar y decodificar los JSON Web Tokens
from passlib.context import CryptContext # Para el hash y la verificación de contraseñas (bcrypt)
from app.core.config import settings # Configuración de la app (SECRET_KEY, algoritmo, expiración)

# Creamos el contexto de hashing, usando bcrypt como esquema
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Verificamos que una contraseña en texto plano coincida con su hash guardado
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Delegamos la comparación en bcrypt, que maneja el salt internamente
    return pwd_context.verify(plain_password, hashed_password)


# Generamos el hash de una contraseña para guardarlo en la base de datos
def get_password_hash(password: str) -> str:
    # Nunca guardamos la contraseña en texto plano, solo su hash
    return pwd_context.hash(password)


# Creamos un token de acceso JWT firmado para un usuario autenticado
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    # Copiamos el payload para no mutar el diccionario que nos pasaron
    to_encode = data.copy()

    # Calculamos cuándo expira el token (el delta recibido, o el default de configuración)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    # Agregamos el claim estándar "exp" con la fecha de expiración
    to_encode.update({"exp": expire})

    # Firmamos y codificamos el token con la SECRET_KEY y el algoritmo configurados
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# Decodificamos y validamos un token de acceso JWT
def decode_access_token(token: str) -> Optional[dict]:
    # Intentamos decodificar el token, verificando firma y expiración
    try:
        # Obtenemos el payload si el token es válido
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # Devolvemos el payload decodificado
        return payload
    # Capturamos cualquier error de JWT (firma inválida, token expirado, mal formado, etc.)
    except jwt.PyJWTError:
        # Devolvemos None para indicar que el token no es válido
        return None
