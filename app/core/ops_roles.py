# Importamos Enum para declarar los roles como un enum de strings
from enum import Enum


# Definimos los roles operacionales disponibles en el módulo de Ops (Fase 1: roles globales,
# no acotados por proyecto). Heredar de str además de Enum nos permite comparar/guardar
# el valor como texto plano (ej. en la columna OpsUserRole.role) sin conversión manual.
class OpsRole(str, Enum):
    # Supervisor de taladro: captura operativa diaria
    RIG_SUPERVISOR = "rig_supervisor"

    # Geólogo de sitio: captura de datos geológicos
    SITE_GEOLOGIST = "site_geologist"

    # Ingeniero de oficina: planeación y calculadores de ingeniería
    OFFICE_ENGINEER = "office_engineer"

    # Administrador: acceso completo, incluye aprobar reportes/planes
    ADMIN = "admin"

    # Solo lectura: puede ver todo pero no editar ni aprobar nada
    READ_ONLY = "read_only"
