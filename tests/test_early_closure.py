"""Fechamento inicial: mostrar previsão, sem inventar probabilidades."""
import ast
from pathlib import Path
import runpy
import pandas as pd
from smartlaunch_core import forecast, load_data, known, simulate, MODEL

sample = runpy.run_path("tests/test_smoke.py")
base, blocks = load_data(sample["buf"].getvalue())
close = pd.Period("2025-07",freq="M")
pv = blocks["PRODUTO 1"]["PV"]
assert max(known(pv,close).index) == close
assert max(known(pv,max(pv.index)).index) == max(pv.index)-1

try:
    simulate("P1",close,blocks,base)
except ValueError as exc:
    assert "erros de arranque" in str(exc),str(exc)
else:
    raise AssertionError("Os primeiros meses não devem gerar uma probabilidade com poucos erros.")

tree=ast.parse(Path("smartlaunch_ui.py").read_text(encoding="utf-8"))
fn=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="preview_forecast"]
assert len(fn)==1
from smartlaunch_core import SHEETS, label
import numpy as np
ns={"np":np,"pd":pd,"SHEETS":SHEETS,"forecast":forecast,"label":label}
exec(compile(ast.fix_missing_locations(ast.Module(body=fn,type_ignores=[])), "preview_only","exec"),ns)
frame,reason=ns["preview_forecast"]("P1",close,blocks,MODEL["P1"])
assert reason is None, reason
assert not frame.empty and "Previsão central (un.)" in frame.columns
print("EARLY CLOSURE PASS")
