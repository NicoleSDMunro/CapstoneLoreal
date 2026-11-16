"""Valida alinhamento entre alertas, prazos e decisões sem dados reais."""
import ast
from pathlib import Path
import numpy as np
import pandas as pd
from smartlaunch_supply import future_lots

src=Path("smartlaunch_ui.py").read_text(encoding="utf-8")
tree=ast.parse(src)
wanted={"rows_from_sim","eligible_lots","classify_action","scenario_plan"}
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
assert {n.name for n in functions}==wanted
ns={"np":np,"pd":pd,"LIM":180,"LIMIT_ALERT":.20, "LIMIT_WARN":.025, "future_lots":future_lots,
    "label":lambda p: p.strftime("%m/%Y")}
exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),
             "smartlaunch_rules", "exec"),ns)

close=pd.Period("2026-06",freq="M")
months=list(pd.period_range("2026-07",periods=4,freq="M"))
result={
    "months":months, "ltm":2, "window":4,
    "production":np.array([100.,0.,100.,0.]),
    "center":np.array([30.,30.,30.,30.]),
    "active":np.array([True,True,True,False]),
    "cov":np.array([[200.,90.,220.,200.],[190.,80.,100.,200.],[40.,80.,100.,200.]]),
    "lost":np.array([[0.,0.,2.,0.],[0.,0.,0.,0.],[0.,0.,0.,0.]]),
    "stock":np.array([[200.,90.,100.,100.],[150.,80.,90.,100.],[60.,70.,90.,100.]]),
}
frame=ns["rows_from_sim"](result)
assert frame.loc[0,"Mês"]=="07/2026"
assert frame.loc[0,"Excesso (%)"]==66.7
assert bool(frame.loc[0,"Alerta excesso"])
assert not bool(frame.loc[3,"Alerta excesso"]), "Fora da janela crítica, sem alerta mesmo com excesso"
assert bool(frame.loc[2,"Alerta ruptura"])

lots=ns["eligible_lots"](result,close)
assert [x["alterável"] for x in lots]==[False,True], lots
act,_=ns["classify_action"](result,close,months[0],"excesso")
assert act=="Ação comercial + revisar futuro", "Lote de setembro não resolve o excesso de julho"
act,_=ns["classify_action"](result,close,months[2],"excesso")
assert act=="Avaliar fornecedor"

before=result["production"].copy()
new=ns["scenario_plan"](result,2,"Reduzir 25%")
assert new[2]==75
assert np.array_equal(result["production"],before)
assert ns["scenario_plan"](result,0,"Manter lote")[0]==100
print("ALERT RULES PASS")
