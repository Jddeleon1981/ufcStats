{#
    One row per event. Deduplicates, casts the date, and splits the location.

    The listing includes cards that have not happened yet, and they are kept:
    an upcoming event is a real event with no bouts attached. Filtering to
    completed cards is a mart concern, not a staging one.
#}

with source as (

    select * from {{ source('raw', 'events') }}

),

deduplicated as (

    -- Bronze is append-only, so a re-scrape leaves more than one row per event.
    -- The newest wins; earlier versions stay in raw for the P3 snapshot.
    select *
    from source
    qualify row_number() over (
        partition by event_url
        order by _ingested_at desc
    ) = 1

),

parsed as (

    select
        event_url,
        event_name,
        {{ parse_site_date('event_date', 'long') }} as event_date,

        -- "Las Vegas, Nevada, USA" or "Shanghai, China": the country is always
        -- the last part and the city the first, so the state is whatever sits
        -- between them, and is null for the two-part form.
        trim(split_part(event_location, ',', 1)) as event_city,
        case
            when length(event_location) - length(replace(event_location, ',', '')) = 2
                then trim(split_part(event_location, ',', 2))
        end as event_state,
        trim(
            split_part(
                event_location,
                ',',
                length(event_location) - length(replace(event_location, ',', '')) + 1
            )
        ) as event_country,
        event_location as event_location_raw,

        _ingested_at

    from deduplicated

)

select * from parsed
