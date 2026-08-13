"""Client-promised Formula R.A.C.E. product shell."""
from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse
import streamlit as st

from data.formula_race_contracts import DemoFormulaRaceProvider, LiveFormulaRaceProvider, RaceSnapshot, Team, Transaction, Submission
from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from data.runtime_database import get_runtime_database
from data.control_runtime import ControlRuntime
from engines.formula_race import BUILD_STATUSES,JUDGING_CATEGORIES,final_standings


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
                operations = db.runtime.get_formula_race_state(event_id) or {}
                operations["Checkpoints"] = db.runtime.get_formula_race_checkpoints(event_id)
            except Exception:
                operations = {}

        report = {}
        captain_status = {}
        if getattr(db.runtime, "can_publish", False):
            try:
                report = db.runtime.get_canonical_transaction_report(event_id) or {}
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
                str(row.get("TeamName", team_id)),
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


NAV = ["Overview", "Live Programme", "Championship", "Teams", "Checkpoints", "Reviews", "Marketplace", "Race Map", "Control Centre"]
MATERIALS = [("Cardboard sheet", 40), ("Wheel set", 120), ("Axle kit", 60), ("Glue sticks", 15)]
CRITERIA = [("Design & innovation", 25), ("Build quality", 25), ("Team identity", 20), ("Performance", 30)]


def _css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,600;0,700;0,800;1,800&family=Inter:wght@400;600;700&display=swap');
    :root{--navy:#071724;--panel:#0d2537;--line:#24465d;--red:#e31b23;--yellow:#f5c400;--blue:#19a8e7;--muted:#91a8b7}
    .stApp{background:linear-gradient(135deg,#06121d 0%,#0a1d2b 60%,#07131d 100%);color:#f7fafc;font-family:Inter,sans-serif}
    header[data-testid="stHeader"]{background:transparent}.block-container{max-width:1500px;padding:1rem 2rem 3rem}
    h1,h2,h3,.race-font{font-family:'Barlow Condensed',sans-serif!important;text-transform:uppercase;letter-spacing:.025em}
    h1{font-style:italic;font-weight:800!important;font-size:3.2rem!important;line-height:.9!important}
    h2{font-weight:800!important;border-left:5px solid var(--red);padding-left:.7rem}
    div[data-testid="stMetric"]{background:linear-gradient(145deg,#0e293c,#091d2b);border:1px solid var(--line);border-top:3px solid var(--red);padding:15px 18px;border-radius:4px}
    div[data-testid="stMetricLabel"]{text-transform:uppercase;color:var(--muted)} div[data-testid="stMetricValue"]{font-family:'Barlow Condensed';font-weight:800}
    .demo{display:inline-block;background:var(--yellow);color:#101820;padding:.22rem .6rem;border-radius:2px;font:800 .75rem Inter;letter-spacing:.12em}
    .status{display:inline-block;border:1px solid #31d17c;color:#31d17c;padding:.2rem .55rem;border-radius:20px;font-size:.74rem;font-weight:700}
    .race-card{background:linear-gradient(145deg,rgba(16,44,63,.94),rgba(8,27,40,.94));border:1px solid var(--line);border-radius:5px;padding:1rem 1.1rem;margin:.35rem 0;min-height:92px}
    .race-card h3{margin:0;color:white}.race-card p{color:var(--muted);margin:.25rem 0}.accent{color:var(--yellow);font-weight:800}.red{color:#ff4950}.muted{color:var(--muted)}
    .rank{font:800 2.1rem 'Barlow Condensed';color:var(--yellow);margin-right:1rem}.bar{height:7px;background:#17394d}.bar>i{display:block;height:7px;background:linear-gradient(90deg,var(--red),var(--yellow))}
    .ticker{border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:.55rem;color:#c5d4de;white-space:nowrap;overflow:hidden}
    div.stButton>button{border-radius:2px;text-transform:uppercase;font-family:'Barlow Condensed';font-weight:800;letter-spacing:.04em;min-height:42px}
    div[data-testid="stHorizontalBlock"]{gap:.75rem}
    [data-testid="stSidebar"]{min-width:17rem;max-width:19rem}
    @media(max-width:900px){.block-container{padding:.7rem 1rem 2rem}h1{font-size:2.3rem!important}.race-card{min-height:auto}}
    </style>""", unsafe_allow_html=True)


def _top(snapshot: RaceSnapshot):
    a,b,c = st.columns([5,2,2])
    with a: st.markdown("<div class='race-font' style='font-size:1.6rem;font-weight:800'>FORMULA <span class='red'>R.A.C.E.</span> <span class='muted'>/ RACE OPERATIONS</span></div>", unsafe_allow_html=True)
    badge = "DEMO DATA" if snapshot.is_demo else f"LIVE DATA · {snapshot.event_id}"
    with b: st.markdown(f"<span class='demo'>{badge}</span>", unsafe_allow_html=True)
    with c: st.markdown(f"<span class='status'>● {snapshot.race_status}</span>", unsafe_allow_html=True)
    selected = st.radio("Primary navigation", NAV, horizontal=True, label_visibility="collapsed", key="race_nav")
    st.markdown(f"<div class='ticker'>LIVE TELEMETRY &nbsp; ◆ &nbsp; {snapshot.active_checkpoint} &nbsp; ◆ &nbsp; ELAPSED {snapshot.elapsed} &nbsp; ◆ &nbsp; {len(snapshot.submissions)} SUBMISSIONS IN FEED</div>", unsafe_allow_html=True)
    return selected


def _title(kicker, title, copy=""):
    st.caption(kicker.upper())
    st.title(title)
    if copy: st.markdown(f"<p class='muted'>{copy}</p>", unsafe_allow_html=True)


def _team_rows(snapshot, limit=None):
    for t in snapshot.teams[:limit]:
        c1,c2,c3,c4 = st.columns([.6,4,1.2,1.2])
        c1.markdown(f"<span class='rank'>{t.rank:02}</span>", unsafe_allow_html=True)
        connection = "🟢 CONNECTED" if t.connected else "⚪ NOT CONNECTED"
        c2.markdown(f"<div><b>{t.name.upper()}</b> <span class='muted'>· {t.country}</span><br><small>{connection}</small><div class='bar'><i style='width:{t.build}%'></i></div></div>", unsafe_allow_html=True)
        c3.metric("Championship score", t.score)
        c4.metric("Wallet", t.balance)


def overview(s):
    _title("Mission AI powered race experience", "Race Control Overview", "One operational picture across programme, championship, submissions and supply.")
    pending=sum(1 for item in s.submissions if item.status.upper() in {"PENDING", "PENDING_REVIEW"})
    cols=st.columns(4)
    for col,(label,value,delta) in zip(cols,[
        ("Teams on track",len(s.teams),"Selected event"),
        ("Active checkpoint",s.active_checkpoint,"Runtime state"),
        ("Pending reviews",pending,"Canonical queue"),
        ("Transactions",len(s.transactions),"Immutable ledger"),
    ]): col.metric(label,value,delta)
    left,right=st.columns([1.45,1])
    with left:
        st.subheader("Live Championship"); _team_rows(s)
    with right:
        st.subheader("Recent Activity")
        for item in s.activity: st.markdown(f"<div class='race-card'>{item}</div>",unsafe_allow_html=True)
    c1,c2=st.columns(2)
    with c1:
        st.subheader("Review Queue")
        identities = {team.id: team.name for team in s.teams}
        for x in s.submissions[:2]: st.markdown(f"<div class='race-card'><h3>{x.checkpoint}</h3><p>{identities.get(x.team_id, x.team_id)} · {x.evidence} · {x.submitted_at}</p><span class='accent'>{x.status}</span></div>",unsafe_allow_html=True)
    with c2:
        st.subheader("System & Stock")
        for n,q in s.stock.items(): st.progress(min(q/70,1),text=f"{n} · {q} available")


def live_programme(s):
    _title("Formula R.A.C.E. / Programme Journey", "Build It. Race It. Win It.", "RACE Checkpoints is one module containing four concurrent activities.")
    checkpoint_state=s.operations.get("Checkpoints",{})
    checkpoint_pct=100*sum(x.status.upper()=="APPROVED" for x in s.submissions)/(max(len(s.teams)*4,1))
    stages=[("01","Launch EXOS",100),("02","RACE Checkpoints",checkpoint_pct),("03","Marketplace / Spend Credits",0),("04","Build",0),("05","Team Photo",0),("06","Drag Race",0),("07","Judging",0),("08","Championship",0)]
    for no,name,p in stages:
        live=name=="RACE Checkpoints" and str(checkpoint_state.get("Status","")).upper()=="LIVE"
        c1,c2,c3=st.columns([.7,4,1.2]); c1.markdown(f"<span class='rank'>{no}</span>",unsafe_allow_html=True); c2.markdown(f"### {name}"); c2.progress(min(float(p)/100,1.0)); c3.markdown("<span class='status'>ACTIVE</span>" if live else ("✓ COMPLETE" if p==100 else "READY"),unsafe_allow_html=True)
    if st.button("Open active checkpoint",type="primary",width="stretch"): st.session_state.race_nav="Checkpoints"; st.rerun()


def championship(s, final=False):
    _title("Official standings" if final else "Live timing", "Final Championship" if final else "Live Championship", "Canonical award-ledger projection when connected; demonstration standings shown now.")
    if final and not s.is_demo:
        rows=final_standings([{"TeamID":t.id,"TeamName":t.name} for t in s.teams],
            [{"TeamID":x.team_id,"Amount":x.amount} for x in s.transactions],s.operations.get("Judging",[]),s.operations.get("RaceResults",[]),s.operations.get("Config",{}))
        st.dataframe(rows,width="stretch",hide_index=True)
    else: _team_rows(s)
    st.subheader("Score Breakdown")
    st.dataframe([{"Team":t.name,"Checkpoints":round(t.score*.52),"Judging":round(t.score*.31),"Drag Race":round(t.score*.17),"Total":t.score} for t in s.teams],width="stretch",hide_index=True)
    if final: st.success("Championship lock is available from Control Centre after canonical scoring reconciliation.")


def teams(s):
    _title("Paddock", "Teams", "Identity, build readiness and wallet position in one view.")
    for t in s.teams:
        with st.expander(f"#{t.rank:02}  {t.name.upper()} · {t.country}"):
            c1,c2,c3=st.columns(3); c1.metric("Championship",t.score); c2.metric("Wallet",f"{t.balance} CR"); c3.metric("Build",f"{t.build}%")
            if st.button("Open team wallet",key=f"wallet_{t.id}"): st.session_state.selected_team=t.id; st.session_state.race_subscreen="wallet"; st.rerun()


def wallet(s):
    team=next((t for t in s.teams if t.id==st.session_state.get("selected_team")),s.teams[0])
    _title(f"{team.country} / Rank #{team.rank}", f"{team.name} Team Wallet", "Ledger projection: credits are not calculated or persisted by this screen.")
    a,b,c,d=st.columns(4); a.metric("Current balance",f"{team.balance} CR"); b.metric("Earned","650 CR"); c.metric("Bonuses","75 CR"); d.metric("Spend","−145 CR")
    st.subheader("Transaction Timeline")
    st.dataframe([x.__dict__ for x in s.transactions if x.team_id==team.id] or [s.transactions[0].__dict__],width="stretch",hide_index=True)
    st.subheader("Achievements"); st.markdown("🏆 **Safety First** &nbsp;&nbsp; ⚡ **Fast Submitter** &nbsp;&nbsp; 🔧 **Master Builder**")
    if st.button("Back to teams"): st.session_state.race_subscreen=""; st.rerun()


def checkpoints(s):
    _title("Parallel Activity Set", "RACE Checkpoints", "All four remain available concurrently until the module is closed.")
    definitions=s.operations.get("Checkpoints",{}).get("Checkpoints",[])
    approved={(x.team_id,x.checkpoint) for x in s.submissions if x.status.upper()=="APPROVED"}
    pending=sum(x.status.upper() in {"PENDING","PENDING_REVIEW"} for x in s.submissions)
    rows=[]
    for team in s.teams:
        complete=sum(any(team.id==team_id and (str(cp.get("Name",""))==checkpoint or str(cp.get("ActivityID",""))==checkpoint) for team_id,checkpoint in approved) for cp in definitions)
        rows.append({"Team":team.name,"Completed":f"{complete}/4","Pending Reviews":sum(x.team_id==team.id and x.status.upper() in {"PENDING","PENDING_REVIEW"} for x in s.submissions),"Credits":team.balance})
    leader=max(rows,key=lambda row:row["Credits"])["Team"] if rows else "—"
    a,b,c=st.columns(3);a.metric("Teams",len(s.teams));b.metric("Pending reviews",pending);c.metric("Current leader",leader)
    st.dataframe(rows,width="stretch",hide_index=True)
    if st.button("Open Control Centre",type="primary",width="stretch"): st.session_state.race_nav="Control Centre"; st.rerun()


def reviews(s, control=None, runtime=None):
    _title("Submission and Award Pipeline", "RACE Review Queue", "Approve through the canonical review and CreditTransaction pipeline.")
    team_identity={team.id:team.name for team in s.teams}
    for x in s.submissions:
        with st.container(border=True):
            c1,c2=st.columns([4,1]); c1.markdown(f"### {x.checkpoint}\n{team_identity.get(x.team_id,x.team_id)} · {x.evidence} · submitted {x.submitted_at}"); c2.markdown(f"**{x.status}**")
            evidence_url = _resolve_race_private_evidence(runtime, x.evidence) if runtime else ""
            if evidence_url:
                st.image(evidence_url, caption=f"{team_identity.get(x.team_id, x.team_id)} · {x.checkpoint}", use_container_width=True)
            elif str(x.evidence).startswith(_RACE_EVIDENCE_PREFIX):
                st.warning("Private photo evidence is unavailable.")
            actor=st.text_input("Facilitator identity",key=f"review_actor_{x.id}") if control else ""
            notes=st.text_input("Notes / rejection reason",key=f"review_notes_{x.id}") if control else ""
            pending=x.status.upper() in {"PENDING","PENDING_REVIEW","SUBMITTED"}
            def decide(decision):
                control.review_race_checkpoint(x.id,decision,actor,notes,notes,f"{x.id}:{decision}")
                st.success("Review saved and projections updated.");st.rerun()
            a,b,c=st.columns(3)
            if a.button("APPROVE",key=f"award_{x.id}",disabled=not pending or bool(control and not actor)):
                decide("APPROVE") if control else st.toast(f"Demo approval for {x.id}")
            if b.button("REQUEST RESUBMISSION",key=f"revise_{x.id}",disabled=not pending or bool(control and not actor)):
                decide("REQUEST_RESUBMISSION") if control else st.toast(f"Demo revision for {x.id}")
            if c.button("REJECT",key=f"reject_{x.id}",disabled=not pending or bool(control and not actor)):
                decide("REJECT") if control else st.toast(f"Demo rejection for {x.id}")
    if st.button("Open team photo gallery",width="stretch"): st.session_state.race_subscreen="gallery"; st.rerun()


def gallery(s, runtime=None):
    _title("Evidence", "Team Photo Gallery", "Review checkpoint evidence by team.")
    for row in range(2):
        cols=st.columns(3)
        for col,t in zip(cols,s.teams[row*3:row*3+3]):
            col.markdown(f"<div class='race-card'><h3>{t.name}</h3><p>Checkpoint build evidence</p></div>",unsafe_allow_html=True)
            evidence = [x for x in s.submissions if x.team_id == t.id and str(x.evidence).startswith(_RACE_EVIDENCE_PREFIX)]
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
    _title("Build Materials Depot", "Pit-Lane Marketplace", "Purchases remain local demo cart actions until canonical Award Transaction spend is connected.")
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
    _title("Official Scoring", "Judging", "Weighted scoring contract prepared for canonical Judge Score and scoring configuration.")
    names=[t.name for t in s.teams]; idx=names.index(st.session_state.get("judge_team",names[0])); team=st.selectbox("Select team",names,index=idx,key="judge_team")
    p,n=st.columns(2)
    if p.button("← Previous team",width="stretch"): st.session_state.judge_team=names[(names.index(team)-1)%len(names)]; st.rerun()
    if n.button("Next team →",width="stretch"): st.session_state.judge_team=names[(names.index(team)+1)%len(names)]; st.rerun()
    total=0.0
    categories=JUDGING_CATEGORIES if control else tuple(name for name,_ in CRITERIA)
    scores={}
    for criterion in categories:
        score=st.slider(criterion,0,10,7,key=f"score_{team}_{criterion}");scores[criterion]=score;total+=score
    st.metric("Total score",f"{total:.1f}"); st.progress((names.index(team)+1)/len(names),text=f"Judging progress · {names.index(team)+1} of {len(names)} teams")
    actor=st.text_input("Facilitator identity",key="race_judge_actor") if control else ""
    reason=st.text_input("Submission or correction reason",key="race_judge_reason") if control else ""
    if st.button("Submit score",type="primary",width="stretch",disabled=bool(control and (not actor or not reason))):
        if control:
            selected=next(t for t in s.teams if t.name==team);control.save_race_judging(s.event_id,selected.id,scores,reason,actor);st.success("Judging score saved with audit history.")
        else: st.session_state.judge_confirm=f"Demo score {total:.1f} prepared for {team}"
    if st.session_state.get("judge_confirm"): st.success(st.session_state.judge_confirm+". No canonical Judge Score was written.")


def drag_results(s, control=None):
    _title("Official Timing", "Drag Race Results", "Heat results and fastest-lap bonus projection.")
    live_rows=s.operations.get("RaceResults",[]) if control else []
    rows=[]
    for i,t in enumerate(s.teams):
        live=next((r for r in live_rows if str(r.get("team_id",""))==t.id),{})
        rows.append({"Pos":live.get("position",i+1),"Team":t.name,"Time ms":live.get("time_ms",live.get("finish_time_ms","—")),"Penalty ms":live.get("penalty_ms",0),"Bonus":live.get("bonus_credits",0),"Verified":live.get("verified",False),"Locked":live.get("locked",False)})
    st.dataframe(rows,width="stretch",hide_index=True)
    if not control: st.markdown("<div class='race-card'><h3>Fastest Lap</h3><p>Velocity · 12.18 seconds</p><span class='accent'>+25 BONUS POINTS</span></div>",unsafe_allow_html=True)
    if control:
        team=st.selectbox("Result team",[t.name for t in s.teams]);time_ms=st.number_input("Finish time (ms)",0,3600000,0);penalty=st.number_input("Penalty (ms)",0,3600000,0);bonus=st.number_input("Bonus credits",0,1000,0);verified=st.checkbox("Verified")
        actor=st.text_input("Facilitator identity",key="race_result_actor");reason=st.text_input("Result or correction reason",key="race_result_reason")
        if st.button("Save Race Result",disabled=not actor or not reason,width="stretch"):
            selected=next(t for t in s.teams if t.name==team);control.save_race_result(s.event_id,selected.id,time_ms,penalty,bonus,verified,reason,actor);st.success("Race result saved with audit history.")
        if st.button("LOCK FINAL RESULTS",type="primary",disabled=not actor or not reason,width="stretch"):
            control.lock_race_results(s.event_id,actor,reason);st.success("Final race positions are locked.");st.rerun()


def build_status(s, control=None):
    _title("Engineering Readiness", "Build Status", "Materials, structural checkpoints and race-readiness by team.")
    live={str(r.get("team_id","")):r for r in s.operations.get("BuildStatus",[])}
    for t in s.teams:
        status=str(live.get(t.id,{}).get("status","Not Started"));pct=BUILD_STATUSES.index(status)*20 if status in BUILD_STATUSES else 0
        c1,c2,c3=st.columns([2,5,1]); c1.markdown(f"**{t.name.upper()}**\n\n{t.country}"); c2.progress(pct/100,text=f"{status} · {pct}%"); c3.markdown("READY" if status in {"Ready to Race","Completed"} else "ACTIVE")
    if control:
        team=st.selectbox("Update team",[t.name for t in s.teams],key="build_team");status=st.selectbox("Build status",BUILD_STATUSES);actor=st.text_input("Facilitator identity",key="build_actor");reason=st.text_input("Required reason",key="build_reason")
        if st.button("Update Build Status",disabled=not actor or not reason,width="stretch"):
            selected=next(t for t in s.teams if t.name==team);control.set_race_build_status(s.event_id,selected.id,status,{},reason,actor);st.success("Build status saved and audited.")


def control_centre(s, control=None):
    _title("Canonical Runtime Facade", "Race Control Centre", "Operational controls are arranged for tablet use. Demo mode never mutates EXOS runtime.")
    checkpoint_state=s.operations.get("Checkpoints",{})
    module_id=str(checkpoint_state.get("ModuleID",f"{s.event_id}-RACE-CHECKPOINTS"))
    checkpoint=st.selectbox("RACE checkpoint module",["RACE Checkpoints"])
    st.caption(f"Selected: {checkpoint} · {checkpoint_state.get('Status','READY')} · four parallel activities")
    def action(label,key,kind="secondary"):
        if st.button(label,key=key,type=kind,width="stretch"): st.toast(f"DEMO ONLY · {label} acknowledged locally")
    actor=st.text_input("Facilitator identity",key="race_control_actor") if control else ""
    def runtime_action(label,action_name,key,kind="secondary"):
        if st.button(label,key=key,type=kind,width="stretch",disabled=bool(control and not actor)):
            if control:
                control.set_race_checkpoint_runtime(s.event_id,module_id,action_name,actor)
                st.success(f"{label} complete.");st.rerun()
            else: st.toast(f"DEMO ONLY · {label}")
    a,b,c=st.columns(3)
    with a: runtime_action("LAUNCH CHECKPOINTS","LAUNCH","launch","primary")
    with b: runtime_action("PAUSE CHECKPOINTS","PAUSE","pause")
    with c: runtime_action("CLOSE CHECKPOINTS","CLOSE","close")
    st.subheader("Marketplace")
    marketplace = control.runtime._marketplace_payload(s.event_id, "", active_only=False) if control else {"items": []}
    active_items = [item for item in marketplace.get("items", []) if item.get("Active")]
    st.caption(f"{len(active_items)} active of {len(marketplace.get('items', []))} configured items")
    def marketplace_action(label, action_name, key, kind="secondary"):
        if st.button(label, key=key, type=kind, width="stretch", disabled=bool(control and not actor)):
            if control:
                control.set_race_marketplace_runtime(s.event_id, action_name, actor)
                st.success(f"{label} complete."); st.rerun()
            else: st.toast(f"DEMO ONLY · {label}")
    a,b,c=st.columns(3)
    with a: marketplace_action("OPEN MARKETPLACE", "OPEN", "marketplace_open", "primary")
    with b: marketplace_action("PAUSE MARKETPLACE", "PAUSE", "marketplace_pause")
    with c: marketplace_action("CLOSE MARKETPLACE", "CLOSE", "marketplace_close")
    if marketplace.get("items"):
        st.dataframe(marketplace["items"], width="stretch", hide_index=True)
    a,b,c=st.columns(3)
    with a: action("Resume race","resume")
    with b: action("Review submissions","review")
    with c: action("Emergency stop","emergency")
    st.subheader("Broadcast Message"); msg=st.text_input("Message",placeholder="Message all participant and projector views")
    if st.button("Broadcast",disabled=not msg,width="stretch"): st.toast("DEMO ONLY · broadcast previewed")
    st.subheader("Recovery & Manual Operations")
    t1,t2,t3=st.tabs(["Participant Recovery","Leader Recovery","Manual Credit Adjustment"])
    with t1: st.text_input("Participant ID"); action("Recover participant","recover_participant")
    with t2: st.selectbox("Team",[t.name for t in s.teams],key="leader_team"); action("Recover leader","recover_leader")
    with t3:
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
                st.session_state.pop(key_name,None);st.rerun()
            except (RuntimeError, ValueError) as error:
                st.error(str(error))
        adjustments=[x.__dict__ for x in s.transactions if x.kind=="MANUAL_ADJUSTMENT"]
        if adjustments:
            st.dataframe(adjustments,width="stretch",hide_index=True)
        else:
            st.caption("No manual credit adjustments recorded for this event.")
    if not control: st.warning("DEMO DATA · No live mutation is performed.")


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
    control = ControlRuntime(db) if db is not None else None
    page=_top(snapshot); sub=st.session_state.get("race_subscreen","")
    if sub=="wallet": wallet(snapshot)
    elif sub=="gallery": gallery(snapshot,runtime)
    elif page=="Overview": overview(snapshot)
    elif page=="Live Programme": live_programme(snapshot)
    elif page=="Championship":
        view=st.radio("Championship view",["Live Championship","Drag Race Results","Final Championship"],horizontal=True,label_visibility="collapsed")
        drag_results(snapshot,control) if view=="Drag Race Results" else championship(snapshot,view=="Final Championship")
    elif page=="Teams": teams(snapshot)
    elif page=="Checkpoints":
        view=st.radio("Checkpoint view",["Checkpoint Control","Build Status"],horizontal=True,label_visibility="collapsed")
        checkpoints(snapshot) if view=="Checkpoint Control" else build_status(snapshot,control)
    elif page=="Reviews":
        view=st.radio("Review view",["Review Queue","Photo Gallery","Judging"],horizontal=True,label_visibility="collapsed")
        reviews(snapshot,control,runtime) if view=="Review Queue" else (gallery(snapshot,runtime) if view=="Photo Gallery" else judging(snapshot,control))
    elif page=="Marketplace":
        if snapshot.is_demo: marketplace(snapshot)
        else:
            _title("Canonical marketplace", "Build Materials Depot", "Live purchases, stock deduction and overspend prevention are recorded through the R.A.C.E. marketplace ledger.")
            marketplace_state = runtime._marketplace_payload(snapshot.event_id, "", active_only=False)
            st.dataframe(marketplace_state.get("items", []), width="stretch", hide_index=True)
            st.dataframe(marketplace_state.get("purchases", []), width="stretch", hide_index=True)
            st.caption("Open, pause, or close the marketplace in Race Control Centre.")
    elif page=="Race Map": race_map(snapshot)
    else:
        control_centre(snapshot,control)
