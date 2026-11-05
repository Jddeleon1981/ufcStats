{#
    One row per fighter per bout, keyed for the star schema.

    The unpivot itself lives in int_fighter_bouts__unpivoted. This model adds
    the surrogate keys and exposes exactly the contracted columns. The
    intermediate also carries event_date, is_finish and bout_duration_seconds
    for the career-to-date windows; they're left out here on purpose, because
    fct_bout already has them and the contract doesn't include them.
#}

with fighter_bouts_source as (

    select * from {{ ref("int_fighter_bouts__unpivoted") }}

),

final as (

    select
        {{ dbt_utils.generate_surrogate_key(['bout_url', 'fighter_url']) }} as fighter_bout_sk,
        {{ dbt_utils.generate_surrogate_key(['bout_url']) }} as bout_sk,
        {{ dbt_utils.generate_surrogate_key(['event_url']) }} as event_sk,
        {{ dbt_utils.generate_surrogate_key(['fighter_url']) }} as fighter_sk,
        {{ dbt_utils.generate_surrogate_key(['opponent_fighter_url']) }} as opponent_fighter_sk,
        corner,
        is_winner,
        result,
        age_at_bout_years,
        knockdowns,
        sig_strikes_landed,
        sig_strikes_attempted,
        sig_strike_accuracy_pct,
        total_strikes_landed,
        total_strikes_attempted,
        takedowns_landed,
        takedowns_attempted,
        takedown_accuracy_pct,
        submission_attempts,
        reversals,
        control_time_seconds,
        sig_strikes_absorbed,
        takedowns_conceded

    from fighter_bouts_source

)

select * from final
