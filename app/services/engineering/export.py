"""CSV export for engineering-module results. Generic: it flattens whatever the
module's compute() returns — the scalar summary values, the input parameters, and
every tabular section (list-of-dicts) — into rows a spreadsheet can open. No
per-module bespoke code, so a new module exports for free."""
from typing import Any


def _is_table(v: Any) -> bool:
    return isinstance(v, list) and v and all(isinstance(x, dict) for x in v)


def module_csv_rows(key: str, title: str, res: dict, params: dict, dunit: str) -> list[list]:
    rows: list[list] = [[f"{title} — engineering result"], [f"Depth unit", dunit], []]

    # --- inputs ---
    rows.append(["# Inputs"])
    for k, v in params.items():
        rows.append([k, v])
    rows.append([])

    # --- scalar summary (skip nested structures) ---
    scalars = [(k, v) for k, v in res.items() if not isinstance(v, (list, dict))]
    if scalars:
        rows.append(["# Summary"])
        for k, v in scalars:
            rows.append([k, v])
        rows.append([])

    # --- every tabular section ---
    for k, v in res.items():
        if not _is_table(v):
            continue
        cols: list[str] = []
        for r in v:
            for c in r.keys():
                if c not in cols and not isinstance(r[c], (list, dict)):
                    cols.append(c)
        rows.append([f"# {k}"])
        rows.append(cols)
        for r in v:
            rows.append([r.get(c) for c in cols])
        rows.append([])
    return rows
