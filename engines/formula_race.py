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
    config=dict(config or {})
    by_team=defaultdict(lambda:{"DayOneCredits":0.0,"BuildScore":0.0,"PhotoScore":0.0,"RaceScore":0.0})
    for row in awards:
        team=str(row.get("TeamID",row.get("team_id","")));kind=str(row.get("Component",row.get("component","DayOneCredits")))
        if kind in by_team[team]:by_team[team][kind]+=float(row.get("Amount",row.get("amount",0)) or 0)
    for row in judging:by_team[str(row.get("TeamID",row.get("team_id","")))]["BuildScore"]=float(row.get("Total",row.get("total_score",0)) or 0)
    for row in race_results:by_team[str(row.get("TeamID",row.get("team_id","")))]["RaceScore"]=float(row.get("BonusCredits",row.get("bonus_credits",0)) or 0)
    result=[]
    for team in teams:
        team_id=str(team.get("TeamID",team.get("id","")));parts=by_team[team_id]
        total=sum(parts.values());result.append({"TeamID":team_id,"TeamName":team.get("TeamName",team.get("name",team_id)),**parts,"OverallTotal":round(total,2)})
    result.sort(key=lambda row:(-row["OverallTotal"],row["TeamName"]))
    for index,row in enumerate(result,1):row["Rank"]=index
    return result

def validate_purchase(balance,stock,price,quantity):
    quantity=int(quantity)
    if quantity<1:return False,"Quantity must be at least one."
    if quantity>int(stock):return False,"Insufficient stock."
    if float(price)*quantity>float(balance):return False,"Insufficient credits."
    return True,""
