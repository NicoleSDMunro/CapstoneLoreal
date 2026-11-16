"""Visualizações operacionais do Smart Launch.

As figuras usam somente o Triângulo e os arrays já calculados pelo motor.
Nenhuma série ilustrativa nem simulação independente é introduzida aqui.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _as_float(values):
    return np.asarray(values, dtype=float)


def forecast_figure(realized, months, operational, official, simulations, close, period_label,
                    critical_count=0, percentile_bounds=(10, 90)):
    """Histórico conhecido até o fechamento e duas projeções da mesma origem."""
    months = list(months)
    operational = _as_float(operational)
    if len(months) != len(operational):
        raise ValueError("Horizonte e previsão operacional incompatíveis.")
    historical = realized.loc[realized.index <= close].tail(12) if len(realized) else realized
    past_x = [period_label(p) for p in historical.index]
    future_x = [period_label(p) for p in months]
    xorder = list(dict.fromkeys(past_x + future_x))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=past_x, y=historical.to_numpy(float), mode="lines+markers",
        name="Vendas realizadas", line=dict(color="#242424", width=3),
        marker=dict(size=6)
    ))
    if months and simulations is not None:
        dm = _as_float(simulations)
        if dm.ndim == 2 and dm.shape[1] == len(months) and dm.shape[0] > 0:
            low_pct, high_pct = percentile_bounds
            if not 0 <= low_pct < high_pct <= 100:
                raise ValueError("Percentis do intervalo simulado inválidos.")
            lo = np.percentile(dm, low_pct, axis=0)
            hi = np.percentile(dm, high_pct, axis=0)
            fig.add_trace(go.Scatter(
                x=future_x, y=lo, mode="lines", line=dict(width=0),
                hoverinfo="skip", showlegend=False
            ))
            fig.add_trace(go.Scatter(
                x=future_x, y=hi, mode="lines", fill="tonexty",
                fillcolor="rgba(35,104,183,0.13)", line=dict(width=0),
                name=f"Faixa simulada P{low_pct:g}–P{high_pct:g} (não calibrada)",
                customdata=np.column_stack((lo, hi)),
                hovertemplate=("%{x}<br>Simulated lower: %{customdata[0]:,.0f} un."+
                               "<br>Simulated upper: %{customdata[1]:,.0f} un."+
                               "<extra>Range, not calibrated</extra>")
            ))
    last = float(historical.iloc[-1]) if len(historical) and historical.index[-1] == close else None
    if months:
        if official is not None:
            off = _as_float(official)
            if off.shape == operational.shape:
                fig.add_trace(go.Scatter(
                    x=([past_x[-1]] if last is not None else []) + future_x,
                    y=([last] if last is not None else []) + off.tolist(),
                    mode="lines+markers", name="Previsão Oficial",
                    line=dict(color="#c45a35", width=2, dash="dash")
                ))
        fig.add_trace(go.Scatter(
            x=([past_x[-1]] if last is not None else []) + future_x,
            y=([last] if last is not None else []) + operational.tolist(),
            mode="lines+markers", name="Previsão em uso",
            line=dict(color="#2168b7", width=3)
        ))
    if past_x and critical_count > 0 and future_x:
        fig.add_vrect(
            x0=len(past_x)-0.5,
            x1=len(past_x)+min(int(critical_count), len(future_x))-0.5,
            fillcolor="rgba(122,92,165,0.08)", line_width=0, layer="below"
        )
    fig.update_layout(
        template="plotly_white", height=400,
        xaxis=dict(title="Mês", type="category", categoryorder="array",
                   categoryarray=xorder),
        yaxis_title="Vendas / previsão (un.)", hovermode="x unified",
        margin=dict(l=20, r=15, t=20, b=60),
        legend=dict(orientation="h", y=-0.25, x=0),
        paper_bgcolor="white", plot_bgcolor="white"
    )
    return fig


def stock_flow_figure(res, period_label, coverage_limit=180):
    """Três painéis alinhados: saldo de estoque, fluxos e cobertura em dias."""
    months = list(res["months"])
    x = [period_label(m) for m in months]
    n = len(months)
    stock = np.asarray(res["stock"], dtype=float)
    cover = np.asarray(res["cov"], dtype=float)
    center = _as_float(res["center"])
    production = _as_float(res["production"])
    if stock.ndim != 2 or cover.ndim != 2 or stock.shape[1] != n or cover.shape[1] != n:
        raise ValueError("Cenários de estoque/cobertura incompatíveis com o horizonte.")
    if len(center) != n or len(production) != n:
        raise ValueError("Previsão e produção incompatíveis com o horizonte.")
    p50_stock = np.percentile(stock, 50, axis=0)
    p50_cover = [float(np.percentile(cover[np.isfinite(cover[:, j]), j], 50))
                 if np.isfinite(cover[:, j]).any() else None for j in range(n)]
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.12,
        row_heights=[0.34, 0.33, 0.33],
        subplot_titles=("Estoque projetado · mediana dos cenários (P50)",
                        "Fluxos mensais: produção planejada e vendas previstas",
                        "Cobertura projetada · P50 (dias)")
    )
    fig.add_trace(go.Scatter(x=x, y=p50_stock, mode="lines+markers",
                             name="Estoque P50", line=dict(color="#323b50", width=3)), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=production, name="Produção planejada",
                         marker_color="#3b9a87"), row=2, col=1)
    fig.add_trace(go.Bar(x=x, y=center, name="Vendas previstas",
                         marker_color="#4e80c5"), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=p50_cover, mode="lines+markers",
                             name="Cobertura P50", line=dict(color="#ad642d", width=3),
                             connectgaps=False), row=3, col=1)
    fig.add_hline(y=coverage_limit, row=3, col=1, line_dash="dash",
                  line_color="#ad352e", annotation_text=str(coverage_limit)+" dias")
    fig.update_layout(
        template="plotly_white", height=710, barmode="group", hovermode="x unified",
        margin=dict(l=25, r=15, t=52, b=35), paper_bgcolor="white",
        plot_bgcolor="white", legend=dict(orientation="h", y=-0.09, x=0)
    )
    fig.update_yaxes(title_text="Unidades", row=1, col=1)
    fig.update_yaxes(title_text="Unidades/mês", row=2, col=1)
    fig.update_yaxes(title_text="Dias", row=3, col=1)
    return fig


def decision_timeline_figure(res, close, period_label, lots,
                             alert_threshold=0.20, warn_threshold=0.025,
                             coverage_limit=180):
    """Riscos por mês + entregas e datas teóricas; não confirma alteração contratual."""
    months = list(res["months"])
    active = np.asarray(res["active"], bool)
    evaluated = np.asarray(res.get("evaluated", np.ones(len(months), bool)), bool)
    c = np.asarray(res["cov"], dtype=float)
    lost = np.asarray(res["lost"], dtype=float)
    e = (c >= coverage_limit).mean(axis=0)
    r = (lost > 0).mean(axis=0)
    points = []
    for i, m in enumerate(months):
        if not active[i]:
            continue
        for kind, value, available in (
            ("Excesso", float(e[i]), bool(evaluated[i])),
            ("Ruptura", float(r[i]), True),
        ):
            if available and value > warn_threshold:
                severe = value > alert_threshold
                points.append(dict(
                    x=period_label(m), y="Risco de "+kind.lower(),
                    text=kind[0]+" "+str(round(value*100))+"%",
                    hover=f"{kind}: {value*100:.1f}% ("+
                          ("alerta" if severe else "aviso")+")",
                    color=("#b42318" if kind=="Excesso" else "#d18a22")
                          if severe else "#c6a39e",
                    size=18 if severe else 13
                ))
    for lot in lots:
        delivery = lot["month"]
        points.append(dict(x=period_label(delivery), y="Produção planejada",
                           text="", hover=f"Lote: {lot['units']:,.0f} un.",
                           color="#318d79", size=16))
        deadline = lot["deadline"]
        if deadline >= close:
            points.append(dict(x=period_label(deadline), y="Prazo teórico do lote",
                               text="", hover=f"Prazo teórico para {period_label(delivery)}"+
                               (" (mês-limite: confirmar data)" if deadline == close else ""),
                               color="#515c93", size=15))
    fig = go.Figure()
    if points:
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in points], y=[p["y"] for p in points],
            mode="markers+text", text=[p["text"] for p in points],
            textposition="top center",
            marker=dict(color=[p["color"] for p in points],
                        size=[p["size"] for p in points],
                        line=dict(color="white", width=1)),
            customdata=[p["hover"] for p in points],
            hovertemplate="%{x}<br>%{customdata}<extra></extra>",
            showlegend=False
        ))
    ordered = [close] + months
    for lot in lots:
        if lot["deadline"] >= close and lot["deadline"] not in ordered:
            ordered.append(lot["deadline"])
    ordered = sorted(set(ordered))
    fig.update_layout(
        template="plotly_white", height=315, margin=dict(l=16, r=20, t=20, b=35),
        xaxis=dict(type="category", categoryorder="array",
                   categoryarray=[period_label(m) for m in ordered],
                   title="Fechamento → meses futuros"),
        yaxis=dict(categoryorder="array",
                   categoryarray=["Prazo teórico do lote", "Produção planejada",
                                  "Risco de ruptura", "Risco de excesso"]),
        paper_bgcolor="white", plot_bgcolor="white"
    )
    return fig


def tradeoff_figure(candidates, selected):
    """Comparação em unidades; verde segue a regra simulada, não é ação autorizada."""
    fig = go.Figure()
    for _, item in candidates.iterrows():
        name = str(item["Alternativa"])
        chosen = name == selected
        valid = bool(item["Dentro do critério do TCC"])
        fig.add_trace(go.Scatter(
            x=[float(item["Excesso potencialmente evitado (un.)"])],
            y=[float(item["Vendas perdidas adicionais (un.)"])],
            mode="markers+text",
            text=[name] if chosen or name == "Manter plano" else [""],
            textposition="top center", name=name,
            marker=dict(size=20 if chosen else 12,
                        color="#18714d" if valid else "#b73b2b",
                        symbol="diamond" if chosen else "circle",
                        line=dict(color="#333" if chosen else "white",
                                  width=2 if chosen else 1)),
            hovertemplate=name+"<br>Excesso potencialmente evitado: %{x:,.0f} un."+
                          "<br>Vendas perdidas adicionais: %{y:,.0f} un.<extra></extra>",
            showlegend=False
        ))
    fig.add_hline(y=0, line_color="#9b9b9b", line_dash="dot")
    fig.add_vline(x=0, line_color="#9b9b9b", line_dash="dot")
    fig.update_layout(
        template="plotly_white", height=335,
        margin=dict(l=15, r=15, t=15, b=15),
        xaxis_title="Excesso potencialmente evitado (un.)",
        yaxis_title="Vendas perdidas adicionais (un.)",
        paper_bgcolor="white", plot_bgcolor="white"
    )
    return fig
