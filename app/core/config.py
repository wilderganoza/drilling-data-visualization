# Importamos las librerias necesarias
from typing import List # Tipo para anotar la lista de orígenes CORS
from pydantic_settings import BaseSettings # Base que lee la configuración desde variables de entorno / .env
from pydantic import Field, model_validator # Field para declarar cada setting, model_validator para validar tras cargar todo

# Definimos el valor placeholder de SECRET_KEY, para poder detectar si el usuario nunca lo cambió
DEFAULT_SECRET_KEY = "change-this-secret-key-in-production"


# Declaramos la configuración global de la aplicación, cargada desde variables de entorno o .env
class Settings(BaseSettings):
    # Guardamos el nombre de la aplicación
    APP_NAME: str = Field(default="Drilling Analysis API")

    # Guardamos la versión de la aplicación
    APP_VERSION: str = Field(default="1.0.0")

    # Guardamos si el modo debug está activo (recarga automática, logs más verbosos)
    DEBUG: bool = Field(default=False)

    # Guardamos el entorno actual (development | production)
    ENVIRONMENT: str = Field(default="production")

    # Guardamos el host donde escucha el servidor
    HOST: str = Field(default="0.0.0.0")

    # Guardamos el puerto donde escucha el servidor
    PORT: int = Field(default=8000)

    # Guardamos la URL de conexión a PostgreSQL
    DATABASE_URL: str = Field(default="postgresql://postgres:postgres@localhost:5432/drilling_db")

    # Guardamos el esquema donde vive esta app dentro de la base compartida de Supabase.
    # Las cinco aplicaciones comparten un mismo proyecto y se separan por esquema.
    DB_SCHEMA: str = Field(default="ddv")

    # Guardamos los orígenes permitidos para CORS. La app web se sirve same-origin
    # (Jinja2 + HTMX desde este mismo proceso FastAPI), así que por defecto no hace
    # falta ningún origen habilitado — solo completar esto si algo externo necesita
    # llamar a /api/v1/* legítimamente desde otro origen.
    CORS_ORIGINS: List[str] = Field(default=[])

    # Guardamos la URL del proyecto Supabase (para Auth y Storage)
    SUPABASE_URL: str = Field(default="")

    # Guardamos la clave publicable de Supabase (segura de exponer, va al navegador)
    SUPABASE_PUBLISHABLE_KEY: str = Field(default="")

    # Guardamos la clave de servicio de Supabase. Salta el RLS por completo, así que
    # no debe llegar al navegador ni quedar en el repositorio.
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")

    # Guardamos el nombre de la cookie donde viaja el token de sesión
    SESSION_COOKIE_NAME: str = Field(default="ddv_session")

    # Guardamos el nombre de la cookie donde viaja el refresh token de Supabase
    REFRESH_COOKIE_NAME: str = Field(default="ddv_refresh")

    # Guardamos si las cookies exigen HTTPS (desactivar solo en desarrollo local)
    COOKIE_SECURE: bool = Field(default=True)

    # Guardamos la clave secreta usada para firmar los JWT
    SECRET_KEY: str = Field(default=DEFAULT_SECRET_KEY)

    # Guardamos el algoritmo de firma de los JWT
    ALGORITHM: str = Field(default="HS256")

    # Guardamos cuántos minutos dura un token de acceso antes de expirar
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=480)

    # Guardamos el nivel de logging de la aplicación
    LOG_LEVEL: str = Field(default="INFO")

    # Guardamos el máximo de filas que cualquier consulta puede pedir
    MAX_QUERY_LIMIT: int = Field(default=100000)

    # Guardamos el límite de filas por defecto cuando una consulta no especifica uno
    DEFAULT_QUERY_LIMIT: int = Field(default=10000)

    # Validamos, una vez cargados todos los settings, que la app no arranque en producción
    # con la SECRET_KEY placeholder (evita dejar un secreto de firma de JWT adivinable)
    @model_validator(mode="after")
    def check_secret_key_in_production(self) -> "Settings":
        # Detectamos la combinación peligrosa: producción + SECRET_KEY nunca configurada
        if self.ENVIRONMENT == "production" and not self.DEBUG and self.SECRET_KEY == DEFAULT_SECRET_KEY:
            # Rechazamos el arranque en vez de servir con una clave insegura conocida
            raise ValueError("SECRET_KEY must be set via environment variable in production; refusing to start with the default placeholder key")

        # Devolvemos la instancia validada
        return self

    # Configuramos cómo pydantic-settings carga estos valores
    class Config:
        # Leemos las variables desde el archivo .env si existe
        env_file = ".env"

        # Exigimos que los nombres de las variables de entorno respeten mayúsculas/minúsculas
        case_sensitive = True

# Creamos la instancia única de configuración que usa el resto de la app
settings = Settings()
