"""Migra los datos de DDV de la base local al esquema ddv de Supabase.

Copia las 46 tablas pequenas (25 875 filas). Deja fuera well_data y
well_data_time a proposito: son 50,6 millones de filas y 21 GB, y eso necesita
antes una decision de disco contratado.

Dos cosas que hay que hacer con cuidado:

  - Las columnas NO estan en el mismo orden en las dos bases. La local la creo
    Alembic y la de Supabase la creo create_all, que coloca id y las marcas de
    auditoria al final. Un COPY sin lista de columnas emparejaria por posicion y
    metaria un uuid en una columna de fecha, que es justo lo que paso al
    intentarlo. Aqui se copian por nombre.

  - Cada tabla va en su propio punto de guardado. Si una falla, se deshace solo
    esa y las demas siguen; si no, un fallo tardio se lleva por delante lo ya
    cargado y todo lo que dependa de ello falla en cascada.

El nombre de cada tabla cambia en el camino: en Supabase ya no llevan el prefijo
ops_ y wells paso a llamarse sensor_wells.
"""

import io
import sys

RAIZ = r"G:\Mi unidad\02. OIG\Drilling Data Visualization\01. Codigo"
sys.path.insert(0, RAIZ)

import psycopg2  # noqa: E402

from app.core.config import settings  # noqa: E402

ORIGEN = "postgresql://postgres:postgres@localhost:5432/drilling_db"

# Las dos tablas de sensores se quedan fuera de esta pasada
# alembic_version tambien queda fuera: Alembic se retiro a proposito y las
# migraciones son SQL plano en supabase/migrations
EXCLUIDAS = {"well_data", "well_data_time", "alembic_version"}


# Nombre local -> nombre en Supabase
def destino(tabla: str) -> str:
    if tabla == "wells":
        return "sensor_wells"
    if tabla.startswith("ops_"):
        return tabla[4:]
    return tabla


# Orden de carga: los padres antes que los hijos, calculado del grafo de claves
# foraneas en vez de escrito a mano, que se desactualizaria.
ORDEN_SQL = """
with recursive fk as (
  select t.relname as tabla, f.relname as padre
  from pg_constraint c
  join pg_class t on t.oid = c.conrelid
  join pg_class f on f.oid = c.confrelid
  join pg_namespace n on n.oid = t.relnamespace
  where n.nspname = 'public' and c.contype = 'f' and t.relname <> f.relname
),
niveles as (
  select t.relname as tabla, 0 as nivel
  from pg_class t join pg_namespace n on n.oid = t.relnamespace
  where n.nspname = 'public' and t.relkind = 'r'
    and not exists (select 1 from fk where fk.tabla = t.relname)
  union all
  select fk.tabla, niveles.nivel + 1
  from fk join niveles on niveles.tabla = fk.padre
  where niveles.nivel < 12
)
select tabla, max(nivel) as nivel from niveles group by tabla order by 2, 1
"""

origen = psycopg2.connect(ORIGEN)
supabase = psycopg2.connect(settings.DATABASE_URL)

cur_o = origen.cursor()
cur_s = supabase.cursor()
cur_s.execute("set search_path = ddv, public")

# Que tablas hay y en que orden cargarlas
cur_o.execute(ORDEN_SQL)
orden = [t for t, _ in cur_o.fetchall()]

# Contamos de verdad, no por estadisticas: pg_stat_user_tables daba 0 filas en
# users porque esa tabla nunca se analizo, y saltarsela hacia fallar por clave
# foranea a las 43 tablas que la referencian.
cur_o.execute("""
    select table_name,
           (xpath('/row/c/text()',
                  query_to_xml(format('select count(*) as c from public.%I', table_name),
                               false, true, '')))[1]::text::bigint as filas
    from information_schema.tables
    where table_schema = 'public' and table_type = 'BASE TABLE'
""")
con_datos = {t: n for t, n in cur_o.fetchall() if n > 0}

tablas = [t for t in orden if t in con_datos and t not in EXCLUIDAS]
tablas += [t for t in con_datos if t not in tablas and t not in EXCLUIDAS]


def columnas(cursor, esquema: str, tabla: str) -> list:
    """Columnas de una tabla, en el orden en que las declara el catalogo."""
    cursor.execute(
        "select column_name from information_schema.columns "
        "where table_schema = %s and table_name = %s order by ordinal_position",
        (esquema, tabla),
    )
    return [c for (c,) in cursor.fetchall()]


# Vaciamos el destino antes de cargar, para que la migracion sea repetible
cur_s.execute("""
    select string_agg(format('ddv.%I', table_name), ', ')
    from information_schema.tables
    where table_schema = 'ddv' and table_name not in ('well_data','well_data_time')
""")
cur_s.execute(f"truncate {cur_s.fetchone()[0]} cascade")
supabase.commit()

print(f"{len(tablas)} tablas por migrar\n")
print(f"{'origen':<26} {'destino':<22} {'filas':>7}  estado")
print("-" * 74)

total = 0
fallos = []
avisos = []

for tabla in tablas:
    dst = destino(tabla)

    cols_o = columnas(cur_o, "public", tabla)
    cols_d = columnas(cur_s, "ddv", dst)

    # Solo se copia lo que existe en las dos, emparejado por nombre
    comunes = [c for c in cols_o if c in cols_d]
    solo_origen = [c for c in cols_o if c not in cols_d]
    solo_destino = [c for c in cols_d if c not in cols_o]

    if solo_origen:
        avisos.append(f"{tabla}: columnas que el destino no tiene: {', '.join(solo_origen)}")

    lista_o = ", ".join(f'"{c}"' for c in comunes)
    lista_d = ", ".join(f'"{c}"' for c in comunes)

    buffer = io.StringIO()
    cur_o.copy_expert(
        f"copy (select {lista_o} from public.{tabla}) to stdout with (format csv)",
        buffer,
    )
    buffer.seek(0)

    # Punto de guardado por tabla: si esta falla, no arrastra a las demas
    cur_s.execute("savepoint tabla_actual")

    try:
        cur_s.copy_expert(
            f"copy ddv.{dst} ({lista_d}) from stdin with (format csv)", buffer
        )
        cur_s.execute(f"select count(*) from ddv.{dst}")
        n = cur_s.fetchone()[0]
        cur_s.execute("release savepoint tabla_actual")

        total += n
        cuadra = n == con_datos[tabla]
        if not cuadra:
            fallos.append(tabla)

        nota = "" if not solo_destino else f" (+{len(solo_destino)} col. nuevas)"
        estado = f"ok{nota}" if cuadra else f"DESCUADRE, origen {con_datos[tabla]}"
        print(f"{tabla:<26} {dst:<22} {n:>7,}  {estado}")

    except Exception as exc:
        cur_s.execute("rollback to savepoint tabla_actual")
        fallos.append(tabla)
        print(f"{tabla:<26} {dst:<22} {'—':>7}  FALLA {str(exc).splitlines()[0][:44]}")

supabase.commit()

# Reajustamos las secuencias, que COPY no toca
cur_s.execute("""
    select c.relname, a.attname, s.relname
    from pg_class s
    join pg_depend d on d.objid = s.oid and d.deptype = 'a'
    join pg_class c on c.oid = d.refobjid
    join pg_attribute a on a.attrelid = c.oid and a.attnum = d.refobjsubid
    join pg_namespace n on n.oid = s.relnamespace
    where s.relkind = 'S' and n.nspname = 'ddv'
""")
secuencias = cur_s.fetchall()

for tabla, columna, secuencia in secuencias:
    cur_s.execute(
        f"select setval('ddv.{secuencia}', "
        f"coalesce((select max({columna}) from ddv.{tabla}), 0) + 1, false)"
    )

supabase.commit()

print(f"\n{total:,} filas migradas · {len(secuencias)} secuencias reajustadas")

for a in avisos:
    print(f"  aviso: {a}")

if fallos:
    print(f"\n{len(fallos)} tablas con problemas:")
    for f in fallos:
        print("   -", f)
    sys.exit(1)

print("todas las tablas cuadran con el origen")
