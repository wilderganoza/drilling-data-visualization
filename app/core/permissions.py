# Importamos las librerías necesarias
from fastapi import Depends, HTTPException # Para inyección de dependencias y para rechazar accesos sin permiso
from sqlalchemy.orm import Session # Para tipar la sesión de base de datos
from app.core.deps import get_current_user_web # Dependencia que resuelve el usuario autenticado por cookie
from app.models.legacy import User # Modelo de usuario
from app.db.session import get_db # Dependencia que entrega una sesión de base de datos
from app.core.ops_roles import OpsRole # Enum con los roles operacionales válidos
from app.models.roles import OpsUserRole # Modelo que guarda el rol activo de cada usuario


# Buscamos el rol operacional activo de un usuario (o None si no tiene uno asignado/válido)
def _get_ops_role(db: Session, user_id: int) -> OpsRole | None:
    # Buscamos la fila de rol por el id del usuario (es la llave primaria de OpsUserRole)
    row = db.get(OpsUserRole, user_id)

    # Si no tiene fila de rol asignada, no tiene rol
    if row is None:
        # Devolvemos None
        return None

    # Intentamos convertir el string guardado a un valor válido del enum
    try:
        # Devolvemos el rol si el string coincide con uno de los valores del enum
        return OpsRole(row.role)
    # El valor guardado no coincide con ningún rol conocido (dato corrupto/rol eliminado)
    except ValueError:
        # Tratamos ese caso igual que "sin rol"
        return None


# Verificamos si el usuario actual tiene alguno de los roles permitidos, sin lanzar
# excepción — pensada para gatear qué se muestra en la UI (botones, secciones), no
# para proteger una ruta (para eso está require_ops_role).
def has_ops_role(db: Session, current_user: User, *allowed: OpsRole) -> bool:
    # Los administradores del sistema siempre pasan, sin importar su rol de ops
    if current_user.is_admin:
        # Devolvemos True
        return True

    # Devolvemos si su rol de ops está entre los permitidos
    return _get_ops_role(db, current_user.id) in allowed


# Construimos una dependencia de FastAPI que exige uno de los roles indicados. Es una
# "fábrica de dependencias": require_ops_role(...) no es en sí la dependencia, sino que
# DEVUELVE una (la función interna _dep), ya cerrada sobre los roles permitidos que le
# pasamos. Necesitamos esta forma anidada porque Depends() solo puede recibir una función
# sin argumentos propios — así es como se parametriza una dependencia en FastAPI (ej.
# CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER), y luego
# Depends(CAN_EDIT) en cada ruta que lo necesite).
def require_ops_role(*allowed: OpsRole):
    # Definimos la dependencia real, cerrada sobre "allowed" por el closure
    def _dep(current_user: User = Depends(get_current_user_web), db: Session = Depends(get_db)) -> User:
        # Los administradores del sistema siempre pasan
        if current_user.is_admin:
            # Devolvemos el usuario autenticado
            return current_user

        # Buscamos el rol de ops del usuario
        role = _get_ops_role(db, current_user.id)

        # Si su rol no está entre los permitidos, rechazamos el acceso
        if role not in allowed:
            # Devolvemos 403 (autenticado, pero sin el rol necesario)
            raise HTTPException(status_code=403, detail="Not enough permissions")

        # Devolvemos el usuario autenticado y autorizado
        return current_user

    # Devolvemos la dependencia ya parametrizada, lista para usarse en Depends(...)
    return _dep
