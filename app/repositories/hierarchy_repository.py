# Importamos los modelos de la jerarquía, sobre los que opera cada repositorio
from app.models.hierarchy import Company, Event, Project, Site, Well, Wellbore
# Importamos BaseRepository para heredar las operaciones CRUD genéricas
from app.repositories.base import BaseRepository


# Definimos el repositorio de empresas
class CompanyRepository(BaseRepository[Company]):
    # Indicamos el modelo que maneja este repositorio
    model = Company


# Definimos el repositorio de proyectos
class ProjectRepository(BaseRepository[Project]):
    # Indicamos el modelo que maneja este repositorio
    model = Project


# Definimos el repositorio de sitios
class SiteRepository(BaseRepository[Site]):
    # Indicamos el modelo que maneja este repositorio
    model = Site


# Definimos el repositorio de pozos operacionales
class WellRepository(BaseRepository[Well]):
    # Indicamos el modelo que maneja este repositorio
    model = Well


# Definimos el repositorio de wellbores
class WellboreRepository(BaseRepository[Wellbore]):
    # Indicamos el modelo que maneja este repositorio
    model = Wellbore


# Definimos el repositorio de eventos
class EventRepository(BaseRepository[Event]):
    # Indicamos el modelo que maneja este repositorio
    model = Event
