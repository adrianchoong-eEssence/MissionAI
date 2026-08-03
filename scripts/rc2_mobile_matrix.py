#!/usr/bin/env python3
"""Create the exact 52-cell physical mobile certification evidence sheet."""

import argparse
import csv
from pathlib import Path


BROWSERS = (
    "iOS Safari",
    "iOS Chrome",
    "Android Chrome",
    "Android Samsung Internet",
)
SCENARIOS = (
    "Fresh join", "Slow join", "Repeated Join tap", "Refresh",
    "Background 30 seconds", "Background 5 minutes", "Screen lock/unlock",
    "Browser close/reopen", "Network lost/restored", "Same-name re-login",
    "Leader reconnect", "Member reconnect",
    "Two concurrent requests for same participant",
)
FIELDS = (
    "Cell", "Browser", "Scenario", "Device", "OSVersion", "BrowserVersion",
    "EventID", "TimestampUTC", "ParticipantIDBefore", "ParticipantIDAfter",
    "TeamIDBefore", "TeamIDAfter", "CountryBefore", "CountryAfter",
    "FlagBefore", "FlagAfter", "LeaderBefore", "LeaderAfter",
    "ParticipantRowsBefore", "ParticipantRowsAfter", "CreditsBefore",
    "CreditsAfter", "RequestID", "HTTPStatus", "LatencyMs", "Result", "Evidence",
)


def rows():
    return [
        {"Cell": index, "Browser": browser, "Scenario": scenario}
        for index, (browser, scenario) in enumerate(
            ((browser, scenario) for browser in BROWSERS for scenario in SCENARIOS),
            start=1,
        )
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows())
    print(f"Created {len(rows())} certification cells at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
