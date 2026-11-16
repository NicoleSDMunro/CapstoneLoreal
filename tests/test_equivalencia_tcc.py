"""Equivalência entre o motor e resultados do notebook final do TCC.

Executar localmente COM autorização de uso do Triângulo real:
    TRIANGULO=/caminho/Triangulo_Produtos_V2.xlsx PYTHONPATH=. python tests/test_equivalencia_tcc.py

Sem a planilha correta, este teste é ignorado (NÃO comprova equivalência).
Os números esperados foram fornecidos no ZIP CapstoneLorealClean_ajustado.
"""
import os
import sys
import numpy as np
import pandas as pd

path=os.environ.get("TRIANGULO")
if not path or not os.path.isfile(path):
    print("EQUIVALÊNCIA TCC NÃO VERIFICADA: defina TRIANGULO com a planilha válida")
    sys.exit(0)

from smartlaunch_core import load_data, simulate, LIM, nivel
from smartlaunch_impact import tcc_lot_limits

with open(path,"rb") as arq:
    base,blocks=load_data(arq.read())
close=pd.Period("2026-06",freq="M")

# Referências declaradas no ZIP ajustado: notebook, passos P.6 e 7.2b.
REF={
    "P1":dict(exc=[.925,.689,.456,.304,.202,None],
              rup=[0,0,0,0,0,.004],
              nivel=["alerta"]*5+["não avaliado"]),
    "P3":dict(exc=[.002,.001,.061,.143,.221],
              rup=[.002,.227,.008,.008,.002],
              nivel=["—","—","aviso","aviso","alerta"]),
}
for product,reference in REF.items():
    res=simulate(product,close,blocks,base)
    for j,(e,r,n) in enumerate(zip(reference["exc"],reference["rup"],reference["nivel"])):
        pe=float((res["cov"][:,j]>=LIM).mean()) if res["evaluated"][j] else None
        pr=float((res["lost"][:,j]>0).mean())
        assert (pe is None and e is None) or abs(pe-e)<1e-9,(product,j,pe,e)
        assert abs(pr-r)<1e-9,(product,j,pr,r)
        assert nivel(pe)==n,(product,j,nivel(pe),n)

try:
    simulate("P2",close,blocks,base)
    raise AssertionError("P2 deveria ficar sem simulação no fechamento jun/26")
except ValueError:
    pass
res=simulate("P3",close,blocks,base)
cuts={str(res["months"][j]):tcc_lot_limits(res,j)["max_cut_pct"]
      for j in range(len(res["months"]))
      if res["production"][j]>0 and res["active"][j]}
assert cuts=={"2026-09":10,"2026-10":30,"2026-11":35},cuts
print("EQUIVALÊNCIA TCC PASS: resultados do ZIP reproduzidos no motor")
