{#
    One row per bout, references from stg_ufcstats__bouts.



#}

with bouts_source as (

    select * from {{ ref("stg_ufcstats__bouts") }}

),

event_source as (

    select * from {{ ref("stg_ufcstats__events") }}

),

gold_bout_layer as (

    select 
        {{ dbt_utils.generate_surrogate_key(['bout_url']) }} as bout_sk,
        bs.bout_url,
        {{ dbt_utils.generate_surrogate_key(['bs.event_url']) }} as event_sk,
        {{ dbt_utils.generate_surrogate_key(['fighter_a_url']) }} as fighter_a_sk,
        {{ dbt_utils.generate_surrogate_key(['fighter_b_url']) }} as fighter_b_sk,
        case when bs.winner_fighter_url is not null
            then {{ dbt_utils.generate_surrogate_key(['bs.winner_fighter_url']) }}
        end as winner_fighter_sk,
        es.event_date,
        bs.weight_class,
        bs.method,
        bs.is_finish,
        bs.is_no_contest,
        bs.is_draw,
        bs.finish_round,
        bs.finish_time_seconds,
        ((bs.finish_round - 1) * 300 + bs.finish_time_seconds) as bout_duration_seconds


    from bouts_source bs join event_source es on bs.event_url = es.event_url
    
)

select * from gold_bout_layer