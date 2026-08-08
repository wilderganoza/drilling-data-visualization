"""Generic editable-grid repository for the spec-driven grid subsections.
One class serves every grid table — the model and its parent FK column are
passed per instance, since the subsections are structurally identical (ordered
rows under a parent) and differ only in their columns and what they hang off:
daily-report capture rows hang off `daily_report_id`, well-plan program rows
off `event_id`."""
# Importamos BaseRepository para heredar las operaciones CRUD genéricas
from app.repositories.base import BaseRepository


# Definimos el repositorio genérico para cualquier subsección de tipo grilla
class GridRepository(BaseRepository):
    """list/create/update/delete/move for any grid-subsection model."""

    # Inicializamos el repositorio con el modelo y el nombre de la FK hacia su padre
    def __init__(self, session, model, parent_field: str = "daily_report_id"):
        # Inicializamos la sesión heredando el comportamiento de BaseRepository
        super().__init__(session)
        # Guardamos el modelo como atributo de instancia (sobrescribe el atributo de clase de BaseRepository)
        self.model = model  # instance attr shadows BaseRepository's class attr
        # Guardamos el nombre del campo que enlaza cada fila con su padre
        self.parent_field = parent_field

    # Listamos las filas de un padre (reporte diario o evento), ordenadas por su orden de despliegue
    def list_for_parent(self, parent_id):
        # Filtramos por el campo padre, ordenamos por sort_order y limitamos a 1000 filas
        return self.list(filters={self.parent_field: parent_id}, order_by=self.model.sort_order, limit=1000)

    # Creamos un alias por compatibilidad con el código de captura de reportes diarios,
    # que se lee mejor como "list_for_report".
    list_for_report = list_for_parent

    # Calculamos el siguiente orden disponible para una fila nueva
    def next_sort_order(self, parent_id) -> int:
        # Obtenemos las filas actuales del padre
        rows = self.list_for_parent(parent_id)
        # Devolvemos el orden siguiente al de la última fila, o 0 si no hay filas
        return (rows[-1].sort_order + 1) if rows else 0

    # Movemos una fila hacia arriba o hacia abajo dentro de su padre
    def move(self, row, direction: str) -> None:
        # Obtenemos todas las filas del padre en su orden actual
        rows = self.list_for_parent(getattr(row, self.parent_field))
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
