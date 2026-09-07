"""Migra las dos tablas de sensores de DDV, que son 50,6 millones de filas.

Se separa del resto de la migracion porque es lo unico que no cabe de una vez:
well_data_time son 18 GB y well_data 3 GB, y el plan Pro trae 8 GB de disco.
Ampliarlo tiene coste, asi que el guion NO se lanza solo: hay que pasarle
--ejecutar, y antes conviene lanzarlo sin nada para ver el plan.

Como esta hecho:

  - Por lotes de 200 000 filas. Un COPY de 45 millones en una sola transaccion
    puede agotar la memoria del servidor y, si se corta a la mitad, se pierde
    todo el trabajo.
  - Reanudable. Cada lote se identifica por el rango de id, asi que si se corta
    se sigue desde donde iba en vez de empezar de cero.
  - Verificado al final: se comparan las cuentas y la suma de una columna
    numerica, que detecta filas perdidas y valores desplazados de columna.

    python migrar_sensores_ddv.py            -> muestra el plan, no escribe
    python migrar_sensores_ddv.py --ejecutar -> migra de verdad
    python migrar_sensores_ddv.py --ejecutar --tabla well_data --limite 5000
"""

import argparse
import io
import sys
import time

RAIZ = r"G:\Mi unidad\02. OIG\Drilling Data Visualization\01. Codigo"
sys.path.insert(0, RAIZ)

import psycopg2  # noqa: E402

from app.core.config import settings  # noqa: E402

ORIGEN = "postgresql://postgres:postgres@localhost:5432/drilling_db"

# Las dos tablas de sensores, con la columna por la que se recorre y una columna
# numerica cuya suma sirve para comprobar que nada se desplazo de sitio
TABLAS = {
    "well_data": {"orden": "id", "control": "hole_depth_feet"},
    "well_data_time": {"orden": "id", "control": "hole_depth_feet"},
}

# Filas por lote. Con 30 columnas de doble precision son unos 50 MB por lote.
LOTE = 200_000


def columnas(cur, esquema, tabla):
    """Columnas de una tabla, en el orden del catalogo."""
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema = %s and table_name = %s order by ordinal_position",
        (esquema, tabla),
    )
    return [c for (c,) in cur.fetchall()]


def escalar(cur, sql):
    """Ejecuta y devuelve el primer valor."""
    cur.execute(sql)
    return cur.fetchone()[0]


def migrar(tabla, cfg, cur_o, cur_s, supabase, limite=None, ejecutar=False):
    """Copia una tabla por lotes y devuelve (filas, segundos)."""
    orden = cfg["orden"]

    # Solo se copian las columnas que existen en las dos bases
    cols_o = columnas(cur_o, "public", tabla)
    cols_d = columnas(cur_s, "ddv", tabla)
    comunes = [c for c in cols_o if c in cols_d]
    lista = ", ".join(f'"{c}"' for c in comunes)

    # Cuantas hay en el origen y por donde va el destino
    total = escalar(cur_o, f"select count(*) from public.{tabla}")
    ya = escalar(cur_s, f"select count(*) from ddv.{tabla}")

    # Se reanuda desde el ultimo id copiado, no desde el principio
    desde = escalar(cur_s, f"select coalesce(max({orden}), 0) from ddv.{tabla}")

    pendientes = escalar(
        cur_o, f"select count(*) from public.{tabla} where {orden} > {desde}")

    if limite:
        pendientes = min(pendientes, limite)

    print(f"\n{tabla}")
    print(f"  columnas comunes : {len(comunes)} de {len(cols_o)}")
    print(f"  filas en origen  : {total:>14,}")
    print(f"  ya en destino    : {ya:>14,}")
    print(f"  por copiar       : {pendientes:>14,}"
          + (f"  (limitado a {limite:,})" if limite else ""))

    if not ejecutar:
        lotes = (pendientes + LOTE - 1) // LOTE
        print(f"  plan             : {lotes} lote(s) de {LOTE:,}")
        return 0, 0.0

    if not pendientes:
        print("  nada que copiar")
        return 0, 0.0

    copiadas = 0
    arranque = time.monotonic()

    while copiadas < pendientes:
        # Cuantas caben en este lote
        cuantas = min(LOTE, pendientes - copiadas)

        # Traemos el lote por rango de id, que usa el indice
        buffer = io.StringIO()
        cur_o.copy_expert(
            f"copy (select {lista} from public.{tabla} "
            f"where {orden} > {desde} order by {orden} limit {cuantas}) "
            f"to stdout with (format csv)",
            buffer,
        )
        buffer.seek(0)

        # Y lo escribimos
        cur_s.copy_expert(
            f"copy ddv.{tabla} ({lista}) from stdin with (format csv)", buffer)
        supabase.commit()

        # El siguiente lote arranca donde acabo este
        desde = escalar(cur_s, f"select max({orden}) from ddv.{tabla}")
        copiadas += cuantas

        # Avance, con lo que queda estimado
        transcurrido = time.monotonic() - arranque
        ritmo = copiadas / transcurrido if transcurrido else 0
        restan = (pendientes - copiadas) / ritmo if ritmo else 0
        print(f"    {copiadas:>12,} / {pendientes:,}"
              f"  ({ritmo:>8,.0f} filas/s, quedan {restan / 60:>5.1f} min)")

    return copiadas, time.monotonic() - arranque


def verificar(tabla, cfg, cur_o, cur_s):
    """Compara cuentas y la suma de la columna de control."""
    n_o = escalar(cur_o, f"select count(*) from public.{tabla}")
    n_s = escalar(cur_s, f"select count(*) from ddv.{tabla}")

    col = cfg["control"]
    s_o = escalar(cur_o, f"select coalesce(sum({col}), 0)::numeric(38,4) "
                         f"from public.{tabla}")
    s_s = escalar(cur_s, f"select coalesce(sum({col}), 0)::numeric(38,4) "
                         f"from ddv.{tabla}")

    filas_ok = n_o == n_s
    suma_ok = abs(float(s_o) - float(s_s)) < 0.01

    print(f"\n{tabla}: verificacion")
    print(f"  filas   origen {n_o:>14,}   destino {n_s:>14,}   "
          f"{'ok' if filas_ok else 'DESCUADRE'}")
    print(f"  suma de {col:<22} {'ok' if suma_ok else 'DESCUADRE'}")

    return filas_ok and suma_ok


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ejecutar", action="store_true",
                   help="copia de verdad; sin esto solo muestra el plan")
    p.add_argument("--tabla", choices=list(TABLAS),
                   help="migra solo esa tabla")
    p.add_argument("--limite", type=int,
                   help="copia como maximo esas filas, para probar")
    args = p.parse_args()

    origen = psycopg2.connect(ORIGEN)
    supabase = psycopg2.connect(settings.DATABASE_URL)
    cur_o, cur_s = origen.cursor(), supabase.cursor()
    cur_s.execute("set search_path = ddv, public")

    tablas = {args.tabla: TABLAS[args.tabla]} if args.tabla else TABLAS

    if not args.ejecutar:
        print("MODO PLAN: no se escribe nada. Anade --ejecutar para migrar.")

    total, segundos = 0, 0.0
    for tabla, cfg in tablas.items():
        n, s = migrar(tabla, cfg, cur_o, cur_s, supabase, args.limite, args.ejecutar)
        total += n
        segundos += s

    if not args.ejecutar:
        print("\nOJO: estas dos tablas son 21 GB. El plan Pro trae 8 GB de disco,")
        print("asi que migrarlas amplia el disco contratado y eso tiene coste.")
        return 0

    print(f"\n{total:,} filas copiadas en {segundos / 60:.1f} min")

    # Solo se verifica lo que se migro entero
    if args.limite:
        print("Migracion parcial (--limite): no se verifica el total.")
        return 0

    ok = all(verificar(t, cfg, cur_o, cur_s) for t, cfg in tablas.items())
    print("\n" + ("todo cuadra con el origen" if ok else "HAY DESCUADRES"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
