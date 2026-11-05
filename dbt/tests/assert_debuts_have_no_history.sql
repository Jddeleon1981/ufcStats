{#
    A debut, and only a debut, has an empty history.

    On a fighter's first bout every count is 0 and every average is null: there
    is nothing before it to count or divide. On every later bout the volume
    averages exist, because time has been fought. A frame that is off by one in
    either direction, or a stray coalesce that turns "unknown" into 0, breaks
    one side of this.

    Comparisons are null-safe (is distinct from) so a null where a 0 belongs
    fails instead of slipping through.
#}

select
    bout_url,
    fighter_url,
    prior_bouts

from {{ ref("int_fighter_bouts__career_to_date") }}
where
    -- a debut has no history at all
    (
        prior_bouts = 0
        and (
            prior_wins + prior_losses + prior_draws is distinct from 0
            or prior_win_streak is distinct from 0
            or prior_minutes_fought is distinct from 0
            or prior_win_rate is not null
            or prior_finish_rate is not null
            or prior_avg_fight_minutes is not null
            or prior_sig_strike_diff_per_min is not null
            or prior_takedown_diff_per_15 is not null
            or prior_control_share is not null
        )
    )
    -- and every later bout has its volume averages
    or (
        prior_bouts > 0
        and (
            prior_avg_fight_minutes is null
            or prior_sig_strike_diff_per_min is null
            or prior_takedown_diff_per_15 is null
            or prior_control_share is null
        )
    )
