# Naming and layering conventions

Decided at the start of the rebuild so that every model added later has an
obvious name and an obvious home. If a new object doesn't fit one of these
rules, the rule is wrong — change it here rather than making an exception.

## Casing

`snake_case` everywhere: columns, models, seeds, macros, tests, file names.

The source site renders display labels (`Str. Acc.`, `SLpM`, `TD Def.`) and the
old MySQL schema mixed conventions (`firstName`, `eventHyperLink`,
`fighter_A_ID`). Neither survives past extraction. Column names are stable
identifiers we control; they are not the source's presentation strings.

## Layers

| Layer | Prefix | Materialization | Rule |
|---|---|---|---|
| Raw (bronze) | `raw.<entity>` | parquet / seed | Append-only. Values exactly as the source rendered them. |
| Staging | `stg_<source>__<entity>` | view | One model per source table. Rename, cast, clean. **No joins, no business logic.** |
| Intermediate | `int_<subject>__<verb>` | ephemeral | Shared building blocks. Never read by anything outside dbt. |
| Marts | `dim_<entity>` / `fct_<event>` | table | The only layer consumers may read. |

The double underscore separates the two halves of a name, so
`stg_ufcstats__fighters` reads as "the `fighters` entity from the `ufcstats`
source" even though both halves contain single underscores.

### Examples

```
stg_ufcstats__fighters        stg_ufcstats__events        stg_ufcstats__bouts
stg_odds__lines

int_fighter_bouts__unpivoted          one row per fighter per bout
int_fighter_bouts__career_to_date     career-to-date windows, as of each bout
int_fighter__crosswalk                ufcstats fighter <-> odds provider identity

dim_fighter    dim_event
fct_bout       fct_fighter_bout       fct_bout_features
```

## Keys

- **Natural keys** are the source's own detail URLs: `fighter_url`, `event_url`,
  `bout_url`. These are what the raw layer carries, and they are stable across
  re-scrapes in a way that an `AUTO_INCREMENT` id never was.
- **Surrogate keys** are generated in staging with
  `dbt_utils.generate_surrogate_key`, and named `<entity>_sk`.
- Foreign keys keep the referenced entity's name: `fighter_sk`, not `fighter_id`
  on one model and `fighterID` on another.

## Columns

- Booleans read as assertions: `is_title_bout`, `has_totals`.
- Dates end `_date`, timestamps end `_at`, durations state their unit:
  `control_time_seconds`, `average_fight_time_minutes`.
- Counts end `_count`; ratios and shares end `_rate` or `_pct` and are stored as
  decimals, not as the source's `"45%"` strings.
- The two sides of a bout are `_a` / `_b` suffixes, never `A`/`B` casing.

## Raw-layer metadata

Every raw record carries four underscore-prefixed columns, and staging drops all
but `_ingested_at`:

| Column | Meaning |
|---|---|
| `_ingested_at` | UTC timestamp the record was scraped. Drives source freshness. |
| `_source_url` | The exact page it came from. |
| `_batch_id` | Ties every record from one extraction run together. |
| `_raw_payload` | The unparsed source values as JSON, so nothing is lost. |

## Tests

- Generic tests live in the model's `.yml` beside it.
- Singular tests are named for the assertion they make, phrased so that a
  failure reads as a sentence: `assert_winner_is_a_participant.sql`,
  `assert_control_time_within_bout_duration.sql`.
