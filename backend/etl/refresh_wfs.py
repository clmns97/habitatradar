#!/usr/bin/env python3
"""Weekend ETL: refresh BfN protected-area tables from the WFS service.

For each of the nine BfN "Schutzgebiet" layers this script:

  1. Loads the layer into a ``<table>_etl_staging`` table via ``ogr2ogr``
     (reprojected to EPSG:3035, geometry column ``geom``, FID column ``id``),
  2. Verifies the staging table actually received rows,
  3. Atomically swaps it into the live table inside a single transaction.

The swap means the live API (``backend/app/services.py``) keeps serving the
previous data right up until ``COMMIT`` — there is no window where a table is
missing or empty. If a layer fails to load, its live table is left untouched.

Connection comes from ``IMPORT_DATABASE_URL`` (the write/ETL role). For Neon we
use a *direct* (non-pooled) endpoint so DDL and the bulk load run on a stable
session; the ``-pooler`` host suffix is stripped automatically.
"""

from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import unquote, urlparse

import psycopg2

WFS_URL = os.getenv("WFS_URL") or "https://geodienste.bfn.de/ogc/wfs/schutzgebiet"
USER_AGENT = os.getenv("ETL_USER_AGENT") or "HabitatRadar-ETL/1.0"
STAGING_SUFFIX = "_etl_staging"
PER_LAYER_TIMEOUT_S = int(os.getenv("ETL_LAYER_TIMEOUT", "1800"))

# (WFS typeName, target table). Table names match backend/app/services.py.
LAYERS: list[tuple[str, str]] = [
    ("bfn_sch_Schutzgebiet:Nationalparke", "nationalparke"),
    ("bfn_sch_Schutzgebiet:Naturparke", "naturparke"),
    ("bfn_sch_Schutzgebiet:Naturschutzgebiete", "naturschutzgebiete"),
    ("bfn_sch_Schutzgebiet:Landschaftsschutzgebiete", "landschaftsschutzgebiete"),
    ("bfn_sch_Schutzgebiet:Biosphaerenreservate", "biosphaerenreservate"),
    ("bfn_sch_Schutzgebiet:Vogelschutzgebiete", "vogelschutzgebiete"),
    ("bfn_sch_Schutzgebiet:Fauna_Flora_Habitat_Gebiete", "fauna_flora_habitat_gebiete"),
    ("bfn_sch_Schutzgebiet:Nationale_Naturmonumente", "nationale_naturmonumente"),
    ("bfn_sch_Schutzgebiet:Biosphaerenreservate_Zonierung", "biosphaerenreservate_zonierung"),
]

# Layers whose name lives under a different attribute. ogr2ogr lowercases all
# WFS attribute names, so these are the lowercased source columns to rename to
# the ``name`` column the backend queries.
NAME_SOURCE: dict[str, str] = {
    "fauna_flora_habitat_gebiete": "gebietsname",
}


def parse_connection() -> tuple[str, str]:
    """Return (psycopg2 dsn, ogr2ogr "PG:" string) from IMPORT_DATABASE_URL."""
    raw = os.getenv("IMPORT_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not raw:
        sys.exit("✗ IMPORT_DATABASE_URL (or DATABASE_URL) is not set")

    # SQLAlchemy-style "+asyncpg" / "+psycopg2" drivers are not valid for libpq.
    scheme_sep = raw.find("://")
    if scheme_sep != -1 and "+" in raw[:scheme_sep]:
        raw = raw[: raw.find("+")] + raw[scheme_sep:]

    parsed = urlparse(raw)
    host = parsed.hostname or ""
    # Neon: use the direct endpoint for a stable session (no PgBouncer).
    host = host.replace("-pooler.", ".")
    port = parsed.port or 5432
    dbname = parsed.path.lstrip("/")
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")

    sslmode = "require" if host.endswith("neon.tech") else "prefer"

    parts = {
        "host": host,
        "port": str(port),
        "dbname": dbname,
        "user": user,
        "password": password,
        "sslmode": sslmode,
    }
    dsn = " ".join(f"{k}={v}" for k, v in parts.items() if v)
    return dsn, "PG:" + dsn


def load_layer_to_staging(typename: str, table: str, pg_conn: str) -> None:
    """Run ogr2ogr to (re)build ``<table>_etl_staging`` from the WFS layer."""
    staging = table + STAGING_SUFFIX
    cmd = [
        "ogr2ogr",
        "-f", "PostgreSQL", pg_conn,
        f"WFS:{WFS_URL}",
        typename,
        "-nln", staging,
        "-overwrite",
        "-t_srs", "EPSG:3035",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=id",
        "-lco", "SPATIAL_INDEX=NONE",  # index is created with a stable name at swap
        "-nlt", "PROMOTE_TO_MULTI",
        "-nlt", "CONVERT_TO_LINEAR",
        "-nlt", "MultiPolygon",
        "-skipfailures",
        "-forceNullable",
        "-makevalid",
        "--config", "OGR_WFS_PAGING_ALLOWED", "OFF",
        "--config", "OGR_WFS_LOAD_MULTIPLE_LAYER_DEFN", "OFF",
        "--config", "GDAL_HTTP_USERAGENT", USER_AGENT,
        "--config", "CPL_DEBUG", "OFF",
    ]
    print(f"📡 Loading {typename} → {staging} ...", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=PER_LAYER_TIMEOUT_S)
    if result.returncode != 0:
        raise RuntimeError(
            f"ogr2ogr failed (exit {result.returncode}).\n"
            f"STDERR: {result.stderr.strip()}\nSTDOUT: {result.stdout.strip()}"
        )


def swap_staging_into_live(conn, table: str) -> int:
    """Atomically replace the live table with its staging table. Returns rows."""
    staging = table + STAGING_SUFFIX
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{staging}"')
        rows = cur.fetchone()[0]
        if rows == 0:
            raise RuntimeError(f"staging table {staging} is empty — keeping live data")

        # Ensure a "name" column exists for the backend query.
        src = NAME_SOURCE.get(table)
        if src:
            cur.execute(
                """
                SELECT
                  bool_or(column_name = 'name')  AS has_name,
                  bool_or(column_name = %s)       AS has_src
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                """,
                (src, staging),
            )
            has_name, has_src = cur.fetchone()
            if not has_name and has_src:
                cur.execute(f'ALTER TABLE "{staging}" RENAME COLUMN "{src}" TO name')

        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = 'name'
            """,
            (staging,),
        )
        if cur.fetchone() is None:
            raise RuntimeError(f"{staging} has no 'name' column — backend would break")

        # Atomic swap: old table (and its index) dropped, staging promoted, fresh
        # spatial index created with a deterministic name on the live table.
        cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        cur.execute(f'ALTER TABLE "{staging}" RENAME TO "{table}"')
        cur.execute(f'CREATE INDEX "{table}_geom_idx" ON "{table}" USING GIST (geom)')
        cur.execute(f'ANALYZE "{table}"')
    conn.commit()
    return rows


def main() -> int:
    dsn, pg_conn = parse_connection()
    print(f"🌍 WFS: {WFS_URL}", flush=True)

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        conn.commit()

        succeeded, failed = [], []
        for typename, table in LAYERS:
            staging = table + STAGING_SUFFIX
            try:
                load_layer_to_staging(typename, table, pg_conn)
                rows = swap_staging_into_live(conn, table)
                print(f"✅ {table}: {rows} features", flush=True)
                succeeded.append(table)
            except Exception as exc:  # noqa: BLE001 — isolate per-layer failures
                conn.rollback()
                print(f"❌ {table}: {exc}", flush=True)
                failed.append(table)
            finally:
                # Drop any leftover staging table from this run.
                with conn.cursor() as cur:
                    cur.execute(f'DROP TABLE IF EXISTS "{staging}" CASCADE')
                conn.commit()
    finally:
        conn.close()

    print(f"\n🎯 Done: {len(succeeded)} refreshed, {len(failed)} failed", flush=True)
    if failed:
        print(f"   Failed: {', '.join(failed)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
