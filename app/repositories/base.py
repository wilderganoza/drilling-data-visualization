# Importamos los tipos que usamos para tipar el repositorio genérico
from typing import Any, Generic, Optional, Sequence, TypeVar

# Importamos func y select para construir las consultas
from sqlalchemy import func, select
# Importamos Session para tipar la sesión de SQLAlchemy
from sqlalchemy.orm import Session

# Declaramos el TypeVar genérico que representa el modelo de cada repositorio concreto
ModelT = TypeVar("ModelT")


# Definimos el repositorio base con las operaciones CRUD genéricas para los modelos de ops
class BaseRepository(Generic[ModelT]):
    """Generic CRUD for ops models. Subclasses set `model` and add only the
    query methods that are genuinely specific to that table (e.g. ordered
    listings, parent/child lookups) — plain get/list/create/update/delete
    should never be re-implemented per model."""

    # Declaramos el modelo que cada subclase debe fijar
    model: type[ModelT]

    # Inicializamos el repositorio con la sesión de base de datos a usar
    def __init__(self, session: Session):
        # Guardamos la sesión para todas las operaciones del repositorio
        self.session = session

    # Buscamos una instancia por su id
    def get(self, id: Any) -> Optional[ModelT]:
        # Delegamos en session.get, que resuelve por llave primaria
        return self.session.get(self.model, id)

    # Listamos instancias con filtros, orden y paginación opcionales
    def list(
        self,
        *,
        filters: Optional[dict[str, Any]] = None,
        order_by: Any = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[ModelT]:
        # Armamos el select base sobre el modelo
        stmt = select(self.model)
        # Aplicamos cada filtro como una condición de igualdad
        for key, value in (filters or {}).items():
            stmt = stmt.where(getattr(self.model, key) == value)
        # Aplicamos el orden si se indicó uno
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        # Aplicamos la paginación
        stmt = stmt.offset(skip).limit(limit)
        # Ejecutamos la consulta y devolvemos los resultados como lista
        return self.session.execute(stmt).scalars().all()

    # Contamos instancias con filtros opcionales
    def count(self, *, filters: Optional[dict[str, Any]] = None) -> int:
        # Armamos el select de conteo sobre el modelo
        stmt = select(func.count()).select_from(self.model)
        # Aplicamos cada filtro como una condición de igualdad
        for key, value in (filters or {}).items():
            stmt = stmt.where(getattr(self.model, key) == value)
        # Ejecutamos la consulta y devolvemos el conteo
        return self.session.execute(stmt).scalar_one()

    # Creamos una nueva instancia con los valores dados
    def create(self, **kwargs: Any) -> ModelT:
        # Construimos la instancia del modelo con los kwargs recibidos
        instance = self.model(**kwargs)
        # Agregamos la instancia a la sesión
        self.session.add(instance)
        # Enviamos el insert a la base de datos para obtener valores generados (ej. id)
        self.session.flush()
        # Devolvemos la instancia creada
        return instance

    # Actualizamos una instancia existente con los valores dados
    def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        # Asignamos cada valor recibido al atributo correspondiente
        for key, value in kwargs.items():
            setattr(instance, key, value)
        # Enviamos los cambios a la base de datos
        self.session.flush()
        # Devolvemos la instancia actualizada
        return instance

    # Borramos una instancia existente
    def delete(self, instance: ModelT) -> None:
        # Marcamos la instancia para borrado
        self.session.delete(instance)
        # Enviamos el delete a la base de datos
        self.session.flush()
