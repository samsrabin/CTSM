"""
Various functions to help the RXCROPMATURITY* SystemTests
"""

from typing import Tuple


def get_usable_years_for_check_rxboth_run(
    run_startyear: int, run_nyears: int, skip_firstrun: bool
) -> Tuple[int, int]:
    """Get the first and last years to run through check_rxboth_run.py"""
    if skip_firstrun:
        first_usable_year = run_startyear + 1
        last_usable_year = first_usable_year
    else:
        first_usable_year = run_startyear + 2
        last_usable_year = run_startyear + run_nyears - 2
    return first_usable_year, last_usable_year
