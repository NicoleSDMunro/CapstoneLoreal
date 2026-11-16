"""Testes isolados da comparação mensal; sem dados confidenciais."""
import numpy as np
import pandas as pd
from smartlaunch_monthly import evaluate_models, monthly_alert_rows

index=pd.period_range("2025-01","2025-10",freq="M")
columns=pd.period_range("2025-01","2025-12",freq="M")
pv=pd.DataFrame(100.0,index=index,columns=columns)
blocks={"PRODUTO 1":{"PV":pv}}

def known_fn(frame,close):
    return pd.Series({m:100.0 for m in columns if m<=close and m>=index[0]},dtype=float)

def forecast_fn(product,targets,origin,blocks,model):
    offset={"MEA-P":0,"MEA":10,"Oficial":20,"Naive":30}[model]
    return np.array([100.0+offset]*len(targets))

details,ranks,winner=evaluate_models("P1",pd.Period("2025-08","M"),blocks,forecast_fn,known_fn)
assert winner=="MEA-P", (winner,ranks)
assert details["Alvo"].max()=="2025-08"
assert len(details)%4==0
assert ranks["Previsões"].nunique()==1
assert ranks.iloc[0]["MAPE (%)"]==0

res={"months":list(pd.period_range("2025-09",periods=2,freq="M")),
     "cov":np.array([[200.,100.],[200.,100.],[100.,100.]]),
     "lost":np.array([[0.,0.],[2.,0.],[0.,0.]]),
     "active":np.array([True,False])}
alerts=monthly_alert_rows(res)
assert alerts.iloc[0]["Alerta excesso"]
assert alerts.iloc[0]["Alerta ruptura"]
assert not alerts.iloc[1]["Alerta excesso"]
print("MONTHLY PASS")
