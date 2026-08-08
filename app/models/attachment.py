"""File attachments (photos, documents) for daily reports and NPT events.
Stored in-DB as bytes to keep deployment dependency-free (no object store /
filesystem coupling). `owner_type` + `owner_id` is a lightweight polymorphic
link so one table serves both report- and NPT-level attachments."""
# Importamos los tipos de columna que usamos en la tabla
from sqlalchemy import Column, Integer, LargeBinary, String
# Importamos UUID de Postgres para tipar owner_id
from sqlalchemy.dialects.postgresql import UUID

# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría (created_by, created_at, etc.)
from app.models.mixins import AuditMixin


# Definimos el modelo de un archivo adjunto
class Attachment(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "ops_attachments"

    # Guardamos el tipo de dueño ("daily_report" | "npt") para el link polimórfico
    owner_type = Column(String(30), nullable=False, index=True)  # "daily_report" | "npt"
    # Guardamos el id del dueño (reporte o evento NPT)
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    # Guardamos el nombre original del archivo
    filename = Column(String(300), nullable=False)
    # Guardamos el content-type (mime type) del archivo
    content_type = Column(String(120), nullable=True)
    # Guardamos el tamaño en bytes del archivo
    size_bytes = Column(Integer, nullable=True)
    # Guardamos una descripción opcional del archivo
    caption = Column(String(500), nullable=True)
    # Guardamos el contenido binario del archivo directamente en la BD
    data = Column(LargeBinary, nullable=False)
