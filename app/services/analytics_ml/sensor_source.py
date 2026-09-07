"""Bridge the ops Analytics to the REAL sensor record.

An ops Event → Wellbore → ops Well may carry a `legacy_well_id` (the unified
legacy sensor well). When it does, we can feed ROP / dysfunction analytics the
actual high-frequency `well_data` (depth-indexed) or `well_data_time` (time-
indexed) instead of the manually-captured `drill-params` grid.

Honest data note: the sensor channel set has ROP, WOB, RPM, SPP, flow, depth and
differential pressure — but NO surface torque, bit size or formation. So MSE
(needs torque + bit diameter) is NOT computed from sensor data; founder analysis
falls back to the ROP-vs-WOB response, which is a valid method on its own.
"""
# Importamos Optional para tipar los retornos que pueden ser None
from typing import Optional

# Importamos text para ejecutar SQL crudo parametrizado
from sqlalchemy import text
# Importamos Session para tipar la sesión de base de datos recibida
from sqlalchemy.orm import Session

# well_data column → standard drilling-point key
# Mapeamos cada columna de well_data/well_data_time a la clave estándar del punto de perforación
_CHANNELS = {
    "depth_md": "bit_depth_feet",
    "rop": "rate_of_penetration_ft_per_hr",
    "wob": "weight_on_bit_klbs",
    "rpm": "rotary_rpm_rpm",
    "flow_gpm": "total_pump_output_gal_per_min",
    "spp_psi": "standpipe_pressure_psi",
    "diff_psi": "differential_pressure_psi",
}


def legacy_well_id(db: Session, event_id: str) -> Optional[int]:
    """event → wellbore → ops well → legacy_well_id (or None)."""
    # Recorremos la jerarquía evento → wellbore → pozo ops para obtener el enlace al pozo legacy
    row = db.execute(text(
        "SELECT w.legacy_well_id FROM events e "
        "JOIN wellbores wb ON wb.id = e.wellbore_id "
        "JOIN wells w ON w.id = wb.well_id "
        "WHERE e.id = :eid"
    ), {"eid": event_id}).fetchone()
    # Devolvemos el id del pozo legacy si existe, o None si no hay enlace
    return row[0] if row and row[0] is not None else None


def has_sensor_data(db: Session, event_id: str, domain: str = "depth") -> bool:
    # Buscamos el pozo legacy enlazado al evento
    lw = legacy_well_id(db, event_id)
    if lw is None:
        # Sin pozo legacy no hay datos de sensor posibles
        return False
    # Elegimos la tabla de sensores según el dominio (profundidad o tiempo)
    table = "well_data_time" if domain == "time" else "well_data"
    try:
        # Verificamos si existe al menos una fila de datos para ese pozo
        return db.execute(text(f"SELECT 1 FROM {table} WHERE well_id=:w LIMIT 1"), {"w": lw}).fetchone() is not None
    except Exception:
        # Si la tabla no existe o falla la consulta, asumimos que no hay datos de sensor
        return False


def drilling_points(db: Session, event_id: str, domain: str = "depth", max_points: int = 4000) -> dict:
    """Real drilling points for the well behind an event, from the sensor record.
    Returns {source, domain, well_id, n, points:[...]} — source is
    'sensor-depth'/'sensor-time' or 'none'. Points use the standard keys
    (torque_ftlb / mse_ksi / bit_size / formation are None — not in the channels)."""
    # Buscamos el pozo legacy enlazado al evento
    lw = legacy_well_id(db, event_id)
    if lw is None:
        # Sin pozo legacy no hay puntos de perforación reales que devolver
        return {"source": "none", "points": [], "n": 0, "domain": domain, "well_id": None}
    # Elegimos la tabla de sensores según el dominio (profundidad o tiempo)
    table = "well_data_time" if domain == "time" else "well_data"

    try:
        # Contamos cuántas filas de sensor tiene este pozo
        n = db.execute(text(f"SELECT count(*) FROM {table} WHERE well_id=:w"), {"w": lw}).scalar() or 0
    except Exception:
        # Si la consulta falla, reportamos que no hay fuente de datos disponible
        return {"source": "none", "points": [], "n": 0, "domain": domain, "well_id": lw}
    if n == 0:
        # Sin filas de sensor, no hay puntos que devolver
        return {"source": "none", "points": [], "n": 0, "domain": domain, "well_id": lw}

    # downsample large series with a modulo stride on the primary key
    # Calculamos el paso de muestreo para no traer más de max_points filas
    stride = max(1, n // max_points)
    # Armamos la lista de columnas a seleccionar, renombradas a las claves estándar
    sel = ", ".join(f"{col} AS {key}" for key, col in _CHANNELS.items())
    # Traemos las filas muestreadas ordenadas por id
    rows = db.execute(text(
        f"SELECT {sel} FROM {table} WHERE well_id=:w AND (id % :s)=0 ORDER BY id LIMIT :lim"
    ), {"w": lw, "s": stride, "lim": max_points}).mappings().all()

    # Keep only ON-BOTTOM drilling samples (real ROP and WOB), then aggregate the
    # high-frequency stream into depth bins so the analytics see clean interval-
    # level points (like the manual grid) instead of noisy 10-second samples.
    raw = []
    for r in rows:
        # Convertimos cada canal relevante a float, tolerando valores nulos o inválidos
        rop, wob, depth = _f(r["rop"]), _f(r["wob"]), _f(r["depth_md"])
        # Descartamos muestras que no representen perforación real en fondo (ROP/WOB positivos y profundidad válida)
        if rop is None or rop <= 0 or wob is None or wob <= 0 or depth is None:
            continue
        raw.append((depth, rop, wob, _f(r["rpm"]), _f(r["flow_gpm"]), _f(r["spp_psi"]), _f(r["diff_psi"])))

    BIN = 30.0  # ft
    bins: dict = {}
    # Agrupamos las muestras crudas en bins de 30 ft para suavizar el ruido de alta frecuencia
    for depth, rop, wob, rpm, flow, spp, diff in raw:
        bins.setdefault(round(depth / BIN) * BIN, []).append((rop, wob, rpm, flow, spp, diff))

    def _avg(vals):
        # Promediamos ignorando los valores nulos dentro del bin
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    points = []
    # Construimos un punto agregado por cada bin de profundidad, ordenado de menor a mayor
    for depth in sorted(bins):
        b = bins[depth]
        points.append({
            "depth_md": depth,
            "rop": _avg([x[0] for x in b]), "wob": _avg([x[1] for x in b]),
            "rpm": _avg([x[2] for x in b]), "flow_gpm": _avg([x[3] for x in b]),
            "spp_psi": _avg([x[4] for x in b]), "diff_psi": _avg([x[5] for x in b]),
            "torque_ftlb": None, "mse_ksi": None, "bit_size": None, "formation": None,
        })
    # Devolvemos los puntos agregados junto con metadatos de la fuente y el muestreo
    return {"source": f"sensor-{domain}", "points": points, "n": len(points),
            "domain": domain, "well_id": lw, "raw_samples": len(raw)}


def _f(v):
    try:
        # Convertimos a float si el valor no es nulo
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        # Si no se puede convertir, tratamos el valor como ausente
        return None
