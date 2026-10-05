"""Tests for the raw-layer load step.

Each test writes tiny parquet files into a temp directory and loads them into an
in-memory DuckDB, so the idempotency guarantees in :mod:`ufcPipeline.load` are
pinned by behaviour rather than by comment.
"""

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from ufcPipeline import load


def _write(root: Path, entity: str, dt: str, part: str, rows: list[dict]) -> Path:
    directory = root / entity / f"dt={dt}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{entity}-{part}.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _count(con, table: str) -> int:
    return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


@pytest.fixture
def con():
    return duckdb.connect(":memory:")


def test_loads_every_file_across_partitions(tmp_path, con):
    _write(tmp_path, "bouts", "2026-09-08", "00000", [{"bout_url": "a", "x": "1"}, {"bout_url": "b", "x": "2"}])
    _write(tmp_path, "bouts", "2026-09-09", "00000", [{"bout_url": "c", "x": "3"}])

    result = load.load_entity(con, "bouts", tmp_path)

    assert result == load.LoadResult("bouts", files_loaded=2, files_skipped=0, rows_loaded=3)
    assert _count(con, "raw.bouts") == 3


def test_reloading_is_a_no_op(tmp_path, con):
    _write(tmp_path, "bouts", "2026-09-08", "00000", [{"bout_url": "a"}, {"bout_url": "b"}])
    load.load_entity(con, "bouts", tmp_path)

    result = load.load_entity(con, "bouts", tmp_path)

    assert result == load.LoadResult("bouts", files_loaded=0, files_skipped=1, rows_loaded=0)
    assert _count(con, "raw.bouts") == 2


def test_new_file_in_an_already_loaded_partition_is_picked_up(tmp_path, con):
    # the resumed-backfill case: the partition existed, then gained a part file
    _write(tmp_path, "bouts", "2026-09-08", "00000", [{"bout_url": "a"}])
    load.load_entity(con, "bouts", tmp_path)
    _write(tmp_path, "bouts", "2026-09-08", "00025", [{"bout_url": "b"}, {"bout_url": "c"}])

    result = load.load_entity(con, "bouts", tmp_path)

    assert result == load.LoadResult("bouts", files_loaded=1, files_skipped=1, rows_loaded=2)
    assert _count(con, "raw.bouts") == 3


def test_dt_column_comes_from_the_partition_path(tmp_path, con):
    _write(tmp_path, "events", "2026-09-08", "00000", [{"event_url": "e1"}])
    _write(tmp_path, "events", "2026-09-10", "00000", [{"event_url": "e2"}])

    load.load_entity(con, "events", tmp_path)

    rows = con.execute("SELECT event_url, dt FROM raw.events ORDER BY dt").fetchall()
    assert rows == [("e1", date(2026, 9, 8)), ("e2", date(2026, 9, 10))]


def test_log_records_each_file_with_its_row_count(tmp_path, con):
    first = _write(tmp_path, "fighters", "2026-09-08", "00000", [{"fighter_url": "f1"}, {"fighter_url": "f2"}])
    second = _write(tmp_path, "fighters", "2026-09-08", "00250", [{"fighter_url": "f3"}])

    load.load_entity(con, "fighters", tmp_path)

    log = con.execute("SELECT entity, file_path, dt, row_count FROM raw._load_log ORDER BY file_path").fetchall()
    assert log == [
        ("fighters", first.as_posix(), date(2026, 9, 8), 2),
        ("fighters", second.as_posix(), date(2026, 9, 8), 1),
    ]


def test_values_stay_as_strings(tmp_path, con):
    # the raw-is-text contract must survive the load: no inference to INTEGER
    _write(tmp_path, "bouts", "2026-09-08", "00000", [{"fighter_a_sig_strikes": "14 of 31", "fighter_a_sig_strike_acc": "45%"}])

    load.load_entity(con, "bouts", tmp_path)

    types = dict(con.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'raw' AND table_name = 'bouts'").fetchall())
    assert types["fighter_a_sig_strikes"] == "VARCHAR"
    assert types["fighter_a_sig_strike_acc"] == "VARCHAR"
    assert types["dt"] == "DATE"


def test_new_column_is_added_and_older_rows_read_null(tmp_path, con):
    _write(tmp_path, "bouts", "2026-09-08", "00000", [{"bout_url": "a", "method": "KO/TKO"}])
    load.load_entity(con, "bouts", tmp_path)
    # a later file with a column the table has never seen
    _write(tmp_path, "bouts", "2026-09-09", "00000", [{"bout_url": "b", "method": "Submission", "referee": "Herb Dean"}])
    load.load_entity(con, "bouts", tmp_path)

    # assert that the new row and column were added. Also check that row one has a null value for the new column
    assert _count(con, "raw.bouts") == 2
    assert _count(con, "raw._load_log") == 2
    assert con.execute("SELECT referee FROM raw.bouts WHERE bout_url = 'a'").fetchone()[0] is None
    assert con.execute("SELECT referee FROM raw.bouts WHERE bout_url = 'b'").fetchone()[0] == "Herb Dean"


def test_missing_entity_directory_loads_nothing(tmp_path, con):
    assert load.load_entity(con, "fighters", tmp_path) == load.LoadResult("fighters", 0, 0, 0)


def test_load_all_covers_every_entity(tmp_path, con):
    _write(tmp_path, "events", "2026-09-08", "00000", [{"event_url": "e"}])
    _write(tmp_path, "bouts", "2026-09-08", "00000", [{"bout_url": "b"}])
    _write(tmp_path, "fighters", "2026-09-08", "00000", [{"fighter_url": "f"}])

    results = load.load_all(con, tmp_path)

    assert [r.entity for r in results] == ["events", "bouts", "fighters"]
    assert all(r.rows_loaded == 1 for r in results)
