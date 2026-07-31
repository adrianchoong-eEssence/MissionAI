import unittest
from unittest.mock import patch

from data import google_sheets
from data.google_sheets import GoogleSheetsDB


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeSheetError(Exception):
    def __init__(self, status_code):
        super().__init__(f"Sheets error {status_code}")
        self.response = FakeResponse(status_code)


class FakeRuntime:
    def __init__(self, players=None, error=None, can_publish=True):
        self.can_publish = can_publish
        self.players = list(players or [])
        self.error = error
        self.calls = []

    def get_players(self, event_id):
        self.calls.append(event_id)
        if self.error:
            raise self.error
        return list(self.players)


class GoogleSheetsResilienceTests(unittest.TestCase):
    def setUp(self):
        google_sheets.get_sheet_participant_count.clear()
        google_sheets.get_sheet_records.clear()
        with google_sheets._PARTICIPANT_COUNT_LOCK:
            google_sheets._LAST_SUCCESSFUL_PARTICIPANT_COUNTS.clear()
        with google_sheets._SHEET_RECORDS_LOCK:
            google_sheets._LAST_SUCCESSFUL_SHEET_RECORDS.clear()

    def make_database(self, runtime):
        database = GoogleSheetsDB.__new__(GoogleSheetsDB)
        database.runtime = runtime
        database._participant_count_warnings = {}
        return database

    def test_retryable_sheet_error_retries_and_recovers(self):
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise FakeSheetError(503)
            return 41

        with patch("data.google_sheets.time.sleep"), patch(
            "data.google_sheets.random.uniform",
            return_value=0,
        ):
            result = google_sheets._call_sheets_with_retry(operation)

        self.assertEqual(result, 41)
        self.assertEqual(attempts["count"], 3)

    def test_nonretryable_sheet_error_is_not_hidden(self):
        with self.assertRaises(FakeSheetError):
            google_sheets._call_sheets_with_retry(
                lambda: (_ for _ in ()).throw(FakeSheetError(403))
            )

    def test_ensure_worksheet_expands_grid_before_adding_headers(self):
        class FakeWorksheet:
            def __init__(self):
                self.col_count = 2
                self.added_columns = []
                self.updated = []

            def row_values(self, row_number):
                return ["EventID", "MissionID"]

            def add_cols(self, count):
                self.added_columns.append(count)
                self.col_count += count

            def update(self, **kwargs):
                self.updated.append(kwargs)

        class FakeWorkbook:
            def __init__(self, worksheet):
                self.existing = worksheet

            def worksheet(self, name):
                return self.existing

        worksheet = FakeWorksheet()
        result = google_sheets.ensure_worksheet(
            FakeWorkbook(worksheet),
            "Missions",
            ["EventID", "MissionID", "Title", "Transmission"],
        )

        self.assertIs(result, worksheet)
        self.assertEqual(worksheet.added_columns, [2])
        self.assertEqual(
            worksheet.updated[0]["range_name"],
            "C1:D1",
        )
        self.assertEqual(
            worksheet.updated[0]["values"],
            [["Title", "Transmission"]],
        )

    def test_participant_count_uses_event_scoped_runtime_query(self):
        runtime = FakeRuntime(
            players=[
                {"ParticipantID": "P-1"},
                {"ParticipantID": "P-2"},
            ]
        )
        database = self.make_database(runtime)

        with patch(
            "data.google_sheets.get_sheet_participant_count",
            return_value=41,
        ):
            count = database.get_participant_count("EVT-0001")

        self.assertEqual(count, 41)
        self.assertEqual(runtime.calls, ["EVT-0001"])
        self.assertEqual(
            database.get_participant_count_warning("EVT-0001"),
            "",
        )

    def test_last_known_participant_count_survives_503(self):
        database = self.make_database(FakeRuntime(can_publish=False))
        with google_sheets._PARTICIPANT_COUNT_LOCK:
            google_sheets._LAST_SUCCESSFUL_PARTICIPANT_COUNTS[
                "EVT-0001"
            ] = 41

        with patch(
            "data.google_sheets.get_sheet_participant_count",
            side_effect=FakeSheetError(503),
        ):
            count = database.get_participant_count("EVT-0001")

        self.assertEqual(count, 41)
        self.assertEqual(
            database.get_participant_count_warning("EVT-0001"),
            google_sheets.PARTICIPANT_COUNT_WARNING,
        )

    def test_runtime_count_remains_available_during_sheet_503(self):
        runtime = FakeRuntime(
            players=[
                {"ParticipantID": "P-1"},
                {"ParticipantID": "P-2"},
            ]
        )
        database = self.make_database(runtime)

        with patch(
            "data.google_sheets.get_sheet_participant_count",
            side_effect=FakeSheetError(503),
        ):
            count = database.get_participant_count("EVT-0002")

        self.assertEqual(count, 2)
        self.assertEqual(
            database.get_participant_count_warning("EVT-0002"),
            "",
        )

    def test_sheet_records_fall_back_to_last_successful_read(self):
        class FakeWorksheet:
            def __init__(self):
                self.error = None

            def get_all_records(self):
                if self.error:
                    raise self.error
                return [{"EventID": "EVT-0001"}]

        worksheet = FakeWorksheet()
        with patch(
            "data.google_sheets.get_worksheets",
            return_value={"Events": worksheet},
        ):
            first = google_sheets.get_sheet_records("Events")
            google_sheets.get_sheet_records.clear()
            worksheet.error = FakeSheetError(503)
            with patch("data.google_sheets.time.sleep"):
                fallback = google_sheets.get_sheet_records("Events")

        self.assertEqual(first, [{"EventID": "EVT-0001"}])
        self.assertEqual(fallback, first)


if __name__ == "__main__":
    unittest.main()
