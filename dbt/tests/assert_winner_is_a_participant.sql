{#
    A bout's winner must be one of its two fighters, or null for a no contest.

#}


select
    winner_fighter_sk, bout_sk, fighter_a_sk, fighter_b_sk
from {{ ref('fct_bout') }}
where
    winner_fighter_sk is not null
    and winner_fighter_sk not in (fighter_a_sk, fighter_b_sk)
