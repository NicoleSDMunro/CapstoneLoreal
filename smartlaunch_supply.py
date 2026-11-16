"""Diagnóstico de lotes futuros e prazos por competência mensal.

O Triângulo não contém um calendário diário de negociação com fornecedor.
Um lote cujo mês-limite coincide com o fechamento exige validação humana:
é incluído apenas para comparação hipotética, nunca como ação autorizada.
"""
import numpy as np


def future_lots(res, close):
    """Lotes positivos futuros do plano; explicita mês-limite e prazo vencido."""
    months = list(res["months"])
    production = np.asarray(res["production"], dtype=float)
    lead_time = int(res["ltm"])
    lots = []
    for idx, month in enumerate(months):
        if month <= close or not np.isfinite(production[idx]) or production[idx] <= 0:
            continue
        deadline = month - lead_time
        if deadline > close:
            situation = "Prazo teórico futuro"
        elif deadline == close:
            situation = "No mês-limite — confirmar com fornecedor"
        else:
            situation = "Prazo teórico encerrado"
        lots.append({
            "index": idx,
            "month": month,
            "units": float(production[idx]),
            "deadline": deadline,
            "situation": situation,
            "boundary": deadline == close,
            "available_for_analysis": deadline >= close,
            "strictly_open": deadline > close,
        })
    return lots


def supply_diagnosis(res, close):
    """Separa falta de lote registrado de prazo vencido, sem inventar compromissos."""
    lots = future_lots(res, close)
    future = [lot for lot in lots if lot["strictly_open"]]
    boundary = [lot for lot in lots if lot["boundary"]]
    expired = [lot for lot in lots if not lot["available_for_analysis"]]
    last = max(res["months"]) if len(res["months"]) else None
    if not lots:
        situation = "Sem lotes positivos futuros registrados"
        guidance = (
            "Nenhuma produção futura positiva consta do plano carregado. "
            "O excesso projetado pode estar no estoque já existente; "
            "avalie ações comerciais e confirme se há compromissos fora do Triângulo."
        )
    elif future:
        situation = "Lotes com prazo teórico futuro"
        guidance = "Há lotes futuros para analisar. Confirmar prazos e contratos antes de agir."
    elif boundary:
        situation = "Lotes no mês-limite"
        guidance = (
            "A decisão ocorre no mesmo mês-limite calculado. "
            "A possibilidade de mudar o lote depende da data de corte do fornecedor."
        )
    else:
        situation = "Lotes futuros com prazo teórico encerrado"
        guidance = (
            "Há produção futura, mas todos os meses-limite calculados são anteriores "
            "ao fechamento. Avaliar exceções contratuais com o fornecedor."
        )
    return {
        "lots": lots, "future": future, "boundary": boundary,
        "expired": expired, "last_month": last, "situation": situation,
        "guidance": guidance,
    }
