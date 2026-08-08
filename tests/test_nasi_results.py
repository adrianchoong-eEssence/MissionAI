import csv
import io

from screens.control_centre import (
    _build_nasi_csv_bytes,
    _build_nasi_result_rows,
    _count_unique_nasi_participants,
    _normalise_nasi_submission,
    _parse_nasi_labelled_remarks,
)


def test_parse_nasi_labelled_remarks_with_standard_markers():
    remarks = """
N — New Ideas: Build one reusable template.
A — Areas for Improvement: Better collaboration across teams.
S - Strengths: Strong storytelling.
I - Implementation: Ship by Friday.
""".strip()
    parsed = _parse_nasi_labelled_remarks(remarks)
    assert parsed["New Ideas"] == "Build one reusable template."
    assert parsed["Areas of Improvement"] == "Better collaboration across teams."
    assert parsed["Strengths"] == "Strong storytelling."
    assert parsed["Implementation"] == "Ship by Friday."


def test_parse_nasi_labelled_remarks_allows_multiline_values():
    remarks = """
N — New Ideas:
A — Areas of Improvement:
- Improve onboarding
- Reduce confusion
S — Strengths:
good narrative
I — Implementation: Start with a prototype.
""".strip()
    parsed = _parse_nasi_labelled_remarks(remarks)
    assert "Improve onboarding" in parsed["Areas of Improvement"]
    assert parsed["Strengths"] == "good narrative"
    assert parsed["Implementation"] == "Start with a prototype."


def test_normalise_nasi_submission_uses_direct_fields_first():
    row = {
        "EventID": "EVT-1",
        "MissionID": "ACT-1",
        "ParticipantID": "P1",
        "SubmittedAt": "2026-08-08T10:00:00Z",
        "TeamName": "Lions",
        "NewIdeas": "direct idea",
        "AreasOfImprovement": "direct fix",
        "Strengths": "direct strength",
        "Implementation": "direct impl",
    }
    normalised = _normalise_nasi_submission(row)
    assert normalised["NewIdeas"] == "direct idea"
    assert normalised["AreasOfImprovement"] == "direct fix"
    assert normalised["EventID"] == "EVT-1"


def test_build_nasi_result_rows_isolated_to_event_and_activity():
    submissions = [
        {
            "EventID": "EVT-1",
            "MissionID": "ACT-1",
            "SubmissionType": "NASI",
            "ParticipantName": "Ada Lovelace",
            "Remarks": "N — New Ideas: idea\nA — Areas of Improvement: improve\nS - Strengths: strong\nI - Implementation: done",
            "SubmittedAt": "2026-01-01T00:00:00Z",
        },
        {
            "EventID": "EVT-2",
            "MissionID": "ACT-1",
            "SubmissionType": "NASI",
            "ParticipantName": "Grace Hopper",
            "Remarks": "N — New Ideas: other event",
        },
        {
            "EventID": "EVT-1",
            "MissionID": "ACT-99",
            "SubmissionType": "NASI",
            "ParticipantName": "Alan Turing",
            "Remarks": "N — New Ideas: ignored",
        },
        {
            "EventID": "EVT-1",
            "MissionID": "ACT-1",
            "SubmissionType": "TEXT",
            "ParticipantName": "No Op",
            "Remarks": "should ignore",
        },
    ]
    rows = _build_nasi_result_rows(submissions, "EVT-1", "ACT-1")
    assert len(rows) == 1
    assert rows[0]["FirstName"] == "Ada"
    assert rows[0]["LastName"] == "Lovelace"


def test_build_nasi_counts_are_unique_per_participant_id():
    rows = [
        {
            "EventID": "EVT-1",
            "MissionID": "ACT-1",
            "SubmissionType": "NASI",
            "ParticipantID": "P1",
            "ParticipantName": "Ada Lovelace",
            "Remarks": "N — New Ideas: first\nA — Areas for Improvement: 1\nS - Strengths: s\nI - Implementation: i",
            "SubmittedAt": "2026-08-08T10:00:00Z",
        },
        {
            "EventID": "EVT-1",
            "MissionID": "ACT-1",
            "SubmissionType": "NASI",
            "ParticipantID": "P1",
            "ParticipantName": "Ada Lovelace",
            "Remarks": "N — New Ideas: second\nA — Areas for Improvement: 2\nS - Strengths: s\nI - Implementation: i",
            "SubmittedAt": "2026-08-08T10:05:00Z",
        },
        {
            "EventID": "EVT-1",
            "MissionID": "ACT-1",
            "SubmissionType": "NASI",
            "ParticipantID": "P2",
            "ParticipantName": "Grace Hopper",
            "Remarks": "N — New Ideas: other\nA — Areas for Improvement: a\nS - Strengths: s\nI - Implementation: i",
            "SubmittedAt": "2026-08-08T10:10:00Z",
        },
    ]
    nasi_rows = _build_nasi_result_rows(rows, "EVT-1", "ACT-1")
    assert _count_unique_nasi_participants(nasi_rows) == 2


def test_build_nasi_csv_bytes_includes_expected_headers_and_content():
    rows = _build_nasi_result_rows(
        [
            {
                "EventID": "EVT-1",
                "MissionID": "ACT-1",
                "SubmissionType": "NASI",
                "ParticipantName": "Ada Lovelace",
                "TeamName": "Lions",
                "Remarks": "N — New Ideas: idea\nA - Areas for Improvement: fix",
                "SubmittedAt": "2026-01-01",
                "ParticipantID": "P-1",
            }
        ],
        "EVT-1",
        "ACT-1",
    )
    csv_data = _build_nasi_csv_bytes(rows)
    output = csv.DictReader(io.StringIO(csv_data.decode("utf-8")))
    headers = output.fieldnames
    assert headers == [
        "First Name",
        "Last Name",
        "Team",
        "New Ideas",
        "Areas of Improvement",
        "Strengths",
        "Implementation",
        "Submitted At",
    ]
    row = next(output)
    assert row["First Name"] == "Ada"
    assert row["Last Name"] == "Lovelace"
    assert row["Team"] == "Lions"
    assert row["New Ideas"] == "idea"


def test_parse_nasi_malformed_row_falls_back_safely():
    parsed = _parse_nasi_labelled_remarks("completely unstructured freeform narrative")
    assert parsed["New Ideas"] == "completely unstructured freeform narrative"
    assert parsed["Areas of Improvement"] == "—"
    assert parsed["Strengths"] == "—"
    assert parsed["Implementation"] == "—"
