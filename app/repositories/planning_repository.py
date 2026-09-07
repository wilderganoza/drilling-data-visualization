# Importamos el modelo WellPlan, sobre el que opera este repositorio
from app.models.planning import WellPlan
# Importamos BaseRepository para heredar las operaciones CRUD genéricas
from app.repositories.base import BaseRepository


# Definimos el repositorio del plan de pozo
class WellPlanRepository(BaseRepository[WellPlan]):
    # Indicamos el modelo que maneja este repositorio
    model = WellPlan

    # Buscamos el plan de pozo de un evento (uno solo, por la relación 1:1)
    def get_by_event(self, event_id):
        # Filtramos por evento y limitamos a un resultado
        results = self.list(filters={"event_id": event_id}, limit=1)
        # Devolvemos el plan si existe, o None si no
        return results[0] if results else None
