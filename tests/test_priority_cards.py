"""O card resume as MESMAS probabilidades mostradas nos gráficos.

Não usar data diária ou promessa de alteração em fornecedor sem fonte.
"""
import numpy as np
import pandas as pd
from smartlaunch_priority import card_summary

months=list(pd.period_range("2026-12", periods=4, freq="M"))
close=pd.Period("2026-11",freq="M")
# 20 cenários: excesso dez 10%, jan 20%, fev 40%; ruptura dez 0, jan 15%.
cov=np.full((20,4),90.)
cov[:6,0]=220
cov[:8,1]=220
cov[:10,2]=220
lost=np.zeros((20,4))
lost[:3,1]=15
res={"months":months,"active":np.array([True,True,True,False]),
     "cov":cov,"lost":lost,"production":np.array([0.,100.,0.,0.]),
     "ltm":1}
summary=card_summary("P2",res,close)
assert summary["alert"]
assert summary["type"]=="Excesso"
assert summary["first_month"]==months[0]
assert summary["peak_month"]==months[2]
assert abs(summary["peak_probability"]-.50)<1e-10
assert abs(summary["first_probability"]-.30)<1e-10
# A produção jan/27 não chega para mitigar um risco de dez/26.
assert not summary["first_target_has_changeable_lot"]
assert summary["deadline"] is None
assert summary["action"]=="Avaliação comercial"

# Com produção prevista para dezembro e prazo aberto, avaliar fornecedor.
res["production"]=np.array([100.,0.,0.,0.])
res["ltm"]=0
s=card_summary("P2",res,close)
assert s["first_target_has_changeable_lot"]
assert s["deadline"]==months[0]
assert s["action"]=="Avaliar fornecedor"
assert s["time_left_months"]==1

# Ruptura como primeiro risco: não recomendar corte de lote.
cov=np.full((20,4),90.)
lost=np.zeros((20,4))
lost[:6,0]=15
res["cov"]=cov
res["lost"]=lost
s=card_summary("P2",res,close)
assert s["type"]=="Ruptura"
assert "reforço" in s["suggested"]

# Sem alerta na janela crítica (risco fora dela não dispara aviso).
res["active"]=np.array([False,False,False,True])
res["lost"]=np.zeros((20,4))
res["cov"]=np.full((20,4),90.)
res["cov"][:10,0]=220
s=card_summary("P2",res,close)
assert not s["alert"]
assert s["action"]=="Monitoramento"
print("PRIORITY CARD PASS")

# Aviso não gera solicitação de fornecedor; alerta requer chance >20%.
res["active"]=np.array([True,True,True,False])
res["cov"]=np.full((20,4),90.)
res["cov"][:3,0]=220  # 15%: aviso
res["lost"]=np.zeros((20,4))
warning=card_summary("P2",res,close)
assert warning["warning"] and not warning["alert"]
assert warning["action"]=="Acompanhar (aviso)"
print("ALERT LEVELS PASS")
