import uvicorn # Uvicorn para ejecutar el servidor ASGI
from app.core.config import settings # Configuración de la aplicación desde el módulo core

# Verificar si este script se está ejecutando directamente (no importado)
if __name__ == "__main__":
    # Ejecutar el servidor uvicorn con la aplicación FastAPI
    uvicorn.run(
        # Ruta al objeto app en el módulo main
        "app.main:app",

        # Host donde se ejecutará el servidor (0.0.0.0 permite conexiones externas)
        host=settings.HOST,

        # Puerto donde escuchará el servidor
        port=settings.PORT,

        # Activar recarga automática en modo debug para desarrollo
        reload=settings.DEBUG,

        # Nivel de logging (convertido a minúsculas para uvicorn)
        log_level=settings.LOG_LEVEL.lower()
    )
