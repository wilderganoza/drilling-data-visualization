# Importamos el modelo DailyReport, sobre el que opera este repositorio
from app.models.daily_report import DailyReport
# Importamos BaseRepository para heredar las operaciones CRUD genéricas
from app.repositories.base import BaseRepository


# Definimos el repositorio de reportes diarios
class DailyReportRepository(BaseRepository[DailyReport]):
    # Indicamos el modelo que maneja este repositorio
    model = DailyReport

    # Listamos los reportes de un evento, ordenados por fecha
    def list_for_event(self, event_id):
        # Filtramos por evento y ordenamos por report_date
        return self.list(filters={"event_id": event_id}, order_by=self.model.report_date)
