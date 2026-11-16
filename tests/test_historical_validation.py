"""Testes de validação histórica: sem vazamento e sem 'realizados' fictícios."""
import runpy
import numpy as np
import pandas as pd
from smartlaunch_validation import (
    recorded_value, observed_cover, deadlines_for_risk,
    reconstruct_history, first_alerts, latest_verifiable_close,
    EVENT_YES, EVENT_NO, EVENT_WAIT, EVENT_NO_STOCK, RUPTURE_UNVERIFIED,
)
from smartlaunch_core import load_data, MODEL, label

m = lambda s: pd.Period(s, freq="M")
origin=m("2026-04")
target=m("2026-05")
six=[target+i for i in range(1,7)]

# Sem as-of futuro: valor registrado em revisão posterior não pode ser lido na origem.
frame=pd.DataFrame({target:[15.,35.]},index=[target,target+1])
assert recorded_value(frame,target,origin) is None
assert recorded_value(frame,target,target)==35.

stock=100
sales={month:10. for month in six}
days,text,event=observed_cover(stock,target,sales,six[-1])
assert event==EVENT_YES and days is None and "180" in text
days,text,event=observed_cover(stock,target,{month:20. for month in six},six[-1])
assert event==EVENT_NO and abs(days-150)<1e-8
days,text,event=observed_cover(stock,target,{six[0]:20.,six[1]:20.},six[1])
assert event==EVENT_WAIT and days is None
days,text,event=observed_cover(None,target,sales,six[-1])
assert event==EVENT_NO_STOCK
days,text,event=observed_cover(0.,target,{},target)
assert event==EVENT_NO and days==0

lot_months=[m("2026-05"),m("2026-07"),m("2026-09")]
lots=np.array([100.,100.,100.])
state,deadline,can=deadlines_for_risk(lots,lot_months,origin,m("2026-08"),2)
assert can and deadline==m("2026-05"), (state,deadline,can)
state,deadline,can=deadlines_for_risk(lots,lot_months,origin,m("2026-05"),2)
assert not can and state=="Prazo teórico encerrado"
state,deadline,can=deadlines_for_risk(lots,lot_months,origin,m("2026-08"),4)
assert not can
# No mês limite, reportar oportunidade teórica sujeita a data de corte.
state,deadline,can=deadlines_for_risk(
    np.array([100.]),[m("2026-11")],m("2026-07"),m("2026-11"),4
)
assert can and deadline==m("2026-07") and "Mês-limite" in state
state,deadline,can=deadlines_for_risk(np.array([0.,0.,100.]),lot_months,origin,m("2026-08"),2)
assert state=="Sem lote positivo até o risco"

# O mesmo alerta emitido em duas origens para o mesmo alvo conta UMA vez.
d=pd.DataFrame([
    {"Produto":"P1","_alvo":target,"_origem":origin,
     "Tipo de alerta":"Excesso","Status observado":EVENT_WAIT},
    {"Produto":"P1","_alvo":target,"_origem":origin-1,
     "Tipo de alerta":"Excesso","Status observado":EVENT_WAIT},
    {"Produto":"P1","_alvo":target,"_origem":origin,
     "Tipo de alerta":"Ruptura","Status observado":RUPTURE_UNVERIFIED},
])
unique=first_alerts(d)
assert len(unique)==2
assert unique[unique["Tipo de alerta"]=="Excesso"].iloc[0]["_origem"]==origin-1

# Executa todo o módulo contra workbook 100% sintético.
sample=runpy.run_path("tests/test_smoke.py")
base,blocks=load_data(sample["buf"].getvalue())
last=latest_verifiable_close(blocks,"P1")
assert last is not None
forecasts,alerts,missing=reconstruct_history(
    "P1",last,blocks,base,model=MODEL["P1"],
    max_origins=7,max_horizon=4
)
assert not forecasts.empty
assert (forecasts["_alvo"]>forecasts["_origem"]).all()
assert (forecasts["Horizonte"]<=4).all()
assert (forecasts["_origem"]<=last).all()
assert forecasts["Previsão no fechamento (un.)"].notna().all()
assert (forecasts["Venda realizada (un.)"].notna() | (forecasts["_alvo"]>last)).all()
if not alerts.empty:
    assert alerts["Na janela crítica"].all()
    assert (alerts["Probabilidade do alerta (%)"]>20).all()
    assert all(x==RUPTURE_UNVERIFIED for x in alerts.loc[
        alerts["Tipo de alerta"]=="Ruptura","Status observado"
    ])
print("HISTORICAL VALIDATION PASS",len(forecasts),"previsões,",len(alerts),"alertas")
