{#
    One row per bout, both corners side by side, cast and flagged.

    Stays at the source's grain: corner A and corner B are columns, not rows.
    Unpivoting to one row per fighter per bout is what the intermediate layer
    does, because that shape is derived rather than given.
#}

with source as (

    select * from {{ source('raw', 'bouts') }}

),

deduplicated as (

    select
        *,
        -- Rows scraped before 2026-10-04 predate the result column. For those,
        -- a no contest is already in winner_name and everything else is a win:
        -- all 61 draws were re-scraped with the column in place.
        coalesce(result, case when winner_name = 'nc' then 'nc' else 'win' end) as outcome
    from source
    qualify row_number() over (
        partition by bout_url
        order by _ingested_at desc
    ) = 1

),

parsed as (

    select
        bout_url,
        event_url,
        fighter_a_url,
        fighter_b_url,

        -- Names are kept even though they also live in the fighters model.
        -- The winner arrives as a name string, so resolving it to a url has to
        -- happen here, where both are in the same row and no join is needed.
        fighter_a_name,
        fighter_b_name,

        -- Every one of the 9,135 raw rows resolves to a corner or to a no
        -- contest or to a draw.
        case
            when winner_name = fighter_a_name then fighter_a_url
            when winner_name = fighter_b_name then fighter_b_url
        end as winner_fighter_url,
        outcome,
        outcome = 'nc' as is_no_contest,
        outcome = 'draw' as is_draw,

        weight_class,
        method,

        -- Whether the bout ended early. Null, not false, for the outcomes that
        -- are neither: a bout that was overturned or that a fighter could not
        -- continue did not "go to decision" in any meaningful sense, and
        -- collapsing them into false would quietly understate finish rate.
        case
            when method in ('KO/TKO', 'Submission', 'TKO - Doctor''s Stoppage') then true
            when method like 'Decision%' then false
        end as is_finish,

        try_cast(finish_round as integer) as finish_round,
        {{ parse_mmss_seconds('finish_time') }} as finish_time_seconds,

        -- Corner A
        try_cast(fighter_a_knockdowns as integer) as fighter_a_knockdowns,
        {{ parse_landed('fighter_a_sig_strikes') }} as fighter_a_sig_strikes_landed,
        {{ parse_attempted('fighter_a_sig_strikes') }} as fighter_a_sig_strikes_attempted,
        {{ parse_percentage('fighter_a_sig_strike_acc') }} as fighter_a_sig_strike_accuracy_pct,
        {{ parse_landed('fighter_a_total_strikes') }} as fighter_a_total_strikes_landed,
        {{ parse_attempted('fighter_a_total_strikes') }} as fighter_a_total_strikes_attempted,
        {{ parse_landed('fighter_a_takedowns') }} as fighter_a_takedowns_landed,
        {{ parse_attempted('fighter_a_takedowns') }} as fighter_a_takedowns_attempted,
        {{ parse_percentage('fighter_a_takedown_acc') }} as fighter_a_takedown_accuracy_pct,
        try_cast(fighter_a_sub_attempts as integer) as fighter_a_submission_attempts,
        try_cast(fighter_a_reversals as integer) as fighter_a_reversals,
        {{ parse_mmss_seconds('fighter_a_control_time') }} as fighter_a_control_time_seconds,

        -- Corner B
        try_cast(fighter_b_knockdowns as integer) as fighter_b_knockdowns,
        {{ parse_landed('fighter_b_sig_strikes') }} as fighter_b_sig_strikes_landed,
        {{ parse_attempted('fighter_b_sig_strikes') }} as fighter_b_sig_strikes_attempted,
        {{ parse_percentage('fighter_b_sig_strike_acc') }} as fighter_b_sig_strike_accuracy_pct,
        {{ parse_landed('fighter_b_total_strikes') }} as fighter_b_total_strikes_landed,
        {{ parse_attempted('fighter_b_total_strikes') }} as fighter_b_total_strikes_attempted,
        {{ parse_landed('fighter_b_takedowns') }} as fighter_b_takedowns_landed,
        {{ parse_attempted('fighter_b_takedowns') }} as fighter_b_takedowns_attempted,
        {{ parse_percentage('fighter_b_takedown_acc') }} as fighter_b_takedown_accuracy_pct,
        try_cast(fighter_b_sub_attempts as integer) as fighter_b_submission_attempts,
        try_cast(fighter_b_reversals as integer) as fighter_b_reversals,
        {{ parse_mmss_seconds('fighter_b_control_time') }} as fighter_b_control_time_seconds,

        _ingested_at

    from deduplicated

)

select * from parsed
