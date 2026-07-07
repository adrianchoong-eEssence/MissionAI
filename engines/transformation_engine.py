from pathlib import Path
import yaml


class TransformationEngine:

    def __init__(self):
        self.intent_file = Path("knowledge_base/programme_intents.yaml")

        if self.intent_file.exists():
            with open(self.intent_file, "r", encoding="utf-8") as f:
                self.intents = yaml.safe_load(f)
        else:
            self.intents = {}

    def get_programme_intents(self):

        return list(
            self.intents.get(
                "programme_intents",
                {}
            ).keys()
        )

    def analyse_intent(self, intent):

        return self.intents.get(
            "programme_intents",
            {}
        ).get(intent, {})