{#
    One row per fighter, as the site showed them at scrape time.

    These are career-to-date figures that the site overwrites after every bout,
    so this model is a snapshot of the latest scrape rather than a historical
    record. Turning the successive raw versions into history is P3's job.
#}

with source as (

    select * from {{ source('raw', 'fighters') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
        partition by fighter_url
        order by _ingested_at desc
    ) = 1

),

parsed as (

    select
        fighter_url,
        fighter_name,
        first_name,
        {{ nullify_sentinels('last_name') }} as last_name,

        -- "5' 11"" -> 71. Feet and inches are separate captures because the
        -- site writes them with two different quote characters.
        try_cast(split_part(height, '''', 1) as integer) * 12
        + try_cast(replace(trim(split_part(height, '''', 2)), '"', '') as integer)
            as height_inches,

        -- "155 lbs." -> 155
        try_cast(split_part({{ nullify_sentinels('weight') }}, ' ', 1) as integer) as weight_lbs,

        -- "75"" -> 75. Missing for roughly one fighter in seven, which is a gap
        -- in the source rather than a parse failure: the site simply has no
        -- reach on file for them.
        try_cast(replace({{ nullify_sentinels('reach') }}, '"', '') as integer) as reach_inches,

        {{ nullify_sentinels('stance') }} as stance,
        {{ parse_site_date('dob', 'short') }} as date_of_birth,

        -- Career rates. The per-minute and per-15-minute figures are already
        -- decimals; the accuracy and defense figures arrive as "45%".
        try_cast(sig_strikes_landed_per_min as decimal(6, 2)) as sig_strikes_landed_per_min,
        try_cast(sig_strikes_absorbed_per_min as decimal(6, 2)) as sig_strikes_absorbed_per_min,
        {{ parse_percentage('sig_strike_accuracy') }} as sig_strike_accuracy_pct,
        {{ parse_percentage('sig_strike_defense') }} as sig_strike_defense_pct,

        try_cast(takedown_average as decimal(6, 2)) as takedowns_per_15_min,
        {{ parse_percentage('takedown_accuracy') }} as takedown_accuracy_pct,
        {{ parse_percentage('takedown_defense') }} as takedown_defense_pct,
        try_cast(submission_average as decimal(6, 2)) as submissions_per_15_min,

        _ingested_at

    from deduplicated

)

select * from parsed
