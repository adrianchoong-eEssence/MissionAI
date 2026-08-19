"""Client-promised Formula R.A.C.E. product shell."""
from __future__ import annotations

import os
import secrets
import uuid
from urllib.parse import urlparse
import pandas as pd
import streamlit as st

from data.formula_race_contracts import DemoFormulaRaceProvider, LiveFormulaRaceProvider, RaceSnapshot, Team, Transaction, Submission
from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from data.runtime_database import RuntimeDatabaseError, get_runtime_database
from data.control_runtime import ControlRuntime
from engines.formula_race import BUILD_STATUSES,JUDGING_CATEGORIES,final_standings
from engines.formula_race_configuration import (
    CAPTAIN_RESULT_METHODS,
    generate_balanced_routes,
    normalise_marketplace_item,
    normalise_station,
    validate_marketplace_items,
    validate_routes,
    validate_stations,
)
from engines.formula_race_championship import (
    COMPONENT_TYPES, TIE_BREAKS, normalise_championship_component,
    championship_component_points, normalise_championship_components, validate_championship_components,
)


def _staging_runtime_enabled() -> bool:
    return str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging"


def _runtime_staging_commit() -> str:
    return str(os.getenv("STREAMLIT_GIT_COMMIT", "")).strip() or "UNKNOWN"


def _supabase_host(runtime) -> str:
    return (urlparse(str(getattr(runtime, "url", ""))).hostname or "").strip()


def _staging_debug_enabled() -> bool:
    return str(st.query_params.get("debug", "")).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_join_code(value: str) -> str:
    return str(value or "").strip().upper()


_RACE_EVIDENCE_PREFIX = "supabase://exos-submissions/"
_PROTECTED_RACE_UAT_EVENT_ID = "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F"
_PROTECTED_RACE_UAT_JOIN_CODE = "RACE4CF0CE"


def _active_race_teams(runtime, event_id: str) -> list[dict]:
    """Return canonical active teams only; no display name is treated as a key."""
    return [
        dict(team)
        for team in (runtime.get_runtime_teams(event_id) or [])
        if bool(team.get("IsActive", True))
    ]


def _generate_unique_captain_pin_rows(teams: list[dict], pin_factory=None) -> list[dict]:
    """Build printable one-time PIN rows without placing internal TeamIDs in them."""
    make_pin = pin_factory or (lambda: "".join(secrets.choice("0123456789") for _ in range(6)))
    used_pins: set[str] = set()
    rows: list[dict] = []
    for team_number, team in enumerate(teams, 1):
        pin = str(make_pin())
        while pin in used_pins:
            pin = str(make_pin())
        used_pins.add(pin)
        rows.append(
            {
                "Team Number": team_number,
                "Team Name": str(team.get("TeamName", "")),
                "Captain PIN": pin,
            }
        )
    return rows


def _resolve_race_private_evidence(runtime, storage_reference: str) -> str:
    reference = str(storage_reference or "").strip()
    if not reference.startswith(_RACE_EVIDENCE_PREFIX):
        return ""
    storage_path = reference[len(_RACE_EVIDENCE_PREFIX):].strip().lstrip("/")
    if not storage_path:
        return ""
    return str(runtime.create_submission_image_url(storage_path) or "")


@st.cache_data(ttl=900, show_spinner=False)
def _cached_event_id_from_join_code(join_code: str, runtime_host: str) -> str:
    if not _staging_runtime_enabled():
        return ""
    runtime = FormulaRaceCoreV2StagingAdapter(get_runtime_database())
    event = runtime.get_event_by_join_code(join_code)
    return str(event.get("EventID", "")).strip()


@st.cache_data(ttl=900, show_spinner=False)
def _cached_runtime_event(event_id: str, runtime_host: str) -> dict:
    if not _staging_runtime_enabled():
        return {}
    runtime = FormulaRaceCoreV2StagingAdapter(get_runtime_database())
    return runtime.get_runtime_event(event_id) or {}


@st.cache_data(ttl=120, show_spinner=False)
def _cached_runtime_teams(event_id: str, runtime_host: str) -> tuple[dict[str, str], ...]:
    if not _staging_runtime_enabled():
        return tuple()
    runtime = FormulaRaceCoreV2StagingAdapter(get_runtime_database())
    rows = runtime.get_runtime_teams(event_id) or []
    return tuple(rows)


@st.cache_data(ttl=120, show_spinner=False)
def _cached_programme_hierarchy(event_id: str, runtime_host: str) -> tuple[dict[str, str], ...]:
    if not _staging_runtime_enabled():
        return tuple()
    runtime = FormulaRaceCoreV2StagingAdapter(get_runtime_database())
    return tuple(runtime.get_programme_hierarchy(event_id) or [])


@st.cache_data(ttl=300, show_spinner=False)
def _cached_marketplace_items(event_id: str, runtime_host: str) -> tuple[dict[str, str], ...]:
    if not _staging_runtime_enabled():
        return tuple()
    runtime = FormulaRaceCoreV2StagingAdapter(get_runtime_database())
    return tuple(runtime._marketplace_payload(event_id, "__RACE_SCREEN__").get("items", []))


def _refresh_after_race_control_write() -> None:
    """Reload the live R.A.C.E. projection after a successful facilitator write."""
    _cached_runtime_event.clear()
    _cached_runtime_teams.clear()
    _cached_programme_hierarchy.clear()
    _cached_marketplace_items.clear()
    st.rerun()


def _resolve_event_from_join_code(runtime, join_code: str) -> str:
    join_code = str(join_code or "").strip().upper()
    if not join_code:
        return ""
    if not hasattr(runtime, "get_event_by_join_code"):
        return ""
    try:
        event = runtime.get_event_by_join_code(join_code)
        return str(event.get("EventID", "")).strip()
    except Exception:
        return ""


def _build_formula_race_runtime():
    runtime = st.session_state.get("formula_race_runtime")
    if runtime is None:
        runtime = get_runtime_database()
        st.session_state["formula_race_runtime"] = runtime
    if not _staging_runtime_enabled():
        return runtime
    return FormulaRaceCoreV2StagingAdapter(runtime)


def _staging_banner() -> None:
    if _staging_runtime_enabled():
        st.caption("EXOS CORE v2 — DEMO")


def _attach_runtime(db):
    runtime = _build_formula_race_runtime()
    if not _staging_runtime_enabled():
        return db, runtime
    # Strict staging mode to prevent silent fallback to legacy runtime paths.
    if not getattr(runtime, "can_publish", False):
        raise RuntimeError("Core v2 runtime not available for staging Formula R.A.C.E.")

    class _FormulaRaceStagingDB:
        def __init__(self, runtime):
            self.runtime = runtime

        def get_event(self, event_id):
            return self.runtime.get_runtime_event(event_id)

        def get_teams(self, event_id):
            return self.runtime.get_runtime_teams(event_id)

        def get_event_submissions(self, event_id):
            return self.runtime.get_canonical_submissions(event_id)

        def get_event_missions(self, event_id):
            return self.runtime.get_programme_hierarchy(event_id)

    return _FormulaRaceStagingDB(runtime), runtime


def _assert_staging_runtime_health(runtime) -> None:
    if not hasattr(runtime, "get_staging_call_counts"):
        raise RuntimeError("Core v2 staging runtime is missing adapter counters.")
    runtime._assert_no_legacy_or_sheet_calls()


def _staging_diagnostics(runtime, requested_join_code: str, event_id: str) -> None:
    normalized_join_code = str(requested_join_code or "").strip().upper()
    host = _supabase_host(runtime)
    resolution = {}
    if hasattr(runtime, "debug_get_runtime_teams"):
        try:
            resolution = runtime.debug_get_runtime_teams(event_id)
        except Exception as error:
            resolution = {
                "requested": str(event_id).strip(),
                "resolved_event_id": "",
                "event_found": False,
                "query": {"event_id": ""},
                "raw_count": 0,
                "fallback_used": False,
                "rows": [],
                "adapter_error": str(error),
            }

    event_identifier = str(event_id or resolution.get("resolved_event_id", "")).strip()
    raw_count = len(resolution.get("rows", [])) if isinstance(resolution.get("rows"), list) else 0
    normalized_count = raw_count
    st.caption(f"DEPLOYED COMMIT: {_runtime_staging_commit()}")
    st.caption(f"EXOS_ENV: {str(os.getenv('EXOS_ENV', '')).strip() or 'unknown'}")
    st.caption(f"SUPABASE HOST: {host}")
    st.caption(f"REQUESTED JOIN CODE: {normalized_join_code or '—'}")
    st.caption(f"RESOLVED EVENT ID: {str(resolution.get('resolved_event_id', event_identifier) or '—')}")
    st.caption(f"EVENT FOUND: {'YES' if resolution.get('event_found') else 'NO'}")
    st.caption(f"TEAM QUERY EVENT ID: {str((resolution.get('query') or {}).get('event_id', '') or '—')}")
    st.caption(f"RAW TEAM ROW COUNT: {raw_count}")
    st.caption(f"NORMALIZED TEAM COUNT: {normalized_count}")
    st.caption(
        f"STRICT PROVIDER REJECTION REASON: {str(resolution.get('adapter_error', '') if resolution.get('adapter_error') else '') or '—'}"
    )


def _snapshot(db, event_id: str):
    if not event_id:
        return DemoFormulaRaceProvider().snapshot(event_id)
    if db is None:
        return DemoFormulaRaceProvider().snapshot(event_id or str(st.session_state.get("active_event_id", "")))

    active_view = st.session_state.get("race_nav", "Overview")
    if active_view == "Overview":
        event = _cached_runtime_event(event_id, _supabase_host(db.runtime))
        if not event:
            raise RuntimeError("Core v2 event lookup did not return an event.")

        raw_teams = _cached_runtime_teams(event_id, _supabase_host(db.runtime))
        teams_data = list(raw_teams)
        if not teams_data:
            raise RuntimeError("Core v2 runtime unavailable for teams.")

        missions = list(_cached_programme_hierarchy(event_id, _supabase_host(db.runtime)))
        try:
            submissions_raw = db.runtime.get_canonical_submissions(event_id)
        except Exception as error:
            raise RuntimeError("Core v2 runtime unavailable for submissions.") from error
        if not submissions_raw:
            submissions_raw = []

        control = {
            "CurrentStageStatus": str(event.get("Status", "READY")),
            "Elapsed": "—",
            "CurrentStageName": "Programme ready",
        }
        operations = {}
        if getattr(db.runtime, "can_publish", False):
            try:
                operations = db.runtime.get_formula_race_state(event_id, teams_data) or {}
            except Exception:
                operations = {}

        report = {}
        captain_status = {}
        if getattr(db.runtime, "can_publish", False):
            try:
                report = db.runtime.get_canonical_transaction_report(event_id, teams_data) or {}
            except Exception:
                report = {}
            try:
                captain_status = {
                    str(row.get("TeamID", "")): bool(row.get("Connected", False))
                    for row in db.runtime.formula_race_team_status(event_id)
                }
            except Exception:
                captain_status = {}

        leaderboard = {str(row.get("TeamID", "")): row for row in report.get("Leaderboard", [])}
        balances = {
            str(row.get("team_id", row.get("TeamID", ""))): row
            for row in report.get("TeamBalances", [])
        }
        mapped_teams = []
        for position, row in enumerate(teams_data, start=1):
            team_id = str(row.get("TeamID", ""))
            standing = leaderboard.get(team_id, {})
            balance = balances.get(team_id, {})
            completed = sum(
                1 for item in submissions_raw
                if str(item.get("TeamID", "")) == team_id
                and str(item.get("Status", "PENDING")).upper() in {"APPROVED", "AWARDED"}
            )
            raw_checkpoint_state = operations.get("Checkpoints", {})
            checkpoints_snapshot = (
                raw_checkpoint_state.get("Checkpoints", [])
                if isinstance(raw_checkpoint_state, dict) else raw_checkpoint_state
            )
            checkpoint_total = len(checkpoints_snapshot)
            build = round(100 * completed / max(checkpoint_total or len(missions), 1))
            mapped_teams.append(Team(
                team_id,
                str(row.get("TeamIdentity") or row.get("TeamName") or team_id),
                str(row.get("Country", "")),
                "#e31b23",
                LiveFormulaRaceProvider(db)._number(standing.get("Score", row.get("Score", 0))),
                LiveFormulaRaceProvider(db)._number(standing.get("AvailableBalance", balance.get("available_balance", 0))),
                build,
                LiveFormulaRaceProvider(db)._number(standing.get("Rank", position), position),
                captain_status.get(team_id, False),
            ))

        transactions = tuple(Transaction(
            str(row.get("award_transaction_id", "")), str(row.get("team_id", "")),
            str(row.get("award_type", "")), int(row.get("amount", 0) or 0),
            str(row.get("reason", row.get("source", ""))), str(row.get("created_at", "")),
        ) for row in report.get("AwardTransactions", []))
        submissions = tuple(Submission(
            str(row.get("SubmissionID", "")), str(row.get("TeamID", "")),
            str(row.get("MissionID", row.get("ActivityID", row.get("MissionName", "Checkpoint")))),
            str(row.get("Status", "PENDING")),
            str(row.get("SubmittedAt", row.get("Timestamp", ""))),
            str(row.get("StorageReference", row.get("PhotoURL", row.get("EvidenceType", "Evidence")))),
        ) for row in submissions_raw)
        checkpoint_state = operations.get("Checkpoints", {})
        if isinstance(checkpoint_state, list):
            checkpoint_state = {"Status": ""}
        active = str(
            "LIVE CHECKPOINTS" if str(checkpoint_state.get("Status", "")).upper() == "LIVE" else
            event.get("StageName", "") or "Programme ready"
        )

        return RaceSnapshot(
            event_id=event_id,
            event_name=str(event.get("EventName", event_id)),
            source="LIVE",
            race_status=str(control.get("CurrentStageStatus", event.get("Status", "READY"))),
            active_checkpoint=active,
            elapsed=str(control.get("Elapsed", "—")),
            teams=tuple(sorted(mapped_teams, key=lambda row: (row.rank, row.name))),
            transactions=transactions,
            submissions=submissions,
            stock={},
            activity=tuple(
                f"{item.submitted_at} · {item.team_id} · {item.checkpoint} · {item.status}"
                for item in submissions[-6:][::-1]
            ),
            operations=operations,
        )

    return LiveFormulaRaceProvider(db).snapshot(
        event_id,
        strict_core_v2=_staging_runtime_enabled(),
    )


NAV = ["Overview", "Programme", "Teams", "Reviews", "Parts Depot", "Build", "Championship", "Race", "Control", "Event Setup"]
MATERIALS = [("Cardboard sheet", 40), ("Wheel set", 120), ("Axle kit", 60), ("Glue sticks", 15)]
CRITERIA = [("Design & innovation", 25), ("Build quality", 25), ("Team identity", 20), ("Performance", 30)]


def _css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,600;0,700;0,800;1,800&family=Inter:wght@400;600;700&display=swap');
    :root{--navy:#071017;--panel:#0d1922;--panel-2:#102431;--line:#294351;--red:#ed3139;--amber:#f7b733;--green:#4dd38a;--blue:#43b6e8;--muted:#9eabb6}
    .stApp{background:radial-gradient(circle at 88% -10%,#17384b 0,transparent 29%),linear-gradient(145deg,#071017 0%,#0a151d 55%,#071017 100%);color:#f5f7f8;font-family:Inter,system-ui,sans-serif}
    header[data-testid="stHeader"]{background:transparent}.block-container{max-width:1440px;padding:.65rem 1.05rem 2.4rem}
    h1,h2,h3,.race-font{font-family:'Barlow Condensed',Impact,sans-serif!important;text-transform:uppercase;letter-spacing:.025em}h1{font-weight:800!important;font-size:2.3rem!important;line-height:.88!important;margin:.18rem 0 .45rem!important}h2{font-size:1.65rem!important;font-weight:800!important;border-left:4px solid var(--red);padding-left:.55rem;margin:.65rem 0 .45rem!important}h3{margin:.05rem 0!important}
    div[data-testid="stMetric"]{background:linear-gradient(145deg,rgba(17,37,49,.98),rgba(9,21,29,.98));border:1px solid var(--line);border-top:2px solid var(--red);padding:.55rem .7rem;border-radius:7px;min-height:76px}div[data-testid="stMetricLabel"]{text-transform:uppercase;color:var(--muted);font-size:.68rem;font-weight:700;letter-spacing:.08em}div[data-testid="stMetricValue"]{font-family:'Barlow Condensed';font-weight:800;font-size:1.7rem}
    .demo{display:inline-block;background:var(--amber);color:#101820;padding:.2rem .5rem;border-radius:3px;font:800 .65rem Inter;letter-spacing:.1em}.status{display:inline-block;border:1px solid rgba(77,211,138,.65);color:var(--green);padding:.2rem .48rem;border-radius:999px;font-size:.65rem;font-weight:800;letter-spacing:.07em}.status.attention{color:var(--amber);border-color:rgba(247,183,51,.65)}
    .pit-header{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;padding:.22rem 0 .5rem;border-bottom:1px solid var(--line)}.pit-brand{font:800 1.25rem/1 'Barlow Condensed',Impact,sans-serif;letter-spacing:.055em}.pit-brand b{color:var(--red)}.pit-label{color:var(--amber);font:800 .62rem Inter,sans-serif;letter-spacing:.14em}.pit-event{color:var(--muted);font-size:.76rem;margin-top:.18rem}.pit-telemetry{display:grid;grid-template-columns:repeat(4,auto);gap:.32rem .7rem;align-items:center;margin:.45rem 0}.pit-telemetry span{color:var(--muted);font-size:.66rem;white-space:nowrap}.pit-telemetry b{color:#fff;font-size:.77rem}.race-kicker{color:var(--amber);font:800 .64rem Inter,sans-serif;letter-spacing:.14em;text-transform:uppercase}.race-copy,.muted{color:var(--muted);font-size:.78rem}.race-card{background:linear-gradient(145deg,rgba(18,34,45,.96),rgba(9,18,25,.96));border:1px solid var(--line);border-radius:7px;padding:.65rem .75rem;margin:.3rem 0;min-height:0}.race-card h3{font-size:1.1rem}.race-card p{color:var(--muted);margin:.18rem 0;font-size:.78rem}.accent{color:var(--amber);font-weight:800}.red{color:#ff6970}.attention{color:var(--amber)!important}.good{color:var(--green)!important}
    .rank{font:800 1.6rem 'Barlow Condensed';color:var(--amber);margin-right:.45rem}.bar{height:5px;background:#17394d}.bar>i{display:block;height:5px;background:linear-gradient(90deg,var(--red),var(--amber))}.ticker{border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:.38rem 0;color:#c5d4de;font-size:.72rem;white-space:nowrap;overflow:hidden}.ops-label{font:800 .63rem Inter,sans-serif;letter-spacing:.11em;color:var(--muted);text-transform:uppercase}.ops-value{font:800 1.15rem 'Barlow Condensed',Impact,sans-serif;color:#fff}.ops-value.attention{color:var(--amber)}
    div.stButton>button{border-radius:5px;text-transform:uppercase;font-family:'Barlow Condensed';font-weight:800;letter-spacing:.05em;min-height:36px;padding:.2rem .55rem}div[data-testid="stHorizontalBlock"]{gap:.55rem}div[data-testid="stRadio"]>div{gap:.28rem;flex-wrap:wrap}div[data-testid="stRadio"] label{min-width:max-content!important;margin:0!important;padding:.22rem .42rem;border:1px solid var(--line);border-radius:4px;font-size:.68rem;font-weight:800;letter-spacing:.04em}div[data-testid="stRadio"] label p{white-space:nowrap!important}.stDataFrame{border:1px solid var(--line);border-radius:6px;overflow:hidden}[data-testid="stExpander"]{border-color:var(--line)!important;background:rgba(11,26,36,.55)}
    @media(max-width:900px){.block-container{padding:.55rem .7rem 2rem}.pit-header{display:block}.pit-telemetry{grid-template-columns:repeat(2,auto);justify-content:start}h1{font-size:2rem!important}.race-card{padding:.6rem}.stDataFrame{overflow-x:auto}}
    </style>""", unsafe_allow_html=True)


def _top(snapshot: RaceSnapshot):
    pending = _pending_reviews(snapshot)
    connected = sum(team.connected for team in snapshot.teams)
    state_class = "attention" if str(snapshot.race_status).upper() in {"PAUSED", "READY"} else ""
    badge = "DEMO DATA" if snapshot.is_demo else "LIVE"
    st.markdown(
        f"<div class='pit-header'><div><div class='pit-label'>FORMULA R.A.C.E. / RACE CONTROL</div>"
        f"<div class='pit-brand'>THE RACE <b>PIT WALL</b></div><div class='pit-event'>{snapshot.event_name}</div></div>"
        f"<div><span class='demo'>{badge}</span> <span class='status {state_class}'>● {snapshot.race_status}</span></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='pit-telemetry'><span>TEAMS <b>{len(snapshot.teams)}</b></span>"
        f"<span>CONNECTED <b>{connected}</b></span><span>PENDING REVIEWS <b>{pending}</b></span>"
        f"<span>CURRENT PHASE <b>{snapshot.active_checkpoint}</b></span></div>", unsafe_allow_html=True,
    )
    selected = st.radio("Primary navigation", NAV, horizontal=True, label_visibility="collapsed", key="race_nav")
    st.markdown(f"<div class='ticker'>LIVE TELEMETRY &nbsp; ◆ &nbsp; {snapshot.active_checkpoint} &nbsp; ◆ &nbsp; {len(snapshot.submissions)} SUBMISSIONS &nbsp; ◆ &nbsp; ELAPSED {snapshot.elapsed}</div>", unsafe_allow_html=True)
    return selected


def _navigate_race(view: str) -> None:
    """Streamlit callback: runs before the keyed navigation widget exists."""
    st.session_state["race_nav"] = view
    st.session_state["race_subscreen"] = ""


def _title(kicker, title, copy=""):
    st.markdown(f"<div class='race-kicker'>{kicker}</div>", unsafe_allow_html=True)
    st.title(title)
    if copy: st.markdown(f"<p class='race-copy'>{copy}</p>", unsafe_allow_html=True)


def _pending_reviews(snapshot: RaceSnapshot) -> int:
    return sum(item.status.upper() in {"PENDING", "PENDING_REVIEW", "SUBMITTED"} for item in snapshot.submissions)


def _facilitator_identity(control=None) -> str:
    """Persist the existing audit identity for this browser session only."""
    if not control:
        return ""
    st.session_state.setdefault("race_control_operator", "")
    return st.text_input("OPERATING AS", key="race_control_operator", placeholder="Facilitator identity")


def _operational_team_rows(snapshot: RaceSnapshot) -> list[dict[str, object]]:
    definitions = snapshot.operations.get("Checkpoints", {}).get("Checkpoints", [])
    total = len(definitions) or 4
    pending_states = {"PENDING", "PENDING_REVIEW", "SUBMITTED"}
    rows = []
    for team in snapshot.teams:
        team_submissions = [item for item in snapshot.submissions if item.team_id == team.id]
        complete = sum(item.status.upper() in {"APPROVED", "AWARDED"} for item in team_submissions)
        rows.append({
            "Rank": team.rank, "Team": team.name, "Captain": "CONNECTED" if team.connected else "OFFLINE",
            "Checkpoints": f"{min(complete, total)}/{total}", "Review": sum(item.status.upper() in pending_states for item in team_submissions),
            "Championship": team.score, "Wallet": team.balance, "Build": f"{team.build}%",
        })
    return rows


def _team_rows(snapshot, limit=None):
    for t in snapshot.teams[:limit]:
        c1,c2,c3,c4 = st.columns([.6,4,1.2,1.2])
        c1.markdown(f"<span class='rank'>{t.rank:02}</span>", unsafe_allow_html=True)
        connection = "🟢 CONNECTED" if t.connected else "⚪ NOT CONNECTED"
        c2.markdown(f"<div><b>{t.name.upper()}</b> <span class='muted'>· {t.country}</span><br><small>{connection}</small><div class='bar'><i style='width:{t.build}%'></i></div></div>", unsafe_allow_html=True)
        c3.metric("Championship score", t.score)
        c4.metric("Wallet", t.balance)


def overview(s):
    _title("Operational command", "Pit Wall Overview", "One dense live view of teams, reviews, readiness and the next facilitator action.")
    pending = _pending_reviews(s)
    connected = sum(team.connected for team in s.teams)
    ready = sum(team.build >= 80 for team in s.teams)
    cols = st.columns(6)
    for col, (label, value) in zip(cols, [
        ("Teams", len(s.teams)), ("Connected", connected), ("Pending reviews", pending),
        ("Programme", s.active_checkpoint), ("Parts depot", "CONFIGURED" if s.stock else "SEE DEPOT"), ("Ready to race", ready),
    ]):
        col.metric(label, value)
    attention = []
    if pending: attention.append(f"<span class='ops-value attention'>{pending}</span> <span class='ops-label'>PENDING REVIEW</span>")
    if ready: attention.append(f"<span class='ops-value good'>{ready}</span> <span class='ops-label'>BUILD READY</span>")
    if not attention: attention.append("<span class='ops-value good'>CLEAR</span> <span class='ops-label'>NO CANONICAL ATTENTION FLAGS</span>")
    st.markdown(f"<div class='race-card'><div class='ops-label'>Needs attention now</div>{' &nbsp; ◆ &nbsp; '.join(attention)}</div>", unsafe_allow_html=True)
    st.subheader("10-Team Operational Grid")
    st.dataframe(_operational_team_rows(s), width="stretch", hide_index=True, column_config={
        "Captain": "CAPTAIN", "Checkpoints": "CP", "Championship": "CHAMPIONSHIP SCORE",
    })
    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("Review Queue")
        identities = {team.id: team.name for team in s.teams}
        review_items = [item for item in s.submissions if item.status.upper() in {"PENDING", "PENDING_REVIEW", "SUBMITTED"}]
        for item in review_items[:3]:
            st.markdown(f"<div class='race-card'><b>{identities.get(item.team_id, 'Team')}</b> · {item.checkpoint}<br><span class='attention'>{item.status}</span> <span class='muted'>· {item.submitted_at or 'time unavailable'}</span></div>", unsafe_allow_html=True)
        if not review_items: st.caption("No canonical submissions require review.")
    with right:
        st.subheader("Live Feed")
        for item in s.activity[:4]: st.markdown(f"<div class='race-card'>{item}</div>", unsafe_allow_html=True)


def live_programme(s):
    _title("Programme control", "Live Programme", "Parallel checkpoint activities remain independently available, open, paused or closed.")
    checkpoint_state=s.operations.get("Checkpoints",{})
    checkpoint_pct=100*sum(x.status.upper()=="APPROVED" for x in s.submissions)/(max(len(s.teams)*4,1))
    stages=[("01","Launch EXOS",100),("02","RACE Checkpoints",checkpoint_pct),("03","Marketplace / Spend Credits",0),("04","Build",0),("05","Team Photo",0),("06","Drag Race",0),("07","Judging",0),("08","Championship",0)]
    for no,name,p in stages:
        live=name=="RACE Checkpoints" and str(checkpoint_state.get("Status","")).upper()=="LIVE"
        c1,c2,c3=st.columns([.7,4,1.2]); c1.markdown(f"<span class='rank'>{no}</span>",unsafe_allow_html=True); c2.markdown(f"### {name}"); c2.progress(min(float(p)/100,1.0)); c3.markdown("<span class='status'>ACTIVE</span>" if live else ("✓ COMPLETE" if p==100 else "READY"),unsafe_allow_html=True)
    st.button("Open programme controls", type="primary", width="stretch", on_click=_navigate_race, args=("Control",))


def championship(s, final=False):
    _title("Final race ranking" if final else "Mission and judging score", "Final Race Results" if final else "Championship", "Championship Rank is distinct from final race rank, which is based on adjusted race time.")
    if final and not s.is_demo:
        rows=final_standings([{"TeamID":t.id,"TeamName":t.name} for t in s.teams],
            [{"TeamID":x.team_id,"Amount":x.amount} for x in s.transactions],s.operations.get("Judging",[]),s.operations.get("RaceResults",[]),s.operations.get("Config",{}))
        st.dataframe(rows,width="stretch",hide_index=True)
    else: _team_rows(s)
    if not final:
        st.subheader("Championship Table")
        components = s.operations.get("Configuration", {}).get("ChampionshipComponents", [])
        component_names = {str(row.get("ComponentID", "")): str(row.get("DisplayName", "Component")) for row in components}
        breakdown = s.operations.get("ChampionshipBreakdown", [])
        rows = []
        for team in s.teams:
            values = {component_names.get(str(row.get("ComponentID", "")), str(row.get("ComponentID", ""))): row.get("Points", 0) for row in breakdown if str(row.get("TeamID", "")) == team.id}
            rows.append({"Rank": team.rank, "Team": team.name, **values, "Total Championship Points": team.score})
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption(f"Tie-break: {s.operations.get('ChampionshipTieBreak', 'TEAM_ID')} · Credits and Wallet are excluded from Championship Points.")
    if final: st.success("Final result locking is available from Race Control after canonical verification.")


def teams(s):
    _title("Team operations", "Teams", "Dense team health, championship position, checkpoint progress and wallet visibility.")
    st.dataframe(_operational_team_rows(s), width="stretch", hide_index=True)
    choices = {f"#{team.rank:02} · {team.name}": team.id for team in s.teams}
    selected = st.selectbox("Open team wallet", list(choices), key="race_team_wallet")
    if st.button("View wallet operations", key="open_selected_wallet"):
        st.session_state.selected_team = choices[selected]; st.session_state.race_subscreen="wallet"; st.rerun()


def wallet(s):
    team=next((t for t in s.teams if t.id==st.session_state.get("selected_team")),s.teams[0])
    _title(f"{team.country} / Rank #{team.rank}", f"{team.name} Team Wallet", "Ledger projection: credits are not calculated or persisted by this screen.")
    team_transactions=[x for x in s.transactions if x.team_id==team.id]
    credits_earned=sum(float(x.amount or 0) for x in team_transactions if float(x.amount or 0)>0)
    credits_spent=-sum(float(x.amount or 0) for x in team_transactions if float(x.amount or 0)<0)
    a,b,c,d=st.columns(4); a.metric("Current balance",f"{team.balance} CR"); b.metric("Credits earned",f"{credits_earned:g} CR"); c.metric("Credits spent",f"{credits_spent:g} CR"); d.metric("Championship score",team.score)
    st.subheader("Transaction Timeline")
    if team_transactions:
        st.dataframe([x.__dict__ for x in team_transactions],width="stretch",hide_index=True)
    else:
        st.caption("No credit transactions recorded for this team.")
    st.caption("Wallet figures are canonical ledger projections. Manual adjustments remain audited in Control.")
    if st.button("Back to teams"): st.session_state.race_subscreen=""; st.rerun()


def checkpoints(s):
    _title("Checkpoint telemetry", "RACE Checkpoints", "All four checkpoint activities may operate concurrently; this view does not imply a single current checkpoint.")
    definitions=s.operations.get("Checkpoints",{}).get("Checkpoints",[])
    approved={(x.team_id,x.checkpoint) for x in s.submissions if x.status.upper()=="APPROVED"}
    pending=sum(x.status.upper() in {"PENDING","PENDING_REVIEW","SUBMITTED"} for x in s.submissions)
    rows=[]
    for team in s.teams:
        complete=sum(any(team.id==team_id and (str(cp.get("Name",""))==checkpoint or str(cp.get("ActivityID",""))==checkpoint) for team_id,checkpoint in approved) for cp in definitions)
        rows.append({"Team":team.name,"Completed":f"{complete}/4","Pending Reviews":sum(x.team_id==team.id and x.status.upper() in {"PENDING","PENDING_REVIEW","SUBMITTED"} for x in s.submissions),"Credits":team.balance})
    leader=max(rows,key=lambda row:row["Credits"])["Team"] if rows else "—"
    a,b,c=st.columns(3);a.metric("Teams",len(s.teams));b.metric("Pending reviews",pending);c.metric("Wallet leader",leader)
    st.dataframe(rows,width="stretch",hide_index=True)
    st.button("Open programme controls", type="primary", width="stretch", on_click=_navigate_race, args=("Control",))


def _official_result_control(station, submission_id):
    """Collect the facilitator-owned official result a measured station requires.

    Migration 033 made the official result facilitator-owned, so the Captain no
    longer submits one.  `exos_v2_formula_race_verify_station_result` still
    refuses to approve a measured station without a result, so the queue that
    approves it has to supply the value Station Results already collects.
    """
    method = str(station.get("ScoringMethod", "")).upper()
    if method not in CAPTAIN_RESULT_METHODS:
        return None, False
    if method == "LOWEST_TIME":
        a, b, c = st.columns(3)
        minutes = a.number_input("Minutes", min_value=0, step=1, value=None, key=f"review_minutes_{submission_id}")
        seconds = b.number_input("Seconds", min_value=0, max_value=59, step=1, value=None, key=f"review_seconds_{submission_id}")
        milliseconds = c.number_input("Milliseconds", min_value=0, max_value=999, step=1, value=None, key=f"review_ms_{submission_id}")
        if minutes is None and seconds is None and milliseconds is None:
            st.caption("Enter the official time before approving this station.")
            return None, True
        return int(minutes or 0) * 60_000 + int(seconds or 0) * 1_000 + int(milliseconds or 0), False
    unit = str(station.get("ResultUnit", "") or "")
    label = str(station.get("ResultLabel", "") or "Official result")
    value = st.number_input(f"{label} ({unit})" if unit else label, min_value=0, step=1, value=None, key=f"review_result_{submission_id}")
    if value is None:
        st.caption("Enter the official result before approving this station.")
        return None, True
    return int(value), False


def reviews(s, control=None, runtime=None):
    _title("Facilitator action queue", "RACE Review Queue", "Private evidence is resolved lazily only for submissions shown here; decisions use the certified review contract.")
    team_identity={team.id:team.name for team in s.teams}
    pending_items = [item for item in s.submissions if item.status.upper() in {"PENDING", "PENDING_REVIEW", "SUBMITTED"}]
    st.metric("PENDING REVIEWS", len(pending_items))
    actor = _facilitator_identity(control)
    # Resolve each pending submission to its canonical station so a measured
    # station is approved with the official result the verification RPC needs.
    station_by_submission = {}
    if pending_items and runtime is not None and hasattr(runtime, "get_canonical_submissions"):
        stations = {str(row.get("ActivityID", "")): row for row in runtime.get_formula_race_stations(s.event_id)}
        station_by_submission = {
            str(row.get("SubmissionID", "")): stations.get(str(row.get("MissionID", "")), {})
            for row in runtime.get_canonical_submissions(s.event_id)
        }
    for x in pending_items:
        with st.container(border=True):
            c1,c2=st.columns([4,1]); c1.markdown(f"### {team_identity.get(x.team_id, 'Team')} · {x.checkpoint}\n<span class='muted'>Submitted {x.submitted_at or 'time unavailable'}</span>", unsafe_allow_html=True); c2.markdown(f"<span class='status attention'>{x.status}</span>", unsafe_allow_html=True)
            evidence_url = _resolve_race_private_evidence(runtime, x.evidence) if runtime else ""
            if evidence_url:
                st.image(evidence_url, caption=f"{team_identity.get(x.team_id, 'Team')} · {x.checkpoint}", use_container_width=True)
            elif str(x.evidence).startswith(_RACE_EVIDENCE_PREFIX):
                st.warning("Private photo evidence is unavailable.")
            notes=st.text_input("Notes / rejection reason",key=f"review_notes_{x.id}") if control else ""
            official_result, awaiting_result = _official_result_control(station_by_submission.get(str(x.id), {}), x.id) if control else (None, False)
            pending=x.status.upper() in {"PENDING","PENDING_REVIEW","SUBMITTED"}
            def decide(decision, official_result=official_result):
                try:
                    with st.spinner("Approving…" if decision == "APPROVE" else "Saving review…"):
                        control.review_race_checkpoint(x.id,decision,actor,notes,notes,f"{x.id}:{decision}",official_result if decision == "APPROVE" else None)
                except (RuntimeDatabaseError, RuntimeError) as error:
                    st.error(f"Review could not be saved: {error}")
                    return
                st.success("Review saved and projections updated.");_refresh_after_race_control_write()
            a,b,c=st.columns(3)
            if a.button("APPROVE",key=f"award_{x.id}",disabled=not pending or bool(control and not actor) or awaiting_result):
                decide("APPROVE") if control else st.toast(f"Demo approval for {x.id}")
            if b.button("REQUEST RESUBMISSION",key=f"revise_{x.id}",disabled=not pending or bool(control and not actor)):
                decide("REQUEST_RESUBMISSION") if control else st.toast(f"Demo revision for {x.id}")
            if c.button("REJECT",key=f"reject_{x.id}",disabled=not pending or bool(control and not actor)):
                decide("REJECT") if control else st.toast(f"Demo rejection for {x.id}")
    if not pending_items: st.success("Review queue clear.")
    if st.button("Open photo gallery",width="stretch"): st.session_state.race_subscreen="gallery"; st.rerun()


def gallery(s, runtime=None):
    _title("Secondary evidence browser", "Photo Gallery", "Private signed image URLs are requested only for evidence displayed in this gallery.")
    for row in range(0, len(s.teams), 3):
        cols=st.columns(3)
        for col,t in zip(cols,s.teams[row:row+3]):
            evidence = [x for x in s.submissions if x.team_id == t.id and str(x.evidence).startswith(_RACE_EVIDENCE_PREFIX)]
            state = evidence[-1].status if evidence else "NO EVIDENCE"
            col.markdown(f"<div class='race-card'><h3>{t.name}</h3><p>{state}</p></div>",unsafe_allow_html=True)
            if not evidence:
                col.caption("No photo evidence submitted.")
            for x in evidence:
                evidence_url = _resolve_race_private_evidence(runtime, x.evidence) if runtime else ""
                if evidence_url:
                    col.image(evidence_url, caption=x.checkpoint, use_container_width=True)
                else:
                    col.warning(f"{x.checkpoint}: private photo evidence is unavailable.")
    if st.button("Back to review queue"): st.session_state.race_subscreen=""; st.rerun()


def marketplace(s):
    _title("Team garage economy", "Parts Depot", "Demo purchases remain local. In a live event, inventory and purchases are rendered from the canonical marketplace projection.")
    team=st.selectbox("Purchasing team",[t.name for t in s.teams]); selected=next(t for t in s.teams if t.name==team); st.metric("Available wallet",f"{selected.balance} CR")
    cart=st.session_state.setdefault("race_cart",{})
    cols=st.columns(4)
    for col,(name,price) in zip(cols,MATERIALS):
        with col:
            st.markdown(f"<div class='race-card'><h3>{name}</h3><p>{s.stock[name]} in stock</p><span class='accent'>{price} CR</span></div>",unsafe_allow_html=True)
            qty=st.number_input("Qty",0,10,key=f"qty_{name}")
            if st.button("Add to cart",key=f"add_{name}",disabled=qty==0): cart[name]=int(qty); st.rerun()
    total=sum(dict(MATERIALS)[n]*q for n,q in cart.items())
    st.subheader("Cart"); st.write(cart or "Your cart is empty."); st.metric("Checkout total",f"{total} CR")
    if total>selected.balance: st.error(f"Insufficient credits · short by {total-selected.balance} CR")
    if st.button("Checkout",type="primary",width="stretch",disabled=not cart or total>selected.balance): st.toast("Demo checkout complete — no ledger transaction was written"); st.session_state.race_cart={}
    st.subheader("Recent Transactions"); st.dataframe([x.__dict__ for x in s.transactions],width="stretch",hide_index=True)


def race_map(s):
    _title("Track Operations", "Race Map", "Course sectors, marshals and live team positions.")
    st.markdown("""<div class='race-card' style='height:360px;position:relative;background:radial-gradient(circle at 50% 50%,#123d55,#071724)'><svg width='100%' height='300' viewBox='0 0 900 300'><path d='M90 160 C150 30 330 30 390 130 S620 280 800 110 C840 75 820 38 750 60' fill='none' stroke='#314f61' stroke-width='42'/><path d='M90 160 C150 30 330 30 390 130 S620 280 800 110 C840 75 820 38 750 60' fill='none' stroke='#f5c400' stroke-width='4' stroke-dasharray='12 10'/><circle cx='390' cy='130' r='12' fill='#e31b23'/><circle cx='650' cy='220' r='12' fill='#19a8e7'/><text x='410' y='120' fill='white'>VELOCITY</text><text x='670' y='245' fill='white'>APEX</text></svg></div>""",unsafe_allow_html=True)
    a,b,c=st.columns(3); a.metric("Track status","CLEAR"); b.metric("Marshal posts","4 / 4"); c.metric("Next heat","12:15")


def judging(s, control=None):
    _title("Efficient one-team scoring", "Judging", "Official criterion scores reconcile configured Championship Components without affecting Credits or Marketplace currency.")
    names=[t.name for t in s.teams]
    st.session_state.setdefault("race_judge_index", 0)
    index=min(max(int(st.session_state["race_judge_index"]),0),len(names)-1)
    team=st.selectbox("Select team",names,index=index,key="judge_team")
    selected_index=names.index(team)
    p,n=st.columns(2)
    if p.button("← Previous team",width="stretch"): st.session_state.race_judge_index=(selected_index-1)%len(names); st.rerun()
    if n.button("Next team →",width="stretch"): st.session_state.race_judge_index=(selected_index+1)%len(names); st.rerun()
    total=0.0
    configuration = s.operations.get("Configuration", {}) if control else {}
    configured_criteria = [row for row in configuration.get("JudgingCriteria", []) if row.get("Enabled", True) and row.get("CriterionName")]
    categories = configured_criteria or ([{"CriterionName": name, "MaximumScore": 10} for name in JUDGING_CATEGORIES] if control else [{"CriterionName": name, "MaximumScore": 10} for name, _ in CRITERIA])
    selected = next(t for t in s.teams if t.name == team)
    if control:
        photo = next((row for row in s.operations.get("TeamPhotos", []) if str(row.get("team_id", "")) == selected.id), {})
        build = next((row for row in s.operations.get("BuildStatus", []) if str(row.get("team_id", "")) == selected.id), {})
        st.caption(f"Build status: {build.get('status', 'Not Started')} · Team Photo: {'submitted' if photo else 'not submitted'}")
        if photo.get("storage_reference"):
            photo_url = control.runtime.get_formula_race_team_photo_url(photo["storage_reference"])
            if photo_url:
                st.image(photo_url, caption=f"{selected.name} · completed-car Team Photo", use_container_width=True)
    scores={}
    for criterion in categories:
        criterion_name = str(criterion.get("CriterionName", ""))
        maximum = max(1, int(float(criterion.get("MaximumScore", 10) or 10)))
        score=st.slider(criterion_name,0,maximum,min(7, maximum),key=f"score_{team}_{criterion_name}");scores[criterion_name]=score;total+=score
    st.metric("Total score",f"{total:.1f}"); st.progress((selected_index+1)/len(names),text=f"Judging progress · {selected_index+1} of {len(names)} teams")
    if control:
        criterion_maxima = {str(row.get("CriterionName", "")): row.get("MaximumScore", 0) for row in categories}
        photo_submitted = bool(next((row for row in s.operations.get("TeamPhotos", []) if str(row.get("team_id", "")) == selected.id), {}))
        subtotal = sum(
            championship_component_points(
                component, scores.get(str(component.get("SourceReference", "")), 0),
                criterion_maxima.get(str(component.get("SourceReference", "")), 0),
                team_photo_submitted=photo_submitted,
            )
            for component in configuration.get("ChampionshipComponents", [])
            if str(component.get("ComponentType", "")) in {"JUDGING_CRITERION", "TEAM_PHOTO"}
        )
        st.metric("Championship subtotal", f"{subtotal:g} points")
    actor=_facilitator_identity(control)
    reason=st.text_input("Submission or correction reason",key="race_judge_reason") if control else ""
    if st.button("Submit score",type="primary",width="stretch",disabled=bool(control and (not actor or not reason))):
        if control:
            with st.spinner("Saving score…"):
                control.save_race_judging(s.event_id,selected.id,scores,reason,actor)
            st.success("Judging score saved with audit history.");_refresh_after_race_control_write()
        else: st.session_state.judge_confirm=f"Demo score {total:.1f} prepared for {team}"
    if st.session_state.get("judge_confirm"): st.success(st.session_state.judge_confirm+". No canonical Judge Score was written.")


def drag_results(s, control=None):
    _title("Live event pressure screen", "Drag Race Results", "Final Race Rank is based on adjusted time. Bonus Value is informational only and never awards spendable Credits.")
    live_rows=s.operations.get("RaceResults",[]) if control else []
    rows=[]
    for i,t in enumerate(s.teams):
        live=next((r for r in live_rows if str(r.get("team_id",""))==t.id),{})
        time_ms = live.get("time_ms", live.get("finish_time_ms", "—"))
        readable = f"{float(time_ms) / 1000:.3f}s" if isinstance(time_ms, (int, float)) else "—"
        rows.append({"Final Rank":live.get("position",i+1),"Team":t.name,"Finish":readable,"Penalty ms":live.get("penalty_ms",0),"Adjusted ms":live.get("adjusted_time_ms",time_ms),"Bonus Value":live.get("bonus_credits",live.get("bonus",0)),"Verified":live.get("verified",False),"Locked":live.get("locked",False)})
    st.dataframe(rows,width="stretch",hide_index=True)
    if not control: st.markdown("<div class='race-card'><h3>Fastest Lap</h3><p>Velocity · 12.18 seconds</p><span class='accent'>INFORMATIONAL RESULT ANNOTATION</span></div>",unsafe_allow_html=True)
    if control:
        team=st.selectbox("Result team",[t.name for t in s.teams]);selected=next(t for t in s.teams if t.name==team);current=next((row for row in live_rows if str(row.get("team_id",""))==selected.id),{})
        locked=bool(current.get("locked",False))
        if current:
            st.caption("Correcting the current pre-lock result. The correction reason and prior result are preserved in the canonical audit log.")
        time_ms=st.number_input("Finish time (ms)",0,3600000,int(current.get("time_ms",0) or 0),key=f"race_result_time_{selected.id}",disabled=locked)
        penalty=st.number_input("Penalty (ms)",0,3600000,int(current.get("penalty_ms",0) or 0),key=f"race_result_penalty_{selected.id}",disabled=locked)
        bonus=st.number_input("Result annotation (informational)",0,1000,int(current.get("bonus_credits",current.get("bonus",0)) or 0),key=f"race_result_bonus_{selected.id}",disabled=locked,help="This does not award Credits, change Wallet balance, Championship Score, or adjusted race time.")
        verified=st.checkbox("Verified",value=bool(current.get("verified",False)),key=f"race_result_verified_{selected.id}",disabled=locked)
        actor=_facilitator_identity(control);reason=st.text_input("Result or correction reason",key="race_result_reason")
        if locked: st.error("Final results are locked. This result cannot be corrected.")
        action_label="Save Result Correction" if current else "Save Race Result"
        if st.button(action_label,disabled=locked or not actor or not reason,width="stretch"):
            with st.spinner("Saving race result…"):
                control.save_race_result(s.event_id,selected.id,time_ms,penalty,bonus,verified,reason,actor)
            st.success("Race result saved with audit history.");_refresh_after_race_control_write()
        verified=sum(bool(row.get("verified", False)) for row in live_rows); missing=max(len(s.teams)-len(live_rows), 0); unverified=max(len(live_rows)-verified, 0)
        st.markdown(f"<div class='race-card'><span class='ops-label'>Final results readiness</span><br><span class='ops-value'>{verified}/{len(s.teams)}</span> VERIFIED &nbsp; · &nbsp; {missing} MISSING &nbsp; · &nbsp; {unverified} UNVERIFIED</div>", unsafe_allow_html=True)
        confirm_lock=st.checkbox("I understand final ranking will be frozen and locked results cannot be edited.",key="race_lock_confirm",disabled=locked)
        if st.button("LOCK FINAL RESULTS",type="primary",disabled=locked or not actor or not reason or not confirm_lock,width="stretch"):
            with st.spinner("Locking final results…"):
                control.lock_race_results(s.event_id,actor,reason)
            st.success("Final race positions are locked.");_refresh_after_race_control_write()


def build_status(s, control=None):
    _title("Pit / garage status", "Build Control", "All ten teams are shown together so facilitators can identify who is behind, building, painting or ready.")
    live={str(r.get("team_id","")):r for r in s.operations.get("BuildStatus",[])}
    for t in s.teams:
        status=str(live.get(t.id,{}).get("status","Not Started"));pct=BUILD_STATUSES.index(status)*20 if status in BUILD_STATUSES else 0
        c1,c2,c3=st.columns([2,5,1]); c1.markdown(f"**{t.name.upper()}**\n\n{t.country}"); c2.progress(pct/100,text=f"{status} · {pct}%"); c3.markdown("<span class='good'>READY</span>" if status in {"Ready to Race","Completed"} else "<span class='muted'>ACTIVE</span>", unsafe_allow_html=True)
    if control:
        team=st.selectbox("Update team",[t.name for t in s.teams],key="build_team");status=st.selectbox("Build status",BUILD_STATUSES);actor=_facilitator_identity(control);reason=st.text_input("Required reason",key="build_reason")
        if st.button("Update Build Status",disabled=not actor or not reason,width="stretch"):
            selected=next(t for t in s.teams if t.name==team)
            with st.spinner("Saving build status…"):
                control.set_race_build_status(s.event_id,selected.id,status,{},reason,actor)
            st.success("Build status saved and audited.");_refresh_after_race_control_write()


def control_centre(s, control=None):
    _title("Facilitator command centre", "Control", "Programme, depot, broadcast, recovery and audited manual operations are separated by operational risk.")
    checkpoint_state=s.operations.get("Checkpoints",{})
    module_id=str(checkpoint_state.get("ModuleID",f"{s.event_id}-RACE-CHECKPOINTS"))
    checkpoint=st.selectbox("RACE checkpoint module",["RACE Checkpoints"])
    st.caption(f"{checkpoint} · {checkpoint_state.get('Status','READY')} · four parallel activities")
    actor=_facilitator_identity(control)
    st.subheader("Programme Control")
    def runtime_action(label,action_name,key,kind="secondary"):
        if st.button(label,key=key,type=kind,width="stretch",disabled=bool(control and not actor)):
            if control:
                with st.spinner(f"{label}…"):
                    control.set_race_checkpoint_runtime(s.event_id,module_id,action_name,actor)
                st.success(f"{label} complete.");_refresh_after_race_control_write()
            else: st.toast(f"DEMO ONLY · {label}")
    a,b,c=st.columns(3)
    with a: runtime_action("LAUNCH CHECKPOINTS","LAUNCH","launch","primary")
    with b: runtime_action("PAUSE CHECKPOINTS","PAUSE","pause")
    with c: runtime_action("CLOSE CHECKPOINTS","CLOSE","close")
    st.subheader("Parts Depot Control")
    marketplace = control.runtime._marketplace_payload(s.event_id, "", active_only=False) if control else {"items": []}
    active_items = [item for item in marketplace.get("items", []) if item.get("Active")]
    depot_state = "OPEN" if active_items else "CLOSED"
    st.markdown(f"<div class='race-card'><span class='ops-label'>Parts depot state</span><br><span class='ops-value'>{depot_state}</span> · {len(active_items)} active of {len(marketplace.get('items', []))} configured items</div>", unsafe_allow_html=True)
    if marketplace.get("CatalogueSource"):
        st.caption(f"Catalogue authority: {marketplace['CatalogueSource']}")
    def marketplace_action(label, action_name, key, kind="secondary"):
        if st.button(label, key=key, type=kind, width="stretch", disabled=bool(control and not actor)):
            if control:
                with st.spinner(f"{label}…"):
                    control.set_race_marketplace_runtime(s.event_id, action_name, actor)
                st.success(f"{label} complete.");_refresh_after_race_control_write()
            else: st.toast(f"DEMO ONLY · {label}")
    a,b,c=st.columns(3)
    with a: marketplace_action("OPEN MARKETPLACE", "OPEN", "marketplace_open", "primary")
    with b: marketplace_action("PAUSE MARKETPLACE", "PAUSE", "marketplace_pause")
    with c: marketplace_action("CLOSE MARKETPLACE", "CLOSE", "marketplace_close")
    if marketplace.get("items"):
        st.dataframe([{
            "Item": item.get("ItemName", ""), "Credit Cost": item.get("CreditCost", 0),
            "Remaining": item.get("StockQuantity", "—"), "State": "OPEN" if item.get("Active") else "CLOSED",
        } for item in marketplace["items"]], width="stretch", hide_index=True)
    st.subheader("Broadcast")
    msg=st.text_input("Broadcast message",placeholder="Message all participant and projector views")
    a,b=st.columns(2)
    with a:
        if st.button("PREVIEW BROADCAST",disabled=not msg,width="stretch"): st.toast("DEMO ONLY · broadcast previewed")
    with b:
        st.link_button("OPEN PROJECTOR", f"?view=projector&event_id={s.event_id}", width="stretch")
    st.subheader("Recovery")
    recovery_team=st.selectbox("Captain recovery team",[t.name for t in s.teams],key="leader_team")
    st.info(f"{recovery_team} uses the existing Captain PIN recovery journey. Race Control does not create or alter Captain credentials.")
    st.subheader("Manual Wallet Operation")
    with st.container(border=True):
        team_name=st.selectbox("Adjust team",[t.name for t in s.teams],key="adjust_team")
        amount=st.number_input("Credit adjustment",-500,500,0,key="race_adjustment_amount")
        reason=st.text_input("Required reason",key="race_adjustment_reason")
        selected=next((team for team in s.teams if team.name==team_name),None)
        key_name=f"race_manual_adjustment:{s.event_id}:{selected.id if selected else ''}:{int(amount)}:{reason.strip()}"
        if key_name not in st.session_state:
            st.session_state[key_name]=f"race-manual-adjustment:{s.event_id}:{selected.id if selected else ''}:{uuid.uuid4()}"
        if st.button("APPLY CREDIT ADJUSTMENT",type="primary",width="stretch",disabled=not control or not actor or not reason.strip() or not amount or selected is None):
            try:
                result=control.adjust_race_credits(s.event_id,selected.id,int(amount),reason,actor,st.session_state[key_name])
                st.success(f"Manual credit adjustment recorded: {result.get('Amount', amount)} credits.")
                st.session_state.pop(key_name,None);_refresh_after_race_control_write()
            except (RuntimeError, ValueError) as error:
                st.error(str(error))
        adjustments=[x.__dict__ for x in s.transactions if x.kind=="MANUAL_ADJUSTMENT"]
        if adjustments:
            st.dataframe(adjustments,width="stretch",hide_index=True)
        else:
            st.caption("No manual credit adjustments recorded for this event.")
    st.subheader("Emergency")
    emergency_confirm=st.checkbox("I understand an emergency action interrupts live operations.", key="race_emergency_confirm")
    if st.button("EMERGENCY STOP", key="emergency", type="secondary", width="stretch", disabled=not emergency_confirm):
        st.toast("DEMO ONLY · Emergency stop acknowledged locally")
    if not control: st.warning("DEMO DATA · No live mutation is performed.")


def station_results(snapshot, control, runtime):
    _title("Official verification", "Station Results", "Verification controls official results and Credits; Captain submission already advances its configured route.")
    teams = {team.id: team.name for team in snapshot.teams}
    stations = {row["ActivityID"]: row for row in runtime.get_formula_race_stations(snapshot.event_id)}
    rows = runtime.get_canonical_submissions(snapshot.event_id)
    table = []
    for row in rows:
        station = stations.get(str(row.get("MissionID", "")), {})
        payload = row.get("SubmissionPayload", {}) or {}
        table.append({"Submission": row.get("SubmissionID", ""), "Station": station.get("DisplayName", row.get("MissionID", "")), "Team": teams.get(str(row.get("TeamID", "")), row.get("TeamID", "")), "Submitted": payload.get("result_value", "—"), "Evidence": row.get("EvidenceType", "NONE"), "Status": row.get("Status", ""), "Official": payload.get("official_result", row.get("Score", "")), "Rank": payload.get("official_rank", "PENDING")})
    st.dataframe(table, width="stretch", hide_index=True)
    pending = [row for row in rows if str(row.get("Status", "")).upper() in {"SUBMITTED", "PENDING", "UNDER REVIEW"}]
    if not pending: return
    labels = {f"{teams.get(str(row.get('TeamID','')), row.get('TeamID',''))} · {stations.get(str(row.get('MissionID','')),{}).get('DisplayName',row.get('MissionID',''))}": row for row in pending}
    with st.form("race_station_result_verify"):
        row = labels[st.selectbox("Submission", list(labels))]
        station = stations.get(str(row.get("MissionID", "")), {})
        value = st.number_input(str(station.get("ResultLabel", "Official result")), value=float((row.get("SubmissionPayload", {}) or {}).get("result_value", 0) or 0), disabled=str(station.get("ScoringMethod", "")).upper() == "NON_SCORING")
        actor = st.text_input("Facilitator identity", key="station_results_actor")
        note = st.text_input("Correction / verification note")
        verify = st.form_submit_button("VERIFY OFFICIAL RESULT", type="primary")
    if verify:
        control.review_race_checkpoint(str(row.get("SubmissionID", "")), "APPROVE", actor, note, note, f"station-verify:{row.get('SubmissionID','')}", value)
        st.success("Official result verified. Ranking reconciles after every active team is verified."); _refresh_after_race_control_write()


def event_setup(snapshot, runtime):
    """R.A.C.E.-only configuration; the protected UAT event cannot be reset."""
    _title("R.A.C.E. configuration", "Event Setup", "Configure event-scoped stations, routes, inventory, judging and Captain access without source changes.")
    event_id, config = snapshot.event_id, runtime.get_formula_race_configuration(snapshot.event_id)
    actor = st.text_input(
        "Configuration Actor (required to save changes)",
        key="race_setup_actor",
        help="Enter the facilitator name recorded with the canonical migration-030 configuration change.",
    )
    configured_stations = [normalise_station(row, index) for index, row in enumerate(runtime.get_formula_race_stations(event_id), 1)]
    station_draft_key = f"race_station_draft:{event_id}"
    station_edit_key = f"race_station_edit:{event_id}"
    station_reference_uploads_key = f"race_station_reference_uploads:{event_id}"
    if station_draft_key not in st.session_state:
        st.session_state[station_draft_key] = [dict(row) for row in configured_stations]
    if station_reference_uploads_key not in st.session_state:
        st.session_state[station_reference_uploads_key] = {}
    stations = st.session_state[station_draft_key]
    original_station_references = {
        str(row.get("ActivityID", "")): str(row.get("ImageReference", "") or "")
        for row in configured_stations
    }
    historical_submissions = runtime.get_canonical_submissions(event_id) or []
    stations_locked = bool(historical_submissions)
    tabs = st.tabs(["Stations", "Team Routes", "Parts Depot", "Judging", "Championship", "Teams & Access", "Reset Event"])
    with tabs[0]:
        st.subheader("Station editor")
        st.caption("Add, edit, disable and preview stations here. Station content is event-scoped and does not require SQL or source changes.")
        if not actor:
            st.info("Enter a Configuration Actor above to enable SAVE STATION CONFIGURATION. You can review station fields before saving.")
        if stations_locked:
            st.warning("Station configuration is locked because this event already has submissions. Migration 030 blocks station changes to protect historical R.A.C.E. data. Safe setup action: configure stations on a clean event before the first Captain submission; do not reset this protected UAT event.")
        if st.button("ADD STATION", type="primary", disabled=stations_locked, key=f"race_add_station:{event_id}"):
            activity_id = f"{event_id}-STATION-{uuid.uuid4().hex[:8].upper()}"
            stations.append(normalise_station({
                "ActivityID": activity_id,
                "DisplayOrder": len(stations) + 1,
                "ShortCode": f"S{len(stations) + 1}",
                "DisplayName": "New station",
                "ParticipantInstruction": "",
                "FacilitatorInstruction": "",
                "ScoringMethod": "FACILITATOR_SCORE",
                "ResultLabel": "Score",
                "ResultUnit": "points",
                "EvidenceRequirement": "PHOTO_OPTIONAL",
                "BaseCredits": 0,
                "Enabled": True,
            }))
            st.session_state[station_edit_key] = activity_id

        editing_activity_id = st.session_state.get(station_edit_key, "")
        scoring_options = ["FACILITATOR_SCORE", "LOWEST_TIME", "HIGHEST_COUNT", "SUCCESS_COUNT", "NON_SCORING"]
        evidence_options = ["PHOTO_REQUIRED", "PHOTO_OPTIONAL", "NO_PHOTO"]
        for index, station in enumerate(stations):
            activity_id = str(station.get("ActivityID", ""))
            with st.container(border=True):
                header, action = st.columns([4, 1])
                header.markdown(f"### {station.get('DisplayOrder', index + 1)} · {station.get('DisplayName') or 'Untitled station'}")
                header.caption(f"{station.get('ShortCode', '')} · {station.get('ScoringMethod', '')} · {'Enabled' if station.get('Enabled') else 'Disabled'}")
                header.caption("Reference image: configured" if station.get("ImageReference") else "Reference image: none")
                if action.button("EDIT", key=f"race_edit_station:{activity_id}", disabled=stations_locked):
                    st.session_state[station_edit_key] = activity_id
                    editing_activity_id = activity_id
                if editing_activity_id != activity_id:
                    continue

                order_col, code_col = st.columns(2)
                display_order = order_col.number_input("Display Order", min_value=1, value=int(station.get("DisplayOrder", index + 1) or index + 1), key=f"race_station_order:{activity_id}")
                short_code = code_col.text_input("Short Code", value=str(station.get("ShortCode", "")), key=f"race_station_code:{activity_id}")
                display_name = st.text_input("Display Name", value=str(station.get("DisplayName", "")), key=f"race_station_name:{activity_id}")
                participant_instruction = st.text_area("Participant Instruction", value=str(station.get("ParticipantInstruction", "")), key=f"race_station_participant:{activity_id}")
                facilitator_instruction = st.text_area("Facilitator Instruction", value=str(station.get("FacilitatorInstruction", "")), key=f"race_station_facilitator:{activity_id}")
                method_col, evidence_col = st.columns(2)
                current_method = str(station.get("ScoringMethod", "FACILITATOR_SCORE"))
                scoring_method = method_col.selectbox("Scoring Method", scoring_options, index=scoring_options.index(current_method) if current_method in scoring_options else 0, key=f"race_station_method:{activity_id}")
                current_evidence = str(station.get("EvidenceRequirement", "PHOTO_OPTIONAL"))
                evidence_requirement = evidence_col.selectbox("Evidence Requirement", evidence_options, index=evidence_options.index(current_evidence) if current_evidence in evidence_options else 1, key=f"race_station_evidence:{activity_id}")
                result_col, credits_col = st.columns(2)
                result_label = result_col.text_input("Result Label", value=str(station.get("ResultLabel", "Result")), key=f"race_station_result_label:{activity_id}")
                result_unit = result_col.text_input("Result Unit", value=str(station.get("ResultUnit", "")), key=f"race_station_result_unit:{activity_id}")
                if scoring_method in {"LOWEST_TIME", "HIGHEST_COUNT", "SUCCESS_COUNT"}:
                    owners = ["FACILITATOR", "CAPTAIN"]
                    current_owner = str(station.get("ResultEntryOwner", "FACILITATOR")).upper()
                    result_entry_owner = result_col.selectbox("Official result entered by", owners, index=owners.index(current_owner) if current_owner in owners else 0, key=f"race_station_result_owner:{activity_id}")
                else:
                    result_entry_owner = "FACILITATOR"
                    if scoring_method == "FACILITATOR_SCORE":
                        result_col.caption("Official score is entered by the facilitator.")
                base_credits = credits_col.number_input("Base Credits", min_value=0, value=int(station.get("BaseCredits", 0) or 0), key=f"race_station_base_credits:{activity_id}")
                enabled = credits_col.checkbox("Enabled", value=bool(station.get("Enabled", True)), key=f"race_station_enabled:{activity_id}")
                performance = dict(station.get("PerformanceCredits", {}) or {})
                if scoring_method == "FACILITATOR_SCORE":
                    performance = {"PerScorePoint": st.number_input("Credits per score point", min_value=0, value=int(performance.get("PerScorePoint", 0) or 0), key=f"race_station_score_point_credits:{activity_id}")}
                elif scoring_method in {"LOWEST_TIME", "HIGHEST_COUNT"}:
                    st.caption("Performance Credits by finishing rank")
                    rank_columns = st.columns(3)
                    rank_credits = dict(performance.get("RankCredits", {}) or {})
                    for rank, column in enumerate(rank_columns, 1):
                        rank_credits[str(rank)] = column.number_input(f"Rank {rank} Credits", min_value=0, value=int(rank_credits.get(str(rank), 0) or 0), key=f"race_station_rank_{rank}:{activity_id}")
                    performance = {"RankCredits": rank_credits}
                elif scoring_method == "SUCCESS_COUNT":
                    performance = {"PerSuccess": st.number_input("Credits per success", min_value=0, value=int(performance.get("PerSuccess", 0) or 0), key=f"race_station_success_credits:{activity_id}")}
                else:
                    performance = {}
                reference_image = str(station.get("ImageReference", "") or "")
                reference_action_key = f"race_station_reference_action:{activity_id}"
                if reference_image:
                    reference_url = runtime.get_formula_race_station_reference_image_url(reference_image)
                    if reference_url:
                        st.image(reference_url, caption="Facilitator reference image", use_container_width=True)
                    reference_col, remove_col = st.columns(2)
                    if reference_col.button("CHANGE IMAGE", key=f"race_change_station_image:{activity_id}"):
                        st.session_state[reference_action_key] = "UPLOAD"
                    if remove_col.button("REMOVE IMAGE", key=f"race_remove_station_image:{activity_id}"):
                        stations[index] = normalise_station({**station, "ImageReference": ""})
                        st.session_state[reference_action_key] = ""
                        st.info("Reference image removed from the draft. Save station configuration to apply it.")
                        continue
                elif st.button("UPLOAD IMAGE", key=f"race_upload_station_image:{activity_id}"):
                    st.session_state[reference_action_key] = "UPLOAD"
                uploaded_reference = None
                if st.session_state.get(reference_action_key) == "UPLOAD":
                    uploaded_reference = st.file_uploader(
                        "Station reference image (facilitator instruction only)",
                        type=["jpg", "jpeg", "png", "webp", "heic"],
                        key=f"race_station_reference_file:{activity_id}",
                        help="Private event/station image. This is not Captain proof or participant evidence.",
                    )
                save_col, cancel_col, disable_col = st.columns(3)
                if save_col.button("SAVE", type="primary", key=f"race_save_station:{activity_id}", disabled=stations_locked):
                    if uploaded_reference is not None:
                        try:
                            reference_image = runtime.upload_formula_race_station_reference_image(
                                event_id, activity_id, uploaded_reference,
                            )
                            st.session_state[station_reference_uploads_key][reference_image] = activity_id
                        except (RuntimeError, ValueError) as error:
                            st.error(str(error))
                            continue
                    stations[index] = normalise_station({
                        **station,
                        "DisplayOrder": display_order,
                        "ShortCode": short_code,
                        "DisplayName": display_name,
                        "ParticipantInstruction": participant_instruction,
                        "FacilitatorInstruction": facilitator_instruction,
                        "ScoringMethod": scoring_method,
                        "ResultEntryOwner": result_entry_owner,
                        "ResultLabel": result_label,
                        "ResultUnit": result_unit,
                        "EvidenceRequirement": evidence_requirement,
                        "BaseCredits": base_credits,
                        "PerformanceCredits": performance,
                        "Enabled": enabled,
                        "ImageReference": reference_image,
                    })
                    st.session_state[station_edit_key] = ""
                    st.session_state[reference_action_key] = ""
                    st.success("Station draft updated. Save station configuration to publish it to this event.")
                if cancel_col.button("CANCEL", key=f"race_cancel_station:{activity_id}"):
                    st.session_state[station_edit_key] = ""
                if disable_col.button("DISABLE", key=f"race_disable_station:{activity_id}", disabled=stations_locked or not station.get("Enabled", True)):
                    stations[index] = normalise_station({**station, "Enabled": False})
                    st.session_state[station_edit_key] = ""
                    st.info("Station disabled in the draft. Save station configuration to apply this non-destructive change.")

        with st.expander("Preview pending station configuration", expanded=bool(stations)):
            st.dataframe(pd.DataFrame(stations)[["DisplayOrder", "ShortCode", "DisplayName", "ScoringMethod", "EvidenceRequirement", "BaseCredits", "Enabled"]] if stations else pd.DataFrame(), width="stretch", hide_index=True)
        save_col, cancel_col = st.columns(2)
        if save_col.button("SAVE STATION CONFIGURATION", type="primary", disabled=not actor or stations_locked):
            errors = validate_stations(stations)
            if errors:
                st.error(" ".join(errors))
            else:
                try:
                    runtime.save_formula_race_configuration(event_id, {"Stations": stations}, actor)
                    for station in stations:
                        activity_id = str(station.get("ActivityID", ""))
                        old_reference = original_station_references.get(activity_id, "")
                        new_reference = str(station.get("ImageReference", "") or "")
                        if old_reference and old_reference != new_reference:
                            runtime.delete_formula_race_station_reference_image(
                                event_id, activity_id, old_reference,
                            )
                    st.session_state.pop(station_draft_key, None)
                    st.session_state.pop(station_edit_key, None)
                    st.session_state.pop(station_reference_uploads_key, None)
                    _refresh_after_race_control_write()
                except RuntimeError as error:
                    st.error(str(error))
        if cancel_col.button("CANCEL STATION CHANGES", disabled=stations_locked):
            for reference, activity_id in st.session_state.get(station_reference_uploads_key, {}).items():
                runtime.delete_formula_race_station_reference_image(event_id, activity_id, reference)
            st.session_state.pop(station_draft_key, None)
            st.session_state.pop(station_edit_key, None)
            st.session_state.pop(station_reference_uploads_key, None)
            st.rerun()
    with tabs[1]:
        st.subheader("Team Routes editor")
        teams = _active_race_teams(runtime, event_id); ids = [str(team.get("TeamID", "")) for team in teams]; routes = config.get("TeamRoutes", {}) or {}
        enabled_stations = [row for row in stations if row.get("Enabled")]
        station_ids = [str(row.get("ActivityID", "")) for row in enabled_stations]
        station_labels = {str(row.get("ActivityID", "")): f"{row.get('ShortCode', '')} · {row.get('DisplayName', '')}" for row in enabled_stations}
        if hasattr(runtime, "get_formula_race_route_reconciliation_preview"):
            route_preview = runtime.get_formula_race_route_reconciliation_preview(event_id)
            if route_preview.get("NeedsReconciliation"):
                st.warning("Saved routes reference retired station IDs. This preview makes no changes; review each proposed route before explicitly saving a reconciliation.")
                st.dataframe(pd.DataFrame(route_preview.get("Teams", []))[[
                    "Team", "CurrentRouteActivityIDs", "ResolvedStationNames", "ExpectedRoute", "ProposedReplacementActivityIDs",
                ]], width="stretch", hide_index=True)
            else:
                st.caption("Route integrity check: all saved team routes resolve to the current canonical station ActivityIDs.")
        if st.button("GENERATE BALANCED ROUTES", disabled=not station_ids):
            st.session_state[f"race_planned_routes:{event_id}"] = generate_balanced_routes(ids, station_ids)
        routes = st.session_state.get(f"race_planned_routes:{event_id}", routes)
        saved = {}
        for team in teams:
            team_id = str(team.get("TeamID", ""))
            saved[team_id] = st.multiselect(
                f"Route for {team.get('TeamName', team_id)}",
                station_ids,
                default=[station_id for station_id in routes.get(team_id, []) if station_id in station_ids],
                format_func=lambda station_id: station_labels.get(station_id, station_id),
                key=f"race_route:{event_id}:{team_id}",
            )
        if st.button("SAVE TEAM ROUTES", type="primary", disabled=not actor):
            errors = validate_routes(saved, ids, station_ids)
            if errors:
                st.error(" ".join(errors))
            else:
                try:
                    runtime.save_formula_race_configuration(event_id, {"TeamRoutes": saved}, actor)
                    _refresh_after_race_control_write()
                except RuntimeError as error:
                    st.error(str(error))
    with tabs[2]:
        st.subheader("Parts Depot editor")
        st.caption("Add or edit event-scoped parts, credits and stock. Changes are previewed in this editable catalogue before saving.")
        items = [normalise_marketplace_item(row, index) for index, row in enumerate(config.get("Marketplace", []) or runtime._marketplace_payload(event_id, "", active_only=False).get("items", []), 1)]
        parts_draft_key = f"race_parts_draft:{event_id}"
        if parts_draft_key not in st.session_state:
            st.session_state[parts_draft_key] = items
        if st.button("ADD PART", key=f"race_add_part:{event_id}"):
            st.session_state[parts_draft_key].append(normalise_marketplace_item({
                "ItemID": f"{event_id}-ITEM-{uuid.uuid4().hex[:8].upper()}",
                "DisplayOrder": len(st.session_state[parts_draft_key]) + 1,
                "Category": "MATERIAL",
                "ItemName": "New part",
                "CreditCost": 0,
                "Enabled": True,
            }))
        items = st.session_state[parts_draft_key]
        editor = st.data_editor(pd.DataFrame(items), num_rows="dynamic", width="stretch", key="race_marketplace_editor")
        values = [{**row, "ItemID": str(row.get("ItemID", "")).strip() or f"{event_id}-ITEM-{index:02d}"} for index, row in enumerate(editor.to_dict("records"), 1)]
        st.download_button("Download marketplace template", pd.DataFrame(values).to_csv(index=False), "race-marketplace.csv", "text/csv")
        if st.button("SAVE MARKETPLACE", type="primary", disabled=not actor):
            errors = validate_marketplace_items(values)
            if errors: st.error(" ".join(errors))
            else:
                try:
                    runtime.save_formula_race_configuration(event_id, {"Marketplace": values}, actor)
                    st.session_state.pop(parts_draft_key, None)
                    _refresh_after_race_control_write()
                except RuntimeError as error:
                    st.error(str(error))
    with tabs[3]:
        st.subheader("Judging editor")
        st.caption("Add or edit judging criteria, descriptions, maximum scores and enabled state before saving.")
        criteria_draft_key = f"race_judging_draft:{event_id}"
        if criteria_draft_key not in st.session_state:
            st.session_state[criteria_draft_key] = config.get("JudgingCriteria", []) or [{"DisplayOrder": 1, "CriterionName": "", "Description": "", "MaximumScore": 10, "Enabled": True}]
        if st.button("ADD JUDGING CRITERION", key=f"race_add_judging:{event_id}"):
            st.session_state[criteria_draft_key].append({"DisplayOrder": len(st.session_state[criteria_draft_key]) + 1, "CriterionName": "", "Description": "", "MaximumScore": 10, "Enabled": True})
        criteria = st.data_editor(pd.DataFrame(st.session_state[criteria_draft_key]), num_rows="dynamic", width="stretch", key="race_judging_editor")
        st.download_button("Download judging template", criteria.to_csv(index=False), "race-judging.csv", "text/csv")
        if st.button("SAVE JUDGING CRITERIA", type="primary", disabled=not actor):
            try:
                runtime.save_formula_race_configuration(event_id, {"JudgingCriteria": criteria.to_dict("records")}, actor)
                st.session_state.pop(criteria_draft_key, None)
                _refresh_after_race_control_write()
            except RuntimeError as error:
                st.error(str(error))
    with tabs[4]:
        st.subheader("Championship Components")
        st.caption("Configure how official judging, Team Photo and final locked Drag Race results contribute Championship Points. Credits and Marketplace currency are not included.")
        components_key = f"race_championship_components:{event_id}"
        if components_key not in st.session_state:
            st.session_state[components_key] = normalise_championship_components(config.get("ChampionshipComponents", []))
        components = st.session_state[components_key]
        criteria_options = [str(row.get("CriterionName", "")) for row in config.get("JudgingCriteria", []) if row.get("Enabled", True) and str(row.get("CriterionName", ""))]
        if st.button("ADD CHAMPIONSHIP COMPONENT", key=f"race_add_championship_component:{event_id}"):
            components.append(normalise_championship_component({"DisplayOrder": len(components) + 1, "DisplayName": "New Championship Component", "ComponentType": "JUDGING_CRITERION", "MaximumChampionshipPoints": 0, "SourceReference": criteria_options[0] if criteria_options else "", "Enabled": True}))
        for index, component in enumerate(components):
            component_id = str(component.get("ComponentID", ""))
            with st.container(border=True):
                st.caption(f"Component {index + 1}")
                order_col, type_col = st.columns(2)
                order = order_col.number_input("Display Order", min_value=1, value=int(component.get("DisplayOrder", index + 1)), key=f"race_championship_order:{component_id}")
                component_type = type_col.selectbox("Component Type", COMPONENT_TYPES, index=COMPONENT_TYPES.index(str(component.get("ComponentType", "JUDGING_CRITERION"))) if str(component.get("ComponentType", "")) in COMPONENT_TYPES else 0, key=f"race_championship_type:{component_id}")
                display_name = st.text_input("Component Display Name", value=str(component.get("DisplayName", "")), key=f"race_championship_name:{component_id}")
                maximum = st.number_input("Maximum Championship Points", min_value=0.0, value=float(component.get("MaximumChampionshipPoints", 0) or 0), key=f"race_championship_max:{component_id}")
                enabled = st.checkbox("Enabled", value=bool(component.get("Enabled", True)), key=f"race_championship_enabled:{component_id}")
                source = "Race Final"
                scoring = dict(component.get("ScoringConfiguration", {}) or {})
                if component_type in {"JUDGING_CRITERION", "TEAM_PHOTO"}:
                    source = st.selectbox("Source Criterion", criteria_options or ["Configure a Judging criterion first"], index=(criteria_options.index(str(component.get("SourceReference", ""))) if str(component.get("SourceReference", "")) in criteria_options else 0), key=f"race_championship_source:{component_id}")
                else:
                    st.caption("Race Championship Points are awarded only from official final-locked Drag Race ranks.")
                    rank_points = dict(scoring.get("RankPoints", {}) or {})
                    for offset in range(0, 10, 5):
                        for rank, column in enumerate(st.columns(5), offset + 1):
                            rank_points[str(rank)] = column.number_input(f"Rank {rank} points", min_value=0.0, value=float(rank_points.get(str(rank), 0) or 0), key=f"race_championship_rank:{component_id}:{rank}")
                    scoring = {"RankPoints": rank_points}
                components[index] = normalise_championship_component({**component, "DisplayOrder": order, "ComponentType": component_type, "DisplayName": display_name, "MaximumChampionshipPoints": maximum, "Enabled": enabled, "SourceReference": source, "ScoringConfiguration": scoring})
        tie_break = st.selectbox("Overall Championship tie-break", TIE_BREAKS, index=TIE_BREAKS.index(str(config.get("ChampionshipTieBreak", "TEAM_ID"))) if str(config.get("ChampionshipTieBreak", "TEAM_ID")) in TIE_BREAKS else 1, help="RACE_RANK uses the final locked Drag Race position. TEAM_ID is the explicit deterministic fallback.")
        if st.button("SAVE CHAMPIONSHIP COMPONENTS", type="primary", disabled=not actor):
            errors = validate_championship_components(components, config.get("JudgingCriteria", []), len(_active_race_teams(runtime, event_id)))
            if errors:
                st.error(" ".join(errors))
            else:
                try:
                    runtime.save_formula_race_configuration(event_id, {"ChampionshipComponents": components, "ChampionshipTieBreak": tie_break}, actor)
                    st.session_state.pop(components_key, None)
                    _refresh_after_race_control_write()
                except RuntimeError as error:
                    st.error(str(error))
    with tabs[5]:
        teams = _active_race_teams(runtime, event_id)
        st.caption(f"Canonical active teams: {len(teams)}")
        if st.button("GENERATE / RESET CAPTAIN PINS", type="primary", disabled=not actor):
            if not teams or any(not str(team.get("TeamID", "")).strip() or not str(team.get("TeamName", "")).strip() for team in teams):
                st.error("Captain PIN generation requires canonical active teams with TeamID and Team Name.")
            else:
                pins = _generate_unique_captain_pin_rows(teams)
                for team, pin_row in zip(teams, pins):
                    runtime.set_team_pin(event_id, str(team.get("TeamID", "")), pin_row["Captain PIN"], actor)
                st.session_state["race_generated_pins"] = pins
        one_time_pins = st.session_state.pop("race_generated_pins", None)
        if one_time_pins:
            st.download_button("Download one-time Captain PIN list", pd.DataFrame(one_time_pins).to_csv(index=False), "captain-pins-once.csv", "text/csv")
            st.caption("PINs are available only in this generation result. Save the export now; plaintext PINs are not retained.")
    with tabs[6]:
        st.warning("Reset preserves event, teams, configuration, Marketplace catalogue, judging configuration and PIN credentials.")
        if event_id == _PROTECTED_RACE_UAT_EVENT_ID:
            st.subheader("Prepare Event for Configuration")
            st.info("The ordinary destructive reset remains protected. This one-time staging/UAT preparation action uses the certified migration-030 reset contract to clear transactional UAT state while preserving this event's identity, teams and Captain PIN credentials.")
            preview = runtime.get_formula_race_configuration_preparation_preview(event_id)
            st.dataframe([
                {"Preserved": "EventID", "Current": preview.get("EventID", "")},
                {"Preserved": "Join Code", "Current": preview.get("JoinCode", "")},
                {"Preserved": "Active Teams", "Current": preview.get("ActiveTeamCount", 0)},
                {"Preserved": "Active Captain PIN credentials", "Current": preview.get("CaptainPinCredentialCount", 0)},
                {"Cleared": "Canonical submissions", "Current": preview.get("CanonicalSubmissionCount", 0)},
                {"Cleared": "Marketplace purchases", "Current": preview.get("MarketplacePurchaseCount", 0)},
                {"Cleared": "Credit / wallet transactions", "Current": preview.get("CreditTransactionCount", 0)},
                {"Cleared": "Build state", "Current": preview.get("BuildStateCount", 0)},
                {"Cleared": "Judging results", "Current": preview.get("JudgingResultCount", 0)},
                {"Cleared": "Race results / final lock", "Current": preview.get("RaceResultCount", 0)},
            ], width="stretch", hide_index=True)
            expected_confirmation = f"PREPARE {_PROTECTED_RACE_UAT_EVENT_ID}"
            confirmation = st.text_input(f"Type {expected_confirmation}", key="race_configuration_preparation_confirmation")
            if not actor:
                st.info("Enter a Configuration Actor above before preparing this protected UAT event.")
            if st.button(
                "PREPARE EVENT FOR CONFIGURATION",
                type="primary",
                disabled=not actor or confirmation != expected_confirmation,
            ):
                if preview.get("JoinCode") != _PROTECTED_RACE_UAT_JOIN_CODE or preview.get("ActiveTeamCount") != 10 or preview.get("CaptainPinCredentialCount") != 10:
                    st.error("Preparation preflight failed: protected event identity, 10 active teams and 10 active Captain PIN credentials are required.")
                else:
                    try:
                        result = runtime.reset_formula_race_event(event_id, f"RESET {event_id}", actor)
                        after = runtime.get_formula_race_configuration_preparation_preview(event_id)
                        prepared = bool(
                            result.get("Reset")
                            and after.get("JoinCode") == _PROTECTED_RACE_UAT_JOIN_CODE
                            and after.get("ActiveTeamCount") == 10
                            and after.get("CaptainPinCredentialCount") == preview.get("CaptainPinCredentialCount")
                            and after.get("CanonicalSubmissionCount") == 0
                        )
                        if prepared:
                            st.success("Configuration preparation complete: transactional UAT state is cleared and station editing is unlocked.")
                            _refresh_after_race_control_write()
                        else:
                            st.error("Preparation reset completed but post-reset preservation verification did not pass. Do not continue configuration until reviewed.")
                    except RuntimeError as error:
                        st.error(str(error))
        else:
            confirmation = st.text_input(f"Type RESET {event_id}", key="race_reset_confirmation")
            if st.button("RESET DISPOSABLE RACE EVENT", type="primary", disabled=not actor or confirmation != f"RESET {event_id}"):
                runtime.reset_formula_race_event(event_id, confirmation, actor); _refresh_after_race_control_write()


def show_formula_race(db=None, event_id=""):
    _css()
    _staging_banner()
    try:
        db, runtime = _attach_runtime(db)
    except RuntimeError as error:
        st.error(f"Runtime unavailable: {error}")
        return
    if db is not None and hasattr(db, "__dict__"):
        db.runtime = runtime
    st.session_state.setdefault("race_join_code", "")
    st.session_state.setdefault("active_event_id", "")
    st.session_state.setdefault("race_nav", NAV[0])
    st.session_state.setdefault("race_subscreen", "")
    if st.session_state.get("race_nav") not in NAV:
        st.session_state["race_nav"] = NAV[0]

    requested_join_code = str(st.query_params.get("join_code", "")).strip()
    if requested_join_code:
        requested_join_code = _normalize_join_code(requested_join_code)
        cached_event_id = _cached_event_id_from_join_code(requested_join_code, _supabase_host(runtime))
        st.session_state.race_join_code = requested_join_code
        if cached_event_id:
            st.session_state.active_event_id = cached_event_id

    if event_id and event_id != st.session_state.get("active_event_id"):
        st.session_state.active_event_id = event_id

    if not event_id:
        event_id = st.session_state.get("active_event_id", "")
    try:
        snapshot = _snapshot(db, event_id)
        if _staging_runtime_enabled():
            _assert_staging_runtime_health(runtime)
    except RuntimeError as error:
        st.error(f"Staging contract violation: {error}")
        if _staging_runtime_enabled():
            if _staging_debug_enabled():
                _staging_diagnostics(runtime, requested_join_code, event_id)
        return

    if _staging_runtime_enabled() and hasattr(runtime, "get_staging_call_counts") and _staging_debug_enabled():
        counts = runtime.get_staging_call_counts()
        st.caption(
            f"LEGACY_RUNTIME_CALLS = {counts['LEGACY_RUNTIME_CALLS']} | "
            f"GOOGLE_SHEETS_RUNTIME_CALLS = {counts['GOOGLE_SHEETS_RUNTIME_CALLS']}"
        )
        _staging_diagnostics(runtime, requested_join_code, event_id)
    if _staging_runtime_enabled() and hasattr(runtime, "get_performance_report") and str(st.query_params.get("performance", "")).lower() in {"1", "true", "yes"}:
        st.dataframe(runtime.get_performance_report().get("Operations", []), width="stretch", hide_index=True)
    control = ControlRuntime(db) if db is not None else None
    page=_top(snapshot); sub=st.session_state.get("race_subscreen","")
    if sub=="wallet": wallet(snapshot)
    elif sub=="gallery": gallery(snapshot,runtime)
    elif page=="Overview": overview(snapshot)
    elif page=="Programme": live_programme(snapshot)
    elif page=="Championship":
        view=st.radio("Championship view",["Championship","Final Race Results"],horizontal=True,label_visibility="collapsed")
        drag_results(snapshot,control) if view=="Final Race Results" else championship(snapshot)
    elif page=="Teams": teams(snapshot)
    elif page=="Build": build_status(snapshot,control)
    elif page=="Reviews":
        view=st.radio("Review view",["Station Results", "Review Queue","Photo Gallery","Judging"],horizontal=True,label_visibility="collapsed")
        station_results(snapshot,control,runtime) if view=="Station Results" else (reviews(snapshot,control,runtime) if view=="Review Queue" else (gallery(snapshot,runtime) if view=="Photo Gallery" else judging(snapshot,control)))
    elif page=="Parts Depot":
        if snapshot.is_demo: marketplace(snapshot)
        else:
            _title("Canonical inventory and purchases", "Parts Depot", "Stock, purchases and credit spend are canonical marketplace projections. Lifecycle controls are in Control.")
            marketplace_state = runtime._marketplace_payload(snapshot.event_id, "", active_only=False)
            active = [row for row in marketplace_state.get("items", []) if row.get("Active")]
            st.metric("PARTS DEPOT", "OPEN" if active else "CLOSED")
            st.caption(f"Catalogue authority: {marketplace_state.get('CatalogueSource', 'unknown')}")
            st.dataframe([{"Item": row.get("ItemName", ""), "Credit Cost": row.get("CreditCost", 0), "Remaining": row.get("StockQuantity", "—"), "State": "OPEN" if row.get("Active") else "CLOSED"} for row in marketplace_state.get("items", [])], width="stretch", hide_index=True)
            st.subheader("Recent Purchases")
            st.dataframe([{"Team": next((team.name for team in snapshot.teams if team.id == row.get("TeamID")), "Team"), "Item": row.get("ItemName", ""), "Quantity": row.get("Quantity", 0), "Credits Spent": row.get("Amount", 0), "Status": row.get("Status", "")} for row in marketplace_state.get("purchases", [])], width="stretch", hide_index=True)
    elif page=="Race":
        view=st.radio("Race view",["Race Status","Race Results"],horizontal=True,label_visibility="collapsed")
        drag_results(snapshot,control) if view=="Race Results" else race_map(snapshot)
    elif page=="Event Setup":
        if snapshot.is_demo: st.info("Event Setup is available only for a selected live R.A.C.E. event.")
        else: event_setup(snapshot, runtime)
    else:
        control_centre(snapshot,control)
