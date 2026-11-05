{#
    The leakage test. Recomputes every count and total in
    int_fighter_bouts__career_to_date without a single window function: a
    self-join to the same fighter's bouts on strictly earlier dates. A row
    where the two disagree means a window frame reached the current bout (or a
    later one), so that feature has leaked.

    A self-join can't share a frame mistake with the model, which is the point.
    Generic tests can't do this: a leaked feature is still unique, filled in
    and in range, and a deliberately leaky frame passed all of them.

    The strict < assumes a fighter never has two bouts on one date. The
    (fighter_url, event_date) uniqueness test on the model enforces that.
#}

with career as (

    select * from {{ ref("int_fighter_bouts__career_to_date") }}

),

fighter_bouts as (

    select * from {{ ref("int_fighter_bouts__unpivoted") }}

),

recomputed as (

    -- Left join so a debut, with no earlier bouts, still gets a row of zeros.
    select
        career.bout_url,
        career.fighter_url,
        count(earlier.bout_url) as prior_bouts,
        count(case when earlier.result = 'win' then 1 end) as prior_wins,
        count(case when earlier.result = 'loss' then 1 end) as prior_losses,
        count(case when earlier.result = 'draw' then 1 end) as prior_draws,
        coalesce(sum(earlier.bout_duration_seconds), 0) / 60.0 as prior_minutes_fought

    from career
    left join fighter_bouts as earlier
        on earlier.fighter_url = career.fighter_url
        and earlier.event_date < career.event_date
    group by career.bout_url, career.fighter_url

)

select
    career.bout_url,
    career.fighter_url,
    career.prior_bouts,
    recomputed.prior_bouts as recomputed_prior_bouts,
    career.prior_wins,
    recomputed.prior_wins as recomputed_prior_wins,
    career.prior_losses,
    recomputed.prior_losses as recomputed_prior_losses,
    career.prior_draws,
    recomputed.prior_draws as recomputed_prior_draws,
    career.prior_minutes_fought,
    recomputed.prior_minutes_fought as recomputed_prior_minutes_fought

from career
inner join recomputed
    on career.bout_url = recomputed.bout_url
    and career.fighter_url = recomputed.fighter_url
where career.prior_bouts is distinct from recomputed.prior_bouts
    or career.prior_wins is distinct from recomputed.prior_wins
    or career.prior_losses is distinct from recomputed.prior_losses
    or career.prior_draws is distinct from recomputed.prior_draws
    -- minutes are a division, so compare with a tolerance rather than exactly
    or abs(career.prior_minutes_fought - recomputed.prior_minutes_fought) > 0.000001
