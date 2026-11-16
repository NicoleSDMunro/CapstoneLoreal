"""Indicadores por alerta, mês-limite e comparação com previsão Oficial."""
import numpy as np
import pandas as pd

from smartlaunch_metrics import (current_alert_opportunities, compare_verified_excess,
                                 format_opportunity_months)
from smartlaunch_validation import EVENT_YES, EVENT_NO

m = lambda v: pd.Period(v, freq="M")
months = [m("2026-08"),m("2026-09"),m("2026-10"),m("2026-11"),m("2026-12")]
close = m("2026-07")
# Dois riscos de excesso com 50%, um de ruptura com 50%:
# agosto sem lote até o risco; nov no mês-limite; dez prazo futuro.
cov=np.full((4,5),90.)
cov[:2,0]=200.
cov[:2,3]=200.
cov[:2,4]=200.
lost=np.zeros((4,5))
lost[:2,4]=100.
res={
    "months":months,"production":np.array([0.,0.,0.,100.,200.]),
    "ltm":4,"active":np.array([True]*5),
    "cov":cov,"lost":lost,
}
result=current_alert_opportunities({"P1":res,"P2":None},close)
assert result["total"]==4,result
assert result["future"]==2,result
assert result["boundary"]==1,result
assert result["possible"]==3 and result["rate"]==75.0,result
assert result["rows"][0]["Situação do prazo"]=="Sem lote positivo até o risco"
assert result["rows"][1]["Situação do prazo"]=="Mês-limite: confirmar corte"
assert current_alert_opportunities({"P2":None},close)["rate"] is None

# Regressão do KeyError da interface: None torna-se pandas.NaT em coluna PeriodDtype.
# Ambos os caminhos (tabela Streamlit e aba Excel) compartilham o mesmo formatter.
raw = pd.DataFrame(result["rows"]).copy()
assert raw["Mês-limite"].isna().any()
formatted = format_opportunity_months(raw)
assert formatted.iloc[0]["Mês-limite"] == "—", formatted
assert formatted.iloc[1]["Mês-limite"] == "jul/26", formatted
assert formatted.iloc[0]["Mês-alvo"] == "ago/26", formatted
assert formatted["Mês-limite"].notna().all()
assert isinstance(formatted.iloc[0]["Mês-limite"], str)
# Caso explícito de série period[M] com NaT, como no erro do Streamlit Cloud.
with_nat = pd.DataFrame({
    "Mês-alvo":pd.Series([m("2026-08"),m("2026-09")],dtype="period[M]"),
    "Mês-limite":pd.Series([pd.NaT,m("2026-07")],dtype="period[M]"),
})
converted = format_opportunity_months(with_nat)
assert converted["Mês-limite"].tolist() == ["—","jul/26"]
import io
buf=io.BytesIO()
with pd.ExcelWriter(buf,engine="openpyxl") as writer:
    formatted.to_excel(writer,sheet_name="Prazo dos alertas",index=False)
assert buf.getbuffer().nbytes>0


# Confirmado: mesma venda/estoque retrospectivos; avisos diferentes.
observed = pd.DataFrame([
    {"Produto":"P1","_alvo":m("2026-11"),"Mês-alvo":"nov/26",
     "Verificação de excesso":EVENT_YES},
    {"Produto":"P1","_alvo":m("2026-12"),"Mês-alvo":"dez/26",
     "Verificação de excesso":EVENT_NO},
])
smart = pd.DataFrame([{
    "Produto":"P1","_alvo":m("2026-11"),"_origem":m("2026-07"),
    "Fechamento":"jul/26","Tipo de alerta":"Excesso",
    "Antecedência (meses)":4,"Emitido em tempo pelo LT":True,
}])
official = pd.DataFrame([{
    "Produto":"P1","_alvo":m("2026-11"),"_origem":m("2026-10"),
    "Fechamento":"out/26","Tipo de alerta":"Excesso",
    "Antecedência (meses)":1,"Emitido em tempo pelo LT":False,
}])
frame=compare_verified_excess(observed,smart,official)
assert len(frame)==1,frame
row=frame.iloc[0]
assert row["Quem avisou primeiro"]=="Smart antes"
assert row["Smart: antecedência (meses)"]==4
assert row["Oficial*: antecedência (meses)"]==1
assert bool(row["Smart: oportunidade pelo LT"])
assert not bool(row["Oficial*: oportunidade pelo LT"])
assert compare_verified_excess(observed.iloc[:0],smart,official).empty
assert compare_verified_excess(observed,smart.iloc[:0],official).iloc[0][
    "Quem avisou primeiro"]=="Só Oficial sinalizou"
print("TIMELINESS METRICS PASS")
