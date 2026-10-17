{#
    Asserts that fights that we know to be draws are actually recorded as draws. Pins Edgar vs. Maynard
    at UFC 125 as a draw.
#}

with expected as (
    select 'http://ufcstats.com/fight-details/91bb64656e13a1d4' as bout_url
)

select *
from expected
LEFT JOIN {{ ref('fct_bout') }} fct_b ON expected.bout_url = fct_b.bout_url
where fct_b.is_draw is distinct from true