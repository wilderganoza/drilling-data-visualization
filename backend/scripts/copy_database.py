"""
Copy full PostgreSQL dataset from source DB to target DB.

Usage:
  SOURCE_DATABASE_URL=postgresql://... TARGET_DATABASE_URL=postgresql://... \
  python scripts/copy_database.py
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, execute_values


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_table_list(conn) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        discovered = [row[0] for row in cur.fetchall()]

    priority = {
        "alembic_version": 0,
        "users": 1,
        "wells": 2,
        "well_data": 3,
        "processed_datasets": 4,
        "processed_records": 5,
        "annotations": 6,
    }
    return sorted(discovered, key=lambda t: (priority.get(t, 999), t))


def get_existing_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            """
        )
        return {row[0] for row in cur.fetchall()}


def get_table_definition(conn, table: str) -> tuple[list[tuple[str, str, bool, str | None]], list[str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              a.attname,
              pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
              a.attnotnull,
              pg_get_expr(d.adbin, d.adrelid) AS column_default
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_catalog.pg_attrdef d
              ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            WHERE n.nspname = 'public'
              AND c.relname = %s
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            (table,),
        )
        columns = [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT a.attname
            FROM pg_catalog.pg_index i
            JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_catalog.pg_attribute a
              ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
            WHERE n.nspname = 'public'
              AND c.relname = %s
              AND i.indisprimary
            ORDER BY array_position(i.indkey, a.attnum)
            """,
            (table,),
        )
        pk_columns = [r[0] for r in cur.fetchall()]

    return columns, pk_columns


def create_table_in_target(src_conn, dst_conn, table: str) -> None:
    columns, pk_columns = get_table_definition(src_conn, table)
    if not columns:
        return

    column_defs = []
    for name, data_type, not_null, default_value in columns:
        parts = [f'"{name}"', data_type]
        if default_value is not None and "nextval(" not in default_value:
            parts.append(f"DEFAULT {default_value}")
        if not_null:
            parts.append("NOT NULL")
        column_defs.append(" ".join(parts))

    if pk_columns:
        pk_sql = ", ".join(f'"{c}"' for c in pk_columns)
        column_defs.append(f"PRIMARY KEY ({pk_sql})")

    create_sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(column_defs)})'
    with dst_conn.cursor() as cur:
        cur.execute(create_sql)
    dst_conn.commit()


def get_columns(conn, table: str) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def reset_sequences(conn, table: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_default LIKE 'nextval%%'
            """,
            (table,),
        )
        serial_columns = [row[0] for row in cur.fetchall()]

    if not serial_columns:
        conn.commit()
        return

    with conn.cursor() as cur:
        for column in serial_columns:
            cur.execute(
                sql.SQL(
                    """
                    SELECT setval(
                      pg_get_serial_sequence(%s, %s),
                      COALESCE((SELECT MAX({col}) FROM {tbl}), 1),
                      true
                    )
                    """
                ).format(
                    col=sql.Identifier(column),
                    tbl=sql.Identifier(table),
                ),
                (f"public.{table}", column),
            )
    conn.commit()


def copy_table(src_conn, dst_conn, table: str, batch_size: int = 10000) -> Tuple[int, int]:
    columns = get_columns(src_conn, table)
    if not columns:
        return 0, 0

    incremental = "id" in columns
    start_after = 0

    if incremental:
        with dst_conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT COALESCE(MAX(id), 0) FROM {}").format(sql.Identifier(table))
            )
            start_after = int(cur.fetchone()[0] or 0)
    else:
        with dst_conn.cursor() as cur:
            cur.execute(
                sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                    sql.Identifier(table)
                )
            )
        dst_conn.commit()

    if incremental:
        select_sql = sql.SQL("SELECT {} FROM {} WHERE id > %s ORDER BY id").format(
            sql.SQL(", ").join(sql.Identifier(c) for c in columns),
            sql.Identifier(table),
        )
    else:
        select_sql = sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(", ").join(sql.Identifier(c) for c in columns),
            sql.Identifier(table),
        )
    insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )

    copied = 0
    batches = 0
    with src_conn.cursor(name=f"src_{table}") as src_cur:
        src_cur.itersize = batch_size
        if incremental:
            src_cur.execute(select_sql, (start_after,))
        else:
            src_cur.execute(select_sql)

        while True:
            rows = src_cur.fetchmany(batch_size)
            if not rows:
                break

            normalized_rows = []
            for row in rows:
                normalized_row = []
                for value in row:
                    if isinstance(value, (dict, list)):
                        normalized_row.append(Json(value))
                    else:
                        normalized_row.append(value)
                normalized_rows.append(tuple(normalized_row))

            with dst_conn.cursor() as dst_cur:
                execute_values(
                    dst_cur,
                    insert_sql.as_string(dst_conn),
                    normalized_rows,
                    page_size=batch_size,
                )
            dst_conn.commit()

            copied += len(rows)
            batches += 1
            print(f"[{table}] copied rows: {copied}", flush=True)

    reset_sequences(dst_conn, table)
    return copied, batches


def main() -> int:
    source_url = require_env("SOURCE_DATABASE_URL")
    target_url = require_env("TARGET_DATABASE_URL")

    print("Connecting to source DB...")
    src_conn = psycopg2.connect(source_url)
    src_conn.autocommit = False

    print("Connecting to target DB...")
    dst_conn = psycopg2.connect(target_url)
    dst_conn.autocommit = False

    try:
        source_tables = get_table_list(src_conn)
        target_tables = get_existing_tables(dst_conn)
        missing_in_target = [t for t in source_tables if t not in target_tables]
        for table in missing_in_target:
            print(f"Creating missing table in target: {table}")
            create_table_in_target(src_conn, dst_conn, table)

        target_tables = get_existing_tables(dst_conn)
        tables = [t for t in source_tables if t in target_tables]
        still_missing = [t for t in source_tables if t not in target_tables]

        print(f"Tables to copy: {tables}")
        if still_missing:
            print(
                "WARNING: target DB is missing tables (run migrations first): "
                f"{still_missing}"
            )

        for table in tables:
            print(f"Copying table: {table}")
            rows, batches = copy_table(src_conn, dst_conn, table)
            print(f"Done {table}: {rows} rows in {batches} batches")

        print("Database copy completed successfully.")
        return 0
    finally:
        src_conn.close()
        dst_conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
