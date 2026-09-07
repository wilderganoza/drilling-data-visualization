# Importamos los tipos de columna que usamos para definir la tabla
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
# Importamos utcnow para sellar la fecha de actualización en UTC
from app.models.legacy import utcnow
# Importamos OpsBase, la base declarativa de la que heredamos este modelo
from app.models.base import OpsBase


# Definimos el modelo que guarda un rol activo de ops por usuario
class OpsUserRole(OpsBase):
    """One active ops role per user (Phase 1 — global, not project-scoped).
    Kept separate from the legacy `users` table rather than adding a column
    there, so this ops-specific concept doesn't touch the shared schema."""

    # Nombramos la tabla
    __tablename__ = "user_roles"

    # Usamos user_id como llave primaria y FK hacia users.id (un solo rol activo por usuario)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    
    # Guardamos el rol como texto
    role = Column(String(50), nullable=False)
    
    # Registramos cuándo se actualizó el rol por última vez
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
