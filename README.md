# UFC Stats — Data Engineering Pipeline

An end-to-end batch pipeline that scrapes [ufcstats.com](http://ufcstats.com), lands the data in a
relational store on AWS, keeps it current with a scheduled incremental load, and engineers
leakage-safe features for fight-outcome modeling. A lightweight Flask app sits on top for browsing.

The focus of this project is the **data engineering**: ingestion, modeling, incremental updates,
and feature engineering — not the web layer.

<p>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/AWS-Lambda%20%7C%20RDS%20%7C%20Secrets%20Manager%20%7C%20SES-FF9900?logo=amazonaws&logoColor=white" alt="AWS">
  <img src="https://img.shields.io/badge/MySQL-8-4479A1?logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/pandas-2.2-150458?logo=pandas&logoColor=white" alt="pandas">
  <img src="https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white" alt="Flask">
</p>

---

## Architecture

```mermaid
flowchart LR
    SRC[ufcstats.com]

    subgraph Ingestion
        BULK["tableSetup.py<br/>one-time bulk load"]
        INCR["ufcDBLambda.py<br/>weekly incremental load"]
    end

    EB["EventBridge cron<br/>(weekly, Sun AM)"] --> INCR
    SM[("AWS Secrets Manager")] -. db creds .-> BULK
    SM -. db creds .-> INCR

    SRC -->|"requests + BeautifulSoup<br/>(thread-pooled, rate-limited)"| BULK
    SRC -->|scrape new events| INCR

    BULK --> DB[("AWS RDS · MySQL<br/>fighters · events · fights")]
    INCR --> DB
    INCR -->|run status| SES["AWS SES<br/>email notification"]

    DB --> FE["featureSetup.py<br/>leakage-safe feature engineering"]
    FE --> ML["explore.ipynb<br/>EDA / modeling"]
    DB --> WEB["Flask app<br/>browse fighters & stats"]
```

**Two ingestion paths feed one store:**

- **Bulk load** (`tableSetup.py`) — a one-time backfill that scrapes every fighter and every event
  since the unified-rules era (Sept 2000), then builds and populates all three tables from scratch.
- **Incremental load** (`ufcDBLambda.py`) — an AWS Lambda triggered weekly by EventBridge. It uses a
  **watermark** (the latest event date already stored) to detect and scrape only new events, updates
  fighter records, appends new fights, and emails a run summary via SES.

---

## Data model

```mermaid
erDiagram
    eventHyperlinks   ||--o{ fightStats : hosts
    fighterHyperlinks ||--o{ fightStats : "fighter A"
    fighterHyperlinks ||--o{ fightStats : "fighter B"

    fighterHyperlinks {
        int    fighterID PK
        string firstName
        string lastName
        string hyperlink
        string Stance
        string DOB
        decimal Strikes_Landed_Per_Minute
        decimal Takedown_Average
    }
    eventHyperlinks {
        int    eventID PK
        string eventName
        string eventDate
        string eventLocation
        string eventHyperLink
    }
    fightStats {
        int    fightID PK
        int    fighter_A_ID FK
        int    fighter_B_ID FK
        int    eventID FK
        string winner
        string method
        string weightClass
        string round
        string time
    }
```

| Table | Grain | Description |
|-------|-------|-------------|
| `fighterHyperlinks` | one row per fighter | Bio + career-level stats (reach, stance, strikes/min, takedown avg, …) and the source URL. |
| `eventHyperlinks` | one row per event | Event name, date, location, source URL. |
| `fightStats` | one row per bout | Per-fight box-score for both fighters, the winner, method/round/time, and FKs to the two fighters and the event. |

---

## Feature engineering

`featureEngineering/featureSetup.py` turns the raw box-score into model-ready, **per-bout** features.
The core design constraint is **no target leakage**: every career-to-date feature is computed using
only the fighter's *prior* bouts, never the one being predicted.

- SQL window functions use `ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING`.
- pandas cumulative features use `.cumsum().shift(1)`.

Features generated per fighter, as-of each bout:

| Feature | Meaning |
|---------|---------|
| `winPercentage` | Career win rate going into the fight |
| `numOfFights` | UFC experience (bouts to date) |
| `winStreak` | Active win streak |
| `averageFightTime` | Mean bout length (minutes) |
| `finishRate` | Share of wins by KO/TKO/submission |
| `strikeDifferential` | Cumulative sig. strikes landed ÷ absorbed |
| `takedownDifferential` | Cumulative takedowns landed ÷ absorbed |
| `averageControlTime` | Mean share of fight time in control |
| `Age`, `weightClass`, `stance` | Static / bout-level attributes |

The result is pivoted into one row per fight (`...A` vs `...B` columns) joined to the `winner`
label — ready to drop into a classifier.

---

## Repository layout

```
ufcStats/
├── ufcPipeline/                   # shared package — single source of truth
│   ├── scraping.py                # pure HTML parsers + network-backed scrapers
│   ├── db.py                      # MySQL connection helper
│   └── secretsManager.py          # AWS Secrets Manager credentials
├── SQL/
│   ├── sqlCreate/
│   │   └── tableSetup.py          # one-time bulk load: build + populate all 3 tables
│   └── sqlUpdate/
│       └── ufcDBLambda.py         # weekly AWS Lambda: watermark-based incremental load
├── featureEngineering/
│   ├── featureSetup.py            # leakage-safe feature engineering (SQL + pandas)
│   └── explore.ipynb              # EDA / model prototyping
├── flaskInt/                      # Flask web app (browse fighters & their stats)
│   ├── run.py
│   └── buildWeb/{routes,forms,__init__}.py + templates/
├── tests/                         # pytest suite + HTML fixtures for the parsers
├── pyproject.toml                 # dependency intent (core + dev/dbt/prod/legacy groups)
├── uv.lock                        # fully resolved graph, committed
└── pylintrc
```

---

## Tech stack

**Ingestion:** Python, `requests`, BeautifulSoup, `concurrent.futures` (thread-pooled scraping)
**Storage:** MySQL on AWS RDS
**Orchestration:** AWS Lambda + EventBridge (weekly cron)
**Secrets / notifications:** AWS Secrets Manager, AWS SES
**Transformation:** pandas, `pandasql`
**Serving:** Flask, Flask-WTF

---

## Running it locally

> Requires [uv](https://docs.astral.sh/uv/). It installs the pinned Python (3.12) itself, so
> nothing else is needed up front. The legacy AWS/MySQL path below additionally needs AWS
> credentials and a MySQL instance.

1. **Install dependencies**
   ```bash
   uv sync                    # core + dev + dbt, into .venv, from uv.lock
   ```
   `uv sync` creates the virtualenv, installs the exact locked versions, and puts
   `ufcPipeline` in it as an editable install — no separate `pip install -e .` step.
   Prefix commands with `uv run` (e.g. `uv run pytest`) and they execute inside that env.

   Optional groups:
   ```bash
   uv sync --group prod       # adds dbt-snowflake, for `dbt build --target prod`
   uv sync --group legacy     # adds Flask / MySQL / boto3 / pandasql for the frozen code below
   ```

2. **Provision credentials.** Create an AWS Secrets Manager secret named `ufcDBcred` (region
   `us-west-1`) holding `username`, `password`, `host`, and `dbInstanceIdentifier`. All scripts read
   DB credentials from here — nothing is hardcoded.

3. **Bulk load the database** (one time):
   ```bash
   cd SQL/sqlCreate && python tableSetup.py
   ```

4. **Engineer features:** open `featureEngineering/explore.ipynb`, or import `featureSetup` and call
   `set_up_features(fights_table, fighters_table)`.

5. **Run the web app:**
   ```bash
   cd flaskInt && python run.py     # http://127.0.0.1:5000
   ```

The incremental Lambda (`ufcDBLambda.py`) is deployed separately and runs on its weekly schedule.

---

## Tests

The HTML parsers are covered by unit tests that run against saved fixtures — no network
or database required:

```bash
uv run pytest
```

---

## Design decisions

- **Watermark-based incremental load** instead of re-scraping everything weekly — cheaper, faster,
  and a good citizen to the source site.
- **Secrets Manager** for DB credentials rather than env vars or hardcoded values.
- **Thread-pooled scraping with a 1s per-request delay** — parallel enough to backfill thousands of
  pages, polite enough not to hammer the source.
- **Leakage-safe feature windows** so the training set reflects only what was knowable before each
  bout.
- **A single scheduled Lambda over a full orchestrator** (Airflow/Dagster/Step Functions): the DAG is
  linear and runs weekly, so the operational overhead of an orchestrator isn't justified yet — see
  the roadmap for when that changes.

---

## Roadmap / known limitations

Honest about where this sits and where it's headed:

- **Reliability:** make the incremental load idempotent (unique keys + upserts) and advance the
  watermark only inside a transaction, so a mid-run failure can't drop events.
- **Schema:** normalize column types — several numeric stats are currently stored as strings.
- **Resilience:** add retry-with-backoff and per-item error isolation to scraping.
- **CI:** run the existing pytest suite in GitHub Actions and grow coverage beyond the parsers.
- **Infrastructure as code:** define the Lambda, schedule, and RDS via SAM/Terraform.
- **Data layering:** land raw scrapes immutably (bronze) before transforming (silver/gold) so the
  pipeline is reprocessable without re-scraping.
- **Modeling & UI:** train a baseline outcome model with a time-based backtest, and flesh out the
  Flask front end.
