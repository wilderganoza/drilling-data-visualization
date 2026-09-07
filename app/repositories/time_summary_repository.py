# Importamos los modelos sobre los que operan estos repositorios
from app.models.time_summary import StepCatalogEntry, TimeSummaryRow
# Importamos BaseRepository para heredar las operaciones CRUD genéricas
from app.repositories.base import BaseRepository


# Definimos el repositorio del catálogo de pasos (Fase/Paso/Operación)
class StepCatalogRepository(BaseRepository[StepCatalogEntry]):
    # Indicamos el modelo que maneja este repositorio
    model = StepCatalogEntry

    # Listamos las entradas del catálogo para un perfil de taladro, ordenadas por número de paso
    def list_for_profile(self, profile: str):
        # Filtramos por perfil y ordenamos por step_no
        return self.list(filters={"profile": profile}, order_by=self.model.step_no)


# Definimos el repositorio de filas del resumen de tiempo
class TimeSummaryRowRepository(BaseRepository[TimeSummaryRow]):
    # Indicamos el modelo que maneja este repositorio
    model = TimeSummaryRow

    # Listamos las filas de un reporte diario, ordenadas por su orden de despliegue
    def list_for_report(self, daily_report_id):
        # Filtramos por reporte diario, ordenamos por sort_order y limitamos a 500 filas
        return self.list(filters={"daily_report_id": daily_report_id}, order_by=self.model.sort_order, limit=500)

    # Calculamos el siguiente orden disponible para una fila nueva
    def next_sort_order(self, daily_report_id) -> int:
        # Obtenemos las filas actuales del reporte
        rows = self.list_for_report(daily_report_id)
        # Devolvemos el orden siguiente al de la última fila, o 0 si no hay filas
        return (rows[-1].sort_order + 1) if rows else 0

    # Movemos una fila hacia arriba o hacia abajo dentro del reporte
    def move(self, row: TimeSummaryRow, direction: str) -> None:
        """Swap sort_order with the adjacent row so the grid's up/down
        buttons reorder without needing to renumber the whole list."""
        # Obtenemos todas las filas del reporte en su orden actual
        rows = self.list_for_report(row.daily_report_id)
        # Buscamos la posición de la fila que queremos mover
        idx = next((i for i, r in enumerate(rows) if r.id == row.id), None)
        # Salimos si la fila ya no existe en la lista
        if idx is None:
            return
        # Calculamos la posición de la fila vecina según la dirección
        neighbor_idx = idx - 1 if direction == "up" else idx + 1
        # Salimos si no hay vecino en esa dirección (es la primera o la última fila)
        if neighbor_idx < 0 or neighbor_idx >= len(rows):
            return
        # Tomamos la fila vecina
        neighbor = rows[neighbor_idx]
        # Intercambiamos el orden entre la fila y su vecina
        row.sort_order, neighbor.sort_order = neighbor.sort_order, row.sort_order
        # Enviamos los cambios a la base de datos
        self.session.flush()
