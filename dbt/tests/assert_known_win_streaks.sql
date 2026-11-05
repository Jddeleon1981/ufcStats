{#
    Pins the win streak entering three real bouts, one for each streak rule.
    All three are in the CI seed, so this runs on every pull request.

      Frankie Edgar, UFC 125: 5. Five straight wins going in.
      Frankie Edgar, UFC 136: 0. His previous bout was the UFC 125 draw, and
          a draw ends a streak.
      Jim Miller, UFC 168: 1. His previous bout was a no contest, which
          neither adds to a streak nor ends it. featureSetup.py reset it to 0.

    Pinned by URL because Edgar and Maynard fought three times. Starts from the
    expected rows, so a bout missing from the model fails as well.
#}

with expected as (

    select
        'http://ufcstats.com/fight-details/91bb64656e13a1d4' as bout_url,
        'http://www.ufcstats.com/fighter-details/f2688492b9a525a3' as fighter_url,
        5 as expected_win_streak
    union all
    select
        'http://ufcstats.com/fight-details/8a660069ae42edc2',
        'http://www.ufcstats.com/fighter-details/f2688492b9a525a3',
        0
    union all
    select
        'http://ufcstats.com/fight-details/39be68189f2d5074',
        'http://www.ufcstats.com/fighter-details/d1941565abf50b16',
        1

)

select
    expected.bout_url,
    expected.fighter_url,
    expected.expected_win_streak,
    career.prior_win_streak
from expected
left join {{ ref("int_fighter_bouts__career_to_date") }} as career
    on expected.bout_url = career.bout_url
    and expected.fighter_url = career.fighter_url
where career.prior_win_streak is distinct from expected.expected_win_streak
