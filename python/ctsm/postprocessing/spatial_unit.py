"""
Data and helpers having to do with CTSM spatial units
"""

from functools import total_ordering


@total_ordering
class SpatialUnit:
    """
    Class for data and helper functions about CTSM spatial units
    """

    def __init__(self, *, dim: str, disp: str, i: str, prefix: str, wt: str, level: int):
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

        # Integer representing level of spatial unit in the hierarchy, with PFT lowest and gridcell
        # highest.
        self.level: int
        super().__setattr__("level", level)

    def __repr__(self):
        return f"{type(self)}({self.dim})"

    def __str__(self):
        return self.disp

    def __setattr__(self, name, value):
        raise AttributeError(f"'{type(self).__name__}' object is immutable")

    def __delattr__(self, name):
        raise AttributeError(f"'{type(self).__name__}' object is immutable")

    def _is_valid_operand(self, other):
        return isinstance(other, type(self))

    def __eq__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self.level == other.level

    def __lt__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self.level < other.level


SU_PFT = SpatialUnit(dim="pft", disp="PFT", i=None, prefix="pfts", wt=None, level=1)
SU_COLS = SpatialUnit(dim="column", disp="column", i="c", prefix="cols", wt="col", level=10)
SU_LAND = SpatialUnit(dim="landunit", disp="land unit", i="l", prefix="land", wt="lunit", level=100)
SU_GRID = SpatialUnit(dim="gridcell", disp="gridcell", i="g", prefix="grid", wt="gcell", level=1000)
SUDICT = {
    SU_PFT.dim: SU_PFT,
    SU_COLS.dim: SU_COLS,
    SU_LAND.dim: SU_LAND,
    SU_GRID.dim: SU_GRID,
}
