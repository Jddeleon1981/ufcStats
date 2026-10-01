{#
    One row per fighter, references from stg_ufcstats__fighters.



#}

with source as (

    select * from {{ ref("stg_ufcstats__fighters") }}

),

gold_fighter_layer as (

    select 
        {{ dbt_utils.generate_surrogate_key(['fighter_url']) }} as fighter_sk,
        fighter_url,
        fighter_name,
        first_name,
        last_name,
        height_inches,
        weight_lbs,
        reach_inches,
        stance,
        date_of_birth,
        sig_strikes_landed_per_min,
        sig_strikes_absorbed_per_min,
        sig_strike_accuracy_pct,
        sig_strike_defense_pct,
        takedowns_per_15_min,
        takedown_accuracy_pct,
        takedown_defense_pct,
        submissions_per_15_min

    from source
    

)

select * from gold_fighter_layer