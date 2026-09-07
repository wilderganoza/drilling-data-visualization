"""Background service that keeps one live WITS0 connection per enabled
RealtimeSource, decodes incoming frames, and inserts them into
well_data_time. One instance of RealtimeIngestManager lives for the whole
process (created in app.main's startup/shutdown hooks, same pattern as
db_manager in app/db/session.py).

The app's ORM stack is synchronous SQLAlchemy (psycopg2, not an async
driver) — every DB call here runs through asyncio.to_thread() so a slow
query never blocks the event loop that's also reading the WITS0 socket."""
# Importamos asyncio para las tareas en background, los sockets y los timeouts
import asyncio
# Importamos datetime/timezone para sellar cuándo llegó el último dato
from datetime import datetime, timezone

# Importamos insert para construir el INSERT crudo sobre la tabla reflejada well_data_time
from sqlalchemy import insert

# Importamos el logger de la app
from app.core.logging import get_logger
# Importamos el gestor de conexión/tablas reflejadas (well_data_time no es un modelo ORM)
from app.db.session import db_manager
# Importamos los modelos de la jerarquía ops, para resolver event -> wellbore -> well -> legacy_well_id
from app.models.hierarchy import Event, Well as OpsWell, Wellbore
# Importamos el modelo de pozo legacy, al que se auto-provisiona un vínculo si el pozo ops no tenía uno
from app.models.legacy import SensorWell as LegacyWell
# Importamos Rig, la ficha del taladro físico (host/puerto/modo del canal WITS0)
from app.models.realtime import Rig
# Importamos el repositorio de fuentes en tiempo real
from app.repositories.realtime_repository import RealtimeSourceRepository
# Importamos el lector de tramas WITS0 desde un socket asyncio
from app.services.realtime.wits0 import iter_wits0_frames
# Importamos la traducción de una trama decodificada a una fila de well_data_time
from app.services.realtime.wits0_map import map_frame_to_row

# Creamos el logger de este módulo
logger = get_logger(__name__)

# Definimos cuánto esperamos antes de reintentar una conexión caída o fallida
RECONNECT_DELAY_SECONDS = 5.0
# Definimos cuánto esperamos a que el taladro se conecte a nosotros en modo "server", antes de reintentar
SERVER_ACCEPT_TIMEOUT_SECONDS = 300.0
# Definimos cada cuántos segundos, como máximo, escribimos el "heartbeat" (última llegada de datos +
# contador de filas) en la base — evita un UPDATE por cada trama si el equipo manda una por segundo
HEARTBEAT_INTERVAL_SECONDS = 5.0


# Centralizamos todas las conexiones WITS0 activas del proceso: una tarea asyncio por RealtimeSource habilitada
class RealtimeIngestManager:
    # Inicializamos el manager sin tareas corriendo todavía
    def __init__(self):
        # Guardamos las tareas en curso, indexadas por el id (string) de la RealtimeSource
        self._tasks: dict[str, asyncio.Task] = {}

    # Reanudamos, al arrancar la app, toda fuente que haya quedado habilitada de una corrida anterior
    async def start(self) -> None:
        # Leemos qué fuentes están habilitadas ahora mismo (fuera del hilo del event loop, es una consulta síncrona)
        sources = await asyncio.to_thread(self._list_enabled_ids)
        for source_id in sources:
            # Lanzamos una tarea de conexión por cada fuente habilitada
            self.spawn(source_id)
        logger.info(f"RealtimeIngestManager: reanudadas {len(sources)} fuentes habilitadas")

    # Cancelamos todas las tareas en curso, de forma prolija, al apagar la app
    async def stop(self) -> None:
        # Cancelamos cada tarea activa
        for task in list(self._tasks.values()):
            task.cancel()
        # Esperamos a que todas terminen de cancelarse (ignorando la CancelledError esperada)
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        # Vaciamos el registro de tareas
        self._tasks.clear()
        logger.info("RealtimeIngestManager: todas las conexiones WITS0 cerradas")

    # Lanzamos (o relanzamos) la tarea de conexión de una fuente puntual — lo llama la ruta web
    # cuando el usuario activa el canal, y start() al arrancar la app
    def spawn(self, source_id: str) -> None:
        # Si ya había una tarea corriendo para esta fuente, la cancelamos primero (evita dos conexiones dobles)
        self.cancel(source_id)
        # Creamos la tarea de background que mantiene viva la conexión con reconexión automática
        task = asyncio.create_task(self._run_source(source_id), name=f"wits0-source-{source_id}")
        self._tasks[source_id] = task

    # Cancelamos la tarea de una fuente puntual — lo llama la ruta web cuando el usuario desactiva el canal
    def cancel(self, source_id: str) -> None:
        task = self._tasks.pop(source_id, None)
        if task is not None:
            task.cancel()

    # Consultamos si una fuente tiene una tarea de conexión corriendo ahora mismo (para la UI de estado)
    def is_running(self, source_id: str) -> bool:
        task = self._tasks.get(source_id)
        return task is not None and not task.done()

    # --- helpers síncronos, siempre invocados vía asyncio.to_thread() ------------------------

    # Leemos los ids (string) de todas las RealtimeSource con enabled=True
    def _list_enabled_ids(self) -> list[str]:
        session = next(db_manager.get_session())
        try:
            repo = RealtimeSourceRepository(session)
            return [str(s.id) for s in repo.list_enabled()]
        finally:
            session.close()

    # Cargamos la fuente y su taladro; devolvemos (None, None) si ya no existe o fue deshabilitada
    def _load_source_and_rig(self, source_id: str):
        session = next(db_manager.get_session())
        try:
            repo = RealtimeSourceRepository(session)
            source = repo.get(source_id)
            if source is None or not source.enabled:
                return None, None
            rig = session.get(Rig, source.rig_id)
            return source, rig
        finally:
            session.close()

    # Resolvemos el well_id legacy (el que usan well_data/well_data_time) a partir del Event ops;
    # si el pozo ops todavía no tenía vínculo legacy, lo creamos aquí mismo (un pozo nuevo, sin
    # datos de sensores importados previamente, simplemente no tenía por qué tener uno todavía).
    def _resolve_legacy_well_id(self, event_id) -> int:
        session = next(db_manager.get_session())
        try:
            event = session.get(Event, event_id)
            wellbore = session.get(Wellbore, event.wellbore_id)
            ops_well = session.get(OpsWell, wellbore.well_id)
            # Si el pozo ops ya está vinculado a un pozo legacy, usamos ese id directamente
            if ops_well.legacy_well_id is not None:
                return ops_well.legacy_well_id
            # Si no, creamos el pozo legacy que va a recibir los datos en tiempo real
            legacy = LegacyWell(well_name=ops_well.legal_well_name, total_rows=0, total_columns=0)
            session.add(legacy)
            session.flush()
            # Vinculamos el pozo ops al pozo legacy recién creado, para que quede unificado a futuro
            ops_well.legacy_well_id = legacy.id
            session.commit()
            logger.info(f"Auto-provisioned legacy well {legacy.id} for ops well {ops_well.id}")
            return legacy.id
        finally:
            session.close()

    # Insertamos una fila de datos en well_data_time, sellada con la fecha/hora actual
    def _insert_row(self, well_id: int, row: dict) -> None:
        table = db_manager.get_domain_table("time")
        if table is None:
            raise RuntimeError("well_data_time table not found — ¿se corrió la importación inicial de datos?")
        now = datetime.now(timezone.utc)
        payload = dict(row)
        # Completamos las columnas que no vienen del mapeo WITS: a qué pozo pertenece y cuándo llegó
        payload["well_id"] = well_id
        # Usamos el mismo formato que ya tienen los datos importados ("YYYY/MM/DD" y "HH:MM:SS")
        payload["yyyy_mm_dd"] = now.strftime("%Y/%m/%d")
        payload["hh_mm_ss"] = now.strftime("%H:%M:%S")
        with db_manager._engine.begin() as cx:
            cx.execute(insert(table).values(**payload))

    # Actualizamos el estado observado de una fuente (lo que ve la UI de estado)
    def _update_status(self, source_id: str, *, status: str | None = None, last_error: str | None = None,
                        touch_data: bool = False, rows_delta: int = 0, set_started: bool = False) -> None:
        session = next(db_manager.get_session())
        try:
            repo = RealtimeSourceRepository(session)
            source = repo.get(source_id)
            if source is None:
                return
            if status is not None:
                source.status = status
            if last_error is not None:
                source.last_error = last_error[:500]
            if touch_data:
                source.last_data_at = datetime.now(timezone.utc)
            if rows_delta:
                source.rows_ingested = (source.rows_ingested or 0) + rows_delta
            if set_started and source.started_at is None:
                source.started_at = datetime.now(timezone.utc)
            session.commit()
        finally:
            session.close()

    # --- el bucle principal por fuente --------------------------------------------------------

    # Esperamos UNA conexión entrante en el puerto dado (modo "server": el taladro se conecta a
    # nosotros) y devolvemos su (reader, writer); cerramos el listener apenas aceptamos la primera.
    async def _accept_once(self, port: int):
        connection: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _on_client(reader, writer):
            # Resolvemos el future con la primera conexión que llegue; ignoramos conexiones extra
            if not connection.done():
                connection.set_result((reader, writer))

        server = await asyncio.start_server(_on_client, host="0.0.0.0", port=port)
        try:
            reader, writer = await asyncio.wait_for(connection, timeout=SERVER_ACCEPT_TIMEOUT_SECONDS)
        finally:
            # Cerramos el listener apenas tenemos una conexión (o si el timeout expiró) — solo
            # aceptamos un taladro por fuente, no un servidor multi-cliente. A propósito NO
            # esperamos server.wait_closed(): esa llamada espera a que TODAS las conexiones que
            # el server llegó a aceptar terminen de cerrarse — incluida la que acabamos de aceptar
            # y que justamente queremos seguir usando más abajo, así que esperarla aquí sería un
            # deadlock permanente (confirmado reproduciendo el cuelgue antes de este fix).
            server.close()
        return reader, writer

    # Mantenemos viva la conexión de una fuente: conecta, lee tramas, reconecta si se cae, para
    # de reintentar solo cuando la fuente fue deshabilitada o borrada.
    async def _run_source(self, source_id: str) -> None:
        while True:
            source, rig = await asyncio.to_thread(self._load_source_and_rig, source_id)
            if source is None or rig is None:
                # La fuente fue deshabilitada/borrada mientras reconectábamos — dejamos de intentar
                return

            well_id = await asyncio.to_thread(self._resolve_legacy_well_id, source.event_id)
            await asyncio.to_thread(self._update_status, source_id, status="connecting", set_started=True)

            reader = writer = None
            try:
                if rig.wits_mode == "server":
                    # Esperamos a que el taladro se conecte a nosotros
                    reader, writer = await self._accept_once(rig.wits_port)
                else:
                    # Nos conectamos nosotros hacia el taladro
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(rig.wits_host, rig.wits_port), timeout=15.0)
            except (OSError, asyncio.TimeoutError) as exc:
                # No pudimos conectar (equipo apagado, IP/puerto incorrectos, red caída, etc.)
                logger.warning(f"WITS0 source {source_id} ({rig.name}): connection failed: {exc}")
                await asyncio.to_thread(self._update_status, source_id, status="error", last_error=str(exc))
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
                continue

            logger.info(f"WITS0 source {source_id} conectada al taladro {rig.name}")
            await asyncio.to_thread(self._update_status, source_id, status="connected")

            rows_since_heartbeat = 0
            last_heartbeat = 0.0
            try:
                # Leemos tramas del socket a medida que llegan, hasta que la conexión se cierre
                async for frame in iter_wits0_frames(reader):
                    row = map_frame_to_row(frame)
                    if not row:
                        # Ningún slot de esta trama está en nuestro mapeo (ver wits0_map.py) — la saltamos
                        continue
                    await asyncio.to_thread(self._insert_row, well_id, row)
                    rows_since_heartbeat += 1
                    # Escribimos el heartbeat (última llegada + contador) como mucho cada
                    # HEARTBEAT_INTERVAL_SECONDS, para no golpear la base con un UPDATE por trama
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                        await asyncio.to_thread(
                            self._update_status, source_id, status="connected",
                            touch_data=True, rows_delta=rows_since_heartbeat)
                        rows_since_heartbeat = 0
                        last_heartbeat = now
            except asyncio.CancelledError:
                # Nos están deteniendo a propósito (desactivación del canal o apagado de la app) — no reintentamos
                raise
            except Exception as exc:
                logger.error(f"WITS0 source {source_id} ({rig.name}): error while reading: {exc}")
                await asyncio.to_thread(
                    self._update_status, source_id, status="error", last_error=str(exc),
                    rows_delta=rows_since_heartbeat)
            else:
                # El taladro cerró la conexión de su lado, sin que nosotros la canceláramos
                await asyncio.to_thread(
                    self._update_status, source_id, status="disconnected", rows_delta=rows_since_heartbeat)
            finally:
                if writer is not None:
                    writer.close()

            # Antes de reintentar, esperamos un poco y confirmamos que la fuente siga habilitada
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)


# Creamos la instancia única del manager que usa toda la aplicación (mismo patrón que db_manager)
realtime_manager = RealtimeIngestManager()
