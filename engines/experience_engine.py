class ExperienceEngine:

    def __init__(self):
        self.current_block = "Arrival"

    def current(self):
        return self.current_block

    def next(self, block):
        self.current_block = block

    def previous(self, block):
        self.current_block = block