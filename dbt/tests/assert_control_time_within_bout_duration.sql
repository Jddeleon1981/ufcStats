{#
    Asserts that the accumulated control time is within the duration of the bout

#}


select
    fct_f_b.bout_sk, fct_f_b.fighter_sk, fct_f_b.corner
from {{ ref('fct_fighter_bout') }} fct_f_b
    JOIN {{ ref('fct_bout') }} fct_b ON fct_f_b.bout_sk = fct_b.bout_sk
where
    fct_f_b.control_time_seconds > fct_b.bout_duration_seconds

