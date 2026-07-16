import unittest

from ai.aura import build_safe_mission_context


class AIFacilitatorSafetyTests(unittest.TestCase):
    def test_safe_context_excludes_answer_and_unreleased_hints(self):
        context = build_safe_mission_context({
            "MissionID": "M01",
            "Title": "Venue Cipher",
            "ParticipantInstructions": "Decode the customer promise.",
            "Clue": "Look for a repeated pattern.",
            "Answer": "ELEVATE",
            "Hint1": "Count the blue symbols.",
            "Hint2": "Read every second letter.",
            "Hint3": "The answer starts with E.",
        })

        self.assertEqual(context["MissionID"], "M01")
        self.assertEqual(context["Title"], "Venue Cipher")
        self.assertNotIn("Answer", context)
        self.assertNotIn("Hint1", context)
        self.assertNotIn("Hint2", context)
        self.assertNotIn("Hint3", context)


if __name__ == "__main__":
    unittest.main()
