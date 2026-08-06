"""Client-promised Formula R.A.C.E. product shell."""
from __future__ import annotations

import streamlit as st

from data.formula_race_contracts import DemoFormulaRaceProvider, LiveFormulaRaceProvider, RaceSnapshot


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
    div[data-testid="stHorizontalBlock"]{gap:.75rem} [data-testid="stSidebar"]{display:none}
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
        c2.markdown(f"<div><b>{t.name.upper()}</b> <span class='muted'>· {t.country}</span><div class='bar'><i style='width:{t.build}%'></i></div></div>", unsafe_allow_html=True)
        c3.metric("Score", t.score)
        c4.metric("Credits", t.balance)


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
        st.subheader("Live Championship"); _team_rows(s,4)
    with right:
        st.subheader("Recent Activity")
        for item in s.activity: st.markdown(f"<div class='race-card'>{item}</div>",unsafe_allow_html=True)
    c1,c2=st.columns(2)
    with c1:
        st.subheader("Review Queue")
        for x in s.submissions[:2]: st.markdown(f"<div class='race-card'><h3>{x.checkpoint}</h3><p>{x.team_id} · {x.evidence} · {x.submitted_at}</p><span class='accent'>{x.status}</span></div>",unsafe_allow_html=True)
    with c2:
        st.subheader("System & Stock")
        for n,q in s.stock.items(): st.progress(min(q/70,1),text=f"{n} · {q} available")


def live_programme(s):
    _title("Day One / Programme Journey", "Build It. Race It. Win It.", "Seven gated checkpoints move every team from briefing to championship.")
    stages=[("01","Design Brief",100),("02","Concept & Roles",100),("03","Skeleton Build",100),("04","Chassis Construction",63),("05","Finishing Touches",0),("06","Drag Race",0),("07","Debrief & Celebrate",0)]
    for no,name,p in stages:
        c1,c2,c3=st.columns([.7,4,1.2]); c1.markdown(f"<span class='rank'>{no}</span>",unsafe_allow_html=True); c2.markdown(f"### {name}"); c2.progress(p/100); c3.markdown("<span class='status'>ACTIVE</span>" if p not in (0,100) else ("✓ COMPLETE" if p==100 else "LOCKED"),unsafe_allow_html=True)
    if st.button("Open active checkpoint",type="primary",width="stretch"): st.session_state.race_nav="Checkpoints"; st.rerun()


def championship(s, final=False):
    _title("Official standings" if final else "Live timing", "Final Championship" if final else "Live Championship", "Canonical award-ledger projection when connected; demonstration standings shown now.")
    _team_rows(s)
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
    _title("Checkpoint Control", "Live Programme Control", "Select a checkpoint to inspect status and telemetry. Runtime changes live only in Control Centre.")
    cp=st.selectbox("Select checkpoint",["CP1 · Design","CP2 · Roles","CP3 · Skeleton","CP4 · Chassis","CP5 · Finish","CP6 · Race","CP7 · Debrief"],index=3)
    a,b,c=st.columns(3); a.metric("Teams complete","3 / 6"); b.metric("Average duration","18:32"); c.metric("Evidence received","9 files")
    st.subheader("Team Telemetry")
    st.dataframe([{"Team":t.name,"Checkpoint":cp,"Progress":f"{min(100,t.build+8)}%","Last signal":f"{t.rank+1} min ago"} for t in s.teams],width="stretch",hide_index=True)
    if st.button("Open Control Centre",type="primary",width="stretch"): st.session_state.race_nav="Control Centre"; st.rerun()


def reviews(s):
    _title("Submission and Award Pipeline", "Review Queue", "Decisions shown here are UAT-only until a canonical submission ID and reviewer identity are available.")
    for x in s.submissions:
        with st.container(border=True):
            c1,c2=st.columns([4,1]); c1.markdown(f"### {x.checkpoint}\n{x.team_id} · {x.evidence} · submitted {x.submitted_at}"); c2.markdown(f"**{x.status}**")
            a,b,c=st.columns(3)
            if a.button("Award",key=f"award_{x.id}",disabled=x.status!="PENDING"): st.toast(f"Demo decision recorded locally for {x.id}")
            if b.button("Request revision",key=f"revise_{x.id}",disabled=x.status!="PENDING"): st.toast(f"Demo revision requested for {x.id}")
            if c.button("Reject",key=f"reject_{x.id}",disabled=x.status!="PENDING"): st.toast(f"Demo rejection recorded locally for {x.id}")
    if st.button("Open team photo gallery",width="stretch"): st.session_state.race_subscreen="gallery"; st.rerun()


def gallery(s):
    _title("Evidence", "Team Photo Gallery", "Review checkpoint evidence by team; demonstration frames stand in for canonical media URLs.")
    for row in range(2):
        cols=st.columns(3)
        for col,t in zip(cols,s.teams[row*3:row*3+3]):
            col.markdown(f"<div class='race-card' style='height:180px;background:linear-gradient(145deg,{t.colour}33,#0c2435)'><span class='demo'>DEMO IMAGE</span><h3 style='margin-top:75px'>{t.name}</h3><p>Checkpoint build evidence</p></div>",unsafe_allow_html=True)
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


def judging(s):
    _title("Official Scoring", "Judging", "Weighted scoring contract prepared for canonical Judge Score and scoring configuration.")
    names=[t.name for t in s.teams]; idx=names.index(st.session_state.get("judge_team",names[0])); team=st.selectbox("Select team",names,index=idx,key="judge_team")
    p,n=st.columns(2)
    if p.button("← Previous team",width="stretch"): st.session_state.judge_team=names[(names.index(team)-1)%len(names)]; st.rerun()
    if n.button("Next team →",width="stretch"): st.session_state.judge_team=names[(names.index(team)+1)%len(names)]; st.rerun()
    total=0.0
    for criterion,weight in CRITERIA:
        score=st.slider(f"{criterion} · {weight}%",0,10,7,key=f"score_{team}_{criterion}"); total+=score*weight/10
    st.metric("Weighted total",f"{total:.1f} / 100"); st.progress((names.index(team)+1)/len(names),text=f"Judging progress · {names.index(team)+1} of {len(names)} teams")
    if st.button("Submit score",type="primary",width="stretch"): st.session_state.judge_confirm=f"Demo score {total:.1f} prepared for {team}"
    if st.session_state.get("judge_confirm"): st.success(st.session_state.judge_confirm+". No canonical Judge Score was written.")


def drag_results(s):
    _title("Official Timing", "Drag Race Results", "Heat results and fastest-lap bonus projection.")
    rows=[]
    for i,t in enumerate(s.teams): rows.append({"Pos":i+1,"Team":t.name,"Best time":f"{12+i}.{18+i*7:02}s","Speed":f"{31-i*1.4:.1f} km/h","Points":120-i*12})
    st.dataframe(rows,width="stretch",hide_index=True); st.markdown("<div class='race-card'><h3>Fastest Lap</h3><p>Velocity · 12.18 seconds</p><span class='accent'>+25 BONUS POINTS</span></div>",unsafe_allow_html=True)


def build_status(s):
    _title("Engineering Readiness", "Build Status", "Materials, structural checkpoints and race-readiness by team.")
    for t in s.teams:
        c1,c2,c3=st.columns([2,5,1]); c1.markdown(f"**{t.name.upper()}**\n\n{t.country}"); c2.progress(t.build/100,text=f"Build completion · {t.build}%"); c3.markdown("✅ READY" if t.build>85 else ("🟡 BUILDING" if t.build>60 else "🔧 ACTION"))


def control_centre(s):
    _title("Canonical Runtime Facade", "Race Control Centre", "Operational controls are arranged for tablet use. Demo mode never mutates EXOS runtime.")
    checkpoint=st.selectbox("Select checkpoint",["CP3 · Skeleton","CP4 · Chassis","CP5 · Finish"],index=1)
    st.caption(f"Selected: {checkpoint} · source {s.source}")
    def action(label,key,kind="secondary"):
        if st.button(label,key=key,type=kind,width="stretch"): st.toast(f"DEMO ONLY · {label} acknowledged locally")
    a,b,c=st.columns(3); 
    with a: action("Launch checkpoint","launch","primary")
    with b: action("Close checkpoint","close")
    with c: action("Pause race","pause")
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
    with t3: st.selectbox("Adjust team",[t.name for t in s.teams],key="adjust_team"); st.number_input("Credit adjustment",-500,500,0); st.text_input("Required reason"); action("Prepare adjustment","adjust_credit")
    st.warning("DEMO DATA · Live controls will call data.control_runtime.ControlRuntime only after canonical event, identity and authority checks pass.")


def show_formula_race(db=None, event_id=""):
    _css()
    if db is None:
        snapshot=DemoFormulaRaceProvider().snapshot(event_id or str(st.session_state.get("active_event_id","")))
    else:
        snapshot=LiveFormulaRaceProvider(db).snapshot(event_id)
    page=_top(snapshot); sub=st.session_state.get("race_subscreen","")
    if sub=="wallet": wallet(snapshot)
    elif sub=="gallery": gallery(snapshot)
    elif page=="Overview": overview(snapshot)
    elif page=="Live Programme": live_programme(snapshot)
    elif page=="Championship":
        view=st.radio("Championship view",["Live Championship","Drag Race Results","Final Championship"],horizontal=True,label_visibility="collapsed")
        drag_results(snapshot) if view=="Drag Race Results" else championship(snapshot,view=="Final Championship")
    elif page=="Teams": teams(snapshot)
    elif page=="Checkpoints":
        view=st.radio("Checkpoint view",["Checkpoint Control","Build Status"],horizontal=True,label_visibility="collapsed")
        checkpoints(snapshot) if view=="Checkpoint Control" else build_status(snapshot)
    elif page=="Reviews":
        view=st.radio("Review view",["Review Queue","Photo Gallery","Judging"],horizontal=True,label_visibility="collapsed")
        reviews(snapshot) if view=="Review Queue" else (gallery(snapshot) if view=="Photo Gallery" else judging(snapshot))
    elif page=="Marketplace":
        if snapshot.is_demo: marketplace(snapshot)
        else:
            _title("Canonical marketplace", "Build Materials Depot", "Live purchases, stock deduction and overspend prevention are operated in Control Centre.")
            st.info("Open Race Control to manage the live marketplace and audited team wallets.")
            st.dataframe([x.__dict__ for x in snapshot.transactions if x.kind in {"SPEND", "REFUND"}], width="stretch", hide_index=True)
    elif page=="Race Map": race_map(snapshot)
    else:
        if snapshot.is_demo: control_centre(snapshot)
        else: st.info("Use the Race Control workspace above for canonical live mutations.")
