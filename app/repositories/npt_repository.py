# Importamos HTTPException para rechazar el cierre de un NPT con hijos abiertos
from fastapi import HTTPException

# Importamos utcnow para sellar la fecha de cierre en UTC
from app.models.legacy import utcnow
# Importamos el modelo NptEvent, sobre el que opera este repositorio
from app.models.npt import NptEvent
# Importamos BaseRepository para heredar las operaciones CRUD genéricas
from app.repositories.base import BaseRepository


# Definimos el repositorio de eventos de tiempo no productivo (NPT)
class NptRepository(BaseRepository[NptEvent]):
    # Indicamos el modelo que maneja este repositorio
    model = NptEvent

    # Listamos los eventos de NPT de un reporte diario, ordenados por fecha de creación
    def list_for_report(self, daily_report_id):
        # Filtramos por reporte diario y limitamos a 500 filas
        return self.list(filters={"daily_report_id": daily_report_id}, order_by=self.model.created_at, limit=500)

    # Listamos los eventos hijos de un evento padre (cuando una falla se dividió en varios)
    def children(self, parent_id):
        # Filtramos por parent_id
        return self.list(filters={"parent_id": parent_id})

    # Cerramos un evento de NPT, siempre que no tenga hijos todavía abiertos
    def close(self, npt: NptEvent, closed_by: int) -> None:
        # Rechazamos el cierre si algún hijo sigue abierto
        if any(not child.is_closed for child in self.children(npt.id)):
            raise HTTPException(400, "No se puede cerrar un NPT con hijos abiertos.")
        # Marcamos el evento como cerrado
        npt.is_closed = True
        # Sellamos cuándo se cerró
        npt.closed_at = utcnow()
        # Guardamos quién lo cerró
        npt.closed_by = closed_by
        # Enviamos los cambios a la base de datos
        self.session.flush()
