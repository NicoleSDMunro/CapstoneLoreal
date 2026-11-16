"""Testes do impacto operacional com cenários sintéticos e trajetórias pareadas."""
import numpy as np
import pandas as pd
from smartlaunch_impact import (
    consumption_after_target, editable_lots, evaluate_lot_options,
    outcome_metrics, historical_mape_vs_official,
)

months=list(pd.period_range("2026-06",periods=9,freq="M"))
dm=np.array([
    [20.]*9,
    [40.]*9,
    [60.]*9,
    [80.]*9,
],dtype=float)
res={
    "months":months,
    "dm":dm,
    "active":np.array([True]*8+[False]),
    "e0":70.,
    "production":np.array([100.,0.,0.,0.,0.,0.,0.,0.,0.]),
    "ltm":1,
}
close=pd.Period("2026-04",freq="M")
lots=editable_lots(res,close)
assert len(lots)==1
assert lots[0]["deadline"]==pd.Period("2026-05",freq="M")
base=outcome_metrics(res,res["production"],0)
assert 0 <= base["fill_rate_pct"] <=100
assert base["evaluated_months"]==8
assert base["extrapolated_months"]==0
assert base["demand_scenarios"]==4

# O lote reduzido pode diminuir o excesso mas nunca diminuir vendas perdidas
# se todos os demais termos permanecerem idênticos.
candidates,benchmark=evaluate_lot_options(res,0,0)
assert len(candidates)==9
baseline=candidates[candidates["Alternativa"]=="Manter plano"].iloc[0]
assert baseline["Excesso potencialmente evitado (un.)"]==0
assert baseline["Vendas perdidas adicionais (un.)"]==0
assert abs(baseline["Fill rate simulado (%)"]-base["fill_rate_pct"])<1e-10
for name in ["Reduzir 5%","Reduzir 10%","Reduzir 25%","Reduzir 50%","Cancelar lote"]:
    option=candidates[candidates["Alternativa"]==name].iloc[0]
    assert option["Excesso potencialmente evitado (un.)"]>=-1e-8, (name,option)
    assert option["Vendas perdidas adicionais (un.)"]>=-1e-8, (name,option)
    assert option["Fill rate simulado (%)"]<=base["fill_rate_pct"]+1e-8, (name,option)

assert np.allclose(res["production"],[100.,0.,0.,0.,0.,0.,0.,0.,0.]),"Plano alterado involuntariamente"
assert candidates["Não dominada (excesso × perda)"].any()

# Quando o alvo é o último mês, repetir o último cenário por seis meses.
six,extrap=consumption_after_target(dm,8)
assert extrap==6
assert np.allclose(six,6*dm[:,-1])
assert outcome_metrics(res,res["production"],8)["extrapolated_months"]==6

# O mês-limite é incluído apenas para comparação: depende da data de corte.
boundary = editable_lots(res,pd.Period("2026-05",freq="M"))
assert len(boundary)==1 and boundary[0]["boundary"]
assert not editable_lots(res,pd.Period("2026-06",freq="M"))

# O benchmark Oficial usa os mesmos pares de fechamento e alvo.
d=pd.DataFrame([
    {"Origem":"jan/26","Alvo":"fev/26","Modelo":"MEA-P","APE":10.},
    {"Origem":"jan/26","Alvo":"fev/26","Modelo":"Oficial","APE":20.},
    {"Origem":"fev/26","Alvo":"mar/26","Modelo":"MEA-P","APE":15.},
    {"Origem":"fev/26","Alvo":"mar/26","Modelo":"Oficial","APE":25.},
    {"Origem":"mar/26","Alvo":"abr/26","Modelo":"MEA-P","APE":40.},
])
c=historical_mape_vs_official(d,"MEA-P")
assert c["pares"]==2 and c["mape_operacional"]==12.5
assert c["mape_oficial"]==22.5 and c["delta_pp"]==10
assert historical_mape_vs_official(d,"Naive") is None
print("IMPACT METRICS PASS")

# Critério do TCC: cortes em passos de 5% não devem criar sinal novo
# nem elevar probabilidade mensal de ruptura em mais de 2,5 p.p.
from smartlaunch_impact import tcc_lot_limits, tcc_check
res_cut={
    "months":months,"dm":dm,
    "active":np.array([True]*8+[False]),
    "e0":0.,
    "production":np.array([80.,0.,0.,0.,0.,0.,0.,0.,0.]),
    "ltm":1,"window":8,
}
limits=tcc_lot_limits(res_cut,0)
assert limits["max_cut_pct"]==0,limits   # 5% cria ruptura no cenário de demanda 80
res_cut["production"][0]=1000.
limits=tcc_lot_limits(res_cut,0)
assert 0<limits["max_cut_pct"]<100,limits
plan=res_cut["production"].copy()
plan[0]=0.
assert tcc_check(res_cut,plan)["new_rupture"]
options,_=evaluate_lot_options(res_cut,0,0)
assert "Dentro do critério do TCC" in options.columns
assert options.loc[options["Alternativa"]=="Cancelar lote",
                   "Dentro do critério do TCC"].iloc[0]==False
print("TCC CUT RULE PASS",limits)
