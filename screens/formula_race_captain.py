"""Formula R.A.C.E. fixed-team captain surface."""
import json
from pathlib import Path
import uuid
import streamlit as st
from data.google_sheets import GoogleSheetsDB
from data.runtime_database import RuntimeDatabaseError, get_runtime_database

ASSET_ROOT=Path(__file__).resolve().parents[1]/"Assets"/"race_teams"
TEAM_ASSETS=json.loads((ASSET_ROOT/"manifest.json").read_text())

def _device_id():
    value=str(st.session_state.get("race_captain_device_id", ""))
    if not value:value=str(uuid.uuid4());st.session_state["race_captain_device_id"]=value
    return value

def _set_session(payload):
    st.session_state["race_captain"]=dict(payload);st.query_params["race"]="1"
    st.query_params["captain_session"]=payload.get("SessionToken","")

def show_formula_race_captain():
    runtime=get_runtime_database();device=_device_id();session=st.session_state.get("race_captain")
    token=str(st.query_params.get("captain_session",""))
    if not session and token:
        try:session=runtime.restore_formula_race_captain(token,device)
        except RuntimeDatabaseError:session=None
        if session:_set_session(session)
    if not session:
        st.title("Formula R.A.C.E.");st.caption("TEAM CAPTAIN ACCESS · ONE TEAM · ONE ACTIVE DEVICE")
        join_code=st.text_input("Event Join Code").upper().strip()
        event=runtime.get_event_by_join_code(join_code) if join_code else None
        db=GoogleSheetsDB() if event else None
        teams=db.get_teams(str(event.get("EventID",""))) if event else []
        team_map={str(r.get("TeamName","")):str(r.get("TeamID","")) for r in teams}
        with st.form("race_captain_login"):
            team=st.selectbox("Team",list(team_map),disabled=not team_map);pin=st.text_input("Team PIN",type="password")
            submit=st.form_submit_button("Open Team Dashboard",type="primary",width="stretch")
        if submit:
            if not event:st.error("Enter a valid Formula R.A.C.E. event code.");return
            try:payload=runtime.formula_race_captain_login(join_code,team_map[team],pin,device)
            except RuntimeDatabaseError as error:st.error(str(error));return
            _set_session(payload);st.rerun()
        return
    db=GoogleSheetsDB()
    event_id=str(session.get("EventID",""));team_id=str(session.get("TeamID",""));name=str(session.get("TeamName",""))
    asset=ASSET_ROOT/TEAM_ASSETS.get(name,"")
    if asset.is_file():st.image(str(asset),width=96)
    st.title(name);st.caption(f"{event_id} · {team_id}")
    missions=db.get_event_missions(event_id)
    submissions=[r for r in db.get_event_submissions(event_id) if str(r.get("TeamID",""))==team_id]
    approved=sum(str(r.get("Status","")).upper() in {"APPROVED","AWARDED"} for r in submissions)
    a,b,c=st.columns(3);a.metric("Missions",f"{approved} / {len(missions)}");b.metric("Build status","Not Started" if not approved else "Building");c.metric("Wallet","Canonical ledger")
    one,two,three=st.tabs(["Missions","Wallet & Marketplace","Submissions"])
    with one:st.dataframe(missions,width="stretch",hide_index=True)
    with two:st.info("Wallet and purchases are scoped to this EventID and TeamID.")
    with three:st.dataframe(submissions,width="stretch",hide_index=True)
    if st.button("Log out",width="stretch"):
        st.session_state.pop("race_captain",None);st.query_params.clear();st.rerun()
