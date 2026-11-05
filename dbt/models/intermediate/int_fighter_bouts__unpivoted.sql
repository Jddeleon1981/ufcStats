{#
    One row per fighter per bout: stg_ufcstats__bouts unpivoted, so every bout
    appears twice, once from each corner's point of view.

    Both fct_fighter_bout and the career-to-date windows need this shape. It
    lives here rather than inside the mart because intermediate models never
    read a mart. Keyed on the site's URLs: surrogate keys are the marts' job.
#}

with bouts_source as (

    select * from {{ ref("stg_ufcstats__bouts") }}

),

events_source as (

    select * from {{ ref("stg_ufcstats__events") }}

),

fighters_source as (

    select * from {{ ref("stg_ufcstats__fighters") }}

),

unpivoted as (

    -- Corner A's point of view: A's numbers are "mine", B's are the opponent's.
    select
        bout_url,
        event_url,
        fighter_a_url as fighter_url,
        fighter_b_url as opponent_fighter_url,
        'a' as corner,

        -- False for a draw, since nobody won. Null only for a no contest,
        -- which is neither a win nor a loss.
        case
            when winner_fighter_url = fighter_a_url then true
            when is_draw then false
            when winner_fighter_url = fighter_b_url then false
        end as is_winner,

        -- No else: a bout that is none of these returns null, and the
        -- not_null constraint on fct_fighter_bout.result fails the build.
        case
            when is_no_contest then 'no_contest'
            when is_draw then 'draw'
            when winner_fighter_url = fighter_a_url then 'win'
            when winner_fighter_url = fighter_b_url then 'loss'
        end as result,

        fighter_a_knockdowns as knockdowns,
        fighter_a_sig_strikes_landed as sig_strikes_landed,
        fighter_a_sig_strikes_attempted as sig_strikes_attempted,
        fighter_a_sig_strike_accuracy_pct as sig_strike_accuracy_pct,
        fighter_a_total_strikes_landed as total_strikes_landed,
        fighter_a_total_strikes_attempted as total_strikes_attempted,
        fighter_a_takedowns_landed as takedowns_landed,
        fighter_a_takedowns_attempted as takedowns_attempted,
        fighter_a_takedown_accuracy_pct as takedown_accuracy_pct,
        fighter_a_submission_attempts as submission_attempts,
        fighter_a_reversals as reversals,
        fighter_a_control_time_seconds as control_time_seconds,
        fighter_b_sig_strikes_landed as sig_strikes_absorbed,
        fighter_b_takedowns_landed as takedowns_conceded,

        is_finish,
        bout_duration_seconds

    from bouts_source

    union all

    -- Corner B's point of view: the same columns with A and B swapped.
    select
        bout_url,
        event_url,
        fighter_b_url as fighter_url,
        fighter_a_url as opponent_fighter_url,
        'b' as corner,

        case
            when winner_fighter_url = fighter_b_url then true
            when is_draw then false
            when winner_fighter_url = fighter_a_url then false
        end as is_winner,

        case
            when is_no_contest then 'no_contest'
            when is_draw then 'draw'
            when winner_fighter_url = fighter_b_url then 'win'
            when winner_fighter_url = fighter_a_url then 'loss'
        end as result,

        fighter_b_knockdowns as knockdowns,
        fighter_b_sig_strikes_landed as sig_strikes_landed,
        fighter_b_sig_strikes_attempted as sig_strikes_attempted,
        fighter_b_sig_strike_accuracy_pct as sig_strike_accuracy_pct,
        fighter_b_total_strikes_landed as total_strikes_landed,
        fighter_b_total_strikes_attempted as total_strikes_attempted,
        fighter_b_takedowns_landed as takedowns_landed,
        fighter_b_takedowns_attempted as takedowns_attempted,
        fighter_b_takedown_accuracy_pct as takedown_accuracy_pct,
        fighter_b_submission_attempts as submission_attempts,
        fighter_b_reversals as reversals,
        fighter_b_control_time_seconds as control_time_seconds,
        fighter_a_sig_strikes_landed as sig_strikes_absorbed,
        fighter_a_takedowns_landed as takedowns_conceded,

        is_finish,
        bout_duration_seconds

    from bouts_source

),

final as (

    -- Joined once, after the unpivot, rather than once per corner.
    select
        unpivoted.*,
        events_source.event_date,

        -- Point-in-time safe: a date of birth never changes, so this is the
        -- fighter's age on the night regardless of when the profile was scraped.
        (events_source.event_date - fighters_source.date_of_birth) / 365.25 as age_at_bout_years

    from unpivoted
    inner join events_source
        on unpivoted.event_url = events_source.event_url
    -- Left join: a fighter with no profile row still keeps their bouts.
    left join fighters_source
        on unpivoted.fighter_url = fighters_source.fighter_url

)

select * from final
