from typing import Optional  # Tipo para valores opcionales en las firmas

from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy

from app.repositories.data_repository import DataRepository  # Repositorio genérico para leer las tablas de sensores (depth/time)
from app.repositories.processed_dataset_repository import ProcessedDatasetRepository  # Repositorio de datasets procesados (casos de limpieza)
from app.db.session import db_manager  # Gestor de conexiones/tablas por dominio (depth/time)
from app.services.outlier_detection import OutlierDetectionService  # Servicio de detección de outliers (usado por otros módulos que reexportan desde aquí)


def parse_dataset_id(raw: str) -> Optional[int]:
    """'raw' (or empty) -> None (use raw well data); anything else -> the processed dataset id."""
    # Si viene vacío o es literalmente "raw", significa que usamos los datos crudos del pozo
    if not raw or raw == "raw":
        return None
    try:
        # Intentamos convertir el valor a un id numérico de dataset procesado
        return int(raw)
    except (TypeError, ValueError):
        # Si no es un número válido, lo tratamos como si no hubiera dataset seleccionado
        return None


def num(value) -> Optional[float]:
    """Coerce to float, filtering out NaN and non-numeric values."""
    try:
        # Intentamos convertir el valor a float
        f = float(value)
    except (TypeError, ValueError):
        # Si no se puede convertir, devolvemos None
        return None
    # Devolvemos el float solo si no es NaN (NaN nunca es igual a sí mismo)
    return f if f == f else None  # NaN != NaN


def fetch_records(
    db: Session,
    well_id: int,
    processed_dataset_id: Optional[int],
    *,
    raw_sample_size: int = 50000,
    processed_page_size: int = 50000,
    domain: str = "depth",
    depth_range: Optional[tuple] = None,
    date_range: Optional[tuple] = None,
) -> list:
    """Raw sensor rows (depth- or time-indexed by `domain`), or a processed
    dataset's stored records — same shape either way. `depth_range`/`date_range`
    only apply to the raw path (pushed down to SQL, before any sampling LIMIT)."""
    # Si no hay dataset procesado seleccionado, leemos directo de la tabla cruda del dominio
    if processed_dataset_id is None:
        # Obtenemos la tabla correspondiente al dominio (depth o time)
        table = db_manager.get_domain_table(domain)
        # Creamos el repositorio genérico apuntando a esa tabla
        repo = DataRepository(db, table)
        # Consultamos una muestra de registros, aplicando los filtros de rango si vienen
        return repo.query_sample(well_id, sample_size=raw_sample_size,
                                 depth_range=depth_range, date_range=date_range)
    # Si hay un dataset procesado, lo leemos desde su repositorio dedicado
    ds_repo = ProcessedDatasetRepository(db)
    # Traemos los registros guardados del dataset, sin incluir los marcados como outliers
    rows = ds_repo.list_records(processed_dataset_id, include_outliers=False, page=1, page_size=processed_page_size)
    # Extraemos solo el payload de datos de cada registro, descartando filas vacías
    return [r.data for r in rows if r.data]


def wells_for_domain(db: Session, domain: str = "depth"):
    """(wells, time_well_ids) for the well picker. For the time domain only wells
    that actually have time-indexed data are returned."""
    # Importamos aquí para evitar import circular con el repositorio de pozos
    from app.repositories.well_repository import WellRepository
    # Obtenemos todos los pozos disponibles (hasta 1000)
    wells = WellRepository(db).get_all(skip=0, limit=1000)
    # Obtenemos el conjunto de ids de pozos que tienen datos en el dominio tiempo
    time_ids = db_manager.time_well_ids()
    # Si el dominio pedido es tiempo, filtramos para mostrar solo esos pozos
    if domain == "time":
        wells = [w for w in wells if w.id in time_ids]
    # Devolvemos la lista de pozos (ya filtrada si aplica) junto con el set de ids de tiempo
    return wells, time_ids


def dataset_options(db: Session, well_id: int, domain: str = "depth"):
    """Options for a well's dataset picker: raw data plus its saved outlier-detection
    cleaning cases *for the given domain*.

    Cleaning cases (``processed_datasets``) record the domain they were created in, so a
    case built on depth-indexed data never appears when the time-indexed database is
    selected (and vice versa). Legacy rows with no stored domain are treated as ``depth``.
    """
    # Importamos aquí para evitar import circular con el modelo legacy
    from app.models.legacy import ProcessedDataset

    # Normalizamos el dominio a "time" o "depth" (cualquier otro valor cae a depth)
    domain = "time" if domain == "time" else "depth"
    # Construimos la consulta base filtrando por el pozo
    query = db.query(ProcessedDataset).filter(ProcessedDataset.well_id == well_id)
    if domain == "depth":
        # Las filas legacy creadas antes de que existiera el campo domain se tratan como depth (NULL == depth).
        query = query.filter(
            (ProcessedDataset.domain == "depth") | (ProcessedDataset.domain.is_(None))
        )
    else:
        # Para el dominio tiempo solo incluimos los datasets marcados explícitamente como time
        query = query.filter(ProcessedDataset.domain == "time")
    # Ejecutamos la consulta ordenando del más reciente al más antiguo
    datasets = query.order_by(ProcessedDataset.created_at.desc()).all()

    # Armamos la lista de opciones empezando siempre con "datos crudos"
    options = [{"value": "raw", "label": "Raw data (original)"}]
    for d in datasets:
        # Agregamos cada dataset procesado, usando su nombre o un id genérico si no tiene nombre
        options.append({"value": d.id, "label": d.name or f"Dataset #{d.id}"})
    # Devolvemos la lista completa de opciones para el selector
    return options
