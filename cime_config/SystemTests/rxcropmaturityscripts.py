from rxcropmaturity import RXCROPMATURITYSHARED


class RXCROPMATURITYSCRIPTS(RXCROPMATURITYSHARED):
    """
    Version of RXCROPMATURITYSHARED test that will skip both GDD-Generating and Prescribed Calendars
    runs, instead just testing the crop calendar scripts using archived inputs. The logic for
    determining that happens in RXCROPMATURITYSHARED.__init__() and is based on the test name.
    """
