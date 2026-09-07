"""CSV export for engineering-module results. Generic: it flattens whatever the
module's compute() returns — the scalar summary values, the input parameters, and
every tabular section (list-of-dicts) — into rows a spreadsheet can open. No
per-module bespoke code, so a new module exports for free."""
# Importamos Any para tipar el valor genérico que evaluamos en _is_table
from typing import Any


def _is_table(v: Any) -> bool:
    # Consideramos que un valor es "tabla" si es una lista no vacía de diccionarios
    return isinstance(v, list) and v and all(isinstance(x, dict) for x in v)


def module_csv_rows(key: str, title: str, res: dict, params: dict, dunit: str) -> list[list]:
    # Iniciamos las filas del CSV con el título del módulo y la unidad de profundidad usada
    rows: list[list] = [[f"{title} — engineering result"], [f"Depth unit", dunit], []]

    # --- inputs ---
    # Agregamos la sección de parámetros de entrada, una fila por cada uno
    rows.append(["# Inputs"])
    for k, v in params.items():
        rows.append([k, v])
    rows.append([])

    # --- scalar summary (skip nested structures) ---
    # Filtramos los valores escalares del resultado (descartamos listas/diccionarios anidados)
    scalars = [(k, v) for k, v in res.items() if not isinstance(v, (list, dict))]
    if scalars:
        # Agregamos la sección de resumen escalar solo si hay valores que mostrar
        rows.append(["# Summary"])
        for k, v in scalars:
            rows.append([k, v])
        rows.append([])

    # --- every tabular section ---
    # Recorremos el resultado buscando cada sección tabular (lista de diccionarios) para exportarla
    for k, v in res.items():
        if not _is_table(v):
            continue
        # Recolectamos las columnas a partir de las claves de cada fila, evitando valores anidados
        cols: list[str] = []
        for r in v:
            for c in r.keys():
                if c not in cols and not isinstance(r[c], (list, dict)):
                    cols.append(c)
        # Agregamos el encabezado de la sección, la fila de columnas y luego cada fila de datos
        rows.append([f"# {k}"])
        rows.append(cols)
        for r in v:
            rows.append([r.get(c) for c in cols])
        rows.append([])
    # Devolvemos todas las filas listas para escribirse como CSV
    return rows
