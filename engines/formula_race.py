"""Deterministic Formula R.A.C.E. projections; persistence remains in EXOS."""
from __future__ import annotations
from collections import defaultdict

BUILD_STATUSES=("Not Started","Collecting Parts","Building","Painting","Ready to Race","Completed")
JUDGING_CATEGORIES=("Engineering Design","Structural Integrity","Innovation","Creativity","Race Performance","Team Presentation")

def judging_total(scores):
    """Configured categories are additive; no hidden weights are invented."""
    return round(sum(float(scores.get(category,0) or 0) for category in JUDGING_CATEGORIES),2)

def wallet_projection(transactions,event_id,team_id):
    rows=[row for row in transactions if str(row.get("EventID",row.get("event_id","")))==str(event_id)
          and str(row.get("TeamID",row.get("team_id","")))==str(team_id)]
    earned=sum(float(row.get("Amount",row.get("amount",0)) or 0) for row in rows
               if float(row.get("Amount",row.get("amount",0)) or 0)>0)
    spent=-sum(float(row.get("Amount",row.get("amount",0)) or 0) for row in rows
               if float(row.get("Amount",row.get("amount",0)) or 0)<0)
    return {"Earned":earned,"Spent":spent,"Balance":earned-spent,"Transactions":rows}

def final_standings(teams,awards,judging,race_results,config=None):
    """Project verified final R.A.C.E. positions from adjusted race time.

    The committed R.A.C.E. config specifies race-time ascending with stable
    TeamID tie-breaking. Judging and bonus credits remain persisted but are not
    configured final-rank inputs, so this function does not invent a formula.
    """
    by_team={str(row.get("TeamID",row.get("team_id",""))):row for row in race_results if bool(row.get("verified",row.get("Verified",False)))}
    rows=[]
    for team in teams:
        team_id=str(team.get("TeamID",team.get("id","")));result=by_team.get(team_id,{})
        time_ms=result.get("time_ms",result.get("finish_time_ms"));penalty=int(result.get("penalty_ms",0) or 0)
        adjusted=None if time_ms is None else int(time_ms or 0)+penalty
        rows.append({"TeamID":team_id,"TeamName":team.get("TeamName",team.get("name",team_id)),"RaceTimeMs":time_ms,"PenaltyMs":penalty,"AdjustedRaceTimeMs":adjusted,"BonusCredits":result.get("bonus_credits",result.get("bonus",0)),"Judging":"informational"})
    rows.sort(key=lambda row:(row["AdjustedRaceTimeMs"] is None,row["AdjustedRaceTimeMs"] or 0,row["TeamID"]))
    for index,row in enumerate(rows,1):row["Rank"]=index
    return rows

def validate_purchase(balance,stock,price,quantity):
    quantity=int(quantity)
    if quantity<1:return False,"Quantity must be at least one."
    if quantity>int(stock):return False,"Insufficient stock."
    if float(price)*quantity>float(balance):return False,"Insufficient credits."
    return True,""
