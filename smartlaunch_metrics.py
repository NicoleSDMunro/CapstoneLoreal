"""Indicadores de antecedência do Smart Launch.

Não confundem uma janela de lead time com mudança de lote contratualmente aprovada.
Contam ocorrências únicas por produto, mês-alvo e tipo de risco no fechamento.
A comparação histórica é retrospectiva e usa somente excessos verificáveis.
"""
import numpy as np
import pandas as pd

from smartlaunch_supply import future_lots
from smartlaunch_validation import first_alerts, EVENT_YES
from smartlaunch_core import label, ALERTA



def format_opportunity_months(frame):
    """Formata meses para tabela e exportação, incluindo prazos inexistentes.

    O pandas converte None em NaT ao inferir uma coluna PeriodDtype; NaT não
    pode ser passado para a função label (que espera um Period válido).
    """
    formatted = frame.copy()

    def readable(value):
        if value is None or pd.isna(value):
            return "—"
        return label(value)

    for column in ("Mês-alvo", "Mês-limite"):
        if column in formatted.columns:
            formatted[column] = formatted[column].astype(object).map(readable)
    return formatted


def current_alert_opportunities(results, close, threshold=ALERTA, coverage_limit=180):
    """Retorna linhas e totais por evento; simulação inválida fica fora do denominador.

    'Prazo futuro' exige deadline > close, 'mês-limite' exige deadline == close.
    Oportunidade considera apenas lotes positivos que chegam até o mês do risco.
    Um lote que chega DEPOIS do risco não altera sua cobertura naquele mês.
    """
    rows = []
    for product, res in results.items():
        if res is None:
            continue
        months = list(res["months"])
        cov = np.asarray(res["cov"], dtype=float)
        lost = np.asarray(res["lost"], dtype=float)
        active = np.asarray(res["active"], dtype=bool)
        if cov.ndim != 2 or lost.shape != cov.shape or cov.shape[1] != len(months):
            raise ValueError("Cenários e meses não compartilham o mesmo formato.")
        lots = future_lots(res, close)
        for idx, month in enumerate(months):
            if not active[idx]:
                continue
            for typ, probability in (
                ("Excesso", float(np.mean(cov[:, idx] >= coverage_limit))
                            if np.isfinite(cov[:, idx]).all() else 0.0),
                ("Ruptura", float(np.mean(lost[:, idx] > 0))),
            ):
                if probability <= threshold:
                    continue
                relevant = [lot for lot in lots if lot["month"] <= month]
                future = [lot for lot in relevant if lot["strictly_open"]]
                boundary = [lot for lot in relevant if lot["boundary"]]
                if future:
                    situation = "Prazo futuro pelo LT"
                    deadline = min(lot["deadline"] for lot in future)
                elif boundary:
                    situation = "Mês-limite: confirmar corte"
                    deadline = min(lot["deadline"] for lot in boundary)
                elif not relevant:
                    situation = "Sem lote positivo até o risco"
                    deadline = None
                else:
                    situation = "Prazos teóricos vencidos"
                    deadline = max(lot["deadline"] for lot in relevant)
                rows.append({
                    "Produto": product,
                    "Mês-alvo": month,
                    "Tipo de risco": typ,
                    "Probabilidade (%)": round(probability * 100, 1),
                    "Situação do prazo": situation,
                    "Mês-limite": deadline,
                    "Prazo futuro": bool(future),
                    "No mês-limite": bool(boundary) and not bool(future),
                    "Oportunidade teórica": bool(future or boundary),
                })
    total = len(rows)
    future_count = sum(row["Prazo futuro"] for row in rows)
    boundary_count = sum(row["No mês-limite"] for row in rows)
    return {
        "rows": rows, "total": total, "future": future_count,
        "boundary": boundary_count, "possible": future_count + boundary_count,
        "rate": 100 * (future_count + boundary_count) / total if total else None,
    }


def compare_verified_excess(projections, smart_alerts, official_alerts):
    """Compara a primeira emissão para cada mês-alvo de excesso CONFIRMADO.

    Simulações histórica do modelo operacional vs previsão Oficial com a MESMA
    regra de risco Smart Launch; não compara com o workflow real da L'Oréal.
    Os dois conjuntos devem ser reconstruídos no mesmo Triângulo, origens,
    período de verificação, horizonte e método de simulação.
    """
    if projections.empty:
        return pd.DataFrame()
    confirmed = (
        projections.loc[
            projections["Verificação de excesso"] == EVENT_YES,
            ["Produto", "_alvo", "Mês-alvo"],
        ].drop_duplicates(["Produto", "_alvo"])
    )
    sm = first_alerts(smart_alerts)
    off = first_alerts(official_alerts)
    if not sm.empty:
        sm = sm[sm["Tipo de alerta"] == "Excesso"]
    if not off.empty:
        off = off[off["Tipo de alerta"] == "Excesso"]

    def lookup(alerts):
        return {(row["Produto"], row["_alvo"]): row
                for _, row in alerts.iterrows()}

    sm_idx, off_idx = lookup(sm), lookup(off)
    rows = []
    for _, event in confirmed.iterrows():
        key = (event["Produto"], event["_alvo"])
        a, b = sm_idx.get(key), off_idx.get(key)
        lead_a = int(a["Antecedência (meses)"]) if a is not None else None
        lead_b = int(b["Antecedência (meses)"]) if b is not None else None
        ontime_a = bool(a["Emitido em tempo pelo LT"]) if a is not None else False
        ontime_b = bool(b["Emitido em tempo pelo LT"]) if b is not None else False
        if a is not None and b is not None:
            comparison = (
                "Smart antes" if a["_origem"] < b["_origem"] else
                "Oficial antes" if b["_origem"] < a["_origem"] else "Mesmo fechamento"
            )
        elif a is not None:
            comparison = "Só Smart sinalizou"
        elif b is not None:
            comparison = "Só Oficial sinalizou"
        else:
            comparison = "Nenhum sinalizou"
        rows.append({
            "Produto": event["Produto"],
            "Mês do excesso verificado": event["Mês-alvo"],
            "Smart: primeiro aviso": a["Fechamento"] if a is not None else "Sem alerta",
            "Smart: antecedência (meses)": lead_a,
            "Smart: oportunidade pelo LT": ontime_a,
            "Oficial*: primeiro aviso": b["Fechamento"] if b is not None else "Sem alerta",
            "Oficial*: antecedência (meses)": lead_b,
            "Oficial*: oportunidade pelo LT": ontime_b,
            "Quem avisou primeiro": comparison,
        })
    return pd.DataFrame(rows)
