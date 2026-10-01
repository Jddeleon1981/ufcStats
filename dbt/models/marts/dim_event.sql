{#
    One row per event, references from stg_ufcstats__events.



#}

with source as (

    select * from {{ ref("stg_ufcstats__events") }}

),

gold_event_layer as (

    select 
        {{ dbt_utils.generate_surrogate_key(['event_url']) }} as event_sk,
        event_url,
        event_name,
        event_date,
        event_city,
        event_state,
        event_country,
        is_modern_era

    from source
    
)

select * from gold_event_layer