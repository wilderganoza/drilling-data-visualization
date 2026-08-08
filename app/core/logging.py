import logging # Módulo de logging de Python para gestionar logs
import sys # Sys para acceder a stdout (salida estándar)
from typing import Any # Any para tipado genérico
from app.core.config import settings # Configuración de la aplicación

# Función para configurar el sistema de logging de la aplicación
def setup_logging() -> None:
    # Crear logger principal con nombre 'drilling_analysis'
    logger = logging.getLogger("drilling_analysis")

    # Establecer nivel de logging desde configuración (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Crear handler para enviar logs a la consola (stdout)
    console_handler = logging.StreamHandler(sys.stdout)

    # Establecer nivel de logging del handler
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Crear formateador para definir el formato de los mensajes de log
    formatter = logging.Formatter(
        # Formato: fecha - nombre del logger - nivel - mensaje
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",

        # Formato de fecha: YYYY-MM-DD HH:MM:SS
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Asignar el formateador al handler de consola
    console_handler.setFormatter(formatter)
    
    # Agregar el handler de consola al logger principal
    logger.addHandler(console_handler)
    
    # Configurar el logger de uvicorn (servidor ASGI)
    uvicorn_logger = logging.getLogger("uvicorn")

    # Establecer el mismo nivel de logging para uvicorn
    uvicorn_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

# Función para obtener una instancia de logger con un nombre específico
def get_logger(name: str) -> logging.Logger:
    # Retornar logger con prefijo 'drilling_analysis.' para jerarquía
    return logging.getLogger(f"drilling_analysis.{name}")
