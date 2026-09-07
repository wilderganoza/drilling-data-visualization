# Importamos Optional para tipar los retornos que pueden ser None
from typing import Optional

# Importamos los modelos sobre los que operan estos repositorios
from app.models.realtime import Rig, RealtimeSource
# Importamos BaseRepository para heredar las operaciones CRUD genéricas
from app.repositories.base import BaseRepository


# Definimos el repositorio del catálogo de taladros
class RigRepository(BaseRepository[Rig]):
    # Indicamos el modelo que maneja este repositorio
    model = Rig

    # Listamos los taladros activos, ordenados por nombre (para poblar el selector de la UI)
    def list_active(self):
        # Filtramos por is_active y ordenamos por nombre
        return self.list(filters={"is_active": True}, order_by=self.model.name, limit=200)


# Definimos el repositorio de fuentes de datos en tiempo real (el vínculo taladro↔evento)
class RealtimeSourceRepository(BaseRepository[RealtimeSource]):
    # Indicamos el modelo que maneja este repositorio
    model = RealtimeSource

    # Buscamos la fuente activa (enabled=True) de un evento, si tiene una
    def get_enabled_for_event(self, event_id) -> Optional[RealtimeSource]:
        # Filtramos por evento y por enabled=True; a lo sumo hay una (lo garantiza el índice único parcial)
        results = self.list(filters={"event_id": event_id, "enabled": True}, limit=1)
        return results[0] if results else None

    # Buscamos la fuente activa (enabled=True) de un taladro, si tiene una
    def get_enabled_for_rig(self, rig_id) -> Optional[RealtimeSource]:
        # Filtramos por taladro y por enabled=True; a lo sumo hay una (lo garantiza el índice único parcial)
        results = self.list(filters={"rig_id": rig_id, "enabled": True}, limit=1)
        return results[0] if results else None

    # Listamos todas las fuentes actualmente activas — es lo que el RealtimeIngestManager
    # lee al arrancar la app para saber qué conexiones tiene que restablecer
    def list_enabled(self):
        # Filtramos por enabled=True, sin límite artificial (nunca serán más que la cantidad de taladros)
        return self.list(filters={"enabled": True}, limit=1000)

    # Listamos el historial de conexiones de un evento, más reciente primero
    def list_for_event(self, event_id):
        # Filtramos por evento y ordenamos por fecha de creación descendente
        return self.list(filters={"event_id": event_id}, order_by=self.model.created_at.desc(), limit=50)
