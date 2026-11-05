{#
    Walking each fighter's bouts in date order, prior_bouts starts at 0 and
    goes up by exactly 1 each time.

    Catches ordering mistakes the other tests can miss: if the windows sorted
    by the wrong column, every total could still look plausible, but the count
    would jump around instead of climbing one bout at a time.
#}

with ordered as (

    select
        bout_url,
        fighter_url,
        event_date,
        prior_bouts,
        lag(prior_bouts) over (partition by fighter_url order by event_date) as previous_prior_bouts

    from {{ ref("int_fighter_bouts__career_to_date") }}

)

select *
from ordered
where
    -- a fighter's first bout starts the count at 0
    (previous_prior_bouts is null and prior_bouts <> 0)
    -- every later bout is exactly one more than the one before
    or (previous_prior_bouts is not null and prior_bouts <> previous_prior_bouts + 1)
