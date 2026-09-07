"""Mapping from WITS0 (record, item) codes to our well_data_time columns.

DELIBERATELY MOSTLY EMPTY. The (record, item) → parameter assignment is
NOT part of the public WITS0 standard for every channel — record 1 has some
well-established public items, but this specific SZJ-II installation ships
its own `WITS_Predefined_xx.ini` (see the system manual, section 2.2.6.6),
and vendors routinely use custom/user-defined record ranges for anything past
the handful of universally-agreed channels. Guessing item numbers here and
shipping them as if verified would silently write the wrong sensor's data
into the wrong column — worse than leaving the mapping empty and refusing to
ingest an unmapped slot.

HOW TO FILL THIS IN (do this before trusting any live data):
1. Get `WITS_Predefined_xx.ini` (or the printed WITS record/item table) from
   the SZJ-II software installed on the actual rig — Appendix/menu 2.2.6.6 in
   the manual, or ask JPIM directly.
2. For each row of interest, add an entry below: WITS_ITEM_MAP[(record, item)]
   = WitsColumn("<well_data_time column name>", scale=1.0, offset=0.0).
   `scale`/`offset` convert the WITS engineering unit to whatever unit our
   column already stores (see app/constants/parameters.py for our column
   names/units — most already match common oilfield units, so scale=1 is
   the common case).
3. Any (record, item) slot NOT listed here is silently ignored by the ingest
   manager (not stored, not an error) — that's intentional, so an unmapped
   channel never gets misfiled under the wrong name.
4. Re-run tests/test_wits0.py after editing (it round-trips a couple of
   entries here against the parser) and watch the first live frames via the
   Rig's "last raw frame" debug view before trusting a new mapping in
   production — see docs/realtime_wits_integration.md, section "Verificación
   del mapeo antes de confiar en los datos"."""
# Importamos dataclass para describir cada entrada del mapeo
from dataclasses import dataclass


# Definimos una entrada del mapeo: a qué columna de well_data_time va, y cómo convertir la unidad
@dataclass(frozen=True)
class WitsColumn:
    # Guardamos el nombre de la columna destino en well_data_time
    column: str
    # Guardamos el factor multiplicativo para convertir la unidad WITS a la unidad de la columna
    scale: float = 1.0
    # Guardamos el desplazamito aditivo (aplicado después del scale) para la misma conversión
    offset: float = 0.0


# Declaramos el mapeo real (record, item) -> WitsColumn. Empieza vacío a propósito — ver el
# docstring de este archivo para el procedimiento de llenarlo con los datos reales del equipo.
#
# Ejemplos ILUSTRATIVOS (comentados, NO confirmados) de cómo se vería una vez tengamos el
# WITS_Predefined_xx.ini real — record 1 "General Time-Based Drilling Data" es la sección más
# comúnmente estandarizada en implementaciones WITS0, pero incluso ahí cada vendor puede variar:
#
# WITS_ITEM_MAP: dict[tuple[int, int], WitsColumn] = {
#     (1, 8):  WitsColumn("bit_depth_feet"),                        # profundidad de la broca, ft
#     (1, 10): WitsColumn("weight_on_bit_klbs"),                    # peso sobre la broca, klb
#     (1, 11): WitsColumn("hook_load_klbs"),                        # peso en el gancho, klb
#     (1, 13): WitsColumn("rotary_rpm_rpm"),                        # RPM de la mesa rotaria
#     (1, 17): WitsColumn("standpipe_pressure_psi"),                # presión de standpipe, psi
#     (1, 19): WitsColumn("rate_of_penetration_ft_per_hr"),         # ROP, ft/hr
# }
WITS_ITEM_MAP: dict[tuple[int, int], WitsColumn] = {}


# Traducimos una trama WITS0 ya decodificada a un diccionario {columna: valor} listo para insertar
# en well_data_time, usando el mapeo de arriba. Los slots sin mapeo configurado se ignoran.
def map_frame_to_row(frame, item_map: dict[tuple[int, int], WitsColumn] | None = None) -> dict:
    # Usamos el mapeo global por defecto, salvo que el llamador pase uno propio (útil para tests)
    active_map = item_map if item_map is not None else WITS_ITEM_MAP
    row: dict = {}
    # Recorremos únicamente los slots que sí tenemos mapeados
    for (record, item), wits_col in active_map.items():
        raw = frame.as_float(record, item)
        if raw is None:
            # El slot no vino en esta trama, o no es numérico — lo dejamos fuera de la fila
            continue
        # Aplicamos la conversión de unidad configurada (scale y luego offset)
        row[wits_col.column] = raw * wits_col.scale + wits_col.offset
    return row
