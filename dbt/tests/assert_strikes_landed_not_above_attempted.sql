{#
    Asserts that the landed values is always less than or equal to the attempted values for
    significant strikes, strikes, and takedowns 

#}


select
    bout_sk, fighter_sk, corner
from {{ ref('fct_fighter_bout') }}
where
    (sig_strikes_landed > sig_strikes_attempted) or (takedowns_landed > takedowns_attempted) or (total_strikes_landed > total_strikes_attempted)

