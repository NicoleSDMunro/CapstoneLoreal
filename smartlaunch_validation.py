"""Validação retrospectiva conservadora dos alertas Smart Launch.

Separa reconstrução do que era previsível na origem (revisão origem+1)
de verificação com revisões posteriores. Não usa projeção futura para chamar
cobertura 'observada'. Não infere venda perdida a partir do estoque zero.
"""
import math
import numpy as np
import pandas as pd

from smartlaunch_core import MODEL, SHEETS, LIM, AVISO, ALERTA, known, label, forecast, simulate

THRESHOLD = ALERTA
SCENARIO_METHOD = "Normal (0, s)"
EVENT_YES = "Excesso verificável"
EVENT_NO = "Sem excesso verificável"
EVENT_WAIT = "Aguardando vendas futuras"
EVENT_NO_STOCK = "Sem estoque registrado"
RUPTURE_UNVERIFIED = "Não verificável: falta venda perdida realizada"


def recorded_value(matrix, month, verification_close):
    """Mês m = coluna m na revisão m+1, apenas se m <= data de verificação."""
    if month > verification_close:
        return None
    review = month + 1
    if review not in matrix.index or month not in matrix.columns:
        return None
    val = matrix.at[review, month]
    if pd.isna(val) or not np.isfinite(float(val)):
        return None
    return float(val)


def observed_cover(stock, month, realized, max_close, limit=180):
    """Cobertura exclusivamente com vendas realizadas futuras, sem extrapolação.

    Retorno: (dias exatos ou None, texto, classificação).
    Se seis meses inteiros foram observados e o estoque dura até 180 dias,
    sabemos apenas o limite inferior (>=180), não a cobertura exata.
    Se faltar qualquer mês antes do esgotamento, a classificação é pendente.
    """
    if stock is None:
        return None, "—", EVENT_NO_STOCK
    if stock < 0:
        return None, "Estoque inconsistente", EVENT_NO_STOCK
    if stock == 0:
        return 0., "0 dias", EVENT_NO
    remaining = float(stock)
    days = 0.
    for step in range(1, 7):
        later = month + step
        qty = realized.get(later) if later <= max_close else None
        if qty is None or not np.isfinite(qty) or qty < 0:
            return None, "Pendente (vendas futuras)", EVENT_WAIT
        if qty > 0 and remaining <= qty:
            days += 30. * remaining / qty
            outcome = EVENT_YES if days >= limit - 1e-9 else EVENT_NO
            return round(days, 1), f"{days:.1f} dias", outcome
        days += 30.
        remaining = max(0., remaining - qty)
    return None, "≥180 dias (mínimo)", EVENT_YES


def deadlines_for_risk(production, months, origin, risk_month, ltm):
    """Prazo teórico por lote positivo que chega até o mês do risco.

    O mês limite (deadline == origin) é apenas uma oportunidade A CONFIRMAR:
    o Triângulo não traz a data diária de corte do fornecedor. O indicador
    não é prova de oportunidade contratual ou mudança efetivamente executada.
    """
    relevant = []
    for month, volume in zip(months, production):
        if month <= risk_month and np.isfinite(volume) and volume > 0:
            relevant.append(month - ltm)
    if not relevant:
        return "Sem lote positivo até o risco", None, False
    future = sorted(x for x in relevant if x > origin)
    boundary = sorted(x for x in relevant if x == origin)
    if future:
        return "Prazo futuro pelo LT (confirmar contrato)", future[0], True
    if boundary:
        return "Mês-limite (confirmar data de corte)", boundary[0], True
    return "Prazo teórico encerrado", max(relevant), False


def available_origin_reviews(blocks, product, as_of_close):
    """Retorna revisões passadas completas para PV, PROD e EST do produto."""
    d = blocks[SHEETS[product]]
    revs = set(d["PV"].index) & set(d["PROD"].index) & set(d["EST"].index)
    return sorted(
        rev for rev in revs
        if rev - 1 <= as_of_close and (rev - 1) in d["EST"].columns
    )


def latest_verifiable_close(blocks, product):
    """Último mês com revisão seguinte tanto no PV como no estoque."""
    data = blocks[SHEETS[product]]
    revisions = set(data["PV"].index) & set(data["EST"].index)
    if not revisions:
        return None
    return max(revisions) - 1


def reconstruct_history(
    product, as_of_close, blocks, base, model=None,
    max_origins=10, max_horizon=9, method=SCENARIO_METHOD, persistent=False,
    threshold=THRESHOLD,
):
    """Reconstitui alertas por origem histórica e verifica eventos posteriormente.

    O modelo especificado permanece constante nesta reconstrução: o sistema
    ainda não persiste qual modelo fora aprovado em cada fechamento passado.
    Cada simulação é reproduzida com a mesma função do painel (inclusive seed).
    Não usa dados após origem para prever, mas usa realizados após origem para
    julgar a previsão SOMENTE se já disponíveis na data de verificação.

    Retorna (projecoes, alertas, lacunas). Alertas: uma linha por tipo de risco.
    """
    if product not in SHEETS:
        raise ValueError("Produto desconhecido.")
    if model is None:
        model = MODEL[product]
    if max_origins < 1 or max_horizon < 1:
        raise ValueError("Horizonte e número de fechamentos devem ser positivos.")
    data = blocks[SHEETS[product]]
    reviews = available_origin_reviews(blocks, product, as_of_close)[-max_origins:]
    realized = {
        month: value
        for month in data["PV"].columns
        if (value := recorded_value(data["PV"], month, as_of_close)) is not None
    }
    stock_by_month = {
        month: recorded_value(data["EST"], month, as_of_close)
        for month in data["EST"].columns
    }
    records, alerts, gaps = [], [], []
    for review in reviews:
        origin = review - 1
        # Evitar iniciar previsão estatística antes da primeira venda conhecida:
        # a função forecast atual usa a data de início da série completa.
        if known(data["PV"], origin).empty:
            gaps.append({
                "Produto": product, "Fechamento": label(origin),
                "Situação": "Sem vendas realizadas até a origem (pré-lançamento não homologado)",
            })
            continue
        months = [
            month for month in sorted(data["PV"].columns)
            if origin < month <= origin + max_horizon
            and month in data["PROD"].columns
        ]
        if not months:
            gaps.append({"Produto": product, "Fechamento": label(origin),
                         "Situação": "Sem meses futuros no triângulo"})
            continue
        try:
            original = simulate(product, origin, blocks, base, method=method,
                                persistent=persistent, operational_model=model)
            simulation_error = None
            projected_months = original["months"]
            projection = dict(zip(projected_months, original["center"]))
            idx = {m: i for i, m in enumerate(projected_months)}
            production = original["production"]
            ltm = original["ltm"]
            # Calendário de lotes da revisão HISTÓRICA, não da atual.
            plan_months = original["months"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            original = None
            simulation_error = str(exc)
            ltm = int(math.ceil(float(base[product][1]) * 7 / 30))
            plan_months = months
            production = np.asarray([
                data["PROD"].at[review, m]
                if review in data["PROD"].index and m in data["PROD"].columns
                else 0. for m in months
            ], dtype=float)
            try:
                values = forecast(product, months, origin, blocks, model=model)
                projection = dict(zip(months, values))
            except (ValueError, KeyError, IndexError, TypeError) as forecast_error:
                gaps.append({
                    "Produto": product, "Fechamento": label(origin),
                    "Situação": "Sem previsão central: " + str(forecast_error),
                })
                continue
            idx = {}
            gaps.append({
                "Produto": product, "Fechamento": label(origin),
                "Situação": "Sem simulação probabilística: " + simulation_error,
            })

        for target in months:
            predicted = projection.get(target)
            if predicted is None or not np.isfinite(predicted):
                continue
            real_sale = realized.get(target)
            stock = stock_by_month.get(target) if target <= as_of_close else None
            cover_days, cover_text, event = observed_cover(
                stock, target, realized, as_of_close
            )
            error_abs = (abs(float(predicted) - real_sale)
                         if real_sale is not None else None)
            ape = (100 * error_abs / real_sale
                   if real_sale is not None and real_sale > 0 else None)
            j = idx.get(target)
            active = bool(original["active"][j]) if j is not None else False
            can_evaluate = (
                j is not None and bool(original.get("evaluated",
                        np.ones(len(original["months"]),bool))[j])
            ) if original is not None else False
            p_ex = float((original["cov"][:,j] >= LIM).mean()) if can_evaluate else None
            p_ru = float((original["lost"][:,j] > 0).mean()) if j is not None else None
            ontime, deadline, actionable = deadlines_for_risk(
                production, plan_months, origin, target, ltm
            )
            record = {
                "Produto": product,
                "Fechamento": label(origin),
                "_origem": origin,
                "Mês-alvo": label(target),
                "_alvo": target,
                "Horizonte": int((target - origin).n),
                "Modelo reconstruído": model,
                "Previsão no fechamento (un.)": round(float(predicted)),
                "Venda realizada (un.)": round(real_sale) if real_sale is not None else None,
                "Erro absoluto (un.)": round(error_abs) if error_abs is not None else None,
                "Erro percentual (%)": round(ape, 1) if ape is not None else None,
                "Estoque na revisão posterior (un.)": round(stock) if stock is not None else None,
                "Cobertura com realizados": cover_text,
                "Verificação de excesso": event,
                "Prob. excesso (%)": round(100*p_ex, 1) if p_ex is not None else None,
                "Prob. ruptura (%)": round(100*p_ru, 1) if p_ru is not None else None,
                "Na janela crítica": active,
                "Probabilidades válidas": original is not None,
                "Situação prazo fornecedor": ontime,
                "Próximo prazo": label(deadline) if deadline is not None else "—",
                "Lote ajustável pelo LT": bool(actionable),
            }
            records.append(record)
            if not active:
                continue
            for event_type, probability in (("Excesso",p_ex), ("Ruptura",p_ru)):
                if probability is None or probability <= threshold:
                    continue
                observed_outcome = (
                    event if event_type == "Excesso" else RUPTURE_UNVERIFIED
                )
                alerts.append({
                    **record,
                    "Tipo de alerta": event_type,
                    "Probabilidade do alerta (%)": round(probability*100, 1),
                    "Status observado": observed_outcome,
                    "Antecedência (meses)": int((target - origin).n),
                    "Emitido em tempo pelo LT": bool(actionable),
                    "Status de oportunidade": ontime,
                })
    projection_df = pd.DataFrame(records)
    alert_df = pd.DataFrame(alerts)
    gaps_df = pd.DataFrame(gaps)
    if not projection_df.empty:
        projection_df = projection_df.sort_values(["_origem","_alvo"])
    if not alert_df.empty:
        alert_df = alert_df.sort_values(["_origem","_alvo","Tipo de alerta"])
    return projection_df, alert_df, gaps_df


def first_alerts(alerts):
    """Deduplica fechamentos sobrepostos: primeira emissão para cada alvo/tipo."""
    if alerts.empty:
        return alerts.copy()
    return (
        alerts.sort_values("_origem")
        .drop_duplicates(["Produto", "_alvo", "Tipo de alerta"], keep="first")
        .sort_values(["_alvo", "Produto", "Tipo de alerta"])
        .reset_index(drop=True)
    )
