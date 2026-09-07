# Importamos las librerias necesarias
import logging # Módulo de logging de Python para gestionar logs
import sys # Para acceder a stdout (salida estándar)
from typing import Any # Any para tipado genérico
from app.core.config import settings # Configuración de la aplicación


# Configuramos el sistema de logging de la aplicación
def setup_logging() -> None:
    # Creamos el logger principal con nombre 'drilling_analysis'
    logger = logging.getLogger("drilling_analysis")

    # Establecemos el nivel de logging desde configuración (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Creamos el handler que envía los logs a la consola (stdout)
    console_handler = logging.StreamHandler(sys.stdout)

    # Establecemos el nivel de logging del handler
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Creamos el formateador que define el formato de los mensajes de log
    formatter = logging.Formatter(
        # Definimos el formato: fecha - nombre del logger - nivel - mensaje
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",

        # Definimos el formato de fecha: YYYY-MM-DD HH:MM:SS
        datefmt="%Y-%m-%d %H:%M:%S")

    # Asignamos el formateador al handler de consola
    console_handler.setFormatter(formatter)

    # Agregamos el handler de consola al logger principal
    logger.addHandler(console_handler)

    # Configuramos el logger de uvicorn (servidor ASGI) para que use el mismo nivel
    uvicorn_logger = logging.getLogger("uvicorn")

    # Establecemos el mismo nivel de logging para uvicorn
    uvicorn_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))


# Obtenemos una instancia de logger con un nombre específico
def get_logger(name: str) -> logging.Logger:
    # Devolvemos el logger con el prefijo 'drilling_analysis.' para mantener la jerarquía
    return logging.getLogger(f"drilling_analysis.{name}")
