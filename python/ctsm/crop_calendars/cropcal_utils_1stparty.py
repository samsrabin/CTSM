"""Useful utilities that ONLY REQUIRE FIRST-PARTY BUILT-IN PYTHON MODULES"""


def check_first_last_seasons(first_season, last_season):
    """Check that first and last seasons are valid"""
    if first_season > last_season:
        raise ValueError(f"first_season ({first_season}) > last_season ({last_season})")
