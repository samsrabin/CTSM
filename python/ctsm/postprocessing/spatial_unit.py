"""
Data and helpers having to do with CTSM spatial units
"""


class SpatialUnit:
    """
    Class for data and helper functions about CTSM spatial units
    """

    def __init__(self, *, dim: str, disp: str, i: str, prefix: str, wt: str):
        # pylint: disable=too-many-arguments

        # Need to use super().__setattr__() because of the __setattr__() override below.

        # Associated dimension name
        self.dim: str
        super().__setattr__("dim", dim)

        # Used when printing messages
        self.disp: str
        super().__setattr__("disp", disp)

        # Prefix for ..._*i variables
        self.i: str
        super().__setattr__("i", i)

        # Prefix for *1d_... variables
        self.prefix: str
        super().__setattr__("prefix", prefix)

        # Suffix for ...1d_wt* variables (also ...itype_* variables)
        self.wt: str
        super().__setattr__("wt", wt)

    def __repr__(self):
        return f"{type(self)}({self.dim})"

    def __str__(self):
        return self.disp

    def __setattr__(self, name, value):
        raise AttributeError(f"'{type(self).__name__}' object is immutable")

    def __delattr__(self, name):
        raise AttributeError(f"'{type(self).__name__}' object is immutable")


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
