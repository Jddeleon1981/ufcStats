"""Load the parquet raw layer into ``raw.*`` tables.

This is where we start loading data. We know partitioned parquet files are written
under data/raw/<entity>/dt=YYYY-MM-DD/ si this module appends those files into
warehouse tables that dbt declares as sources. We hold back from applying any
transformations so each table here is of a "bronze" type plus a "dt" column
taken from the path


Remember that idempotency is per file, not per partition. This is because patition
level can fail when it only loads a subset of the available files. Upon revisiting
we will see that the current date has been handled and move on labeling it a success.

Wheras, with idempotency tracked at the file level, we can safely retry individual files
without affecting the rest of the partition. If the first run only loads a subset of the
actual files it's okay because we will revisit the unloaded files on the next run.

This means means a re run will skip what alreary landed. A crash mid file leaves
no rows or log entrt so the next run will retry instead of double loading. Finally,
a partition that gains files later on, like through a resumed backfill, picks up
only the new ones.

Databricks has the "COPY INTO" command for loading data into tables from files and
has some of this functionality natively built in. We'll be able to take advantage of
this later when loading into prod.

Databricks' ``COPY INTO`` does exactly this natively with its own file
tracking; the prod load in a later phase is that statement over a Volume.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

ENTITIES = ("events", "bouts", "fighters")
RAW_SCHEMA = "raw"
LOG_TABLE = f"{RAW_SCHEMA}._load_log"


@dataclass(frozen=True)
class LoadResult:
    """What one call to :func:`load_entity` did."""

    entity: str
    files_loaded: int
    files_skipped: int
    rows_loaded: int


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """
    Ensure the raw schema exists. Creates the load log table if it doesn't exists so we
    have a place to track loaded files.
    """
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LOG_TABLE} (
            entity     VARCHAR NOT NULL,
            file_path  VARCHAR NOT NULL PRIMARY KEY,
            dt         DATE    NOT NULL,
            row_count  BIGINT  NOT NULL,
            loaded_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )


def _ensure_table(con: duckdb.DuckDBPyConnection, entity: str, sample: Path) -> None:
    """Create ``raw.<entity>`` with the first file's columns plus ``dt``.

    Types come straight from the parquet, which is how the raw-is-text contract
    reaches the warehouse: strings stay strings, and only ``_ingested_at`` and
    ``dt`` are typed.
    """
    # hive_partitioning=false: DuckDB would otherwise read dt= out of the path
    # itself, with whatever type it guesses. We add dt explicitly, as a DATE we
    # parsed, so the column is ours to define.
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.{entity} AS
        SELECT *, CAST(NULL AS DATE) AS dt
        FROM read_parquet(?, hive_partitioning = false)
        WHERE false
        """,
        [sample.as_posix()],
    )


def partition_files(entity: str, root: Path) -> list[tuple[date, Path]]:
    """Every parquet file under the entity as ``(dt, path)``, oldest partition first."""
    entity_dir = Path(root) / entity
    if not entity_dir.exists():
        return []
    files = []
    for part_dir in sorted(entity_dir.glob("dt=*")):
        dt = date.fromisoformat(part_dir.name.removeprefix("dt="))
        files.extend((dt, path) for path in sorted(part_dir.glob("*.parquet")))
    return files


def loaded_files(con: duckdb.DuckDBPyConnection, entity: str) -> set[str]:
    """File paths already recorded in the load log for this entity."""
    rows = con.execute(f"SELECT file_path FROM {LOG_TABLE} WHERE entity = ?", [entity]).fetchall()
    return {row[0] for row in rows}


def load_entity(con: duckdb.DuckDBPyConnection, entity: str, root: Path) -> LoadResult:
    """Append every not-yet-loaded file for ``entity`` into ``raw.<entity>``."""
    _ensure_schema(con)
    files = partition_files(entity, root)
    if not files:
        return LoadResult(entity, 0, 0, 0)

    _ensure_table(con, entity, files[0][1])
    already = loaded_files(con, entity)

    files_loaded = files_skipped = rows_loaded = 0
    for dt, path in files:
        key = path.as_posix()
        if key in already:
            files_skipped += 1
            continue

        # rows and the log entry land together or not at all
        con.begin()
        try:
            # BY NAME matches columns by name, so a file with a column the table
            # does not have fails loudly instead of landing in the wrong column
            (row_count,) = con.execute(
                f"""
                INSERT INTO {RAW_SCHEMA}.{entity} BY NAME
                SELECT *, ? AS dt FROM read_parquet(?, hive_partitioning = false)
                """,
                [dt, key],
            ).fetchone()
            con.execute(
                f"INSERT INTO {LOG_TABLE} (entity, file_path, dt, row_count) VALUES (?, ?, ?, ?)",
                [entity, key, dt, row_count],
            )
            con.commit()
        except Exception:
            con.rollback()
            raise

        files_loaded += 1
        rows_loaded += row_count

    return LoadResult(entity, files_loaded, files_skipped, rows_loaded)


def load_all(
    con: duckdb.DuckDBPyConnection,
    root: Path,
    entities: tuple[str, ...] = ENTITIES,
) -> list[LoadResult]:
    """Load every entity. Order matches ``ENTITIES``; each is independent."""
    return [load_entity(con, entity, root) for entity in entities]


if __name__ == "__main__":
    # `uv run python -m ufcPipeline.load` loads data/raw into the dev DuckDB file,
    # the same one dbt's dev target points at.
    repo_root = Path(__file__).resolve().parents[1]
    database = repo_root / "data" / "ufc_dev.duckdb"
    raw_root = repo_root / "data" / "raw"

    with duckdb.connect(str(database)) as connection:
        for result in load_all(connection, raw_root):
            print(f"{result.entity:>9}: +{result.rows_loaded:>6} rows from {result.files_loaded} files ({result.files_skipped} already loaded)")
