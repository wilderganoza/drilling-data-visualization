from datetime import datetime  # Usamos datetime para parsear las marcas de tiempo de los registros
from typing import Optional  # Tipamos el retorno opcional del parseo de timestamps

from fastapi import APIRouter, Depends, Form, Request  # Router y utilidades de FastAPI para las rutas web
from fastapi.responses import HTMLResponse  # Tipo de respuesta HTML para las rutas
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy inyectada

from app.core.deps import get_current_user_web  # Dependencia que exige un usuario autenticado
from app.models.legacy import User, Well  # Modelos User y Well (pozo legacy con datos de sensores)
from app.repositories.well_repository import WellRepository  # Repositorio para consultar los pozos
from app.db.session import get_db, get_depth_db  # Dependencias de sesión: BD principal y BD de dominio profundidad
from app.web.shared import dataset_options, fetch_records, num as _num, parse_dataset_id  # Helpers compartidos entre vistas web
from app.web.templating import templates  # Motor de plantillas Jinja compartido

router = APIRouter()

SAMPLE_SIZE = 50000  # Límite de registros que muestreamos para no sobrecargar los gráficos


def _depth_of(record: dict) -> float:
    # Preferimos la profundidad del hoyo; si no existe, usamos la del bit; si tampoco, devolvemos cero
    return _num(record.get("hole_depth_feet")) or _num(record.get("bit_depth_feet")) or 0.0


def _parse_timestamp(date_str, time_str) -> Optional[datetime]:
    # Sin fecha no hay nada que parsear
    if not date_str:
        return None
    # Source column is yyyy_mm_dd stored as "YYYY/MM/DD" text, not ISO dashes.
    # Probamos ambos formatos posibles porque la columna de origen no siempre usa guiones ISO
    for date_fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            # Si hay hora, combinamos fecha y hora en un solo datetime
            if time_str:
                return datetime.strptime(f"{date_str} {time_str}", f"{date_fmt} %H:%M:%S")
            # Si no hay hora, parseamos solo la fecha
            return datetime.strptime(date_str, date_fmt)
        except ValueError:
            # Probamos el siguiente formato si este no coincide
            continue
    # Ningún formato coincidió: no pudimos parsear el timestamp
    return None


def _build_chart_payload(records: list[dict], domain: str = "depth") -> dict:
    """Build the Wells-view chart data for the given domain.

    Depth-indexed data is a *depth series*: it is sorted by depth and every chart
    uses depth on the X axis (monotonic). Time-indexed data is a *time series*: the
    bit trips up and down the hole, so plotting it against depth is meaningless (the
    same depth recurs at many times and the X axis collapses). For the time domain we
    therefore sort chronologically and use **elapsed hours** as a continuous X axis.
    """
    is_time = domain == "time"

    # Parse every timestamp once — needed for the time-domain X axis and for stats.
    # Parseamos cada timestamp una sola vez, ya que lo necesitamos tanto para el eje X de tiempo como para las estadísticas
    parsed = [_parse_timestamp(r.get("yyyy_mm_dd"), r.get("hh_mm_ss")) for r in records]
    valid_ts = [t for t in parsed if t is not None]
    # Guardamos el timestamp inicial para calcular horas transcurridas
    start_ts = min(valid_ts) if valid_ts else None

    if is_time:
        # Chronological order; drop rows without a usable timestamp.
        # En dominio tiempo ordenamos cronológicamente y descartamos filas sin timestamp válido
        ordered = sorted(
            (p for p in zip(parsed, records) if p[0] is not None),
            key=lambda p: p[0],
        )
    else:
        # En dominio profundidad ordenamos por profundidad, ya que es un eje monotónico
        ordered = sorted(zip(parsed, records), key=lambda p: _depth_of(p[1]))

    rop_data = []
    depth_time_data = []
    multi_param_data = []
    rop_values = []
    depths = []

    for ts, r in ordered:
        # Obtenemos la profundidad preferida (hoyo) o, si falta, la del bit
        depth = _num(r.get("hole_depth_feet")) if _num(r.get("hole_depth_feet")) is not None else _num(r.get("bit_depth_feet"))
        bit_depth = _num(r.get("bit_depth_feet"))
        rop = _num(r.get("rate_of_penetration_ft_per_hr"))
        date_str = r.get("yyyy_mm_dd")
        time_str = r.get("hh_mm_ss")
        timestamp = f"{date_str} {time_str}" if date_str and time_str else date_str

        if is_time:
            # Elapsed hours since the first sample: a continuous, monotonic X axis.
            # Calculamos horas transcurridas desde la primera muestra para un eje X continuo y monotónico
            x = round((ts - start_ts).total_seconds() / 3600.0, 4) if (ts and start_ts) else None
        else:
            # En dominio profundidad, el eje X es directamente la profundidad
            x = depth

        rop_data.append({"x": x, "rop": rop})
        depth_time_data.append({"x": x, "time": timestamp, "depth": bit_depth})
        multi_param_data.append(
            {
                "x": x,
                "wob": _num(r.get("weight_on_bit_klbs")),
                "rpm": _num(r.get("rotary_rpm_rpm")),
                "pressure": _num(r.get("standpipe_pressure_psi")),
                "hookload": _num(r.get("hook_load_klbs")),
            }
        )

        # Acumulamos los valores de ROP y profundidad para calcular promedios y máximos después
        if rop is not None:
            rop_values.append(rop)
        if bit_depth is not None:
            depths.append(bit_depth)

    # Calculamos el ROP promedio y la profundidad máxima alcanzada
    avg_rop = sum(rop_values) / len(rop_values) if rop_values else None
    max_depth = max(depths) if depths else None

    # Devolvemos el payload completo que consumen los gráficos de la vista Wells
    return {
        "rop_data": rop_data,
        "depth_time_data": depth_time_data,
        "multi_param_data": multi_param_data,
        "total_records": len(records),
        "avg_rop": avg_rop,
        "max_depth": max_depth,
        "start_date": start_ts.strftime("%Y-%m-%d") if start_ts else None,
        "is_time": is_time,
        "x_label": "Elapsed Time (hr)" if is_time else "Depth (ft)",
    }


@router.get("/wells", response_class=HTMLResponse)
async def wells_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos todos los pozos para poblar el selector de la página
    wells = WellRepository(db).get_all(skip=0, limit=1000)
    # Importamos db_manager aquí para consultar los pozos con datos de dominio tiempo
    from app.db.session import db_manager
    time_well_ids = db_manager.time_well_ids()
    # Renderizamos la página principal de Wells
    return templates.TemplateResponse(
        request,
        "pages/wells.html",
        {"request": request, "wells": wells, "current_user": current_user,
         "time_well_ids": time_well_ids, "has_time_data": db_manager.has_time_data()},
    )


@router.get("/wells/well-options", response_class=HTMLResponse)
async def wells_well_options(request: Request, domain: str = "depth", db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Importamos el helper aquí para evitar dependencias circulares en el módulo
    from app.web.shared import wells_for_domain
    # Filtramos los pozos según el dominio elegido (profundidad o tiempo)
    wells, time_ids = wells_for_domain(db, domain)
    # Devolvemos el fragmento HTML con las opciones de pozo ya filtradas
    return templates.TemplateResponse(request, "partials/well_options.html",
                                      {"request": request, "wells": wells, "time_well_ids": time_ids})


@router.get("/wells/datasets", response_class=HTMLResponse)
async def wells_dataset_options(
    request: Request,
    well_id: int,
    domain: str = "depth",
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos las opciones de dataset disponibles para el pozo y dominio elegidos
    options = dataset_options(db, well_id, domain)
    # Devolvemos el fragmento HTML con el selector de dataset ya poblado
    return templates.TemplateResponse(
        request,
        "partials/dataset_select.html",
        {
            "request": request,
            "options": options,
            "select_id": "wells-dataset-select",
            "select_name": "dataset_id",
        },
    )


@router.post("/wells/open", response_class=HTMLResponse)
async def wells_open(
    request: Request,
    well_id: str = Form(""),
    dataset_id: str = Form("raw"),
    domain: str = Form("depth"),
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # well_id arrives as a string so an empty submission (e.g. clicking "Open Well"
    # before picking a well, which happens right after switching domain) renders the
    # empty state instead of a 422.
    # Intentamos convertir well_id a entero; si no hay pozo seleccionado, mostramos el estado vacío
    try:
        well_id_int = int(well_id)
    except (TypeError, ValueError):
        return templates.TemplateResponse(
            request,
            "partials/wells_charts.html",
            {"request": request, "well_name": None, "has_data": False, "payload": None},
        )
    well_id = well_id_int

    # Resolvemos el identificador de dataset (raw o el id de un dataset procesado)
    processed_dataset_id = parse_dataset_id(dataset_id)
    # Buscamos el pozo para mostrar su nombre; si no existe, usamos un nombre genérico con el id
    well = db.query(Well).filter(Well.id == well_id).first()
    well_name = well.well_name if well else f"Well {well_id}"

    # Obtenemos los registros del pozo respetando el dominio (profundidad o tiempo)
    records = fetch_records(db, well_id, processed_dataset_id, raw_sample_size=SAMPLE_SIZE, processed_page_size=SAMPLE_SIZE, domain=domain)
    has_data = len(records) > 0
    # Construimos el payload de los gráficos solo si hay datos que mostrar
    payload = _build_chart_payload(records, domain) if has_data else None

    # Renderizamos el fragmento con los gráficos del pozo abierto
    return templates.TemplateResponse(
        request,
        "partials/wells_charts.html",
        {
            "request": request,
            "well_name": well_name,
            "has_data": has_data,
            "payload": payload,
        },
    )
