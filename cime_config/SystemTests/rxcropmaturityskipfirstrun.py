from rxcropmaturity import RXCROPMATURITYSHARED


class RXCROPMATURITYSKIPFIRSTRUN(RXCROPMATURITYSHARED):
    def run_phase(self):
        self._run_phase(skip_firstrun=True)
