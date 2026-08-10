"""Formula R.A.C.E. fixed-team captain surface."""
import json
from pathlib import Path
import uuid
import html
import os
import streamlit as st
from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter
from data.runtime_database import RuntimeDatabaseError, get_runtime_database

ASSET_ROOT=Path(__file__).resolve().parents[1]/"Assets"/"race_teams"
TEAM_ASSETS=json.loads((ASSET_ROOT/"manifest.json").read_text())


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


def _is_valid_login_payload(payload: dict[str, object]) -> bool:
    event_id = str(payload.get("EventID", "")).strip()
    team_id = str(payload.get("TeamID", "")).strip()
    token = _normalise_session_token(payload.get("SessionToken"))
    return bool(event_id and team_id and token and not bool(payload.get("Ambiguous")) and not bool(payload.get("RecoveryRequired")))


def _device_id():
    value=str(st.session_state.get("race_captain_device_id", ""))
    if not value:value=str(uuid.uuid4());st.session_state["race_captain_device_id"]=value
    return value

def _set_session(payload):
    if not _is_valid_login_payload(payload or {}):
        raise RuntimeError("Invalid captain login payload.")
    st.session_state["race_captain"]=dict(payload);st.query_params["race"]="1"
    token = _normalise_session_token(payload.get("SessionToken"))
    if str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging":
        print(
            f"CAPTAIN UUID TRACE | _set_session | rpc/table: captain_session | field: SessionToken | "
            f"is_none: {payload.get('SessionToken') is None} | is_literal_none: {str(payload.get('SessionToken')).strip().lower() == 'none'} | "
            f"is_valid_uuid: {bool(_is_valid_session_token(payload.get('SessionToken')))}"
        )
    if token:
        st.query_params["captain_session"]=token
    else:
        try:
            st.query_params.pop("captain_session", None)
        except Exception:
            if "captain_session" in st.query_params:
                st.query_params["captain_session"] = ""


def _is_staging_mode() -> bool:
    return str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging"


def _build_runtime(runtime_override=None):
    runtime = runtime_override or get_runtime_database()
    if not _is_staging_mode():
        return runtime
    return FormulaRaceCoreV2StagingAdapter(runtime)

def show_formula_race_captain(runtime_override=None):
    runtime = _build_runtime(runtime_override)
    if _is_staging_mode() and not runtime.can_publish:
        st.error("Core v2 staging runtime is unavailable.")
        return
    if _is_staging_mode() and hasattr(runtime, "_assert_no_legacy_or_sheet_calls"):
        try:
            runtime._assert_no_legacy_or_sheet_calls()
        except RuntimeError as error:
            st.error(str(error))
            return
    if _is_staging_mode():
        st.caption("EXOS CORE V2 — STAGING")
    device=_device_id();session=st.session_state.get("race_captain")
    token=str(st.query_params.get("captain_session",""))
    if str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging":
        raw_token = token
        is_none = raw_token is None
        is_literal_none = str(raw_token).strip().lower() == "none"
        normalised = _normalise_session_token(raw_token)
        print(
            f"CAPTAIN UUID TRACE | captain_session_query_param | rpc/table: query_params | field: captain_session | "
            f"is_none: {is_none} | is_literal_none: {is_literal_none} | is_valid_uuid: {bool(normalised)}"
        )
    token=_normalise_session_token(token)
    if session and not _is_valid_login_payload(session):
        if str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging":
            print("CAPTAIN UUID TRACE | session_state_invalid_session | rpc/table: session_state | field: race_captain.SessionToken | is_none: True | is_literal_none: True | is_valid_uuid: False")
        st.session_state.pop("race_captain",None)
        if "captain_session" in st.query_params:
            st.query_params.pop("captain_session",None)
        session = None
    if not session and token:
        try:session=runtime.restore_formula_race_captain(token,device)
        except RuntimeDatabaseError:session=None
        if session:
            try:
                _set_session(session)
            except RuntimeError:
                st.session_state.pop("race_captain",None)
                session=None
    if not session:
        st.title("Formula R.A.C.E.");st.caption("TEAM CAPTAIN ACCESS · ONE TEAM · ONE ACTIVE DEVICE")
        join_code=st.text_input("Event Join Code").upper().strip()
        event=runtime.get_event_by_join_code(join_code) if join_code else None
        teams=runtime.get_runtime_teams(str(event.get("EventID",""))) if event else []
        team_map={str(r.get("TeamName","")):str(r.get("TeamID","")) for r in teams}
        team_names=sorted(team_map.keys())
        with st.form("race_captain_login"):
            team=st.selectbox("Team",team_names,disabled=not team_names);pin=st.text_input("Team PIN",type="password")
            submit=st.form_submit_button("Open Team Dashboard",type="primary",width="stretch")
        if submit:
            if not event:st.error("Enter a valid Formula R.A.C.E. event code.");return
            if not team:
                st.error("Choose a team before continuing.")
                return
            try:payload=runtime.formula_race_captain_login(join_code,team_map[team],pin,device)
            except RuntimeDatabaseError as error:st.error(str(error));return
            try:_set_session(payload)
            except RuntimeError as error:st.error(str(error));return
            st.rerun()
            return
    event_id=str(session.get("EventID",""));team_id=str(session.get("TeamID",""));name=str(session.get("TeamName",""))
    if not _is_valid_login_payload(session):
        if _is_staging_mode():
            print("CAPTAIN UUID TRACE | session_state_rejected_before_workspace | rpc/table: race_captain_session | field: SessionToken | is_none: True | is_literal_none: True | is_valid_uuid: False")
        st.session_state.pop("race_captain",None)
        if "captain_session" in st.query_params:
            st.query_params.pop("captain_session",None)
        return
    try:workspace=runtime.formula_race_captain_workspace(session.get("SessionToken",""),device)
    except RuntimeDatabaseError as error:
        st.error(str(error));return
    if _is_staging_mode() and hasattr(runtime, "get_staging_call_counts"):
        runtime._assert_no_legacy_or_sheet_calls()
        counts = runtime.get_staging_call_counts()
        st.caption(
            f"LEGACY_RUNTIME_CALLS = {counts['LEGACY_RUNTIME_CALLS']} | "
            f"GOOGLE_SHEETS_RUNTIME_CALLS = {counts['GOOGLE_SHEETS_RUNTIME_CALLS']}"
        )
    submissions=[
        row for row in (
            runtime.get_canonical_submissions(event_id) if runtime.can_publish else []
        ) if str(row.get("TeamID",""))==team_id
    ]
    asset=ASSET_ROOT/TEAM_ASSETS.get(name,"")
    if asset.is_file():st.image(str(asset),width=96)
    st.title(name);st.caption(f"{event_id} · {team_id}")
    checkpoints=list(workspace.get("Checkpoints",[]))
    checkpoint_runtime=dict(workspace.get("CheckpointRuntime",{}))
    approved=sum(str(r.get("Status","")).upper()=="APPROVED" for r in checkpoints)
    wallet=dict(workspace.get("Wallet",{}));build=dict(workspace.get("BuildStatus",{}))
    a,b,c=st.columns(3);a.metric("RACE Checkpoints",f"{approved} / {len(checkpoints) or 4}");b.metric("Build status",build.get("status","Not Started"));c.metric("Wallet",wallet.get("Balance",0))
    one,two,three=st.tabs(["RACE Checkpoints","Wallet & Marketplace","Submissions"])
    with one:
        st.markdown("<style>.race-checkpoint{background:#0b1725;border:1px solid #253950;border-left:5px solid #ff5555;border-radius:16px;padding:18px;margin:10px 0;color:#f3f6fa}.race-checkpoint h3{margin:0;color:#fff}.race-checkpoint .credits{color:#ffca3a;font-weight:800}.race-checkpoint .status{letter-spacing:.08em;font-size:.78rem;font-weight:900}</style>",unsafe_allow_html=True)
        runtime_status=str(checkpoint_runtime.get("status",checkpoint_runtime.get("Status","READY"))).upper()
        if runtime_status!="LIVE":st.info(f"RACE Checkpoints are {runtime_status}. Your four cards will open when the facilitator launches them.")
        for checkpoint in checkpoints:
            status=str(checkpoint.get("Status","AVAILABLE")).upper()
            st.markdown(f"<div class='race-checkpoint'><div class='status'>{html.escape(status)}</div><h3>{html.escape(str(checkpoint.get('Name','Checkpoint')))}</h3><div class='credits'>{checkpoint.get('Credits',0)} Credits</div><p>{html.escape(str(checkpoint.get('Instructions','')))}</p><small>Proof: {html.escape(str(checkpoint.get('ProofType','Photo')))}</small></div>",unsafe_allow_html=True)
            disabled=runtime_status!="LIVE" or status in {"UNDER REVIEW","APPROVED","SUBMITTED"}
            with st.expander("Open checkpoint",expanded=status=="REJECTED / RESUBMIT"):
                proof_type=str(checkpoint.get("ProofType","Photo"))
                uploaded=st.file_uploader("Photo proof",type=["jpg","jpeg","png","webp"],disabled=disabled or proof_type=="Text",key=f"race_proof_{checkpoint.get('ActivityID')}")
                answer=st.text_area("Text answer",disabled=disabled or proof_type=="Photo",key=f"race_answer_{checkpoint.get('ActivityID')}")
                if st.button("Submit Proof",type="primary",disabled=disabled,key=f"race_submit_{checkpoint.get('ActivityID')}"):
                    storage_reference=""
                    try:
                        if uploaded:
                            storage_path=f"{event_id}/{team_id}/{checkpoint.get('ActivityID')}/{uuid.uuid4()}-{uploaded.name}"
                            runtime.upload_submission_image(storage_path,uploaded.getvalue(),uploaded.type or "image/jpeg")
                            storage_reference="supabase://exos-submissions/"+storage_path
                        runtime.formula_race_submit_checkpoint(session.get("SessionToken",""),device,
                            checkpoint.get("ActivityID",""),answer,storage_reference,str(uuid.uuid4()))
                        st.success("Proof submitted for facilitator review.");st.rerun()
                    except RuntimeDatabaseError as error:st.error(str(error))
    with two:
        st.caption("All wallet and marketplace activity is scoped to this EventID and TeamID.")
        items=list(workspace.get("Marketplace",[]))
        if not items:st.info("Marketplace is not open yet.")
        else:
            labels={f"{item.get('ItemName')} · {item.get('CreditCost')} Credits · {item.get('StockQuantity')} available":item for item in items}
            with st.form("race_marketplace_purchase"):
                selected=st.selectbox("Material",list(labels));quantity=st.number_input("Quantity",1,20,1)
                buy=st.form_submit_button("Confirm Purchase",type="primary",width="stretch")
            if buy:
                try:
                    result=runtime.formula_race_purchase(session.get("SessionToken",""),device,
                        labels[selected].get("ItemID",""),quantity,str(uuid.uuid4()))
                    st.success(f"Purchase confirmed. Balance: {result.get('Balance',0)} Credits");st.rerun()
                except RuntimeDatabaseError as error:st.error(str(error))
        purchases=list(workspace.get("Purchases",[]))
        if purchases:st.dataframe(purchases,width="stretch",hide_index=True)
    with three:
        if submissions:
            st.dataframe(submissions,width="stretch",hide_index=True)
        else:
            st.info("No submissions yet for this team.")
    if st.button("Log out",width="stretch"):
        try:runtime.formula_race_captain_logout(session.get("SessionToken",""),device)
        except RuntimeDatabaseError:pass
        st.session_state.pop("race_captain",None);st.query_params.clear();st.rerun()
