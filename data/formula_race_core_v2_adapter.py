"""Core v2 Formula R.A.C.E. runtime adapter for staging client paths.

This adapter intentionally exposes the legacy runtime method surface consumed by
Formula R.A.C.E. screens while persisting and reading through Core v2 tables and
RPCs only.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID
from typing import Any
from urllib.parse import urlparse

from data.runtime_database import RuntimeDatabaseError

KNOWN_PROD_HOSTS = {
    "bqsbkdfzqyiodivhyxnq.supabase.co",
}

_FORBIDDEN_CORE_V2_PATHS = {
    "runtime_events",
    "runtime_teams",
    "runtime_participants",
    "runtime_submissions",
    "runtime_missions",
    "runtime_mission_submissions",
    "runtime_mission_evidence",
    "runtime_mission_status",
    "runtime_credit_transactions",
    "runtime_team_wallets",
    "runtime_marketplace_items",
    "runtime_marketplace_purchases",
    "formula_race_checkpoints",
    "formula_race_team_access",
    "formula_race_checkpoint_runtime",
    "formula_race_build_status",
    "formula_race_judging",
    "formula_race_results",
}

_FORBIDDEN_CORE_V2_RPC_PREFIXES = (
    "exos_formula_race_",
    "exos_set_formula_race_",
    "exos_formula_race_",
)


def _require_staging_runtime(runtime) -> None:
    env = str(os.getenv("EXOS_ENV", "")).strip().lower()
    if env != "staging":
        raise RuntimeError("EXOS_ENV must be set to 'staging' for Core v2 Formula R.A.C.E. path.")

    runtime_url = str(getattr(runtime, "url", "")).strip()
    if not runtime_url:
        raise RuntimeError("Supabase runtime URL is not configured.")
    host = (urlparse(runtime_url).hostname or "").lower()
    if host in KNOWN_PROD_HOSTS:
        raise RuntimeError(f"Refusing to target known production host: {host}")

    if not getattr(runtime, "is_configured", False):
        raise RuntimeError("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY missing.")

    if not getattr(runtime, "can_publish", False):
        raise RuntimeError("SUPABASE_SECRET_KEY is required for Formula R.A.C.E. Core v2 actions.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(row: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if row is None:
        return {} if fallback is None else dict(fallback)
    return dict(row)


def _resolve_event_candidates(event_id: str) -> list[str]:
    value = str(event_id or "").strip()
    if not value:
        return []
    return [value]


def _uuid_filter_value(value: str) -> str:
    return _normalise_uuid_value(value)


def _is_valid_uuid(value: str) -> bool:
    return bool(_normalise_uuid_value(value))


def _normalise_uuid_value(value: object) -> str:
    raw = str(value).strip() if value is not None else ""
    try:
        return str(UUID(raw))
    except (ValueError, AttributeError, TypeError):
        return ""


def _require_uuid(value: object, field: str) -> str:
    token = _normalise_uuid_value(value)
    if not token:
        raise RuntimeError(f"Invalid UUID supplied for {field}.")
    return token


def _optional_uuid_filter(
    field: str,
    value: object,
    *,
    required: bool,
    step: str,
    rpc_or_table: str,
) -> str | None:
    token = _normalise_uuid_value(value)
    if not token:
        if required:
            raise RuntimeError(f"Invalid UUID supplied for {field}.")
        _trace_uuid_context(f"{step}.omit", rpc_or_table, field, value)
        return None
    _trace_uuid_context(step, rpc_or_table, field, token)
    return f"eq.{token}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(default)


def _trace_uuid_context(step: str, rpc_or_table: str, field: str, value) -> None:
    if str(os.getenv("EXOS_ENV", "")).strip().lower() != "staging":
        return
    raw = "" if value is None else str(value).strip()
    is_none = value is None
    is_literal_none = raw.lower() == "none"
    is_valid_uuid = False
    if raw:
        try:
            UUID(raw)
            is_valid_uuid = True
        except Exception:
            is_valid_uuid = False
    print(
        f"CAPTAIN UUID TRACE | {step} | rpc/table: {rpc_or_table} | field: {field} | "
        f"is_none: {is_none} | is_literal_none: {is_literal_none} | is_valid_uuid: {is_valid_uuid}"
    )


def _trace_captain_login_raw_response(response: object) -> None:
    """Log staging-only response structure without exposing login data."""
    if str(os.getenv("EXOS_ENV", "")).strip().lower() != "staging":
        return

    is_dict = isinstance(response, dict)
    is_list = isinstance(response, list)
    top_level = response if is_dict else {}
    first_item = response[0] if is_list and response else None
    first_mapping = first_item if isinstance(first_item, dict) else {}
    field_source = top_level if is_dict else first_mapping

    print("CAPTAIN_LOGIN_RAW_TRACE", flush=True)
    print(f"response_python_type={type(response).__name__}", flush=True)
    print(f"is_dict={str(is_dict).lower()}", flush=True)
    print(f"is_list={str(is_list).lower()}", flush=True)
    print(f"list_length={len(response) if is_list else 0}", flush=True)
    print(f"top_level_keys={','.join(sorted(top_level.keys()))}", flush=True)
    if is_list and response:
        print(f"first_item_type={type(first_item).__name__}", flush=True)
        print(f"first_item_keys={','.join(sorted(first_mapping.keys()))}", flush=True)
    if is_dict:
        for key, value in top_level.items():
            print(f"key_name={key}", flush=True)
            print(f"value_python_type={type(value).__name__}", flush=True)

    for key in (
        "SessionToken",
        "session_token",
        "EventID",
        "event_id",
        "TeamID",
        "team_id",
        "Ambiguous",
        "RecoveryRequired",
    ):
        present = key in field_source
        value = field_source.get(key) if present else None
        print(f"KEY={key}", flush=True)
        print(f"PRESENT={str(present).lower()}", flush=True)
        print(f"TYPE={type(value).__name__}", flush=True)
        print(f"IS_NONE={str(value is None).lower()}", flush=True)
        if key in {"SessionToken", "session_token"}:
            raw = "" if value is None else str(value)
            print(f"STRING_LENGTH={len(raw)}", flush=True)
            print(f"VALID_UUID={str(_is_valid_uuid(raw)).lower()}", flush=True)

    for key in ("data", "result", "payload", "rows", "value"):
        if key in top_level:
            nested = top_level[key]
            nested_keys = nested.keys() if isinstance(nested, dict) else []
            print(f"NESTED_KEY={key}", flush=True)
            print(f"NESTED_TYPE={type(nested).__name__}", flush=True)
            print(f"NESTED_KEYS={','.join(sorted(nested_keys))}", flush=True)


def _in_filter(values: list[str]) -> str:
    sanitized = [str(value).replace('"', '\"').strip() for value in values if str(value).strip()]
    if not sanitized:
        return ""
    if len(sanitized) == 1:
        return f'eq.{sanitized[0]}'
    return "in.({})".format(
        ",".join(f'"{value}"' for value in sanitized)
    )


class FormulaRaceCoreV2StagingAdapter:
    """Compatibility adapter over Core v2 runtime tables/functions."""

    def __init__(self, runtime) -> None:
        _require_staging_runtime(runtime)
        self.runtime = runtime
        self.legacy_runtime_calls = 0
        self.google_sheets_runtime_calls = 0
        self.last_login_rpc_response: dict[str, Any] | None = None
        self.last_login_normalized_token: str = ""

    @staticmethod
    def _is_google_sheets_like(path: str) -> bool:
        return path.lower().startswith("sheets_") or path.lower().startswith("google_sheets")

    def _assert_no_legacy_or_sheet_calls(self) -> None:
        if self.legacy_runtime_calls:
            raise RuntimeError(f"LEGACY_RUNTIME_CALLS = {self.legacy_runtime_calls}")
        if self.google_sheets_runtime_calls:
            raise RuntimeError(f"GOOGLE_SHEETS_RUNTIME_CALLS = {self.google_sheets_runtime_calls}")

    def get_staging_call_counts(self) -> dict[str, int]:
        return {
            "LEGACY_RUNTIME_CALLS": int(self.legacy_runtime_calls),
            "GOOGLE_SHEETS_RUNTIME_CALLS": int(self.google_sheets_runtime_calls),
        }

    def __getattr__(self, name: str):
        return getattr(self.runtime, name)

    def _get(self, path: str, query: dict[str, Any] | None = None, admin: bool = True) -> list[dict[str, Any]]:
        if path in _FORBIDDEN_CORE_V2_PATHS:
            self.legacy_runtime_calls += 1
            raise RuntimeError(f"Blocked forbidden legacy path in Core v2 staging: {path}")
        if self._is_google_sheets_like(path):
            self.google_sheets_runtime_calls += 1
        result = self.runtime._request("GET", path, query=query, admin=admin)
        return result if isinstance(result, list) else ([] if result is None else list(result) if isinstance(result, tuple) else [])

    def _post(self, path: str, payload: dict[str, Any] | None = None, admin: bool = True) -> dict[str, Any] | list[dict[str, Any]] | None:
        if path in _FORBIDDEN_CORE_V2_PATHS:
            self.legacy_runtime_calls += 1
            raise RuntimeError(f"Blocked forbidden legacy path in Core v2 staging: {path}")
        if self._is_google_sheets_like(path):
            self.google_sheets_runtime_calls += 1
        payload = payload or {}
        return self.runtime._request("POST", path, payload=payload, admin=admin)

    def _patch(self, path: str, query: dict[str, Any], payload: dict[str, Any], admin: bool = True):
        if path in _FORBIDDEN_CORE_V2_PATHS:
            self.legacy_runtime_calls += 1
            raise RuntimeError(f"Blocked forbidden legacy path in Core v2 staging: {path}")
        if self._is_google_sheets_like(path):
            self.google_sheets_runtime_calls += 1
        return self.runtime._request("PATCH", path, payload=payload, query=query, admin=admin)

    def _delete(self, path: str, query: dict[str, Any], admin: bool = True):
        if path in _FORBIDDEN_CORE_V2_PATHS:
            self.legacy_runtime_calls += 1
            raise RuntimeError(f"Blocked forbidden legacy path in Core v2 staging: {path}")
        if self._is_google_sheets_like(path):
            self.google_sheets_runtime_calls += 1
        return self.runtime._request("DELETE", path, query=query, admin=admin)

    def _rpc(self, name: str, payload: dict[str, Any], admin: bool = True):
        if name.lower().startswith(_FORBIDDEN_CORE_V2_RPC_PREFIXES):
            self.legacy_runtime_calls += 1
            raise RuntimeError(f"Blocked forbidden legacy race rpc in Core v2 staging: {name}")
        return self.runtime._request("POST", f"rpc/{name}", payload=payload, admin=admin)

    # ---------------------------
    # Compatibility reads (Legacy UI-facing methods)
    # ---------------------------
    def get_event_by_join_code(self, join_code: str) -> dict[str, Any]:
        rows = self._get(
            "events_v2",
            {
                "join_code": f"eq.{str(join_code).strip().upper()}",
                "select": "event_id,event_name,join_code,lifecycle_status",
                "limit": "1",
            },
        )
        row = rows[0] if rows else {}
        return {
            "EventID": str(row.get("event_id", "")),
            "EventName": str(row.get("event_name", "")),
            "JoinCode": str(row.get("join_code", "")),
            "Status": str(row.get("lifecycle_status", "READY")),
        }

    def get_runtime_event(self, event_id: str) -> dict[str, Any]:
        event_row = self._lookup_event(event_id)
        return {
            "EventID": str(event_row.get("event_id", "")),
            "EventName": str(event_row.get("event_name", "")),
            "JoinCode": str(event_row.get("join_code", "")),
            "Status": str(event_row.get("lifecycle_status", "READY")),
        }

    def _lookup_event(self, event_id: str) -> dict[str, Any]:
        candidates = _resolve_event_candidates(event_id)
        if not candidates:
            return {}

        for key in candidates:
            rows = self._get(
                "events_v2",
                {
                    "event_id": f"eq.{str(key).strip()}",
                    "select": "event_id,event_name,join_code,lifecycle_status",
                    "limit": "1",
                },
            )
            if rows:
                return rows[0]

        for key in candidates:
            rows = self._get(
                "events_v2",
                {
                    "join_code": f"eq.{str(key).strip().upper()}",
                    "select": "event_id,event_name,join_code,lifecycle_status",
                    "limit": "1",
                },
            )
            if rows:
                return rows[0]

        return {}

    def debug_get_runtime_teams(self, event_id: str) -> dict[str, Any]:
        row = self._get(
            "events_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "event_id,event_name,join_code,lifecycle_status",
                "limit": "1",
            },
        )
        resolved_event = row[0] if row else self._lookup_event(event_id)
        resolved_event_id = str(resolved_event.get("event_id", "")).strip() if resolved_event else ""
        primary_query = {
            "event_id": f"eq.{resolved_event_id}",
            "is_active": "eq.true",
            "select": "team_id,team_name,country,team_flag,is_active",
            "order": "team_id.asc",
        }
        primary_rows = self._get("teams_v2", primary_query) if resolved_event_id else []
        fallback_rows = []
        if not primary_rows and resolved_event_id:
            fallback_query = {
                "event_id": f"eq.{resolved_event_id}",
                "select": "team_id,team_name,country,team_flag,is_active",
                "order": "team_id.asc",
            }
            fallback_rows = self._get("teams_v2", fallback_query)
        rows = primary_rows if primary_rows else fallback_rows
        normalized_count = len(rows)
        return {
            "requested": str(event_id).strip(),
            "resolved_event_id": resolved_event_id,
            "event_found": bool(resolved_event_id),
            "query": primary_query if primary_rows else {
                "event_id": f"eq.{resolved_event_id}",
                "is_active": "eq.true",
                "select": "team_id,team_name,country,team_flag,is_active",
                "order": "team_id.asc",
            },
            "raw_count": len(primary_rows if primary_rows else fallback_rows),
            "fallback_used": bool(fallback_rows) and not primary_rows,
            "rows": rows,
        }

    def get_runtime_teams(self, event_id: str) -> list[dict[str, Any]]:
        debug = self.debug_get_runtime_teams(event_id)
        rows = debug.get("rows", [])
        return [
            {
                "TeamID": str(row.get("team_id", "")),
                "TeamName": str(row.get("team_name", "")),
                "Country": str(row.get("country", "")),
                "TeamFlag": str(row.get("team_flag", "")),
                "IsActive": bool(row.get("is_active", True)),
            }
            for row in rows
        ]

    def get_canonical_submissions(self, event_id: str) -> list[dict[str, Any]]:
        rows = self._get(
            "submissions_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "submission_id,event_id,team_id,participant_id,activity_id,submission_status,submission_payload,reviewed_at,reviewed_by,score,submission_key,submitted_at,created_at",
                "order": "submitted_at.desc",
            },
        )
        submission_ids = [str(row.get("submission_id", "")) for row in rows if row.get("submission_id")]
        evidence_rows = self._get(
            "submission_evidence_v2",
            {
                "submission_id": _in_filter(submission_ids),
                "select": "submission_id,evidence_type,evidence_uri,evidence_payload,captured_by,captured_at",
                "order": "captured_at.desc",
            },
        ) if submission_ids else []
        evidence_by_submission = {
            str(row.get("submission_id", "")): row
            for row in evidence_rows
            if str(row.get("submission_id", ""))
        }
        return [
            {
                "SubmissionID": str(row.get("submission_id", "")),
                "EventID": str(row.get("event_id", "")),
                "TeamID": str(row.get("team_id", "")),
                "MissionID": str(row.get("activity_id", "")),
                "Status": str(row.get("submission_status", "PENDING")),
                "Judge": str(row.get("reviewed_by", "")),
                "Score": row.get("score", ""),
                "SubmissionPayload": row.get("submission_payload", {}),
                "StorageReference": str(
                    (row.get("submission_payload") or {}).get("storage_reference", "")
                    or evidence_by_submission.get(str(row.get("submission_id", "")), {}).get("evidence_uri", "")
                ),
                "EvidenceType": str(
                    evidence_by_submission.get(str(row.get("submission_id", "")), {}).get("evidence_type", "NONE")
                ),
                "EvidenceURI": str(
                    evidence_by_submission.get(str(row.get("submission_id", "")), {}).get("evidence_uri", "")
                ),
                "SubmittedAt": row.get("submitted_at") or row.get("created_at"),
            }
            for row in rows
        ]

    def get_programme_hierarchy(self, event_id: str) -> list[dict[str, Any]]:
        programmes = self._get("programmes_v2", {"event_id": f"eq.{str(event_id).strip()}", "select": "programme_id"})
        programme_ids = [str(row.get("programme_id")) for row in programmes if row.get("programme_id")]
        if not programme_ids:
            return []

        modules = self._get("modules_v2", {"programme_id": _in_filter(programme_ids), "select": "module_id"})
        module_ids = [str(row.get("module_id")) for row in modules if row.get("module_id")]
        if not module_ids:
            return []

        rows = self._get(
            "activities_v2",
            {
                "programme_id": _in_filter(programme_ids),
                "module_id": _in_filter(module_ids),
                "select": "activity_id,activity_name,module_id,activity_order,activity_type",
                "order": "module_id.asc,activity_order.asc",
            },
        )
        return [
            {
                "ActivityID": str(row.get("activity_id", "")),
                "ActivityName": str(row.get("activity_name", "")),
                "ModuleID": str(row.get("module_id", "")),
                "ActivityType": str(row.get("activity_type", "")),
                "ActivityOrder": row.get("activity_order"),
            }
            for row in rows
        ]

    def _get_checkpoint_activities(self, event_id: str) -> list[dict[str, Any]]:
        programmes = self._get("programmes_v2", {"event_id": f"eq.{str(event_id).strip()}", "select": "programme_id"})
        programme_ids = [str(row.get("programme_id")) for row in programmes]
        if not programme_ids:
            return []
        modules = self._get("modules_v2", {"programme_id": _in_filter(programme_ids), "select": "module_id"})
        module_ids = [str(row.get("module_id")) for row in modules]
        if not module_ids:
            return []

        rows = self._get(
            "activities_v2",
            {
                "programme_id": _in_filter(programme_ids),
                "module_id": _in_filter(module_ids),
                "activity_type": "eq.CHECKPOINT",
                "select": "activity_id,activity_name,module_id,activity_payload,activity_order",
                "order": "activity_order.asc",
            },
        )
        return rows

    def get_formula_race_checkpoints(self, event_id: str) -> dict[str, Any]:
        checkpoints = []
        activities = self._get_checkpoint_activities(event_id)
        module_id = str((activities[0] or {}).get("module_id", "")) if activities else f"{event_id}-RACE-CHECKPOINTS"

        for row in activities:
            payload = row.get("activity_payload")
            if not isinstance(payload, dict):
                payload = {}
            checkpoints.append(
                {
                    "CheckpointID": str(row.get("activity_id", "")),
                    "ActivityID": str(row.get("activity_id", "")),
                    "Name": str(row.get("activity_name", "")),
                    "Credits": payload.get("credits", 0),
                    "ProofType": str(payload.get("proof_type", payload.get("proofType", "Photo"))),
                    "Instructions": str(payload.get("instructions", "")),
                    "Status": "AVAILABLE",
                }
            )

        return {"Checkpoints": checkpoints, "Status": "READY", "ModuleID": module_id}

    def formula_race_team_status(self, event_id: str) -> list[dict[str, Any]]:
        sessions = self._get(
            "team_access_sessions_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "is_active": "eq.true",
                "select": "team_id,device_id,last_seen_at,updated_at",
            },
        )
        return [
            {"TeamID": str(row.get("team_id", "")), "Connected": True, "LastSeenAt": row.get("updated_at", row.get("last_seen_at"))}
            for row in sessions
        ]

    def get_formula_race_state(self, event_id: str) -> dict[str, Any]:
        checkpoints = self.get_formula_race_checkpoints(event_id)
        build_rows = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "team_id,activity_id,build_status,progress_pct",
            },
        )
        judging_rows = self._get(
            "judging_scores_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "team_id,judge_name,score_dimension,score_value,decision,rationale,recorded_at",
                "order": "recorded_at.asc",
            },
        )
        results_rows = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "team_id,race_result_id,result_payload,locked,ranking_position,checkpoint,updated_at",
                "order": "ranking_position.asc,team_id.asc",
            },
        )
        return {
            "Checkpoints": checkpoints,
            "BuildStatus": build_rows,
            "Judging": judging_rows,
            "RaceResults": [
                {
                    "team_id": str(row.get("team_id", "")),
                    "position": row.get("ranking_position"),
                    "checkpoint": row.get("checkpoint"),
                    "locked": bool(row.get("locked", False)),
                    **(_as_dict(row.get("result_payload"), {})),
                }
                for row in results_rows
            ],
            "Teams": self.get_runtime_teams(event_id),
        }

    def get_canonical_transaction_report(self, event_id: str) -> dict[str, Any]:
        tx_rows = self._get(
            "credit_transactions_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "credit_transaction_id,event_id,team_id,participant_id,transaction_type,amount,reason,idempotency_key,created_at",
                "order": "created_at.asc",
            },
        )
        scores = self._get("score_transactions_v2", {"event_id": f"eq.{str(event_id).strip()}", "select": "team_id,score_delta,reason,created_at"})

        balances: dict[str, float] = defaultdict(float)
        credits_earned: dict[str, float] = defaultdict(float)
        credits_spent: dict[str, float] = defaultdict(float)
        for row in tx_rows:
            team_id = str(row.get("team_id", ""))
            try:
                amount = float(row.get("amount", 0) or 0)
                balances[team_id] += amount
                if amount > 0:
                    credits_earned[team_id] += amount
                elif amount < 0:
                    credits_spent[team_id] += -amount
            except (TypeError, ValueError):
                pass

        championship_scores: dict[str, float] = defaultdict(float)
        for row in scores:
            team_id = str(row.get("team_id", ""))
            try:
                championship_scores[team_id] += float(row.get("score_delta", 0) or 0)
            except (TypeError, ValueError):
                pass
        team_ids = {str(row.get("TeamID", "")) for row in self.get_runtime_teams(event_id)}
        team_ids = sorted((team_ids | set(balances) | set(championship_scores)) - {""})
        ranked_team_ids = sorted(team_ids, key=lambda team_id: (-championship_scores[team_id], team_id))
        live_ranks = {team_id: index for index, team_id in enumerate(ranked_team_ids, start=1)}

        leaderboard = [
            {
                "TeamID": team_id,
                "teamId": team_id,
                "ChampionshipScore": championship_scores[team_id],
                "Score": championship_scores[team_id],
                "CreditsEarned": credits_earned[team_id],
                "CreditsSpent": credits_spent[team_id],
                "WalletBalance": balances[team_id],
                "AvailableBalance": balances[team_id],
                "Rank": live_ranks[team_id],
            }
            for team_id in ranked_team_ids
        ]

        return {
            "AwardTransactions": [
                {
                    "award_transaction_id": row.get("credit_transaction_id"),
                    "award_type": row.get("transaction_type"),
                    "team_id": row.get("team_id"),
                    "TeamID": row.get("team_id"),
                    "amount": row.get("amount", 0),
                    "Amount": row.get("amount", 0),
                    "reason": row.get("reason", ""),
                    "source": row.get("transaction_type", ""),
                    "created_at": row.get("created_at", ""),
                }
                for row in tx_rows
            ],
            "TeamBalances": [
                {
                    "team_id": team_id,
                    "teamId": team_id,
                    "credits_earned": credits_earned[team_id],
                    "credits_spent": credits_spent[team_id],
                    "available_balance": amount,
                }
                for team_id, amount in sorted(balances.items(), key=lambda item: item[0])
            ],
            "Leaderboard": leaderboard,
            "ScoreTransactions": scores,
        }

    # ---------------------------
    # Captain identity / session
    # ---------------------------
    def set_team_pin(self, event_id: str, team_id: str, pin: str, actor: str = "facilitator") -> dict[str, Any]:
        return (
            self._rpc(
                "exos_v2_set_team_access_pin",
                {
                    "p_event_id": str(event_id).strip(),
                    "p_team_id": str(team_id).strip(),
                    "p_pin": str(pin).strip(),
                    "p_actor": str(actor).strip(),
                },
            )
            or {}
        )

    def formula_race_captain_login(self, join_code: str, team_id: str, pin: str, device_id: str) -> dict[str, Any]:
        _trace_uuid_context("formula_race_captain_login.request", "rpc/exos_v2_team_access_login", "p_join_code", join_code)
        _trace_uuid_context("formula_race_captain_login.request", "rpc/exos_v2_team_access_login", "p_team_id", team_id)
        _trace_uuid_context("formula_race_captain_login.request", "rpc/exos_v2_team_access_login", "p_device_id", device_id)
        raw_response = self._rpc(
            "exos_v2_team_access_login",
            {
                "p_join_code": str(join_code).strip().upper(),
                "p_team_id": str(team_id).strip(),
                "p_pin": str(pin).strip(),
                "p_device_id": str(device_id).strip(),
            },
        )
        _trace_captain_login_raw_response(raw_response)
        row = raw_response or {}
        self.last_login_rpc_response = dict(row) if isinstance(row, dict) else {}
        event_id = str(row.get("EventID", row.get("event_id", ""))).strip()
        team_id = str(row.get("TeamID", row.get("team_id", ""))).strip()
        ambiguous = bool(row.get("Ambiguous", False))
        recovery_required = bool(row.get("RecoveryRequired", False))
        if not event_id or not team_id:
            raise RuntimeError("Login response missing EventID or TeamID.")
        if recovery_required:
            self.last_login_normalized_token = ""
            return {
                "SessionToken": "",
                "EventID": event_id,
                "TeamID": team_id,
                "TeamName": str(row.get("TeamName", row.get("team_name", ""))),
                "RecoveryRequired": True,
                "Ambiguous": ambiguous,
            }
        if ambiguous:
            raise RuntimeError("Login response indicates unresolved captain identity state.")
        raw_token = row.get("SessionToken", row.get("session_token", ""))
        _trace_uuid_context("formula_race_captain_login.response", "rpc/exos_v2_team_access_login", "SessionToken", raw_token)
        token = _normalise_uuid_value(raw_token)
        self.last_login_normalized_token = token
        if not token:
            raise RuntimeError("Invalid captain session token returned by login service.")
        return {
            "SessionToken": token,
            "EventID": event_id,
            "TeamID": team_id,
            "TeamName": str(row.get("TeamName", row.get("team_name", ""))),
            "RecoveryRequired": recovery_required,
            "Ambiguous": ambiguous,
        }

    def formula_race_captain_recover(
        self, join_code: str, team_id: str, pin: str, device_id: str
    ) -> dict[str, Any]:
        row = self._rpc(
            "exos_v2_recover_team_access",
            {
                "p_join_code": str(join_code).strip().upper(),
                "p_team_id": str(team_id).strip(),
                "p_pin": str(pin).strip(),
                "p_device_id": str(device_id).strip(),
            },
        ) or {}
        event_id = str(row.get("EventID", row.get("event_id", ""))).strip()
        recovered_team_id = str(row.get("TeamID", row.get("team_id", ""))).strip()
        token = _normalise_uuid_value(row.get("SessionToken", row.get("session_token", "")))
        if not event_id or not recovered_team_id or not token:
            raise RuntimeError("Team access recovery could not establish a new session.")
        return {
            "SessionToken": token,
            "EventID": event_id,
            "TeamID": recovered_team_id,
            "TeamName": str(row.get("TeamName", row.get("team_name", ""))),
            "RecoveryRequired": False,
            "Ambiguous": False,
        }

    def restore_formula_race_captain(self, session_token: str, device_id: str) -> dict[str, Any]:
        _trace_uuid_context("restore_formula_race_captain.request", "rpc/exos_v2_restore_team_access", "p_session_token", session_token)
        _trace_uuid_context("restore_formula_race_captain.request", "rpc/exos_v2_restore_team_access", "p_device_id", device_id)
        token = _require_uuid(session_token, "p_session_token")
        row = self._rpc(
            "exos_v2_restore_team_access",
            {
                "p_session_token": token,
                "p_device_id": str(device_id).strip(),
            },
        ) or {}
        _trace_uuid_context("restore_formula_race_captain.response", "rpc/exos_v2_restore_team_access", "SessionToken", row.get("SessionToken"))
        response_token = _normalise_uuid_value(row.get("SessionToken", token))
        if not response_token:
            raise RuntimeError("Invalid captain session token returned by restore service.")
        return {
            "SessionToken": response_token,
            "EventID": str(row.get("EventID", row.get("event_id", ""))),
            "TeamID": str(row.get("TeamID", row.get("team_id", ""))),
            "TeamName": str(row.get("TeamName", row.get("team_name", ""))),
            "RecoveryRequired": bool(row.get("RecoveryRequired", False)),
            "Ambiguous": bool(row.get("Ambiguous", False)),
        }

    def _checkpoint_payload(self, activity_row: dict[str, Any], runtime_state: dict[str, Any] | None = None) -> dict[str, Any]:
        activity_id = str(activity_row.get("activity_id", ""))
        payload = activity_row.get("activity_payload")
        if not isinstance(payload, dict):
            payload = {}

        status = "AVAILABLE"
        state_payload = runtime_state.get("state_payload") if runtime_state else {}
        if isinstance(state_payload, dict):
            mapped = str(state_payload.get("status", "")).upper()
            if mapped:
                if mapped in {"PENDING", "SUBMITTED"}:
                    status = "SUBMITTED"
                elif mapped in {"APPROVED", "APPROVE"}:
                    status = "APPROVED"
                elif mapped in {"REVIEW", "UNDER_REVIEW"}:
                    status = "UNDER REVIEW"
                elif mapped in {"LIVE", "LAUNCH"}:
                    status = "ACTIVE"
                else:
                    status = mapped

        return {
            "ActivityID": activity_id,
            "Name": str(activity_row.get("activity_name", "")),
            "Credits": payload.get("credits", 0),
            "Instructions": str(payload.get("instructions", "")),
            "ProofType": str(payload.get("proof_type", payload.get("proofType", "Photo"))),
            "Status": status,
        }

    def formula_race_captain_workspace(self, session_token: str, device_id: str) -> dict[str, Any]:
        token = _require_uuid(session_token, "session_token")
        _trace_uuid_context("formula_race_captain_workspace.request", "team_access_sessions_v2", "session_token", token)
        _trace_uuid_context("formula_race_captain_workspace.request", "team_access_sessions_v2", "device_id", device_id)
        rows = self._get(
            "team_access_sessions_v2",
            {
                "session_token": f"eq.{token}",
                "device_id": f"eq.{str(device_id).strip()}",
                "select": "team_access_session_id,event_id,team_id,is_active,last_seen_at,updated_at",
                "limit": "1",
            },
        )
        if not rows:
            raise RuntimeError("Invalid captain session.")

        row = rows[0]
        _trace_uuid_context("formula_race_captain_workspace.session_row", "team_access_sessions_v2", "team_access_session_id", row.get("team_access_session_id"))
        _trace_uuid_context(
            "formula_race_captain_workspace.session_row",
            "team_access_sessions_v2",
            "team_access_credential_id",
            row.get("team_access_credential_id"),
        )
        if not bool(row.get("is_active", False)):
            raise RuntimeError("Captain session is inactive.")

        event_id = str(row.get("event_id", ""))
        team_id = str(row.get("team_id", ""))

        checkpoint_state = []
        for activity in self._get_checkpoint_activities(event_id):
            runtime_rows = self._get(
                "activity_runtime_v2",
                {
                    "event_id": f"eq.{event_id}",
                    "team_id": f"eq.{team_id}",
                    "activity_id": f"eq.{activity.get('activity_id')}",
                    "order": "updated_at.desc",
                    "limit": "1",
                },
            )
            runtime_id = runtime_rows[0].get("runtime_id") if runtime_rows else None
            _trace_uuid_context("formula_race_captain_workspace.runtime_rows", "activity_runtime_v2", "runtime_id", runtime_id)
            checkpoint_state.append(self._checkpoint_payload(activity, runtime_rows[0] if runtime_rows else None))

        session_status = "LIVE" if any(row.get("Status") in {"LIVE", "OPEN", "ACTIVE"} for row in checkpoint_state) else "READY"

        report = self.get_canonical_transaction_report(event_id)
        standing = next((entry for entry in report.get("Leaderboard", []) if str(entry.get("TeamID", "")) == team_id), {})
        team = next((entry for entry in self.get_runtime_teams(event_id) if str(entry.get("TeamID", "")) == team_id), {})
        wallet = self._wallet_payload(event_id, team_id)
        return {
            "EventID": event_id,
            "TeamID": team_id,
            "TeamIdentity": str(team.get("TeamIdentity", team.get("TeamName", team_id))),
            "ChampionshipScore": standing.get("ChampionshipScore", 0),
            "ChampionshipRank": standing.get("Rank", 0),
            "CreditsEarned": wallet.get("CreditsEarned", 0),
            "CreditsSpent": wallet.get("CreditsSpent", 0),
            "Checkpoints": checkpoint_state,
            "CurrentCheckpoint": next((checkpoint for checkpoint in checkpoint_state if str(checkpoint.get("Status", "")).upper() not in {"APPROVED", "SUBMITTED", "UNDER REVIEW"}), checkpoint_state[0] if checkpoint_state else {}),
            "CheckpointRuntime": {"status": session_status},
            "Wallet": wallet,
            "BuildStatus": self._build_status_payload(event_id, team_id),
            "Marketplace": self._marketplace_payload(event_id, team_id).get("items", []),
            "Purchases": self._marketplace_payload(event_id, team_id).get("purchases", []),
            "Session": row,
        }

    def formula_race_captain_logout(self, session_token: str, device_id: str) -> dict[str, Any]:
        token = _require_uuid(session_token, "session_token")
        _trace_uuid_context("formula_race_captain_logout.request", "team_access_sessions_v2", "session_token", token)
        _trace_uuid_context("formula_race_captain_logout.request", "team_access_sessions_v2", "device_id", device_id)
        rows = self._get(
            "team_access_sessions_v2",
            {
                "session_token": f"eq.{token}",
                "device_id": f"eq.{str(device_id).strip()}",
                "select": "team_access_session_id",
                "limit": "1",
            },
        )
        if not rows:
            return {"ok": True}
        session_id = rows[0].get("team_access_session_id")
        _trace_uuid_context("formula_race_captain_logout.session", "team_access_sessions_v2", "team_access_session_id", session_id)
        if session_id:
            self._patch(
                "team_access_sessions_v2",
                {"team_access_session_id": f"eq.{session_id}"},
                {"is_active": False, "updated_at": _now_iso()},
            )
        return {"ok": True}

    # ---------------------------
    # Control-plane writes from Control Runtime
    # ---------------------------
    def set_formula_race_checkpoint_runtime(self, event_id: str, module_id: str, action: str, actor: str):
        action = str(action).strip().upper()
        _trace_uuid_context("set_formula_race_checkpoint_runtime.request", "activities_v2", "event_id", event_id)
        _trace_uuid_context("set_formula_race_checkpoint_runtime.request", "activities_v2", "module_id", module_id)
        now = _now_iso()
        now_iso = now
        team_rows = self.get_runtime_teams(event_id)
        activity_rows = self._get("activities_v2", {"module_id": f"eq.{str(module_id).strip()}", "select": "activity_id", "limit": "100"})

        for team in team_rows:
            team_id = str(team.get("TeamID", ""))
            captain_actor = self._rpc(
                "exos_v2_formula_race_captain_actor",
                {"p_event_id": str(event_id), "p_team_id": team_id},
            ) or {}
            participant_id = _require_uuid(captain_actor.get("ParticipantID", captain_actor.get("participant_id", captain_actor)), "race captain technical actor")
            _trace_uuid_context("set_formula_race_checkpoint_runtime.participant", "participants_v2", "participant_id", participant_id)

            for row in activity_rows:
                activity_id = str(row.get("activity_id"))
                _trace_uuid_context("set_formula_race_checkpoint_runtime.activity", "activities_v2", "activity_id", activity_id)
                existing = self._get(
                    "activity_runtime_v2",
                    {
                        "event_id": f"eq.{str(event_id)}",
                        "participant_id": f"eq.{participant_id}",
                        "activity_id": f"eq.{activity_id}",
                        "select": "runtime_id",
                        "limit": "1",
                    },
                )
                payload = {
                    "event_id": str(event_id),
                    "team_id": team_id,
                    "participant_id": participant_id,
                    "activity_id": activity_id,
                    "state_payload": {"status": action, "actor": str(actor), "updated_at": now_iso},
                    "is_completed": action == "CLOSE",
                    "completion_ratio": 100 if action == "CLOSE" else 0,
                    "activity_started_at": now_iso if action == "LAUNCH" else None,
                    "activity_ended_at": now_iso if action == "CLOSE" else None,
                    "updated_at": now_iso,
                }
                if existing:
                    _trace_uuid_context("set_formula_race_checkpoint_runtime.patch", "activity_runtime_v2", "runtime_id", existing[0].get("runtime_id"))
                    self._patch("activity_runtime_v2", {"runtime_id": f"eq.{existing[0].get('runtime_id')}"}, payload)
                else:
                    self._post("activity_runtime_v2", payload)

        return {"state": action}

    def set_formula_race_marketplace_runtime(self, event_id: str, action: str, actor: str):
        action = str(action).strip().upper()
        if action not in {"OPEN", "PAUSE", "CLOSE"}:
            raise RuntimeError("Marketplace action must be OPEN, PAUSE, or CLOSE.")
        if not str(actor).strip():
            raise RuntimeError("Facilitator identity is required to change the marketplace state.")
        items = self._get(
            "marketplace_items_v2",
            {"event_id": f"eq.{str(event_id).strip()}", "select": "item_id"},
        )
        if not items:
            raise RuntimeError("Marketplace catalogue is not configured for this event.")
        active = action == "OPEN"
        self._patch(
            "marketplace_items_v2",
            {"event_id": f"eq.{str(event_id).strip()}"},
            {"is_active": active},
        )
        persisted = self._get(
            "marketplace_items_v2",
            {"event_id": f"eq.{str(event_id).strip()}", "select": "item_id,is_active"},
        )
        active_count = sum(bool(item.get("is_active", False)) for item in persisted)
        if len(persisted) != len(items) or (active and active_count != len(items)) or (not active and active_count):
            raise RuntimeError("Marketplace activation state did not persist. Refresh Race Control and retry.")
        return {"state": action, "active": active, "item_count": len(persisted), "active_item_count": active_count, "actor": str(actor).strip()}

    def set_formula_race_build_status(self, event_id: str, team_id: str, status: str, checklist: dict[str, Any], reason: str, actor: str):
        _trace_uuid_context("set_formula_race_build_status.request", "build_status_v2", "event_id", event_id)
        _trace_uuid_context("set_formula_race_build_status.request", "build_status_v2", "team_id", team_id)
        activities = self._get_checkpoint_activities(event_id)
        activity_id = str(activities[0].get("activity_id")) if activities else f"{event_id}-CHECKPOINT"
        _trace_uuid_context("set_formula_race_build_status.request", "build_status_v2", "activity_id", activity_id)
        build_status = str(status or "NOT_STARTED").strip().upper().replace(" ", "_")
        payload = {
            "event_id": str(event_id),
            "team_id": str(team_id),
            "activity_id": activity_id,
            "build_status": build_status,
            "progress_pct": 100 if build_status in {"COMPLETED", "READY_TO_RACE"} else 0,
            "build_payload": {"checklist": checklist or {}, "actor": str(actor), "reason": str(reason)},
            "started_at": _now_iso(),
            "last_updated": _now_iso(),
        }
        if build_status == "COMPLETED":
            payload["completed_at"] = _now_iso()
        existing = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{str(event_id)}",
                "team_id": f"eq.{str(team_id)}",
                "activity_id": f"eq.{activity_id}",
                "select": "event_id",
                "limit": "1",
            },
        )
        if existing:
            return self._patch("build_status_v2", {"event_id": f"eq.{str(event_id)}", "team_id": f"eq.{str(team_id)}", "activity_id": f"eq.{activity_id}"}, payload) or {}
        return self._post("build_status_v2", payload) or {}

    def save_formula_race_judging(self, event_id: str, team_id: str, scores: dict[str, Any], reason: str, actor: str):
        activities = self._get_checkpoint_activities(event_id)
        activity_id = str(activities[0].get("activity_id")) if activities else f"{event_id}-CHECKPOINT"
        rows = []
        for dimension, score in (scores or {}).items():
            existing = self._get(
                "judging_scores_v2",
                {
                    "event_id": f"eq.{str(event_id)}",
                    "team_id": f"eq.{str(team_id)}",
                    "activity_id": f"eq.{activity_id}",
                    "judge_name": f"eq.{str(actor).strip()}",
                    "score_dimension": f"eq.{str(dimension).strip()}",
                    "select": "judging_score_id",
                    "limit": "1",
                },
            )
            payload = {
                "event_id": str(event_id),
                "team_id": str(team_id),
                "activity_id": activity_id,
                "judge_name": str(actor).strip(),
                "score_dimension": str(dimension).strip(),
                "score_value": float(score or 0),
                "decision": "SUBMITTED",
                "rationale": str(reason or "").strip(),
                "recorded_at": _now_iso(),
            }
            if existing:
                rows.append(self._patch("judging_scores_v2", {"judging_score_id": f"eq.{existing[0].get('judging_score_id')}"}, payload) or {})
            else:
                rows.append(self._post("judging_scores_v2", payload) or {})
        return rows

    def save_formula_race_result(self, event_id: str, team_id: str, time_ms: int, penalty_ms: int, bonus: float, verified: bool, reason: str, actor: str):
        activities = self._get_checkpoint_activities(event_id)
        activity_id = str(activities[0].get("activity_id")) if activities else f"{event_id}-FINAL"
        payload = {
            "event_id": str(event_id),
            "team_id": str(team_id),
            "activity_id": activity_id,
            "checkpoint": "Race Final",
            "result_payload": {
                "time_ms": int(time_ms),
                "penalty_ms": int(penalty_ms),
                "bonus": float(bonus),
                "verified": bool(verified),
                "reason": str(reason),
                "judge": str(actor),
            },
            "locked": False,
            "recorded_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        existing = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{str(event_id)}",
                "team_id": f"eq.{str(team_id)}",
                "activity_id": f"eq.{activity_id}",
                "checkpoint": "eq.Race Final",
                "select": "race_result_id,locked",
                "limit": "1",
            },
        )
        if existing and bool(existing[0].get("locked", False)):
            raise RuntimeError("Race result is locked and immutable until explicit unlock.")
        if existing:
            return self._patch("race_results_v2", {"race_result_id": f"eq.{existing[0].get('race_result_id')}"}, payload) or {}
        return self._post("race_results_v2", payload) or {}

    def get_race_build_status(self, event_id: str) -> list[dict[str, Any]]:
        return self._get("build_status_v2", {"event_id": f"eq.{str(event_id).strip()}", "select": "team_id,activity_id,event_id,build_status,progress_pct,build_payload,started_at,completed_at,last_updated"})

    def get_race_judging(self, event_id: str) -> list[dict[str, Any]]:
        return self._get(
            "judging_scores_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "judging_score_id,team_id,judge_name,score_dimension,score_value,decision,rationale,recorded_at",
                "order": "recorded_at.asc",
            },
        )

    def get_race_results(self, event_id: str) -> list[dict[str, Any]]:
        rows = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "team_id,event_id,activity_id,checkpoint,ranking_position,result_payload,locked,updated_at",
                "order": "ranking_position.asc,team_id.asc",
            },
        )
        out = []
        for row in rows:
            payload = row.get("result_payload")
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                {
                    "team_id": str(row.get("team_id", "")),
                    "time_ms": payload.get("time_ms", 0),
                    "penalty_ms": payload.get("penalty_ms", 0),
                    "bonus_credits": payload.get("bonus", 0),
                    "position": row.get("ranking_position"),
                    "locked": bool(row.get("locked", False)),
                    "checkpoint": str(row.get("checkpoint", "")),
                }
            )
        return out

    # Queue 2 authoritative R.A.C.E. mutation boundary. These definitions
    # intentionally supersede the compatibility implementations above.
    def formula_race_submit_checkpoint(self, session_token: str, device_id: str, activity_id: str, text_response: str = "", storage_reference: str = "", idempotency_key: str = "") -> dict[str, Any]:
        token = _require_uuid(session_token, "session_token")
        if not str(activity_id).strip():
            raise RuntimeError("Invalid activity id.")
        return self._rpc(
            "exos_v2_formula_race_submit_checkpoint",
            {
                "p_session_token": token,
                "p_device_id": str(device_id).strip(),
                "p_activity_id": str(activity_id).strip(),
                "p_text_response": str(text_response),
                "p_storage_reference": str(storage_reference),
                "p_idempotency_key": str(idempotency_key).strip(),
            },
        ) or {}

    def formula_race_purchase(self, session_token: str, device_id: str, item_id: str, quantity: int = 1, idempotency_key: str = "") -> dict[str, Any]:
        token = _require_uuid(session_token, "session_token")
        if not str(item_id).strip():
            raise RuntimeError("Invalid marketplace item id.")
        if not str(idempotency_key).strip():
            raise RuntimeError("A stable purchase idempotency key is required.")
        return self._rpc(
            "exos_v2_formula_race_purchase",
            {
                "p_session_token": token,
                "p_device_id": str(device_id).strip(),
                "p_item_id": str(item_id).strip(),
                "p_quantity": int(quantity or 0),
                "p_idempotency_key": str(idempotency_key).strip(),
            },
        ) or {}

    def formula_race_review_checkpoint(self, submission_id: str, decision: str, reviewer_id: str, notes: str = "", reason: str = "", idempotency_key: str = "") -> dict[str, Any]:
        return self._rpc(
            "exos_v2_formula_race_review_checkpoint",
            {
                "p_submission_id": _require_uuid(submission_id, "submission_id"),
                "p_decision": str(decision).strip().upper(),
                "p_reviewer": str(reviewer_id).strip(),
                "p_notes": str(notes),
                "p_reason": str(reason),
                "p_idempotency_key": str(idempotency_key).strip(),
            },
        ) or {}

    def lock_formula_race_results(self, event_id: str, actor: str, reason: str) -> dict[str, Any]:
        return self._rpc(
            "exos_v2_formula_race_lock_final_results",
            {"p_event_id": str(event_id), "p_actor": str(actor).strip(), "p_reason": str(reason).strip()},
        ) or {}

    # ---------------------------
    # Internal helpers
    # ---------------------------
    def _wallet_balance(self, event_id: str, team_id: str) -> int:
        rows = self._get(
            "credit_transactions_v2",
            {
                "event_id": f"eq.{str(event_id)}",
                "team_id": f"eq.{str(team_id)}",
                "select": "amount",
            },
        )
        balance = 0
        for row in rows:
            try:
                balance += int(row.get("amount", 0) or 0)
            except (TypeError, ValueError):
                pass
        return balance

    def _build_status_payload(self, event_id: str, team_id: str) -> dict[str, Any]:
        _trace_uuid_context("_build_status_payload.request", "build_status_v2", "event_id", event_id)
        _trace_uuid_context("_build_status_payload.request", "build_status_v2", "team_id", team_id)
        rows = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{str(event_id).strip()}",
                "team_id": f"eq.{str(team_id).strip()}",
                "select": "activity_id,build_status,progress_pct,build_payload,started_at,completed_at,last_updated",
                "order": "last_updated.desc",
            },
        )

        if not rows:
            return {
                "status": "NOT_STARTED",
                "Status": "NOT_STARTED",
                "Progress": 0,
                "ActivityID": "",
                "Activities": [],
                "ActivityStatus": [],
                "LastUpdated": "",
            }

        latest = rows[0]
        latest_status = str(latest.get("build_status", "NOT_STARTED")).strip().upper().replace(" ", "_")
        if not latest_status:
            latest_status = "NOT_STARTED"

        try:
            latest_progress = int(latest.get("progress_pct", 0) or 0)
        except (TypeError, ValueError):
            latest_progress = 0

        return {
            "status": latest_status,
            "Status": latest_status,
            "Progress": latest_progress,
            "ActivityID": str(latest.get("activity_id", "")),
            "Activities": [
                {
                    "ActivityID": str(row.get("activity_id", "")),
                    "Status": str(row.get("build_status", "NOT_STARTED")).strip().upper().replace(" ", "_"),
                    "Progress": _safe_int(row.get("progress_pct", 0)),
                    "StartedAt": row.get("started_at"),
                    "CompletedAt": row.get("completed_at"),
                    "LastUpdated": row.get("last_updated"),
                    "Payload": _as_dict(row.get("build_payload")),
                }
                for row in rows
            ],
            "ActivityStatus": [
                {
                    "ActivityID": str(row.get("activity_id", "")),
                    "Status": str(row.get("build_status", "NOT_STARTED")).strip().upper().replace(" ", "_"),
                    "Progress": _safe_int(row.get("progress_pct", 0)),
                }
                for row in rows
            ],
            "LastUpdated": latest.get("last_updated", ""),
            "StartedAt": latest.get("started_at"),
            "CompletedAt": latest.get("completed_at"),
        }

    def _wallet_payload(self, event_id: str, team_id: str) -> dict[str, Any]:
        rows = self._get(
            "credit_transactions_v2",
            {"event_id": f"eq.{str(event_id)}", "team_id": f"eq.{str(team_id)}", "select": "amount"},
        )
        earned = sum(_safe_int(row.get("amount", 0)) for row in rows if _safe_int(row.get("amount", 0)) > 0)
        spent = sum(-_safe_int(row.get("amount", 0)) for row in rows if _safe_int(row.get("amount", 0)) < 0)
        return {"CreditsEarned": earned, "CreditsSpent": spent, "Balance": earned - spent}

    def _marketplace_payload(self, event_id: str, team_id: str, active_only: bool = True) -> dict[str, Any]:
        item_query = {"event_id": f"eq.{str(event_id)}", "select": "item_id,item_name,unit_cost_credits,stock_limit,is_active"}
        if active_only:
            item_query["is_active"] = "eq.true"
        item_rows = self._get("marketplace_items_v2", item_query)
        purchase_query = {
            "marketplace_transactions_v2",
        }
        purchase_rows = self._get(
            "marketplace_transactions_v2",
            {
                "event_id": f"eq.{str(event_id)}",
                "team_id": f"eq.{str(team_id)}",
                "select": "marketplace_transaction_id,item_id,quantity,amount_paid,status,purchased_at,idempotency_key",
            },
        ) if str(team_id).strip() else self._get(
            "marketplace_transactions_v2",
            {
                "event_id": f"eq.{str(event_id)}",
                "select": "marketplace_transaction_id,team_id,item_id,quantity,amount_paid,status,purchased_at,idempotency_key",
            },
        )
        stock_rows = self._get(
            "marketplace_transactions_v2",
            {
                "event_id": f"eq.{str(event_id)}",
                "status": "eq.COMPLETED",
                "select": "item_id,quantity",
            },
        )
        reserved = {}
        for row in stock_rows:
            item_id = str(row.get("item_id", ""))
            reserved[item_id] = reserved.get(item_id, 0) + _safe_int(row.get("quantity", 0))
        stock_lookup = {str(row.get("item_id")): row for row in item_rows}
        items = [
            {
                "ItemID": item_id,
                "ItemName": str(row.get("item_name", "")),
                "CreditCost": row.get("unit_cost_credits", 0),
                "StockQuantity": (
                    None if row.get("stock_limit") is None
                    else max(_safe_int(row.get("stock_limit")) - reserved.get(item_id, 0), 0)
                ),
                "Active": bool(row.get("is_active", True)),
            }
            for item_id, row in stock_lookup.items()
        ]
        purchases = []
        for row in purchase_rows:
            row_item = stock_lookup.get(str(row.get("item_id", "")), {})
            purchases.append(
                {
                    "PurchaseID": row.get("marketplace_transaction_id"),
                    "ItemID": str(row.get("item_id", "")),
                    "ItemName": str(row_item.get("item_name", "")),
                    "Quantity": row.get("quantity", 0),
                    "Amount": row.get("amount_paid", 0),
                    "Status": row.get("status", ""),
                    "PurchasedAt": row.get("purchased_at", ""),
                    "IdempotencyKey": row.get("idempotency_key", ""),
                }
            )
        return {"items": items, "purchases": purchases, "state": "OPEN" if items else "CLOSED"}

    @staticmethod
    def staging_runtime_guard() -> bool:
        return True
