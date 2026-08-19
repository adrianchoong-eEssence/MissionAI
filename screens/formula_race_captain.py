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
from engines.formula_race_configuration import captain_result_entry_method

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
    .block-container { max-width:1120px; padding:.5rem .8rem 3rem; }
    [data-testid="stHeader"] { background:transparent; }
    .race-shell { max-width:920px; margin:0 auto; }
    .race-kicker,.race-overline { color:var(--race-amber); font:800 .70rem/1 Inter,sans-serif; letter-spacing:.15em; text-transform:uppercase; }
    .race-wordmark,.race-team-name,.race-panel-title { font-family:'Barlow Condensed',Impact,sans-serif; text-transform:uppercase; letter-spacing:.03em; }
    .race-wordmark { font-size:1.55rem; font-weight:800; line-height:1; }.race-wordmark b{color:var(--race-red)}
    .race-team-name { margin:.14rem 0 0; font-size:2.25rem; font-weight:800; line-height:.88; color:#fff; overflow-wrap:anywhere; text-shadow:0 10px 30px rgba(67,182,232,.14); }
    .race-subtle { color:var(--race-muted); font-size:.82rem; }
    .race-login,.race-panel,.race-metric,.race-checkpoint,.race-store-item { border:1px solid var(--race-line); background:linear-gradient(145deg,rgba(18,34,45,.96),rgba(9,18,25,.96)); border-radius:12px; }
    .race-login { max-width:530px; margin:8vh auto 0; padding:1.35rem; }.race-login h1{font:800 3.3rem/.82 'Barlow Condensed',Impact,sans-serif;margin:.4rem 0 1rem;text-transform:uppercase}.race-login h1 b{color:var(--race-red)}
    .race-header { display:flex; align-items:flex-end; justify-content:space-between; gap:1rem; margin:.5rem 0 1rem; }.race-live{color:var(--race-green);font-weight:800;font-size:.72rem;letter-spacing:.08em;white-space:nowrap}
    .race-standing{display:flex;align-items:center;gap:.65rem;margin:.5rem 0 .2rem;padding:.55rem 0;border-top:1px solid var(--race-line);border-bottom:1px solid var(--race-line)}.race-standing strong{font:800 2.4rem/.75 'Barlow Condensed',Impact,sans-serif;color:#fff}.race-standing span{font:800 .68rem Inter,sans-serif;letter-spacing:.11em;color:var(--race-muted)}.race-standing em{display:block;color:var(--race-amber);font:800 .72rem Inter,sans-serif;letter-spacing:.08em;font-style:normal}.race-standing.leader{border-color:rgba(247,183,51,.48);background:linear-gradient(90deg,rgba(247,183,51,.12),transparent 65%)}.race-standing.leader strong{color:var(--race-amber)}.race-standing.podium strong{color:#d8e8f0}
    .race-metric-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.55rem; margin:.55rem 0 .8rem; }
    .race-metric { padding:.45rem .15rem; min-width:0; border-bottom:2px solid var(--race-line); }.race-metric.accent{border-bottom-color:var(--race-red)} .race-metric strong{display:block;overflow-wrap:anywhere;color:#fff;font:800 1.8rem/.86 'Barlow Condensed',Impact,sans-serif;letter-spacing:.02em}.race-metric small{display:block;margin-bottom:.22rem;color:var(--race-muted);font:700 .62rem Inter,sans-serif;letter-spacing:.1em;text-transform:uppercase}
    .race-panel { padding:.85rem; margin:.55rem 0; }.race-panel-title{font-size:1.4rem;font-weight:800;margin:0 0 .2rem}.race-current{position:relative;overflow:hidden;border-left:4px solid var(--race-red);background:linear-gradient(120deg,rgba(237,49,57,.16),rgba(16,38,53,.88) 42%,rgba(9,18,25,.96));box-shadow:0 14px 38px rgba(0,0,0,.17)}.race-current:after{content:'';position:absolute;right:-55px;top:-80px;width:190px;height:190px;border:1px solid rgba(67,182,232,.19);border-radius:50%;box-shadow:0 0 0 22px rgba(67,182,232,.04),0 0 0 45px rgba(67,182,232,.03)}.race-current>*{position:relative;z-index:1}.race-current-detail{margin-top:0;border-top:0;border-radius:0 0 12px 12px}.race-reference-label{margin:.6rem 0 .15rem;color:var(--race-amber);font:800 .68rem Inter,sans-serif;letter-spacing:.13em}.race-journey-label{display:flex;align-items:center;justify-content:space-between;margin:.6rem 0 .25rem;color:var(--race-muted);font:800 .65rem Inter,sans-serif;letter-spacing:.1em}.race-stage-track{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.3rem;margin:.1rem 0 .65rem}.race-stage-track:before{content:'';position:absolute;left:12%;right:12%;top:.73rem;height:1px;background:var(--race-line)}.race-stage{position:relative;padding:.25rem .1rem;text-align:center;color:var(--race-muted);font:800 .62rem Inter,sans-serif;letter-spacing:.04em;white-space:nowrap;background:var(--race-ink)}.race-stage:before{content:'';display:block;width:.68rem;height:.68rem;margin:0 auto .22rem;border:2px solid var(--race-line);border-radius:50%;background:var(--race-ink)}.race-stage.active:before,.race-stage.available:before{border-color:var(--race-amber);box-shadow:0 0 0 3px rgba(247,183,51,.10)}.race-stage.approved:before{border-color:var(--race-green);background:var(--race-green)}.race-stage.review:before,.race-stage.submitted:before{border-color:var(--race-blue);background:var(--race-blue)}.race-stage.selected{color:#fff}.race-stage.selected:before{border-color:var(--race-red);background:var(--race-red);box-shadow:0 0 0 4px rgba(237,49,57,.18)}.race-stage-row{display:grid;grid-template-columns:2.1rem minmax(0,1fr) auto auto;align-items:center;gap:.45rem;padding:.48rem .1rem;margin:.15rem 0;border-bottom:1px solid rgba(38,56,70,.72)}.race-stage-row.complete{opacity:.58}.race-stage-row strong{font:800 1rem/1 'Barlow Condensed',Impact,sans-serif;text-transform:uppercase;overflow-wrap:anywhere}.race-stage-row small{color:var(--race-muted);font-size:.7rem}.race-reward{display:inline-flex;align-items:center;gap:.28rem;margin-top:.42rem;padding:.26rem .46rem;border-radius:999px;background:rgba(247,183,51,.12);color:var(--race-amber);font:800 .72rem Inter,sans-serif;letter-spacing:.05em}.race-reward:before{content:'◆';font-size:.55rem}.race-proof{margin:.35rem 0 .55rem;padding:.65rem .7rem;border-top:1px solid var(--race-line);background:rgba(7,16,23,.34)}.race-proof-title{color:var(--race-amber);font:800 .68rem Inter,sans-serif;letter-spacing:.13em}.race-status{display:inline-block;padding:.22rem .45rem;border:1px solid var(--race-line);border-radius:999px;color:#c9d3da;font:800 .62rem Inter,sans-serif;letter-spacing:.09em}.race-status.active,.race-status.available{color:var(--race-amber);border-color:rgba(247,183,51,.55)}.race-status.approved{color:var(--race-green);border-color:rgba(77,211,138,.55)}.race-status.review,.race-status.submitted{color:var(--race-blue);border-color:rgba(67,182,232,.55)}.race-status.rejected{color:#ff8a8e;border-color:rgba(237,49,57,.55)}
    .race-store-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem; }.race-store-item{padding:.85rem}.race-cost{color:var(--race-amber);font:800 1.45rem 'Barlow Condensed',Impact,sans-serif}.race-note{padding:.7rem .8rem;border-left:3px solid var(--race-blue);background:rgba(67,182,232,.09);color:#d8e8f0;font-size:.86rem}
    div[data-testid="stRadio"] > div { gap:.24rem; } div[data-testid="stRadio"] label { flex:1;justify-content:center;min-width:0;margin:0!important;border:1px solid var(--race-line);border-radius:8px;padding:.42rem .12rem;background:rgba(10,23,32,.7);font-size:.68rem;font-weight:800;letter-spacing:.02em;white-space:nowrap; } div[data-testid="stRadio"] label p{white-space:nowrap!important;overflow:visible!important} div[data-testid="stRadio"] label:has(input:checked){border-color:var(--race-red);background:rgba(237,49,57,.13)}
    div.stButton>button,div[data-testid="stFormSubmitButton"]>button { min-height:42px;border-radius:7px;text-transform:uppercase;font-weight:800;letter-spacing:.04em; } div[data-testid="stMetric"]{background:transparent;border:0;padding:0} [data-testid="stMetricLabel"]{color:var(--race-muted)}div[data-testid="stFileUploader"]{padding:.35rem .45rem;border:1px dashed var(--race-line);border-radius:8px;background:rgba(7,16,23,.35)}div[data-testid="stFileUploader"] small{display:none!important}textarea{min-height:68px!important;background:#0b161f!important;color:#f5f7f8!important}
    @media (max-width:600px) { .block-container{padding:.35rem .65rem 2.5rem}.race-header{align-items:flex-start;flex-direction:column;gap:.35rem}.race-team-name{font-size:2rem}.race-store-grid{grid-template-columns:1fr}.race-login{margin:3vh auto 0;padding:1rem}.race-login h1{font-size:2.7rem}.race-stage-row{grid-template-columns:1.8rem minmax(0,1fr) auto}.race-stage-row small{display:none} }
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


def _team_options(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Bind canonical roster rows to Captain selector labels without changing them."""
    options: dict[str, str] = {}
    for row in rows:
        label = str(row.get("TeamIdentity") or row.get("TeamName") or "").strip()
        team_id = str(row.get("TeamID") or "").strip()
        if label and team_id:
            options[label] = team_id
    return options


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


def _authoritative_checkpoint_selection(
    checkpoints: list[dict[str, Any]],
    canonical_current_activity_id: str,
    retained_selection: str = "",
) -> tuple[str, bool]:
    """Return the only Captain selection permitted while a route is active.

    A Journey can retain a visual selection in Streamlit session state, but
    only TeamRoutes plus canonical submissions determine progression.  A
    previously submitted/pending station must therefore never remain selected
    after the workspace has advanced to the next configured ActivityID.
    """
    checkpoint_ids = {
        str(row.get("ActivityID", "")).strip()
        for row in checkpoints
        if str(row.get("ActivityID", "")).strip()
    }
    canonical = str(canonical_current_activity_id or "").strip()
    retained = str(retained_selection or "").strip()
    if canonical and canonical in checkpoint_ids:
        return canonical, bool(retained) and retained != canonical
    # A completed/invalid route has no canonical current station.  Do not let
    # a stale selection masquerade as one.
    return "", bool(retained)


def _rank_treatment(rank: Any) -> tuple[str, str]:
    try:
        position = int(float(rank))
    except (TypeError, ValueError):
        return "", "CHAMPIONSHIP POSITION"
    if position == 1:
        return "leader", "CHAMPIONSHIP LEADER"
    if position <= 3:
        return "podium", "PODIUM POSITION"
    return "", "CHAMPIONSHIP POSITION"


def _build_phase_copy(value: Any) -> tuple[str, int]:
    raw = str(value or "NOT_STARTED").upper().replace("_", " ")
    phases = ["NOT STARTED", "COLLECTING PARTS", "BUILDING", "PAINTING", "READY TO RACE", "COMPLETED"]
    aliases = {"IN PROGRESS": "BUILDING", "READY": "READY TO RACE"}
    phase = aliases.get(raw, raw)
    return phase.title(), phases.index(phase) if phase in phases else 0


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
    st.session_state.pop("race_captain_selected_checkpoint", None)
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
    # A checkpoint selection belongs to one Captain route at one point in
    # time.  It must never survive a login/recovery and override the canonical
    # current station recalculated after a proof submission.
    st.session_state.pop("race_captain_selected_checkpoint", None)
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
    show_diagnostics = _staging_mode() and str(st.query_params.get("performance", st.query_params.get("debug", ""))).lower() in {"1", "true", "yes", "on"}
    if show_diagnostics:
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
        team_map=_team_options(teams)
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
    if show_diagnostics and hasattr(runtime, "get_staging_call_counts"):
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
    route_configuration_issue=dict(workspace.get("RouteConfigurationIssue", {}))
    if route_configuration_issue.get("StaleActivityIDs"):
        st.warning("Race Control is reconciling your configured route. Submissions are temporarily unavailable until the route uses the current stations.")
        return
    checkpoint_ids={str(row.get("ActivityID", "")) for row in checkpoints}
    retained_selection = str(st.session_state.get("race_captain_selected_checkpoint", ""))
    selected_id, clear_retained_selection = _authoritative_checkpoint_selection(
        checkpoints,
        str(workspace.get("CurrentCheckpoint", {}).get("ActivityID", "")),
        retained_selection,
    )
    if clear_retained_selection:
        st.session_state.pop("race_captain_selected_checkpoint", None)
    if selected_id not in checkpoint_ids:
        selected_id=str(next((row.get("ActivityID", "") for row in checkpoints if _status_copy(row.get("Status")) in {"ACTIVE","AVAILABLE","REJECTED / RESUBMIT"}), checkpoints[0].get("ActivityID", "") if checkpoints else ""))
    current=next((row for row in checkpoints if str(row.get("ActivityID", "")) == selected_id), checkpoints[0] if checkpoints else {})
    current_status=_status_copy(current.get("Status")); runtime_status=str(checkpoint_runtime.get("status",checkpoint_runtime.get("Status","READY"))).upper()
    standing_class,standing_copy=_rank_treatment(rank)
    st.markdown("<div class='race-shell'>",unsafe_allow_html=True)
    left,right=st.columns([4,1])
    with left:
        st.markdown("<div class='race-wordmark'>FORMULA <b>R.A.C.E.</b> <span class='race-subtle'>/ TEAM GARAGE</span></div>",unsafe_allow_html=True)
        st.markdown(f"<div class='race-team-name'>{html.escape(team_identity)}</div>",unsafe_allow_html=True)
    with right:
        if asset.is_file(): st.image(str(asset),width=78)
        st.markdown("<div class='race-live'>● LIVE CAPTAIN</div>",unsafe_allow_html=True)
    st.markdown(f"<div class='race-standing {standing_class}'><strong>#{html.escape(_display_number(rank))}</strong><span>CHAMPIONSHIP<br><em>{standing_copy}</em></span></div>",unsafe_allow_html=True)
    st.markdown("<div class='race-metric-grid'>" +
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
        stage_track = "".join(
            f"<div class='race-stage {_status_class(_status_copy(checkpoint.get('Status')))} {'selected' if str(checkpoint.get('ActivityID', '')) == selected_id else ''}'>CP{index}</div>"
            for index, checkpoint in enumerate(checkpoints, start=1)
        )
        if stage_track: st.markdown(f"<div class='race-journey-label'><span>RACE JOURNEY</span><span>SELECTED: CP{next((index for index, row in enumerate(checkpoints, start=1) if str(row.get('ActivityID', '')) == selected_id), '—')}</span></div><div class='race-stage-track'>{stage_track}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='race-panel race-current'><div class='race-overline'>Your current mission</div><div class='race-panel-title'>{html.escape(str(current.get('Name','Race Control is preparing the next checkpoint')))}</div><span class='race-status {_status_class(current_status)}'>{html.escape(current_status)}</span></div>",unsafe_allow_html=True)
        reference_image = str(current.get("ImageReference", "") or "")
        if reference_image:
            reference_url = runtime.get_formula_race_station_reference_image_url(reference_image)
            if reference_url:
                st.markdown("<div class='race-reference-label'>STATION REFERENCE</div>", unsafe_allow_html=True)
                st.image(reference_url, use_container_width=True)
        st.markdown(f"<div class='race-panel race-current race-current-detail'><p class='race-subtle'>{html.escape(str(current.get('Instructions','Stand by for the next mission.')))}</p><div class='race-reward'>EARN {html.escape(_display_number(current.get('Credits',0),'0'))} CREDITS</div></div>",unsafe_allow_html=True)
        if runtime_status!="LIVE":
            st.info(f"Race Control has checkpoints {runtime_status.lower()}. Your mission will unlock here when it goes live.")
            return
        current_disabled=runtime_status!="LIVE" or current_status in {"AWAITING REVIEW","APPROVED","SUBMITTED","LOCKED"}
        if current:
            st.markdown("<div class='race-proof'><div class='race-proof-title'>PROOF</div></div>", unsafe_allow_html=True)
            method=str(current.get("ScoringMethod","NON_SCORING")).upper()
            evidence_requirement=str(current.get("EvidenceRequirement",current.get("ProofType","PHOTO_OPTIONAL"))).upper()
            uploaded=None
            if evidence_requirement != "NO_PHOTO":
                uploaded=st.file_uploader("Photo evidence" + (" (required)" if evidence_requirement == "PHOTO_REQUIRED" else " (optional)"),type=["jpg","jpeg","png","webp"],disabled=current_disabled,key=f"race_proof_{current.get('ActivityID')}")
            result_value=None
            result_entry_method=captain_result_entry_method(current)
            if result_entry_method == "LOWEST_TIME":
                a,b,c=st.columns(3); minutes=a.number_input("Minutes",min_value=0,step=1,disabled=current_disabled,key=f"race_minutes_{current.get('ActivityID')}"); seconds=b.number_input("Seconds",min_value=0,max_value=59,step=1,disabled=current_disabled,key=f"race_seconds_{current.get('ActivityID')}"); milliseconds=c.number_input("Milliseconds",min_value=0,max_value=999,step=1,disabled=current_disabled,key=f"race_milliseconds_{current.get('ActivityID')}"); result_value=int(minutes)*60000+int(seconds)*1000+int(milliseconds)
            elif result_entry_method in {"HIGHEST_COUNT", "SUCCESS_COUNT"}:
                result_value=st.number_input(str(current.get("ResultLabel", "Result")),min_value=0,step=1,disabled=current_disabled,key=f"race_result_{current.get('ActivityID')}")
            elif method != "NON_SCORING": st.caption("The station facilitator records the official result. Submit completion evidence only.")
            answer=st.text_area("Notes for the facilitator",disabled=current_disabled,key=f"race_answer_{current.get('ActivityID')}",height=68)
            if st.button("SUBMIT PROOF",type="primary",disabled=current_disabled,key=f"race_submit_{current.get('ActivityID')}"):
                storage_reference=""
                try:
                    if evidence_requirement == "PHOTO_REQUIRED" and not uploaded: raise RuntimeError("Photo evidence is required for this station.")
                    with st.spinner("Submitting proof…"):
                        if uploaded:
                            started_at=perf_counter(); payload,content_type,photo=_optimise_race_photo(uploaded); runtime.record_performance_component("captain.photo_processing",started_at)
                            if photo["Optimised"]: st.caption(f"Photo optimised: {photo['OriginalBytes'] // 1024} KB to {photo['UploadBytes'] // 1024} KB")
                            storage_path=f"{event_id}/{team_id}/{current.get('ActivityID')}/{uuid.uuid4()}-{uploaded.name.rsplit('.', 1)[0]}.jpg"
                            runtime.upload_submission_image(storage_path,payload,content_type)
                            storage_reference="supabase://exos-submissions/"+storage_path
                        activity_id=str(current.get("ActivityID", ""))
                        runtime.formula_race_submit_checkpoint(session.get("SessionToken",""),device,activity_id,answer,storage_reference,_submission_idempotency_key(event_id,team_id,activity_id),result_value=result_value,result_unit=str(current.get("ResultUnit", "") or "CONFIGURED") if result_entry_method else "")
                    next_checkpoint=dict(workspace.get("NextCheckpoint",{})); next_name=str(next_checkpoint.get("DisplayName",next_checkpoint.get("Name","")))
                    # The workspace recomputes progress from TeamRoutes and
                    # persisted submissions on rerun.  Discarding the old
                    # visual selection prevents a submitted station from
                    # continuing to render as the current mission.
                    st.session_state.pop("race_captain_selected_checkpoint", None)
                    st.success("STATION COMPLETE · " + (f"NEXT STOP: {next_name}" if next_name else "Awaiting the next configured stop."));st.rerun()
                except (RuntimeDatabaseError, RuntimeError) as error: st.error(_captain_error(error))
        for index, checkpoint in enumerate(checkpoints, start=1):
            if checkpoint.get("ActivityID") == current.get("ActivityID"): continue
            status=_status_copy(checkpoint.get("Status")); css_class="complete" if status=="APPROVED" else ""
            st.markdown(f"<div class='race-stage-row {css_class}'><span class='race-overline'>CP{index}</span><strong>{html.escape(str(checkpoint.get('Name','Checkpoint')))}</strong><span class='race-status {_status_class(status)}'>{html.escape(status)}</span><span class='race-cost'>+{html.escape(_display_number(checkpoint.get('Credits',0),'0'))}</span></div>",unsafe_allow_html=True)
            if status not in {"APPROVED", "SUBMITTED", "AWAITING REVIEW", "LOCKED"}:
                if st.button(f"VIEW CP{index}",key=f"race_view_{checkpoint.get('ActivityID')}",width="stretch"):
                    st.session_state["race_captain_selected_checkpoint"]=str(checkpoint.get("ActivityID", ""));st.rerun()
    if captain_section == "Wallet & Marketplace":
        purchases=list(workspace.get("Purchases",[])); items=list(workspace.get("Marketplace",[])); spent=sum(float(row.get("Amount",0) or 0) for row in purchases)
        st.markdown("<div class='race-panel'><div class='race-overline'>TEAM GARAGE / PARTS DEPOT</div><div class='race-panel-title'>Fund the build</div><p class='race-subtle'>Mission Credits become the components your team takes to the race.</p><div class='race-metric-grid'>" +
            f"<div class='race-metric accent'><small>Wallet balance</small><strong>{html.escape(_display_number(wallet.get('Balance',0)))}</strong></div><div class='race-metric'><small>Credits earned</small><strong>{html.escape(_display_number(wallet.get('CreditsEarned',workspace.get('CreditsEarned'))))}</strong></div><div class='race-metric'><small>Credits spent</small><strong>{html.escape(_display_number(wallet.get('CreditsSpent',workspace.get('CreditsSpent',spent)),'0'))}</strong></div></div></div>",unsafe_allow_html=True)
        if not items: st.info("The Marketplace is not open yet.")
        else:
            for item in items:
                item_name=html.escape(str(item.get("ItemName","Part"))); cost=_display_number(item.get("CreditCost",0),'0'); stock=item.get("StockQuantity")
                st.markdown(f"<div class='race-store-item'><h3>{item_name}</h3><div class='race-cost'>{html.escape(cost)} CREDITS</div><p class='race-subtle'>{'Stock: '+html.escape(_display_number(stock)) if stock is not None else 'Available while supplies last'}</p></div>",unsafe_allow_html=True)
                description = str(item.get("Description", "") or "")
                if description:
                    st.caption(description)
                image_reference = str(item.get("ImageReference", "") or "")
                if image_reference:
                    image_url = runtime.get_formula_race_station_reference_image_url(image_reference)
                    if image_url:
                        st.image(image_url, caption=str(item.get("ItemName", "Part")), use_container_width=True)
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
        purchases=list(workspace.get("Purchases",[])); phase,phase_index=_build_phase_copy(build.get("status",build.get("Status","NOT STARTED"))); progress=max(0,min(100,int(build.get("Progress",0) or 0)))
        build_phases=[("NOT STARTED", "START"), ("COLLECTING PARTS", "PARTS"), ("BUILDING", "BUILD"), ("PAINTING", "PAINT"), ("READY TO RACE", "READY"), ("COMPLETED", "DONE")]
        build_track="".join(f"<div class='race-stage {'approved' if index < phase_index else ('selected' if index == phase_index else '')}'>{label}</div>" for index,(_,label) in enumerate(build_phases))
        st.markdown(f"<div class='race-panel'><div class='race-overline'>Garage progress</div><div class='race-panel-title'>{html.escape(phase)}</div><p class='race-subtle'>Build status is updated by Race Control. The next race-ready step is visible to your whole team.</p></div><div class='race-stage-track' style='grid-template-columns:repeat(6,minmax(0,1fr))'>{build_track}</div>",unsafe_allow_html=True)
        st.progress(progress,text=f"{progress}% COMPLETE")
        photo_component_enabled = any(
            str(component.get("ComponentType", "")).upper() == "TEAM_PHOTO" and bool(component.get("Enabled", True))
            for component in workspace.get("ChampionshipComponents", [])
        )
        if photo_component_enabled:
            st.markdown("<div class='race-panel'><div class='race-overline'>Build complete</div><div class='race-panel-title'>Team Photo</div><p class='race-subtle'>Upload one completed-car photo with your team. This private Day 2 submission is separate from checkpoint proof.</p></div>", unsafe_allow_html=True)
            team_photo = dict(workspace.get("TeamPhoto", {}) or {})
            if team_photo.get("storage_reference"):
                photo_url = runtime.get_formula_race_team_photo_url(team_photo["storage_reference"])
                if photo_url:
                    st.image(photo_url, caption="Submitted Team Photo", use_container_width=True)
                st.caption("Team Photo submitted. Upload a replacement only if your facilitator asks for a correction.")
            team_photo_upload = st.file_uploader("Upload Team Photo", type=["jpg", "jpeg", "png", "webp"], key="race_team_photo_upload")
            build_complete = phase == "COMPLETED"
            if not build_complete:
                st.caption("Team Photo unlocks when Race Control marks the Team Garage build complete.")
            if st.button("SUBMIT TEAM PHOTO", type="primary", disabled=team_photo_upload is None or not build_complete, key="race_team_photo_submit"):
                try:
                    with st.spinner("Submitting Team Photo…"):
                        payload, content_type, _photo = _optimise_race_photo(team_photo_upload)
                        storage_path = f"team-photos/{event_id}/{team_id}/{uuid.uuid4()}-{team_photo_upload.name.rsplit('.', 1)[0]}.jpg"
                        runtime.upload_submission_image(storage_path, payload, content_type)
                        runtime.formula_race_submit_team_photo(session.get("SessionToken", ""), device, "supabase://exos-submissions/" + storage_path)
                    st.success("TEAM PHOTO SUBMITTED · Your facilitator can now review it with the configured judging criterion.")
                    st.rerun()
                except (RuntimeDatabaseError, RuntimeError) as error:
                    st.error(_captain_error(error))
        if purchases: st.dataframe([{ "Part":row.get("ItemName",""),"Quantity":row.get("Quantity",0),"Status":row.get("Status","")} for row in purchases],width="stretch",hide_index=True)
        else: st.info("Your collected components will appear here once purchases are confirmed.")
    if captain_section == "Submissions":
        st.markdown("<div class='race-panel'><div class='race-overline'>Team race log</div><div class='race-panel-title'>Your race record</div><p class='race-subtle'>Mission proof, review outcomes, components and build milestones—without technical audit detail.</p></div>",unsafe_allow_html=True)
        submissions=list(workspace.get("Submissions", []))
        log=[]
        for row in submissions:
            log.append({"Moment":row.get("SubmittedAt",row.get("created_at","")),"Race log":f"Checkpoint {_status_copy(row.get('Status',row.get('submission_status','SUBMITTED'))).title()}","Detail":row.get("CheckpointName",row.get("ActivityName","Mission proof"))})
        for row in workspace.get("Purchases",[]):
            log.append({"Moment":row.get("PurchasedAt",""),"Race log":"Component purchased","Detail":f"{row.get('ItemName','Component')} × {row.get('Quantity',1)}"})
        if build.get("LastUpdated"):
            log.append({"Moment":build.get("LastUpdated",""),"Race log":"Garage progress updated","Detail":_build_phase_copy(build.get("status",build.get("Status","NOT STARTED")))[0]})
        if log:
            st.dataframe(sorted(log,key=lambda row:str(row.get("Moment", "")),reverse=True),width="stretch",hide_index=True)
        else: st.info("Your team’s mission, component and build moments will appear here as the race progresses.")
    if st.button("LOG OUT",width="stretch"):
        try:runtime.formula_race_captain_logout(session.get("SessionToken",""),device)
        except (RuntimeDatabaseError,RuntimeError):pass
        _clear_captain_state();st.query_params.clear();st.rerun()
    st.markdown("</div>",unsafe_allow_html=True)
