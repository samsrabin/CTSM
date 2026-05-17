"""
Data and helpers having to do with CTSM spatial units
"""


class SpatialUnit:
    """
    Class for data and helper functions about CTSM spatial units
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, *, dim: str, disp: str, i: str, prefix: str, wt: str):
        # pylint: disable=too-many-arguments

        # Associated dimension name
        self.dim = dim

        # Used when printing messages
        self.disp = disp

        # Prefix for ..._*i variables
        self.i = i

        # Prefix for *1d_... variables
        self.prefix = prefix

        # Suffix for ...1d_wt* variables (also ...itype_* variables)
        self.wt = wt

    def __repr__(self):
        return f"{type(self)}({self.dim})"

    def __str__(self):
        return self.disp


SU_PFT = SpatialUnit(dim="pft", disp="PFT", i=None, prefix="pfts", wt=None)
SU_COLS = SpatialUnit(dim="column", disp="column", i="c", prefix="cols", wt="col")
SU_LAND = SpatialUnit(dim="landunit", disp="land unit", i="l", prefix="land", wt="lunit")
SU_GRID = SpatialUnit(dim="gridcell", disp="gridcell", i="g", prefix="grid", wt="gcell")
SUDICT = {
    SU_PFT.dim: SU_PFT,
    SU_COLS.dim: SU_COLS,
    SU_LAND.dim: SU_LAND,
    SU_GRID.dim: SU_GRID,
}
