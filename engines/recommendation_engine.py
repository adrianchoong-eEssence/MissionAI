from engines.experience_engine import ExperienceEngine


class RecommendationEngine:

    def __init__(self):
        self.engine = ExperienceEngine()

    def recommend(self, objectives=None, venue=None, duration=None, pax=None):

        if objectives is None:
            objectives = []

        recommendations = []

        for activity in self.engine.all():

            score = 0
            text = str(activity).lower()

            for obj in objectives:
                if obj.lower() in text:
                    score += 5

            if venue and venue.lower() in text:
                score += 3

            if duration and duration.lower() in text:
                score += 2

            recommendations.append({
                "score": score,
                "activity": activity
            })

        recommendations.sort(key=lambda x: x["score"], reverse=True)

        return recommendations