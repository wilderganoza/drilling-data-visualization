"""Real-time rig connectivity — the catalog of physical rigs that carry a
SZJ-II (or compatible) drilling instrumentation system, and the live feed
that ties one rig's data stream to the Event currently being drilled with it.

A `Rig` is a fixed piece of hardware (one row per physical unit, created once
and rarely edited): it owns the network coordinates of its WITS0 channel.
A `RealtimeSource` is the *link* between a rig and an Event — created/enabled
each time a rig starts drilling a well, disabled when it stops or moves to a
different well. Keeping these separate (rather than a field on Event) lets one
rig's connection history span many wells over its lifetime, and lets us refuse
to double-book a rig (or double-feed an Event) at the model layer."""
# Importamos los tipos de columna que usamos en las tablas
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
# Importamos UUID de Postgres para tipar el id del evento
from sqlalchemy.dialects.postgresql import UUID
# Importamos relationship para exponer el evento/taladro desde cada lado
from sqlalchemy.orm import relationship

# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría
from app.models.mixins import AuditMixin

# Declaramos los modos de conexión soportados para el canal WITS0 de un taladro
WITS_MODES = ("client", "server")
# Declaramos los protocolos de tiempo real soportados (hoy solo WITS0; deja espacio para WITSML/Modbus a futuro)
REALTIME_PROTOCOLS = ("wits0",)
# Declaramos los estados posibles de una fuente de datos en tiempo real
REALTIME_STATUSES = ("disconnected", "connecting", "connected", "error")


# Definimos el catálogo de taladros físicos, cada uno con su propio equipo de instrumentación
class Rig(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "rigs"

    # Guardamos el nombre del taladro (ej. "Taladro 1"), único para poder identificarlo sin ambigüedad
    name = Column(String(100), nullable=False, unique=True)

    # Guardamos el protocolo de tiempo real que expone este taladro (hoy siempre "wits0")
    protocol = Column(String(20), nullable=False, default="wits0")

    # Guardamos si nuestra app se conecta hacia el taladro ("client") o si el taladro se conecta
    # hacia nosotros y solo escuchamos ("server") — depende de cómo quede configurado el SZJ-II en sitio
    wits_mode = Column(String(10), nullable=False, default="client")

    # Guardamos el host/IP del canal WITS0 (la IP del equipo SZJ-II en modo client; nuestra propia
    # IP/interfaz en modo server, solo informativo)
    wits_host = Column(String(100), nullable=True)

    # Guardamos el puerto TCP del canal WITS0 (a dónde nos conectamos en modo client, o dónde
    # escuchamos en modo server)
    wits_port = Column(Integer, nullable=True)

    # Guardamos si el taladro está habilitado para usarse (permite retirar un taladro sin borrar su historial)
    is_active = Column(Boolean, default=True, nullable=False)

    # Guardamos notas libres (ej. datos de contacto del ingeniero de JPIM para ese taladro)
    notes = Column(String(1000), nullable=True)

    # Relacionamos el taladro con todo su historial de conexiones (una por cada pozo que perforó)
    realtime_sources = relationship("RealtimeSource", back_populates="rig")


# Definimos el vínculo entre un taladro y el Event que está perforando con él ahora mismo
# (o perforó en el pasado — el historial se conserva, solo se desactiva).
class RealtimeSource(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "realtime_sources"

    # Guardamos a qué evento (pozo/campaña) pertenece esta conexión
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True)

    # Guardamos a qué taladro físico está conectada
    rig_id = Column(UUID(as_uuid=True), ForeignKey("rigs.id"), nullable=False, index=True)

    # Guardamos si el canal está activo — el RealtimeIngestManager solo mantiene una tarea
    # de red corriendo por cada fuente con enabled=True
    enabled = Column(Boolean, default=False, nullable=False)

    # Guardamos el estado observado de la conexión (lo actualiza el servicio de ingesta, no el usuario)
    status = Column(String(20), nullable=False, default="disconnected")

    # Guardamos el último error de conexión/parseo, para mostrarlo en la UI si algo falla
    last_error = Column(String(500), nullable=True)

    # Guardamos cuándo llegó el último dato válido (para detectar un canal "conectado pero mudo")
    last_data_at = Column(DateTime, nullable=True)

    # Guardamos cuántas filas hemos insertado desde que se activó este canal, como indicador rápido en la UI
    rows_ingested = Column(Integer, nullable=False, default=0)

    # Guardamos cuándo se activó y cuándo se desactivó este canal (historial de uso del taladro)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)

    # Relacionamos la fuente con su evento
    event = relationship("Event")
    # Relacionamos la fuente con su taladro
    rig = relationship("Rig", back_populates="realtime_sources")
