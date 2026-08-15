from __future__ import annotations

import uuid
import html
import io
import os
import json
from time import perf_counter
from pathlib import Path
from typing import Any
import streamlit as st

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from data.runtime_database import RuntimeDatabaseError, get_runtime_database

ASSET_ROOT=Path(__file__).resolve().parents[1]/"Assets"/"race_teams"
TEAM_ASSETS=json.loads((ASSET_ROOT/"manifest.json").read_text())


def _race_css() -> None:
    """Inject the Captain-only R.A.C.E. presentation layer.

    This deliberately scopes the experience to the dedicated Captain surface;
    Standard EXOS pages must retain their frozen visual language.
    """
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,600;0,700;0,800;1,800&family=Inter:wght@400;500;600;700&display=swap');
    :root { --race-ink:#071017; --race-panel:#0d1922; --race-panel-2:#101f2a; --race-line:#263846; --race-red:#ed3139; --race-amber:#f7b733; --race-green:#4dd38a; --race-blue:#43b6e8; --race-muted:#9eabb6; }
    .stApp { background:radial-gradient(circle at 82% -8%,#18384a 0,transparent 28%),linear-gradient(145deg,#071017 0%,#0a151d 55%,#071017 100%); color:#f5f7f8; font-family:Inter,system-ui,sans-serif; }
    .block-container { max-width:1120px; padding:1rem 1rem 3.5rem; }
    [data-testid="stHeader"] { background:transparent; }
    .race-shell { max-width:920px; margin:0 auto; }
    .race-kicker,.race-overline { color:var(--race-amber); font:800 .70rem/1 Inter,sans-serif; letter-spacing:.15em; text-transform:uppercase; }
    .race-wordmark,.race-team-name,.race-panel-title { font-family:'Barlow Condensed',Impact,sans-serif; text-transform:uppercase; letter-spacing:.03em; }
    .race-wordmark { font-size:1.55rem; font-weight:800; line-height:1; }.race-wordmark b{color:var(--race-red)}
    .race-team-name { margin:.22rem 0 0; font-size:2.25rem; font-weight:800; line-height:.88; color:#fff; overflow-wrap:anywhere; }
    .race-subtle { color:var(--race-muted); font-size:.82rem; }
    .race-login,.race-panel,.race-metric,.race-checkpoint,.race-store-item { border:1px solid var(--race-line); background:linear-gradient(145deg,rgba(18,34,45,.96),rgba(9,18,25,.96)); border-radius:12px; }
    .race-login { max-width:530px; margin:8vh auto 0; padding:1.35rem; }.race-login h1{font:800 3.3rem/.82 'Barlow Condensed',Impact,sans-serif;margin:.4rem 0 1rem;text-transform:uppercase}.race-login h1 b{color:var(--race-red)}
    .race-header { display:flex; align-items:flex-end; justify-content:space-between; gap:1rem; margin:.5rem 0 1rem; }.race-live{color:var(--race-green);font-weight:800;font-size:.72rem;letter-spacing:.08em;white-space:nowrap}
    .race-metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.55rem; margin:.7rem 0 1rem; }
    .race-metric { padding:.7rem .75rem; min-width:0; border-top:3px solid var(--race-line); }.race-metric.accent{border-top-color:var(--race-red)} .race-metric strong{display:block;overflow-wrap:anywhere;color:#fff;font:800 1.8rem/.86 'Barlow Condensed',Impact,sans-serif;letter-spacing:.02em}.race-metric small{display:block;margin-bottom:.22rem;color:var(--race-muted);font:700 .62rem Inter,sans-serif;letter-spacing:.1em;text-transform:uppercase}
    .race-panel { padding:1rem; margin:.75rem 0; }.race-panel-title{font-size:1.4rem;font-weight:800;margin:0 0 .25rem}.race-checkpoint{padding:.85rem;margin:.55rem 0;border-left:4px solid var(--race-line)}.race-checkpoint.current{border-left-color:var(--race-red);box-shadow:0 0 0 1px rgba(237,49,57,.14)}.race-checkpoint.complete{opacity:.65}.race-checkpoint h3,.race-store-item h3{font:800 1.2rem/1 'Barlow Condensed',Impact,sans-serif;text-transform:uppercase;margin:.2rem 0}.race-checkpoint p{margin:.35rem 0;color:var(--race-muted);font-size:.86rem}.race-status{display:inline-block;padding:.22rem .45rem;border:1px solid var(--race-line);border-radius:999px;color:#c9d3da;font:800 .62rem Inter,sans-serif;letter-spacing:.09em}.race-status.active,.race-status.available{color:var(--race-amber);border-color:rgba(247,183,51,.55)}.race-status.approved{color:var(--race-green);border-color:rgba(77,211,138,.55)}.race-status.review,.race-status.submitted{color:var(--race-blue);border-color:rgba(67,182,232,.55)}.race-status.rejected{color:#ff8a8e;border-color:rgba(237,49,57,.55)}
    .race-store-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem; }.race-store-item{padding:.85rem}.race-cost{color:var(--race-amber);font:800 1.45rem 'Barlow Condensed',Impact,sans-serif}.race-note{padding:.7rem .8rem;border-left:3px solid var(--race-blue);background:rgba(67,182,232,.09);color:#d8e8f0;font-size:.86rem}
    div[data-testid="stRadio"] > div { gap:.35rem; } div[data-testid="stRadio"] label { flex:1;justify-content:center;margin:0!important;border:1px solid var(--race-line);border-radius:8px;padding:.42rem .25rem;background:rgba(10,23,32,.7);font-size:.76rem;font-weight:800;letter-spacing:.04em; } div[data-testid="stRadio"] label:has(input:checked){border-color:var(--race-red);background:rgba(237,49,57,.13)}
    div.stButton>button,div[data-testid="stFormSubmitButton"]>button { min-height:44px;border-radius:7px;text-transform:uppercase;font-weight:800;letter-spacing:.04em; } div[data-testid="stMetric"]{background:transparent;border:0;padding:0} [data-testid="stMetricLabel"]{color:var(--race-muted)}
    @media (max-width:600px) { .block-container{padding:.65rem .7rem 3rem}.race-header{align-items:flex-start;flex-direction:column;gap:.35rem}.race-team-name{font-size:2rem}.race-metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.race-store-grid{grid-template-columns:1fr}.race-login{margin:3vh auto 0;padding:1rem}.race-login h1{font-size:2.7rem} }
    </style>
    """, unsafe_allow_html=True)


def _display_number(value: Any, empty: str = "—") -> str:
    if value is None or value == "":
        return empty
    try:
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:,.1f}"
    except (TypeError, ValueError):
        return str(value)


def _status_copy(value: Any) -> str:
    raw = str(value or "AVAILABLE").strip().upper().replace("_", " ")
    aliases = {"UNDER REVIEW": "AWAITING REVIEW", "REVIEW": "AWAITING REVIEW", "PENDING": "AWAITING REVIEW", "NOT STARTED": "NOT STARTED", "READY": "AVAILABLE"}
    return aliases.get(raw, raw)


def _status_class(value: str) -> str:
    lower = value.lower()
    if "approve" in lower: return "approved"
    if "review" in lower or "await" in lower: return "review"
    if "submit" in lower: return "submitted"
    if "reject" in lower or "resubmit" in lower: return "rejected"
    if "active" in lower: return "active"
    if "available" in lower: return "available"
    return "locked"


def _captain_error(error: Exception, item: dict[str, Any] | None = None, balance: Any = None) -> str:
    message = str(error).lower()
    if "insufficient credit" in message:
        cost = _display_number((item or {}).get("CreditCost", 0), "0")
        wallet = _display_number(balance, "0")
        try:
            shortage = max(0, float((item or {}).get("CreditCost", 0) or 0) - float(balance or 0))
            shortage_copy = _display_number(shortage, "0")
        except (TypeError, ValueError):
            shortage_copy = "more"
        return f"NOT ENOUGH CREDITS · This item costs {cost}. Your wallet has {wallet}. You need {shortage_copy} more."
    if "insufficient stock" in message:
        return "This part is no longer available in the required quantity."
    if "invalid pin" in message:
        return "The team PIN is incorrect."
    if "session" in message:
        return "Your captain session has expired. Sign in again."
    return "That action could not be completed. Please try again or speak to Race Control."


def _is_valid_session_token(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        parsed = uuid.UUID(raw)
        return str(parsed) == raw.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _normalise_session_token(value) -> str:
    raw = str(value or "").strip()
    return raw if _is_valid_session_token(raw) else ""


def _staging_mode() -> bool:
    return str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging"


def _normalise_session_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    token = _normalise_session_token(payload.get("SessionToken", payload.get("session_token")))
    event_id = str(payload.get("EventID", payload.get("event_id", ""))).strip()
    team_id = str(payload.get("TeamID", payload.get("team_id", ""))).strip()
    if not token or not event_id or not team_id:
        return None
    if bool(payload.get("Ambiguous")) or bool(payload.get("RecoveryRequired")):
        return None
    return {
        "SessionToken": token,
        "EventID": event_id,
        "TeamID": team_id,
        "TeamName": str(payload.get("TeamName", "")),
        "Ambiguous": False,
        "RecoveryRequired": False,
    }


def _clear_captain_query_param() -> None:
    st.query_params.pop("captain_session", None)
    if "captain_session" in st.query_params:
        st.query_params["captain_session"] = ""


def _clear_captain_state() -> None:
    st.session_state.pop("race_captain", None)
    _clear_captain_query_param()


def _write_captain_session_param(token: str) -> None:
    normalised = _normalise_session_token(token)
    if not normalised:
        _clear_captain_query_param()
        return
    st.query_params["captain_session"] = normalised


def _device_id():
    value=str(st.session_state.get("race_captain_device_id", ""))
    if not _is_valid_session_token(value):
        value=_normalise_session_token(st.query_params.get("captain_device", ""))
    if not value:
        value=str(uuid.uuid4())
    st.session_state["race_captain_device_id"]=value
    st.query_params["captain_device"]=value
    return value


def _submission_idempotency_key(event_id: str, team_id: str, activity_id: str) -> str:
    key_name=f"race_submission_key:{event_id}:{team_id}:{activity_id}"
    key=str(st.session_state.get(key_name,""))
    if not key:
        key=f"race-captain-submit:{event_id}:{team_id}:{activity_id}:{uuid.uuid4()}"
        st.session_state[key_name]=key
    return key


def _purchase_idempotency_key(event_id: str, team_id: str, item_id: str, quantity: int) -> str:
    key_name=f"race_purchase_key:{event_id}:{team_id}:{item_id}:{int(quantity)}"
    key=str(st.session_state.get(key_name,""))
    if not key:
        key=f"race-captain-purchase:{event_id}:{team_id}:{item_id}:{int(quantity)}:{uuid.uuid4()}"
        st.session_state[key_name]=key
    return key


def _optimise_race_photo(uploaded) -> tuple[bytes, str, dict[str, Any]]:
    raw = uploaded.getvalue()
    details: dict[str, Any] = {"OriginalBytes": len(raw), "UploadBytes": len(raw), "Optimised": False}
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1600, 1600))
            if image.mode != "RGB":
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
                image = background
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            compressed = output.getvalue()
        if len(compressed) < len(raw):
            details.update({"UploadBytes": len(compressed), "Optimised": True})
            return compressed, "image/jpeg", details
    except Exception:
        pass
    return raw, uploaded.type or "image/jpeg", details

def _set_session(payload):
    normalised_session = _normalise_session_payload(payload)
    if not normalised_session:
        raise RuntimeError("Invalid captain login payload.")
    st.session_state["race_captain"] = normalised_session
    st.session_state.pop("race_captain_recovery", None)
    st.query_params["race"] = "1"
    token = normalised_session.get("SessionToken", "")
    if _staging_mode():
        print(
            f"CAPTAIN UUID TRACE | _set_session | rpc/table: captain_session | field: SessionToken | "
            f"is_none: {payload.get('SessionToken') is None} | is_literal_none: {str(payload.get('SessionToken')).strip().lower() == 'none'} | "
            f"is_valid_uuid: {bool(_is_valid_session_token(payload.get('SessionToken')))}"
        )
    _write_captain_session_param(token)


def _is_staging_mode() -> bool:
    return _staging_mode()


def _build_runtime(runtime_override=None):
    runtime = runtime_override or get_runtime_database()
    if not _staging_mode():
        return runtime
    return FormulaRaceCoreV2StagingAdapter(runtime)

def show_formula_race_captain(runtime_override=None):
    _race_css()
    runtime = _build_runtime(runtime_override)
    if _staging_mode() and not runtime.can_publish:
        st.error("Core v2 staging runtime is unavailable.")
        return
    if _staging_mode() and hasattr(runtime, "_assert_no_legacy_or_sheet_calls"):
        try:
            runtime._assert_no_legacy_or_sheet_calls()
        except RuntimeError as error:
            st.error(str(error))
            return
    if _staging_mode():
        st.caption("EXOS CORE V2 — STAGING")
    device=_device_id();raw_session=st.session_state.get("race_captain")
    token=str(st.query_params.get("captain_session",""))
    if _staging_mode():
        raw_token = token
        is_none = raw_token is None
        is_literal_none = str(raw_token).strip().lower() == "none"
        normalised = _normalise_session_token(raw_token)
        print(
            f"CAPTAIN UUID TRACE | captain_session_query_param | rpc/table: query_params | field: captain_session | "
            f"is_none: {is_none} | is_literal_none: {is_literal_none} | is_valid_uuid: {bool(normalised)}"
        )
    token=_normalise_session_token(token)
    session = _normalise_session_payload(raw_session)
    if raw_session is not None and not session:
        _clear_captain_state()
    if "captain_session" in st.query_params and not token:
        _clear_captain_query_param()
    if not session and token:
        try:session=runtime.restore_formula_race_captain(token,device)
        except (RuntimeDatabaseError,RuntimeError):
            _clear_captain_state();session=None
        if session:
            try:
                _set_session(session)
            except RuntimeError:
                _clear_captain_state()
                session=None
    if not session:
        st.markdown("<div class='race-login'><div class='race-kicker'>EXOS powered championship</div><h1>FORMULA <b>R.A.C.E.</b></h1><p class='race-subtle'>TEAM CAPTAIN ACCESS</p></div>", unsafe_allow_html=True)
        recovery=st.session_state.get("race_captain_recovery")
        if isinstance(recovery,dict):
            st.warning("This team is active on another device. Confirm your PIN to take over Captain access.")
            with st.form("race_captain_recovery_form"):
                recovery_pin=st.text_input("Team PIN",type="password",key="race_captain_recovery_pin")
                recover_submit=st.form_submit_button("RECOVER TEAM ACCESS",type="primary",width="stretch")
            if recover_submit:
                try:
                    with st.spinner("AUTHENTICATING…"):
                        payload=runtime.formula_race_captain_recover(str(recovery.get("JoinCode", "")),str(recovery.get("TeamID", "")),recovery_pin,device)
                    payload["TeamName"]=str(recovery.get("TeamName", ""))
                    _set_session(payload)
                except RuntimeDatabaseError as error:
                    st.error(_captain_error(error))
                    return
                except RuntimeError as error:
                    st.error(_captain_error(error))
                    return
                st.rerun()
                return
            return
        join_code=st.text_input("Event Join Code",placeholder="ENTER JOIN CODE",key="race_captain_join_code").upper().strip()
        event=runtime.get_event_by_join_code(join_code) if join_code else None
        teams=runtime.get_runtime_teams(str(event.get("EventID",""))) if event else []
        team_map={str(r.get("TeamIdentity",r.get("TeamName",""))):str(r.get("TeamID","")) for r in teams}
        team_names=sorted(team_map.keys())
        with st.form("race_captain_login"):
            team=st.selectbox("Team",team_names,disabled=not team_names);pin=st.text_input("Team PIN",type="password")
            submit=st.form_submit_button("ENTER TEAM GARAGE",type="primary",width="stretch")
        if submit:
            if not event:st.error("Enter a valid Formula R.A.C.E. event code.");return
            if not team:
                st.error("Choose a team before continuing.")
                return
            try:
                with st.spinner("AUTHENTICATING…"):
                    payload=runtime.formula_race_captain_login(join_code,team_map[team],pin,device)
            except RuntimeDatabaseError as error:
                st.error(_captain_error(error))
                return
            except RuntimeError as error:
                st.error(_captain_error(error))
                return
            if bool(payload.get("RecoveryRequired",False)):
                st.session_state["race_captain_recovery"]={
                    "JoinCode":join_code,
                    "EventID":str(payload.get("EventID", "")),
                    "TeamID":str(payload.get("TeamID", "")),
                    "TeamName":team,
                }
                st.rerun()
                return
            try:_set_session(payload)
            except RuntimeError as error:st.error(_captain_error(error));return
            st.rerun()
            return
    if not session:
        return
    event_id=str(session.get("EventID",""));team_id=str(session.get("TeamID",""));name=str(session.get("TeamName",""))
    if not _normalise_session_payload(session):
        if _is_staging_mode():
            print("CAPTAIN UUID TRACE | session_state_rejected_before_workspace | rpc/table: race_captain_session | field: SessionToken | is_none: True | is_literal_none: True | is_valid_uuid: False")
        _clear_captain_state()
        return
    try:
        workspace=runtime.formula_race_captain_workspace(str(session.get("SessionToken","")),device)
    except RuntimeDatabaseError as error:
        st.error(_captain_error(error));return
    except RuntimeError:
        _clear_captain_state()
        st.info("Your captain session has expired. Sign in again.")
        return
    if _is_staging_mode() and hasattr(runtime, "get_staging_call_counts"):
        runtime._assert_no_legacy_or_sheet_calls()
        counts = runtime.get_staging_call_counts()
        st.caption(
            f"LEGACY_RUNTIME_CALLS = {counts['LEGACY_RUNTIME_CALLS']} | "
            f"GOOGLE_SHEETS_RUNTIME_CALLS = {counts['GOOGLE_SHEETS_RUNTIME_CALLS']}"
        )
    asset=ASSET_ROOT/TEAM_ASSETS.get(name,"")
    team_identity=str(workspace.get("TeamIdentity",name or "Your Team"))
    checkpoints=list(workspace.get("Checkpoints",[]))
    checkpoint_runtime=dict(workspace.get("CheckpointRuntime",{}))
    wallet=dict(workspace.get("Wallet",{}));build=dict(workspace.get("BuildStatus",{}))
    championship=dict(workspace.get("Championship",{}))
    rank=championship.get("Rank",workspace.get("ChampionshipRank",workspace.get("Rank")))
    score=championship.get("Score",workspace.get("ChampionshipScore"))
    current=next((row for row in checkpoints if _status_copy(row.get("Status")) in {"ACTIVE","AVAILABLE","REJECTED / RESUBMIT"}), checkpoints[0] if checkpoints else {})
    current_status=_status_copy(current.get("Status")); runtime_status=str(checkpoint_runtime.get("status",checkpoint_runtime.get("Status","READY"))).upper()
    st.markdown("<div class='race-shell'>",unsafe_allow_html=True)
    left,right=st.columns([4,1])
    with left:
        st.markdown("<div class='race-wordmark'>FORMULA <b>R.A.C.E.</b> <span class='race-subtle'>/ TEAM GARAGE</span></div>",unsafe_allow_html=True)
        st.markdown(f"<div class='race-team-name'>{html.escape(team_identity)}</div>",unsafe_allow_html=True)
    with right:
        if asset.is_file(): st.image(str(asset),width=78)
        st.markdown("<div class='race-live'>● LIVE CAPTAIN</div>",unsafe_allow_html=True)
    st.markdown("<div class='race-metric-grid'>" +
        f"<div class='race-metric'><small>Championship rank</small><strong>#{html.escape(_display_number(rank))}</strong></div>" +
        f"<div class='race-metric'><small>Championship score</small><strong>{html.escape(_display_number(score))}</strong></div>" +
        f"<div class='race-metric'><small>Credits earned</small><strong>{html.escape(_display_number(wallet.get('CreditsEarned',workspace.get('CreditsEarned'))))}</strong></div>" +
        f"<div class='race-metric accent'><small>Wallet balance</small><strong>{html.escape(_display_number(wallet.get('Balance', 0)))}</strong></div></div>",unsafe_allow_html=True)
    captain_section = st.radio(
        "Captain navigation",
        ["RACE Checkpoints", "Wallet & Marketplace", "Build", "Submissions"],
        format_func={"RACE Checkpoints": "RACE", "Wallet & Marketplace": "WALLET", "Build": "BUILD", "Submissions": "HISTORY"}.get,
        horizontal=True,
        label_visibility="collapsed",
        key="race_captain_section",
    )
    if captain_section == "RACE Checkpoints":
        st.markdown(f"<div class='race-panel'><div class='race-overline'>Current checkpoint</div><div class='race-panel-title'>{html.escape(str(current.get('Name','Race Control is preparing the next checkpoint')))}</div><span class='race-status {_status_class(current_status)}'>{html.escape(current_status)}</span><p class='race-subtle'>{html.escape(str(current.get('Instructions','Stand by for the next mission.')))}</p><div class='race-cost'>+{html.escape(_display_number(current.get('Credits',0),'0'))} CREDITS</div></div>",unsafe_allow_html=True)
        if runtime_status!="LIVE": st.info(f"Race Control has checkpoints {runtime_status.lower()}. Your mission will unlock here when it goes live.")
        for checkpoint in checkpoints:
            status=_status_copy(checkpoint.get("Status")); is_current=checkpoint.get("ActivityID")==current.get("ActivityID")
            css_class="current" if is_current else ("complete" if status=="APPROVED" else "")
            st.markdown(f"<div class='race-checkpoint {css_class}'><span class='race-status {_status_class(status)}'>{html.escape(status)}</span><h3>{html.escape(str(checkpoint.get('Name','Checkpoint')))}</h3><p>{html.escape(str(checkpoint.get('Instructions','')))}</p><div class='race-cost'>+{html.escape(_display_number(checkpoint.get('Credits',0),'0'))} CREDITS</div></div>",unsafe_allow_html=True)
            disabled=runtime_status!="LIVE" or status in {"AWAITING REVIEW","APPROVED","SUBMITTED","LOCKED"}
            if is_current or status=="REJECTED / RESUBMIT":
                with st.expander("SUBMIT PROOF",expanded=is_current and not disabled):
                    proof_type=str(checkpoint.get("ProofType","Photo")).upper()
                    uploaded=st.file_uploader("Photo proof",type=["jpg","jpeg","png","webp"],disabled=disabled or proof_type=="TEXT",key=f"race_proof_{checkpoint.get('ActivityID')}")
                    answer=st.text_area("Optional notes",disabled=disabled,key=f"race_answer_{checkpoint.get('ActivityID')}")
                    if st.button("SUBMIT PROOF",type="primary",disabled=disabled,key=f"race_submit_{checkpoint.get('ActivityID')}"):
                        storage_reference=""
                        try:
                            with st.spinner("Submitting proof…"):
                                if uploaded:
                                    started_at=perf_counter(); payload,content_type,photo=_optimise_race_photo(uploaded); runtime.record_performance_component("captain.photo_processing",started_at)
                                    if photo["Optimised"]: st.caption(f"Photo optimised: {photo['OriginalBytes'] // 1024} KB to {photo['UploadBytes'] // 1024} KB")
                                    storage_path=f"{event_id}/{team_id}/{checkpoint.get('ActivityID')}/{uuid.uuid4()}-{uploaded.name.rsplit('.', 1)[0]}.jpg"
                                    runtime.upload_submission_image(storage_path,payload,content_type)
                                    storage_reference="supabase://exos-submissions/"+storage_path
                                activity_id=str(checkpoint.get("ActivityID", ""))
                                runtime.formula_race_submit_checkpoint(session.get("SessionToken",""),device,activity_id,answer,storage_reference,_submission_idempotency_key(event_id,team_id,activity_id))
                            st.success("PROOF SUBMITTED · Awaiting Race Control review.");st.rerun()
                        except (RuntimeDatabaseError, RuntimeError) as error: st.error(_captain_error(error))
    if captain_section == "Wallet & Marketplace":
        purchases=list(workspace.get("Purchases",[])); items=list(workspace.get("Marketplace",[])); spent=sum(float(row.get("Amount",0) or 0) for row in purchases)
        st.markdown("<div class='race-panel'><div class='race-overline'>TEAM GARAGE / PARTS DEPOT</div><div class='race-panel-title'>Wallet & Marketplace</div><div class='race-metric-grid'>" +
            f"<div class='race-metric accent'><small>Wallet balance</small><strong>{html.escape(_display_number(wallet.get('Balance',0)))}</strong></div><div class='race-metric'><small>Credits earned</small><strong>{html.escape(_display_number(wallet.get('CreditsEarned',workspace.get('CreditsEarned'))))}</strong></div><div class='race-metric'><small>Credits spent</small><strong>{html.escape(_display_number(wallet.get('CreditsSpent',workspace.get('CreditsSpent',spent)),'0'))}</strong></div></div></div>",unsafe_allow_html=True)
        if not items: st.info("The Marketplace is not open yet.")
        else:
            for item in items:
                item_name=html.escape(str(item.get("ItemName","Part"))); cost=_display_number(item.get("CreditCost",0),'0'); stock=item.get("StockQuantity")
                st.markdown(f"<div class='race-store-item'><h3>{item_name}</h3><div class='race-cost'>{html.escape(cost)} CREDITS</div><p class='race-subtle'>{'Stock: '+html.escape(_display_number(stock)) if stock is not None else 'Available while supplies last'}</p></div>",unsafe_allow_html=True)
                can_buy=bool(item.get("Active",True)) and float(wallet.get("Balance",0) or 0)>=float(item.get("CreditCost",0) or 0)
                if st.button(f"BUY {str(item.get('ItemName','PART')).upper()}",key=f"race_buy_{item.get('ItemID')}",disabled=not can_buy,width="stretch"):
                    try:
                        item_id=str(item.get("ItemID", ""))
                        with st.spinner("Purchasing…"): result=runtime.formula_race_purchase(session.get("SessionToken",""),device,item_id,1,_purchase_idempotency_key(event_id,team_id,item_id,1))
                        st.success(f"PURCHASE CONFIRMED · Wallet balance: {_display_number(result.get('Balance',0))}");st.rerun()
                    except (RuntimeDatabaseError,RuntimeError) as error:st.error(_captain_error(error,item,wallet.get("Balance")))
        if purchases:
            st.markdown("<div class='race-panel'><div class='race-panel-title'>Recent purchases</div></div>",unsafe_allow_html=True)
            st.dataframe([{k:v for k,v in row.items() if k not in {"PurchaseID","ItemID","IdempotencyKey"}} for row in purchases],width="stretch",hide_index=True)
    if captain_section == "Build":
        purchases=list(workspace.get("Purchases",[])); phase=_status_copy(build.get("status",build.get("Status","NOT STARTED"))).title(); progress=max(0,min(100,int(build.get("Progress",0) or 0)))
        st.markdown(f"<div class='race-panel'><div class='race-overline'>Garage progress</div><div class='race-panel-title'>{html.escape(phase)}</div><p class='race-subtle'>Build status is updated by Race Control.</p></div>",unsafe_allow_html=True)
        st.progress(progress,text=f"{progress}% COMPLETE")
        if purchases: st.dataframe([{ "Part":row.get("ItemName",""),"Quantity":row.get("Quantity",0),"Status":row.get("Status","")} for row in purchases],width="stretch",hide_index=True)
        else: st.info("Your collected parts will appear here once purchases are confirmed.")
    if captain_section == "Submissions":
        st.markdown("<div class='race-panel'><div class='race-overline'>Race history</div><div class='race-panel-title'>Checkpoint record</div><p class='race-subtle'>Your proof and review outcomes, without technical identifiers.</p></div>",unsafe_allow_html=True)
        submissions=list(workspace.get("Submissions", []))
        if submissions:
            history=[{"Checkpoint":row.get("CheckpointName",row.get("ActivityName","Checkpoint")),"Status":_status_copy(row.get("Status",row.get("submission_status","SUBMITTED"))),"Reward":row.get("Credits",row.get("CreditValue","—")),"Submitted":row.get("SubmittedAt",row.get("created_at",""))} for row in submissions]
            st.dataframe(history,width="stretch",hide_index=True)
        else: st.info("No checkpoint proof has been submitted yet.")
    if st.button("LOG OUT",width="stretch"):
        try:runtime.formula_race_captain_logout(session.get("SessionToken",""),device)
        except (RuntimeDatabaseError,RuntimeError):pass
        _clear_captain_state();st.query_params.clear();st.rerun()
    st.markdown("</div>",unsafe_allow_html=True)
