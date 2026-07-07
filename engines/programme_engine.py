from pathlib import Path
import yaml


class ProgrammeEngine:

    def __init__(self):
        self.pattern_folder = Path("knowledge_base/programme_patterns")

    def get_pattern(self, programme_type):

        filename = programme_type.lower().replace(" ", "_") + ".yaml"

        file = self.pattern_folder / filename

        if not file.exists():
            return None

        with open(file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)