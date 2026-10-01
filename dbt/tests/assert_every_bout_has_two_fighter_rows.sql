{#
    Asserts that every bout in fct_bout has exactly two rows in fct_fighter_bout

#}


select
    fct_b.bout_sk, count(fct_f_b.bout_sk) as fighter_count
from {{ ref('fct_bout') }} fct_b
    LEFT JOIN {{ ref('fct_fighter_bout') }} fct_f_b ON fct_f_b.bout_sk = fct_b.bout_sk
group by fct_b.bout_sk
having count(fct_f_b.bout_sk) != 2
