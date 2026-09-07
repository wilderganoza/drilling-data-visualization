# Importamos uuid para generar los ids de las tablas ops
import uuid
# Importamos los tipos de columna que usamos en los mixins
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer
# Importamos UUID de Postgres para tipar el id primario
from sqlalchemy.dialects.postgresql import UUID
# Importamos declared_attr para declarar columnas que dependen de la clase que hereda el mixin
from sqlalchemy.orm import declared_attr
# Importamos utcnow para sellar fechas en UTC
from app.models.legacy import utcnow

# Definimos el mixin que agrega id/created_at/updated_at/created_by/updated_by a cualquier tabla ops
class AuditMixin:
    # Usamos UUID como llave primaria
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Guardamos cuándo se creó el registro
    created_at = Column(DateTime, default=utcnow, nullable=False)
    
    # Guardamos cuándo se actualizó el registro por última vez
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Declaramos created_by dinámicamente para que la FK apunte a users.id en cada tabla que herede el mixin
    @declared_attr
    def created_by(cls):
        # Devolvemos la columna con la FK hacia el usuario que creó el registro
        return Column(Integer, ForeignKey("users.id"), nullable=True)

    # Declaramos updated_by dinámicamente por la misma razón que created_by
    @declared_attr
    def updated_by(cls):
        # Devolvemos la columna con la FK hacia el usuario que actualizó el registro
        return Column(Integer, ForeignKey("users.id"), nullable=True)

# Definimos el mixin para registros que nunca se borran físicamente, solo se cierran
class SoftCloseMixin:
    # Guardamos si el registro está cerrado
    is_closed = Column(Boolean, default=False, nullable=False)

    # Guardamos cuándo se cerró el registro
    closed_at = Column(DateTime, nullable=True)

    # Declaramos closed_by dinámicamente para que la FK apunte a users.id en cada tabla que herede el mixin
    @declared_attr
    def closed_by(cls):
        # Devolvemos la columna con la FK hacia el usuario que cerró el registro
        return Column(Integer, ForeignKey("users.id"), nullable=True)

    # Declaramos superseded_by_id dinámicamente porque la FK debe apuntar a la misma tabla que hereda el mixin
    @declared_attr
    def superseded_by_id(cls):
        # Devolvemos la columna que enlaza este registro con el que lo reemplazó
        return Column(UUID(as_uuid=True), ForeignKey(f"{cls.__tablename__}.id"), nullable=True)
