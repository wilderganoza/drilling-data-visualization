# Importamos las librerias necesarias
import time # Para medir el tiempo transcurrido y cachear time_well_ids con un TTL
from sqlalchemy import create_engine, MetaData, Table, text # Para el engine, la metadata reflejada, tipar tablas y ejecutar SQL crudo puntual
from sqlalchemy.orm import sessionmaker, Session # Para la fábrica de sesiones y tipar la sesión
from typing import Generator, Dict, Any # Para tipar los generadores y diccionarios que devolvemos
from app.core.config import settings # Configuración de la app (DATABASE_URL)
from app.core.logging import get_logger # Para registrar la actividad de conexión
from app.models.legacy import Base # Base declarativa legacy, de donde sacamos las tablas a crear

# Creamos el logger de este módulo
logger = get_logger(__name__)


# Centralizamos toda la conexión a la base de datos: el engine, la fábrica de sesiones
# y la metadata reflejada de las tablas de sensores (que no declara ningún modelo).
class DatabaseManager:
    # Inicializamos el manager sin conexión todavía (se conecta explícitamente con initialize())
    def __init__(self):
        # Guardamos el engine de SQLAlchemy (se crea en initialize())
        self._engine = None

        # Guardamos la fábrica de sesiones (se crea en initialize())
        self._session_factory = None

        # Guardamos la metadata reflejada de las tablas de sensores (se crea en initialize())
        self._metadata = None

    # Abrimos la conexión real a PostgreSQL y preparamos todo lo necesario para operar
    def initialize(self):
        # Registramos que estamos por conectar
        logger.info("Initializing PostgreSQL connection...")

        # Creamos el engine con pool de conexiones (pre-ping evita usar conexiones muertas).
        # El search_path fija el esquema de esta app dentro de la base compartida de
        # Supabase: así los modelos y el reflect() siguen usando nombres sin calificar.
        # Va en connect_args y no en la URL para que no dependa de cómo se pegó el .env.
        self._engine = create_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            connect_args={"options": f"-csearch_path={settings.DB_SCHEMA},public"},
        )

        # Creamos la fábrica de sesiones ligada a ese engine
        self._session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self._engine)

        # Acotamos las tablas legacy a crear explícitamente (create_all no debe tocar las
        # tablas ops_*, que vienen de las migraciones SQL en supabase/migrations/)
        LEGACY_TABLES = [Base.metadata.tables[name] for name in ("users", "sensor_wells", "processed_datasets", "processed_records")]

        # Creamos esas tablas legacy si no existen todavía
        Base.metadata.create_all(bind=self._engine, tables=LEGACY_TABLES)

        # Preparamos un objeto de metadata separado para reflejar las tablas de sensores
        self._metadata = MetaData()

        # Reflejamos el esquema real de la base (well_data, well_data_time si existe, etc.)
        self._metadata.reflect(bind=self._engine)

        # Registramos que la conexión quedó lista
        logger.info(f"PostgreSQL connected: {settings.DATABASE_URL.split('@')[-1]}")

    # Entregamos una sesión suelta, para lo que no es una petición
    def session(self) -> Session:
        """Una sesión nueva, que el llamador cierra.

        `get_session()` es la dependencia de FastAPI: cede la sesión y la cierra
        al terminar la petición. Esta es para lo demás —tareas de fondo, guiones,
        una comprobación puntual—, que no tiene petición de la que colgar.

        Las otras cuatro aplicaciones la exponen con este nombre; DDV solo tenía
        la dependencia, y quien necesitaba una sesión suelta acababa escribiendo
        `next(db_manager.get_session())`, que funciona por accidente y no cierra
        nada.
        """
        # Fallamos explícitamente si alguien la pide antes de initialize()
        if self._session_factory is None:
            raise RuntimeError(
                "DatabaseManager.initialize() must be called before opening sessions")

        # Devolvemos una sesión nueva
        return self._session_factory()

    # Entregamos una sesión de base de datos, para usar como dependencia de FastAPI
    def get_session(self) -> Generator[Session, None, None]:
        # Nos aseguramos de que initialize() ya se haya llamado
        if self._session_factory is None:
            # Avisamos con un error claro en vez de fallar más adelante con un mensaje confuso
            raise RuntimeError("Database not initialized")

        # Abrimos una sesión nueva
        session = self._session_factory()

        # Entregamos la sesión al llamador
        try:
            # Cedemos el control (yield) para que FastAPI la use durante el request
            yield session
        # Pase lo que pase durante el request (éxito o excepción)...
        finally:
            # ...siempre cerramos la sesión para no dejar conexiones colgadas
            session.close()

    # Buscamos una tabla reflejada por su nombre
    def get_table(self, table_name: str) -> Table:
        # Nos aseguramos de que initialize() ya se haya llamado
        if self._metadata is None:
            # Avisamos con un error claro en vez de fallar más adelante con un mensaje confuso
            raise RuntimeError("Database not initialized")

        # Devolvemos la tabla si existe, o None si no
        return self._metadata.tables.get(table_name)

    # Buscamos la tabla del dominio profundidad (alias explícito de get_table, para simetría con get_domain_table)
    def get_depth_table(self, table_name: str) -> Table:
        # Delegamos en get_table
        return self.get_table(table_name)

    # Buscamos la tabla de sensores del dominio pedido (profundidad o tiempo)
    def get_domain_table(self, domain: str = "depth") -> Table:
        # El dominio tiempo vive en una tabla aparte, que puede no existir en instalaciones viejas
        if domain == "time":
            # Buscamos primero en la metadata ya reflejada
            t = self._metadata.tables.get("well_data_time")

            # Si no estaba reflejada (se creó después del último reflect(), por ejemplo), la reflejamos ahora
            if t is None:
                # Intentamos reflejar la tabla directamente contra el engine
                try:
                    # Reflejamos solo esta tabla puntual, sin repetir el reflect() completo
                    t = Table("well_data_time", self._metadata, autoload_with=self._engine)
                # La tabla realmente no existe en esta base (well_data_time nunca se importó)
                except Exception:
                    # Devolvemos None para que el llamador sepa que no hay datos de tiempo
                    t = None

            # Devolvemos la tabla de tiempo (o None si no existe)
            return t

        # Por defecto (o domain="depth"), devolvemos la tabla de profundidad
        return self.get_table("well_data")

    # Verificamos si esta base de datos tiene la tabla de datos indexados por tiempo
    def has_time_data(self) -> bool:
        # Consultamos el catálogo de Postgres en vez de solo mirar la metadata en memoria,
        # porque la tabla puede haberse creado después de que este proceso arrancó
        try:
            # Abrimos una conexión de corta duración solo para esta consulta
            with self._engine.connect() as cx:
                # to_regclass devuelve NULL si la tabla no existe, sin lanzar excepción
                return cx.execute(text("SELECT to_regclass('well_data_time')")).scalar() is not None
        # Cualquier problema de conexión/permmisos lo tratamos como "no hay datos de tiempo"
        except Exception:
            # Devolvemos False en vez de dejar que la excepción se propague
            return False

    # Definimos la consulta recursiva que recorre, uno por uno, todos los well_id distintos
    # presentes en well_data_time (evita un SELECT DISTINCT completo sobre una tabla de decenas
    # de millones de filas, que sería mucho más lento que esta caminata usando el índice de well_id)
    _TIME_WELL_IDS_SQL = """
        WITH RECURSIVE t AS (
            (SELECT well_id FROM well_data_time ORDER BY well_id LIMIT 1)
            UNION ALL
            SELECT (SELECT well_id FROM well_data_time WHERE well_id > t.well_id ORDER BY well_id LIMIT 1)
            FROM t WHERE t.well_id IS NOT NULL
        )
        SELECT well_id FROM t WHERE well_id IS NOT NULL
    """

    # Obtenemos el set de well_id que tienen datos en el dominio tiempo, cacheado por un TTL
    def time_well_ids(self, ttl: float = 120.0) -> set:
        # Si esta base ni siquiera tiene la tabla de tiempo, no hay nada que buscar
        if not self.has_time_data():
            # Devolvemos un set vacío
            return set()

        # Tomamos la hora actual para comparar contra el caché
        now = time.monotonic()

        # Leemos el caché guardado en instancias previas de esta llamada, si existe
        cached = getattr(self, "_time_well_ids_cache", None)

        # Leemos cuándo se llenó ese caché
        cached_at = getattr(self, "_time_well_ids_cache_at", 0.0)

        # Si el caché existe y todavía no venció su TTL, lo reutilizamos
        if cached is not None and (now - cached_at) < ttl:
            # Devolvemos el caché sin volver a consultar la base
            return cached

        # Recalculamos porque no había caché o ya venció
        try:
            # Abrimos una conexión de corta duración solo para esta consulta
            with self._engine.connect() as cx:
                # Ejecutamos la consulta recursiva y armamos el set de well_id
                ids = {r[0] for r in cx.execute(text(self._TIME_WELL_IDS_SQL)).fetchall()}
        # Si la consulta falla (ej. problema de conexión pasajero)...
        except Exception:
            # ...devolvemos el caché anterior si había uno, o un set vacío si nunca se calculó
            return cached if cached is not None else set()

        # Guardamos el resultado nuevo en el caché de instancia
        self._time_well_ids_cache = ids

        # Guardamos cuándo se calculó, para el próximo chequeo de TTL
        self._time_well_ids_cache_at = now

        # Devolvemos el set recién calculado
        return ids

    # Armamos el diccionario {columna: tipo} de la tabla de profundidad, para inspección/debug
    def get_depth_columns(self) -> Dict[str, Any]:
        # Buscamos la tabla de profundidad
        table = self.get_table("well_data")

        # Si existe, devolvemos su esquema de columnas
        if table is not None:
            # Mapeamos cada columna a su tipo como string
            return {col.name: str(col.type) for col in table.columns}

        # Si la tabla no existe, devolvemos un diccionario vacío
        return {}

    # Cerramos la conexión a la base de datos (usado al apagar la aplicación)
    def close(self):
        # Solo hay algo que cerrar si initialize() llegó a crear el engine
        if self._engine:
            # Liberamos todas las conexiones del pool
            self._engine.dispose()

            # Registramos que la conexión quedó cerrada
            logger.info("PostgreSQL connection closed")

# Creamos la instancia única del manager que usa toda la aplicación
db_manager = DatabaseManager()


# Definimos la dependencia de FastAPI que entrega una sesión de base de datos por request
def get_db() -> Generator[Session, None, None]:
    # Delegamos en la sesión del manager, propagando el yield tal cual
    yield from db_manager.get_session()

# Creamos un alias explícito para las rutas que leen del dominio profundidad — misma
# dependencia que get_db, pero con un nombre que documenta la intención en la firma de la ruta
get_depth_db = get_db
