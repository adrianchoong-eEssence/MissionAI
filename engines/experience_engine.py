from pathlib import Path
import yaml


class ExperienceEngine:

    def __init__(self):
        self.activity_path = Path("knowledge_base/activities")
        self.activities = []
        self.load()

    def load(self):
        self.activities = []

        if not self.activity_path.exists():
            return

        for file in self.activity_path.glob("*.yaml"):
            with open(file, "r", encoding="utf-8") as f:
                activity = yaml.safe_load(f)

                if activity:
                    activity["_source"] = file.name
                    self.activities.append(activity)

    def all(self):
        return self.activities

    def search(self, keyword):
        keyword = keyword.lower()
        results = []

        for activity in self.activities:
            if keyword in str(activity).lower():
                results.append(activity)

        return results