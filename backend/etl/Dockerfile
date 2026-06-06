# ETL image: GDAL/ogr2ogr for the WFS load + psycopg2 for the atomic swap.
# Built with build context = backend/ so it shares the etl/ sources.
FROM ghcr.io/osgeo/gdal:ubuntu-small-latest

# psycopg2 from apt (the distro wheel) — avoids a source build with no compiler.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-psycopg2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY etl/ ./etl/
ENTRYPOINT ["python3", "etl/refresh_wfs.py"]
