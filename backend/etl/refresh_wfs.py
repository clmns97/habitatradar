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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, urlparse

import psycopg2

WFS_URL = os.getenv("WFS_URL") or "https://geodienste.bfn.de/ogc/wfs/schutzgebiet"
USER_AGENT = os.getenv("ETL_USER_AGENT") or "HabitatRadar-ETL/1.0"
STAGING_SUFFIX = "_etl_staging"
PER_LAYER_TIMEOUT_S = int(os.getenv("ETL_LAYER_TIMEOUT", "1800"))
# How many layers to fetch+load concurrently (independent staging tables).
MAX_PARALLEL = int(os.getenv("ETL_PARALLEL", "3"))
WFS_PAGE_SIZE = os.getenv("ETL_WFS_PAGE_SIZE", "5000")

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
        # NOTE: do NOT force "FID=id" — several BfN layers carry a *string* "id"
        # attribute, which collides with an integer FID column ("Wrong field type
        # for ID"). We let GDAL create its own integer "ogc_fid" and guarantee an
        # "id" column at swap time instead (see swap_staging_into_live).
        "-lco", "SPATIAL_INDEX=NONE",  # index is created with a stable name at swap
        "-nlt", "PROMOTE_TO_MULTI",
        "-nlt", "CONVERT_TO_LINEAR",
        "-nlt", "MultiPolygon",
        "-forceNullable",
        "-makevalid",
        # NOTE: -skipfailures is intentionally NOT set — recent GDAL forbids
        # combining it with -gt (skipfailures forces per-feature commits). We
        # rely on -makevalid to repair geometries and keep the fast bulk load.
        "-gt", "unlimited",  # one transaction per layer — fewer remote round-trips
        "--config", "PG_USE_COPY", "YES",  # COPY-based bulk load instead of INSERT
        "--config", "OGR_WFS_PAGING_ALLOWED", "ON",
        "--config", "OGR_WFS_PAGE_SIZE", WFS_PAGE_SIZE,  # stream fetch+parse
        "--config", "OGR_WFS_LOAD_MULTIPLE_LAYER_DEFN", "OFF",
        "--config", "GDAL_HTTP_USERAGENT", USER_AGENT,
        "--config", "CPL_DEBUG", "OFF",
    ]
    print(f"📡 Loading {typename} → {staging} ...", flush=True)
    started = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=PER_LAYER_TIMEOUT_S)
    if result.returncode != 0:
        raise RuntimeError(
            f"ogr2ogr failed (exit {result.returncode}).\n"
            f"STDERR: {result.stderr.strip()}\nSTDOUT: {result.stdout.strip()}"
        )
    print(f"   …{staging} fetched in {time.perf_counter() - started:.0f}s", flush=True)


def swap_staging_into_live(conn, table: str) -> int:
    """Atomically replace the live table with its staging table. Returns rows."""
    staging = table + STAGING_SUFFIX
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{staging}"')
        rows = cur.fetchone()[0]
        if rows == 0:
            raise RuntimeError(f"staging table {staging} is empty — keeping live data")

        # Ensure an "id" column exists for the backend query. When the layer has
        # no source "id" attribute, promote GDAL's generated "ogc_fid".
        cur.execute(
            """
            SELECT
              bool_or(column_name = 'id')        AS has_id,
              bool_or(column_name = 'ogc_fid')   AS has_ogc_fid
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (staging,),
        )
        has_id, has_ogc_fid = cur.fetchone()
        if not has_id:
            if not has_ogc_fid:
                raise RuntimeError(f"{staging} has neither 'id' nor 'ogc_fid'")
            cur.execute(f'ALTER TABLE "{staging}" RENAME COLUMN ogc_fid TO id')

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


def drop_staging(conn, table: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{table + STAGING_SUFFIX}" CASCADE')
    conn.commit()


def main() -> int:
    dsn, pg_conn = parse_connection()
    print(f"🌍 WFS: {WFS_URL} (parallel={MAX_PARALLEL})", flush=True)

    with psycopg2.connect(dsn) as setup:
        with setup.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        setup.commit()

    # Phase 1: fetch + load every layer to its staging table, in parallel. The
    # layers are independent and the work is network/insert bound, so concurrency
    # is the big win. Each ogr2ogr opens its own connection.
    loaded, failed = [], []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {
            pool.submit(load_layer_to_staging, typename, table, pg_conn): table
            for typename, table in LAYERS
        }
        for future in as_completed(futures):
            table = futures[future]
            try:
                future.result()
                loaded.append(table)
            except Exception as exc:  # noqa: BLE001 — isolate per-layer failures
                print(f"❌ {table} (load): {exc}", flush=True)
                failed.append(table)
    print(f"📦 Staging loads done in {time.perf_counter() - started:.0f}s", flush=True)

    # Phase 2: swap each successfully-staged layer into its live table. Serial and
    # fast — just DDL — so the API sees each table replaced atomically.
    swapped = []
    with psycopg2.connect(dsn) as conn:
        for table in loaded:
            try:
                rows = swap_staging_into_live(conn, table)
                print(f"✅ {table}: {rows} features", flush=True)
                swapped.append(table)
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print(f"❌ {table} (swap): {exc}", flush=True)
                failed.append(table)
            finally:
                drop_staging(conn, table)
        # Clean up staging tables left behind by failed loads.
        for table in failed:
            try:
                drop_staging(conn, table)
            except Exception:  # noqa: BLE001
                conn.rollback()

    print(f"\n🎯 Done: {len(swapped)} refreshed, {len(failed)} failed", flush=True)
    if failed:
        print(f"   Failed: {', '.join(failed)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
