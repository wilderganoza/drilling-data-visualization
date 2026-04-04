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
from psycopg2.extras import execute_values


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

    with dst_conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(sql.Identifier(table)))
    dst_conn.commit()

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
        src_cur.execute(select_sql)

        while True:
            rows = src_cur.fetchmany(batch_size)
            if not rows:
                break

            with dst_conn.cursor() as dst_cur:
                execute_values(dst_cur, insert_sql.as_string(dst_conn), rows, page_size=batch_size)
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
        tables = get_table_list(src_conn)
        print(f"Tables to copy: {tables}")

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
