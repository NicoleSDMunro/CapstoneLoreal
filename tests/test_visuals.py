"""Teste de regressão dos gráficos: dados sintéticos, sem Triângulo empresarial."""
import numpy as np
import pandas as pd

from smartlaunch_visuals import (
    forecast_figure, stock_flow_figure, decision_timeline_figure, tradeoff_figure
)
from smartlaunch_supply import future_lots
from smartlaunch_core import label

close = pd.Period("2026-06", freq="M")
months = [close + i for i in range(1, 6)]
history = pd.Series(
    [180, 155, 135, 120],
    index=pd.period_range("2026-03", periods=4, freq="M"),
    dtype=float
)
demand = np.array([[110, 100, 100, 90, 90],
                   [120, 100, 90, 90, 90],
                   [105, 95, 95, 90, 80]], dtype=float)
stock = np.array([[550, 420, 330, 255, 200],
                  [540, 430, 340, 250, 190],
                  [530, 410, 325, 245, 180]], dtype=float)
cover = np.array([[230, 210, 190, 150, np.nan],
                  [225, 202, 178, 145, np.nan],
                  [245, 200, 180, 146, np.nan]], dtype=float)
lost = np.zeros_like(stock)
lost[0, 1] = 10
res = {
    "months": months,
    "center": demand.mean(axis=0),
    "production": np.array([0., 200., 0., 130., 0.]),
    "dm": demand, "stock": stock, "cov": cover, "lost": lost,
    "active": np.array([True, True, True, True, False]),
    "evaluated": np.array([True, True, True, True, False]),
    "ltm": 2
}
p = forecast_figure(history, months, res["center"], np.ones(5)*120,
                    demand, close, label, critical_count=3)
assert len(p.data) == 5, "Realizado + 2 previsões + limites da simulação"
assert "realizad" in p.data[0].name.lower()
assert any("Oficial" in (trace.name or "") for trace in p.data)
assert "não calibrada" in str([t.name for t in p.data])
f = stock_flow_figure(res, label)
assert len(f.data) == 4
assert f.data[-1].y[-1] is None, "Último mês não pode aparecer como cobertura zero"
lots = future_lots(res, close)
assert len(lots) == 2
t = decision_timeline_figure(res, close, label, lots)
assert t.data and len(t.data[0].x) >= 2
assert any(x == label(months[3]) for x in t.data[0].x)
frame = pd.DataFrame([
    {"Alternativa": "Manter plano", "Excesso potencialmente evitado (un.)": 0,
     "Vendas perdidas adicionais (un.)": 0, "Dentro do critério do TCC": True},
    {"Alternativa": "Reduzir 10%", "Excesso potencialmente evitado (un.)": 1000,
     "Vendas perdidas adicionais (un.)": 10, "Dentro do critério do TCC": True},
    {"Alternativa": "Cancelar lote", "Excesso potencialmente evitado (un.)": 3000,
     "Vendas perdidas adicionais (un.)": 100, "Dentro do critério do TCC": False},
])
chart = tradeoff_figure(frame, "Reduzir 10%")
assert len(chart.data) == 3
assert any(trace.marker.symbol == "diamond" for trace in chart.data)
print("VISUAL PASS: histórico, faixas simuladas, estoque, cobertura, LT, cortes")
