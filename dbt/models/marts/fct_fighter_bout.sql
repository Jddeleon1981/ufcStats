{#
    Two rows per bout, one per fighter and it references from stg_ufcstats__bouts.



#}

with bouts_source as (

    select * from {{ ref("stg_ufcstats__bouts") }}

),

fighter_source as (

    select * from {{ ref("dim_fighter") }}

),

event_source as (

    select * from {{ ref("dim_event") }}

),

gold_fighter_bout_layer as (

    {# Fighter A section #}
    select 
        {{ dbt_utils.generate_surrogate_key(['bout_url', 'fighter_a_url']) }} as fighter_bout_sk,
        {{ dbt_utils.generate_surrogate_key(['bout_url']) }} as bout_sk,
        {{ dbt_utils.generate_surrogate_key(['bs.event_url']) }} as event_sk,
        {{ dbt_utils.generate_surrogate_key(['fighter_a_url']) }} as fighter_sk,
        {{ dbt_utils.generate_surrogate_key(['fighter_b_url']) }} as opponent_fighter_sk,
        'a' as corner,
        case
            when bs.winner_fighter_url = bs.fighter_a_url then true
            when bs.winner_fighter_url = bs.fighter_b_url then false
            when bs.outcome = 'draw' then false
            else null
        end as is_winner,
        ((es.event_date - fs.date_of_birth) / 365.25) as age_at_bout_years,
        bs.fighter_a_knockdowns as knockdowns,
        bs.fighter_a_sig_strikes_landed as sig_strikes_landed,
        bs.fighter_a_sig_strikes_attempted as sig_strikes_attempted,
        bs.fighter_a_sig_strike_accuracy_pct as sig_strike_accuracy_pct,
        bs.fighter_a_total_strikes_landed as total_strikes_landed,
        bs.fighter_a_total_strikes_attempted as total_strikes_attempted,
        bs.fighter_a_takedowns_landed as takedowns_landed,
        bs.fighter_a_takedowns_attempted as takedowns_attempted,
        bs.fighter_a_takedown_accuracy_pct as takedown_accuracy_pct,
        bs.fighter_a_submission_attempts as submission_attempts,
        bs.fighter_a_reversals as reversals,
        bs.fighter_a_control_time_seconds as control_time_seconds,
        bs.fighter_b_sig_strikes_landed as sig_strikes_absorbed,
        bs.fighter_b_takedowns_landed as takedowns_conceded

    from bouts_source bs left join fighter_source fs on bs.fighter_a_url = fs.fighter_url
                         join event_source es on bs.event_url = es.event_url

    UNION ALL

    {# Fighter B section #}
    select 
        {{ dbt_utils.generate_surrogate_key(['bout_url', 'fighter_b_url']) }} as fighter_bout_sk,
        {{ dbt_utils.generate_surrogate_key(['bout_url']) }} as bout_sk,
        {{ dbt_utils.generate_surrogate_key(['bs.event_url']) }} as event_sk,
        {{ dbt_utils.generate_surrogate_key(['fighter_b_url']) }} as fighter_sk,
        {{ dbt_utils.generate_surrogate_key(['fighter_a_url']) }} as opponent_fighter_sk,
        'b' as corner,
        case
            when bs.winner_fighter_url = bs.fighter_a_url then false
            when bs.winner_fighter_url = bs.fighter_b_url then true
            when bs.outcome = 'draw' then false
            else null
        end as is_winner,
        ((es.event_date - fs.date_of_birth) / 365.25) as age_at_bout_years,
        bs.fighter_b_knockdowns as knockdowns,
        bs.fighter_b_sig_strikes_landed as sig_strikes_landed,
        bs.fighter_b_sig_strikes_attempted as sig_strikes_attempted,
        bs.fighter_b_sig_strike_accuracy_pct as sig_strike_accuracy_pct,
        bs.fighter_b_total_strikes_landed as total_strikes_landed,
        bs.fighter_b_total_strikes_attempted as total_strikes_attempted,
        bs.fighter_b_takedowns_landed as takedowns_landed,
        bs.fighter_b_takedowns_attempted as takedowns_attempted,
        bs.fighter_b_takedown_accuracy_pct as takedown_accuracy_pct,
        bs.fighter_b_submission_attempts as submission_attempts,
        bs.fighter_b_reversals as reversals,
        bs.fighter_b_control_time_seconds as control_time_seconds,
        bs.fighter_a_sig_strikes_landed as sig_strikes_absorbed,
        bs.fighter_a_takedowns_landed as takedowns_conceded

    from bouts_source bs left join fighter_source fs on bs.fighter_b_url = fs.fighter_url
                         join event_source es on bs.event_url = es.event_url

)

select * from gold_fighter_bout_layer