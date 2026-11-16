"""Regressões de prazo e de diagnóstico de fornecedores com dados fictícios."""
import numpy as np
import pandas as pd
from smartlaunch_supply import future_lots, supply_diagnosis
from smartlaunch_impact import editable_lots
from smartlaunch_priority import card_summary

close = pd.Period("2026-07", freq="M")
months = list(pd.period_range("2026-08", periods=5, freq="M"))
base = {
    "months": months, "ltm": 4,
    "active": np.array([True] * 5),
    "cov": np.full((20, 5), 110.),
    "lost": np.zeros((20, 5)),
    "production": np.zeros(5),
}
base["cov"][:10, 0] = 210.
base["cov"][:10, 3] = 210.

# Excesso sem nenhum novo lote no arquivo: não culpar lead time.
empty = supply_diagnosis(base, close)
assert not empty["lots"]
assert "Sem lotes positivos" in empty["situation"]
assert not editable_lots(base, close)
card = card_summary("P1", base, close)
assert card["action"] == "Avaliação comercial"
assert card["future_lot_count"] == 0
assert "Nenhum lote futuro positivo" in card["suggested"]

# Em julho, lote de novembro está no mês-limite (nov - 4 = jul).
base["production"] = np.array([0., 0., 0., 100., 200.])
lots = future_lots(base, close)
assert len(lots) == 2
assert lots[0]["month"] == pd.Period("2026-11", freq="M")
assert lots[0]["deadline"] == close
assert lots[0]["boundary"] and lots[0]["available_for_analysis"]
assert "confirmar" in lots[0]["situation"]
assert lots[1]["month"] == pd.Period("2026-12", freq="M")
assert lots[1]["deadline"] == pd.Period("2026-08", freq="M")
assert lots[1]["strictly_open"]
assert len(editable_lots(base, close)) == 2

# O excesso projetado de agosto não é removido por lotes que chegam em nov/dez.
card = card_summary("P1", base, close)
assert card["first_month"] == pd.Period("2026-08", freq="M")
assert card["action"] == "Avaliação comercial"
assert card["future_lot_after_risk_count"] == 2
assert card["future_lot_count"] == 2
assert not card["first_target_has_changeable_lot"]

# Mesmo lote de novembro com fechamento agosto tem prazo teórico vencido.
aug = pd.Period("2026-08", freq="M")
lots_aug = future_lots(base, aug)
assert len(lots_aug) == 2
assert not lots_aug[0]["available_for_analysis"]
assert lots_aug[1]["boundary"]
assert len(editable_lots(base, aug)) == 1

# Se houver lote no próprio mês do risco, o mês-limite requer confirmação.
base["cov"][:] = 90.
base["cov"][:8, 3] = 220.
card = card_summary("P1", base, close)
assert card["first_month"] == pd.Period("2026-11", freq="M")
assert card["action"] == "Avaliar fornecedor"
assert card["boundary_lot"]
assert "Mês-limite" in card["urgency"]
print("SUPPLY DEADLINES PASS")
