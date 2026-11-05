{{ config(materialized='table') }}

{#
    One row per fighter per bout, describing the fighter as they entered it.
    Every value comes from bouts strictly before this one, never the bout
    itself. These are the point-in-time features: dim_fighter's career rates
    are not, because the site overwrites them after every bout.

    Every aggregate shares one frame, the `prior` window: the fighter's bouts
    in date order, from their first up to the one before this. On a debut the
    frame is empty, so counts are 0 and averages are null. The frame is only
    correct while a fighter never has two bouts on one date.

    A table rather than the folder's ephemeral default, so tests can select
    from it.
#}

with fighter_bouts_source as (

    select * from {{ ref("int_fighter_bouts__unpivoted") }}

),

running_totals as (

    select
        bout_url,
        fighter_url,
        event_date,

        -- count() over an empty frame is 0, so these are never null. Counting
        -- a case expression keeps the filter portable: not every engine
        -- accepts count(*) filter (where ...) as a window function.
        count(*) over prior as prior_bouts,
        count(case when result = 'win' then 1 end) over prior as prior_wins,
        count(case when result = 'loss' then 1 end) over prior as prior_losses,
        count(case when result = 'draw' then 1 end) over prior as prior_draws,

        -- A DQ win has a null is_finish, so it counts as a win but not a finish.
        count(case when result = 'win' and is_finish then 1 end) over prior as prior_finish_wins,

        -- Volume includes no contests: the time and the strikes happened even
        -- though the result was voided. sum() over an empty frame is null.
        coalesce(sum(bout_duration_seconds) over prior, 0) as prior_seconds_fought,
        sum(sig_strikes_landed - sig_strikes_absorbed) over prior as prior_sig_strike_diff,
        sum(takedowns_landed - takedowns_conceded) over prior as prior_takedown_diff,
        sum(control_time_seconds) over prior as prior_control_seconds

    from fighter_bouts_source
    window prior as (
        partition by fighter_url
        order by event_date
        rows between unbounded preceding and 1 preceding
    )

),

final as (

    select
        bout_url,
        fighter_url,
        event_date,

        prior_bouts,
        prior_wins,
        prior_losses,
        prior_draws,

        -- Draws are a result and count; no contests aren't. Null until the
        -- fighter has at least one bout with a result.
        cast(prior_wins as double) / nullif(prior_wins + prior_losses + prior_draws, 0) as prior_win_rate,

        -- Knockouts and submissions per win. Null until the first win.
        cast(prior_finish_wins as double) / nullif(prior_wins, 0) as prior_finish_rate,

        prior_seconds_fought / 60.0 as prior_minutes_fought,
        prior_seconds_fought / 60.0 / nullif(prior_bouts, 0) as prior_avg_fight_minutes,

        -- Differentials over total time fought rather than averages of
        -- per-bout rates, so a 30-second fight weighs less than a 25-minute
        -- one. Units follow the site: strikes per minute, takedowns per 15.
        prior_sig_strike_diff / nullif(prior_seconds_fought / 60.0, 0) as prior_sig_strike_diff_per_min,
        prior_takedown_diff / nullif(prior_seconds_fought / 900.0, 0) as prior_takedown_diff_per_15,
        cast(prior_control_seconds as double) / nullif(prior_seconds_fought, 0) as prior_control_share

    from running_totals

)

select * from final
