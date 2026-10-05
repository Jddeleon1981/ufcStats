"""DB-free extraction of ufcstats.com into bronze records.

Everything here keys on the site's own detail URLs instead of database surrogate
keys, so a scrape runs against an empty environment and can be replayed without
a warehouse standing. Two rules define this layer:

* **Values are never cleaned. They land exactly as the site renders them. Parsing and
  casting belong in dbt staging, where they are testable and re-runnable.
* **Column names are stable snake_case**, because the site's own labels
  (``"Str. Acc."``, ``"SLpM"``) are display strings, not identifiers. The
  original label-to-value mapping is preserved verbatim in ``_raw_payload`` so
  nothing is lost.

Every record carries ``_ingested_at``, ``_source_url`` and ``_batch_id``.
"""

import json
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from ufcPipeline import session as http
from ufcPipeline.scraping import (
    EVENTS_URL,
    parse_bout,
    parse_event_fights,
    parse_events,
    parse_fighter_name,
    parse_fighter_stats,
)

# the unified rules took effect in Sept 2000. Before then it was like a entirely different sport
MODERN_ERA_START = date(2000, 9, 1)

# the totals table's 20 cells, in page order
BOUT_TOTALS_COLUMNS = [
    "fighter_a_name",
    "fighter_b_name",
    "fighter_a_knockdowns",
    "fighter_b_knockdowns",
    "fighter_a_sig_strikes",
    "fighter_b_sig_strikes",
    "fighter_a_sig_strike_acc",
    "fighter_b_sig_strike_acc",
    "fighter_a_total_strikes",
    "fighter_b_total_strikes",
    "fighter_a_takedowns",
    "fighter_b_takedowns",
    "fighter_a_takedown_acc",
    "fighter_b_takedown_acc",
    "fighter_a_sub_attempts",
    "fighter_b_sub_attempts",
    "fighter_a_reversals",
    "fighter_b_reversals",
    "fighter_a_control_time",
    "fighter_b_control_time",
]

# the site's display labels mapped onto stable column names
FIGHTER_STAT_COLUMNS = {
    "Height": "height",
    "Weight": "weight",
    "Reach": "reach",
    "STANCE": "stance",
    "DOB": "dob",
    "SLpM": "sig_strikes_landed_per_min",
    "Str. Acc.": "sig_strike_accuracy",
    "SApM": "sig_strikes_absorbed_per_min",
    "Str. Def": "sig_strike_defense",
    "TD Avg.": "takedown_average",
    "TD Acc.": "takedown_accuracy",
    "TD Def.": "takedown_defense",
    "Sub. Avg.": "submission_average",
}


def new_batch_id() -> str:
    """An opaque id tying every record from one extraction run together."""
    return uuid.uuid4().hex


def _stamp(record: dict, source_url: str, batch_id: str, payload) -> dict:
    """Attach the raw-layer metadata every bronze record carries."""
    record["_source_url"] = source_url
    record["_batch_id"] = batch_id
    record["_ingested_at"] = datetime.now(UTC)
    record["_raw_payload"] = json.dumps(payload, ensure_ascii=False)
    return record


# Entities
def extract_events(sess, batch_id: str) -> list[dict]:
    """Every completed event listed on the site, unfiltered and uncast."""
    response = http.get(sess, EVENTS_URL)
    return [
        _stamp(
            {
                "event_url": url,
                "event_name": name,
                "event_date": event_date,
                "event_location": location,
            },
            source_url=EVENTS_URL,
            batch_id=batch_id,
            payload=[name, event_date, location, url],
        )
        for name, event_date, location, url in parse_events(response.text)
    ]


def select_events(
    events: Iterable[dict],
    since: date = MODERN_ERA_START,
    until: date | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Modern-era events that have actually happened, newest first.

    The events page lists upcoming cards alongside completed ones, so ``until``
    (today by default) is what keeps a card with no results out of the scrape.
    """
    until = until or datetime.now(UTC).date()
    selected = []
    for event in events:
        event_date = datetime.strptime(event["event_date"], "%B %d, %Y").date()
        if since <= event_date <= until:
            selected.append(event)
    selected.sort(key=lambda e: datetime.strptime(e["event_date"], "%B %d, %Y"), reverse=True)
    return selected[:limit] if limit else selected


def _bout_record(bout: dict, bout_url: str, event_url: str, winner: str, weight_class: str, result: str) -> dict:
    """Flatten one parsed bout into a raw record keyed by the site's own URLs."""
    fighter_urls = bout["fighter_urls"]
    # strict=True: the caller already skips totals shorter than the column list,
    # so a length mismatch here means the page rendered MORE cells than expected.
    # Truncating those silently would drop scraped stats, so fail loudly instead.
    record = dict(zip(BOUT_TOTALS_COLUMNS, bout["totals"], strict=True))
    record.update(
        {
            "bout_url": bout_url,
            "event_url": event_url,
            "fighter_a_url": fighter_urls[0] if fighter_urls else None,
            "fighter_b_url": fighter_urls[1] if len(fighter_urls) > 1 else None,
            "winner_name": winner,
            "result": result,
            "weight_class": weight_class,
            "method": bout["method"],
            "finish_round": bout["finish_round"],
            "finish_time": bout["finish_time"],
        }
    )
    return record


def extract_bouts(sess, events: Iterable[dict], batch_id: str, on_error=None) -> list[dict]:
    """Every bout on the given events, one record per bout.

    Failures are isolated per bout: a card with no totals table, or a page that
    will not parse, is skipped and reported rather than losing the whole run.
    """
    bouts = []
    for event in events:
        event_url = event["event_url"]
        try:
            fights = parse_event_fights(http.get(sess, event_url).text)
        except Exception as error:
            if on_error:
                on_error(event_url, error)
            continue

        for winner, weight_class, bout_url, result in fights:
            try:
                bout = parse_bout(http.get(sess, bout_url).text)
            except Exception as error:
                if on_error:
                    on_error(bout_url, error)
                continue
            if not bout or len(bout["totals"]) < len(BOUT_TOTALS_COLUMNS):
                continue

            record = _bout_record(bout, bout_url, event_url, winner, weight_class, result)
            bouts.append(_stamp(record, bout_url, batch_id, bout))
    return bouts


def fighter_urls_from_bouts(bouts: Iterable[dict]) -> list[str]:
    """The distinct fighters appearing in a set of bouts.

    Deriving the fighter list from the bouts rather than the site's A-Z index
    keeps the extract referentially complete by construction — every fighter a
    bout points at is one we fetched — and skips thousands of pages for fighters
    who never appear.
    """
    urls: dict[str, None] = {}
    for bout in bouts:
        for key in ("fighter_a_url", "fighter_b_url"):
            if bout.get(key):
                urls.setdefault(bout[key], None)
    return list(urls)


def extract_fighters(sess, fighter_urls: Iterable[str], batch_id: str, on_error=None) -> list[dict]:
    """Career-to-date profile for each fighter URL.

    These values are a snapshot of what the site shows *today* — they change
    after every bout. Capturing that drift over successive runs is what the dbt
    snapshot in a later phase is for.
    """
    fighters = []
    for url in fighter_urls:
        try:
            html = http.get(sess, url).text
        except Exception as error:
            if on_error:
                on_error(url, error)
            continue

        name = parse_fighter_name(html)
        name_parts = name.split(" ", 1)
        stats = parse_fighter_stats(html, name_parts[0], name_parts[1] if len(name_parts) > 1 else "", url)
        stats.pop("", None)  # the page has a blank spacer list item

        record = {
            "fighter_url": url,
            "fighter_name": name,
            "first_name": stats.pop("First Name"),
            "last_name": stats.pop("Last Name"),
        }
        stats.pop("URL", None)
        for label, column in FIGHTER_STAT_COLUMNS.items():
            record[column] = stats.get(label)
        fighters.append(_stamp(record, url, batch_id, stats))
    return fighters


# Landing
def partition_dir(entity: str, root: Path, partition_date: date | None = None) -> Path:
    """The ``dt=`` directory one run's records land in.

    Readers that want *this* run scope to this directory; readers that want the
    full history glob the entity directory and de-duplicate on the natural key,
    which is what dbt staging does.
    """
    partition_date = partition_date or datetime.now(UTC).date()
    return Path(root) / entity / f"dt={partition_date.isoformat()}"


def write_parquet(
    records: list[dict],
    entity: str,
    root: Path,
    partition_date: date | None = None,
    part: str | None = None,
) -> Path:
    """Land one entity's records under ``<root>/<entity>/dt=YYYY-MM-DD/``.

    The Hive-style partition directory is what lets DuckDB and Snowflake read
    the whole history back with ``hive_partitioning``, and what makes a re-run
    on a later date additive instead of destructive.

    ``part`` writes a numbered file alongside any others in the same partition
    rather than replacing it, so a long backfill can checkpoint as it goes. The
    readers glob the directory, so many parts read back as one table.
    """
    directory = partition_dir(entity, root, partition_date)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (f"{entity}-{part}.parquet" if part else f"{entity}.parquet")
    pd.DataFrame(records).to_parquet(path, index=False)
    return path


def landed_keys(
    entity: str,
    root: Path,
    column: str,
    partition_date: date | None = None,
) -> set:
    """Values of ``column`` already written to today's partition.

    Lets a resumed backfill skip what it already has instead of starting over,
    which is the difference between a five-hour run being safe to interrupt and
    being all-or-nothing.
    """
    directory = partition_dir(entity, root, partition_date)
    if not directory.exists():
        return set()
    keys: set = set()
    for path in directory.glob("*.parquet"):
        keys.update(pd.read_parquet(path, columns=[column])[column].dropna())
    return keys
