"""Prioridades operacionais do Smart Launch, calculadas (sem inventar datas diárias).

Os prazos disponíveis no Triângulo são aproximações em competências mensais;
a data exata e a autorização de alteração dependem do sistema do fornecedor.
"""
import numpy as np
from smartlaunch_supply import future_lots, supply_diagnosis
from smartlaunch_core import AVISO, ALERTA

THRESHOLD = ALERTA


def card_summary(product, res, close, threshold=THRESHOLD):
    """Resumo coerente com probabilidades e janela crítica da simulação.

    O risco principal é o evento do primeiro mês alertado; se os dois tipos
    ocorrerem juntos, usamos o mais provável naquele mês. O pico e a cobertura
    referem-se ao mesmo risco selecionado e à MESMA simulação.
    """
    months = list(res["months"])
    supply = supply_diagnosis(res, close)
    all_lots = supply["lots"]
    window = np.asarray(res["active"], dtype=bool)
    ex = np.mean(np.asarray(res["cov"]) >= 180, axis=0)
    evaluated = np.asarray(res.get("evaluated", np.ones(len(months), bool)), dtype=bool)
    ex = np.where(evaluated, ex, 0.0)
    ru = np.mean(np.asarray(res["lost"]) > 0, axis=0)
    events = []
    for j, month in enumerate(months):
        if not window[j]:
            continue
        for name, probability in (("Excesso", ex[j]), ("Ruptura", ru[j])):
            if float(probability) > threshold:
                events.append((j, month, name, float(probability)))
    if not events:
        warnings = [(j, month, name, float(probability))
                    for j, month in enumerate(months) if window[j]
                    for name, probability in (("Excesso", ex[j]), ("Ruptura", ru[j]))
                    if AVISO < float(probability) <= threshold]
        first_warning = min(warnings, key=lambda x:(x[0],-x[3])) if warnings else None
        return {
            "product": product, "alert": False,
            "warning": bool(warnings),
            "warning_type": first_warning[2] if first_warning else None,
            "warning_month": first_warning[1] if first_warning else None,
            "warning_probability": first_warning[3] if first_warning else None,
            "model_scope": "Apenas janela crítica",
            "action": "Acompanhar (aviso)" if warnings else "Monitoramento",
            "message": ("Aviso acima de 2,5%, mas nenhum alerta acima de 20%: "
                        "acompanhar no próximo fechamento, sem propor ação no fornecedor."
                        if warnings else "Sem gatilhos probabilísticos no período avaliado."),
            "supply_note": supply["guidance"],
            "future_lot_count": len(all_lots),
            "first_target_has_changeable_lot": False,
        }
    events.sort(key=lambda x: (x[0], -x[3]))
    first_j, first_month, category, first_probability = events[0]
    matching = [event for event in events if event[2] == category]
    peak_j, peak_month, _, peak_probability = max(matching, key=lambda x: x[3])
    cover = float(np.median(np.asarray(res["cov"])[:, peak_j]))
    ltm = int(res["ltm"])
    relevant_lots = [
        lot for lot in all_lots if lot["month"] <= first_month
    ]
    actionable = sorted(
        (lot for lot in relevant_lots if lot["available_for_analysis"]),
        key=lambda x: x["deadline"]
    )
    if actionable:
        deadline = actionable[0]["deadline"]
        boundary = actionable[0]["boundary"]
        urgency = ("Mês-limite: confirmar data de corte" if boundary
                   else "Em prazo teórico futuro")
        time_left_months = (deadline - close).n
        action = "Avaliar fornecedor"
        suggested = (
            "Avaliar redução ou adiamento do lote no fornecedor, após confirmar "
            "prazo de corte, contrato e unidades ainda não comprometidas."
            if category == "Excesso" else
            "Avaliar reforço ou antecipação do abastecimento, sujeito ao prazo "
            "real e às condições contratuais."
        )
        qualification = (
            "No mês-limite não há garantia de negociação. " if boundary else
            "O prazo futuro é apenas teórico. "
        ) + "Confirmar capacidade, contrato, lote mínimo e data exata."
        deadline_label = "Próximo prazo teórico"
    elif relevant_lots:
        deadline = max(lot["deadline"] for lot in relevant_lots)
        urgency = "Prazo teórico encerrado"
        time_left_months = None
        action = (
            "Avaliação comercial" if category == "Excesso"
            else "Monitorar e avaliar alocação"
        )
        suggested = (
            "Os lotes que chegam até o primeiro excesso estão fora do prazo teórico. "
            "Avaliar estoque existente e ação comercial; confirmar exceções com Suprimentos."
            if category == "Excesso" else
            "Os lotes que chegam até a primeira ruptura estão fora do prazo teórico. "
            "Avaliar alocação e confirmar exceções com Suprimentos."
        )
        qualification = "Não apresentar mudanças de lote como executáveis."
        deadline_label = "Último prazo teórico"
    else:
        deadline = None
        urgency = "Sem lote positivo até o primeiro risco"
        time_left_months = None
        action = (
            "Avaliação comercial" if category == "Excesso"
            else "Monitorar e avaliar alocação"
        )
        if all_lots:
            suggested = (
                "O excesso inicial não pode ser eliminado cancelando lotes que chegam depois. "
                "Avaliar estoque atual e ação comercial, além de revisar os lotes futuros "
                "para evitar novos acúmulos."
                if category == "Excesso" else
                "Os lotes registrados chegam depois da primeira ruptura. "
                "Avaliar alocação e eventuais ajustes futuros com Suprimentos."
            )
        else:
            suggested = (
                "Nenhum lote futuro positivo está registrado no Triângulo até o fim "
                "do horizonte. Avaliar o estoque acumulado, ação comercial e "
                "eventuais compromissos externos ao arquivo."
                if category == "Excesso" else
                "Nenhum lote futuro positivo está registrado no Triângulo. "
                "Avaliar alocação e eventuais compromissos externos."
            )
        qualification = "Não foi possível identificar lote alterável na base."
        deadline_label = "Prazo de lote"
    return {
        "product": product, "alert": True, "type": category,
        "first_month": first_month, "first_probability": first_probability,
        "peak_month": peak_month, "peak_probability": peak_probability,
        "coverage_peak_days": cover, "deadline": deadline,
        "deadline_label": deadline_label, "urgency": urgency,
        "time_left_months": time_left_months, "action": action,
        "suggested": suggested, "qualification": qualification,
        "lead_time_months": ltm, "first_target_has_changeable_lot": bool(actionable),
        "future_lot_count": len(all_lots),
        "future_lot_after_risk_count": sum(lot["month"] > first_month for lot in all_lots),
        "supply_note": supply["guidance"],
        "boundary_lot": bool(actionable and actionable[0]["boundary"]),
    }
