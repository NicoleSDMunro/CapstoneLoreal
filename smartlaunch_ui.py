"""Smart Launch — central de alertas mensal, sem números ilustrativos."""
import hashlib
import html
from io import BytesIO
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from smartlaunch_core import (
    MODEL, SHEETS, LIM, N, label, load_data, known, forecast,
    simulate, impacts, fmt, AVISO, ALERTA, MARGEM_MC,
    nivel, chance_txt,
)
from smartlaunch_monthly import evaluate_models
from smartlaunch_visuals import (forecast_figure, stock_flow_figure,
                                 decision_timeline_figure, tradeoff_figure)
from smartlaunch_priority import card_summary
from smartlaunch_executive import render_executive_dashboard
from smartlaunch_metrics import (current_alert_opportunities, compare_verified_excess,
                                 format_opportunity_months)
from smartlaunch_supply import future_lots, supply_diagnosis
from smartlaunch_impact import (editable_lots, outcome_metrics, evaluate_lot_options,
                                historical_mape_vs_official, tcc_lot_limits, tcc_check)
from smartlaunch_validation import (
    reconstruct_history, first_alerts, latest_verifiable_close,
    available_origin_reviews, EVENT_YES, EVENT_NO,
)

st.set_page_config(page_title="Smart Launch | Decisões de abastecimento", page_icon="📦", layout="wide")
st.markdown("""
<style>
:root {color-scheme:light;}
.stApp {background:#f8f8f7; color:#141414;}
[data-testid="stSidebar"] {background:#ffffff; border-right:1px solid #e4e4e1;}
[data-testid="stHeader"] {background:#f8f8f7;}
[data-testid="stMetric"] {background:#ffffff; border:1px solid #e4e4e1; border-radius:16px; padding:16px;}
[data-testid="stMetricLabel"] {color:#6f6f6f;}
h1,h2,h3 {letter-spacing:-.035em; color:#111!important;}
h1 {font-weight:750!important;}
div[data-testid="stVerticalBlockBorderWrapper"]>div {border-color:#e3e4e1!important; border-radius:17px!important;}
.stButton>button {border-radius:30px; border:1px solid #171717; min-height:42px;}
.stButton>button[kind="primary"] {background:#111; color:white;}
div[data-testid="stAlert"] {border-radius:12px;}
[data-testid="stSidebar"] [data-testid="stRadio"] label {padding:3px 0;}
.cardeyebrow {font-size:12px; font-weight:650; letter-spacing:.07em; color:#888; text-transform:uppercase;}
.note {font-size:13px; color:#777;}
.pill {display:inline-block; margin:2px 6px 2px 0; padding:5px 10px; border-radius:20px; font-size:12px; font-weight:650; background:#f1f1ef;}
.pill-red {color:#af2517; background:#fff0ed;}
.pill-amber {color:#895b00; background:#fff3d9;}
.pill-green {color:#165e3c; background:#e9f5eb;}
.pill-muted {color:#595959; background:#eeeeec;}
.timeline {display:grid;gap:0;overflow-x:auto;min-width:640px;}
.timeline-cell {padding:11px 2px;text-align:center;border-bottom:1px solid #ebebe8;font-size:13px;min-height:46px;}
.timeline-head {font-size:12px;color:#777;font-weight:650;}
.timeline-product {text-align:left;font-weight:700;padding-left:8px;}
.tdot {display:inline-block;width:26px;height:26px;line-height:26px;border-radius:50%;color:white;font-size:11px;font-weight:750;text-align:center;margin:1px;}
.tdot-e {background:#b42318;}
.tdot-r {background:#e5ac38;color:#382700;}
.tdot-p {background:#171717;}
.decision-panel {background:#fbfbfa;border-radius:16px;padding:18px 20px;min-height:162px;}
.decision-eyebrow {font-size:11px;letter-spacing:.09em;font-weight:750;color:#666;text-transform:uppercase;margin-bottom:8px;}
.decision-description {font-size:14px;line-height:1.5;color:#181818;}
.decision-number {font-size:29px;font-weight:760;line-height:1.2;color:#101010;margin:8px 0;}
.decision-deadline {font-size:24px;font-weight:760;line-height:1.25;color:#9c6300;margin:7px 0;}
.decision-line {font-size:13px;color:#454545;line-height:1.55;margin-top:6px;}
.decision-action {background:#f6f6f4;border:1px solid #eeefec;border-radius:13px;padding:13px 16px;}
.decision-footnote {color:#6c6c6c;font-size:12px;line-height:1.5;}
</style>
""", unsafe_allow_html=True)

NAV = ["Central de decisões", "Análise do produto", "Resultados e confiabilidade"]
PRODUCT_VIEWS = ["Decisão e alternativas", "Riscos por mês", "Previsão × Oficial", "Simular lote específico"]
RESULT_VIEWS = ["Valor demonstrado", "Validação por fechamento", "Metodologia e auditoria"]
LEGACY_PRODUCT = {
    "Impacto operacional": "Decisão e alternativas",
    "Riscos de estoque": "Riscos por mês",
    "Previsão e modelos": "Previsão × Oficial",
    "Simulador de decisões": "Simular lote específico",
}
LEGACY_RESULTS = {
    "Validação histórica dos alertas": "Validação por fechamento",
    "Histórico e metodologia": "Metodologia e auditoria",
}
DEFAULT_METHOD = "Normal (0, s)"
LIMIT_WARN = AVISO
LIMIT_ALERT = ALERTA
CHANCE_NOTE = ("As chances são **simuladas** a partir de 1.000 trajetórias e poucos erros "
               "históricos. Não têm calibração comprovada. O erro de Monte Carlo "
               "na frequência simulada pode chegar a cerca de ±3 p.p., mas isso "
               "NÃO captura a incerteza do modelo. **Aviso > 2,5%** = acompanhar; "
               "**alerta > 20%** = avaliar uma ação.")

def pct_cell(value):
    return None if value is None or not np.isfinite(value) else int(round(float(value)))


def navigate(page, product=None):
    """Navegação compatível com os links da versão anterior, com 3 áreas visíveis."""
    if page in LEGACY_PRODUCT:
        st.session_state["nav_page"] = "Análise do produto"
        st.session_state["product_view"] = LEGACY_PRODUCT[page]
    elif page in LEGACY_RESULTS:
        st.session_state["nav_page"] = "Resultados e confiabilidade"
        st.session_state["results_view"] = LEGACY_RESULTS[page]
    elif page == "Valor demonstrado":
        st.session_state["nav_page"] = "Resultados e confiabilidade"
        st.session_state["results_view"] = "Valor demonstrado"
    elif page == "Atualização mensal" or page == "Visão geral":
        st.session_state["nav_page"] = "Central de decisões"
    else:
        st.session_state["nav_page"] = page
    if product is not None:
        st.session_state["selected_product"] = product


def approve_model(product, new_model, close):
    old = st.session_state.get("operational_" + product, MODEL[product])
    st.session_state["operational_" + product] = new_model
    st.session_state.setdefault("approvals", []).append({
        "Produto": product, "Fechamento": label(close),
        "Anterior": old, "Aprovado": new_model,
        "Registrado em (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })


def update_uploaded_file(uploaded):
    if uploaded is None:
        return
    data = uploaded.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    if digest != st.session_state.get("data_digest"):
        st.session_state["triangulo_file_bytes"] = data
        st.session_state["triangulo_file_name"] = uploaded.name
        st.session_state["data_digest"] = digest
        st.session_state["uploaded_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        st.session_state.pop("selected_revision", None)
        for key in ("validation_asof","validation_product","validation_model","validation_origins","validation_horizon"):
            st.session_state.pop(key, None)


def explain_empty():
    st.info("Para começar, envie a versão mensal do Triângulo de Produtos. A análise será feita com os dados do arquivo, sem números demonstrativos.")
    uploaded = st.file_uploader("Carregar Triângulo de Produtos (.xlsx)", type=["xlsx"], key="main_upload")
    update_uploaded_file(uploaded)


def preview_forecast(product, close, blocks, operational_model):
    """Previsão pontual histórica sem estimar probabilidades quando faltam resíduos."""
    data = blocks[SHEETS[product]]
    revision = close + 1
    if revision not in data["PV"].index:
        return None, "Revisão " + label(revision) + " não encontrada para PV."
    months = [m for m in sorted(data["PV"].columns)
              if m > close and m in data["PROD"].columns]
    if not months:
        return None, "Não existem meses futuros nas colunas do Triângulo."
    try:
        values = forecast(product, months, close, blocks, model=operational_model)
        if len(values) != len(months) or not np.isfinite(values).all():
            return None, "A previsão central contém valores ausentes."
        return pd.DataFrame({"Mês": [label(m) for m in months],
                             "Previsão central (un.)": np.round(values).astype(int)}), None
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return None, str(exc)


def show_available_forecast(product, close, blocks):
    frame, issue = preview_forecast(product, close, blocks,
                                    st.session_state["operational_" + product])
    if frame is None:
        st.caption("Previsão central indisponível para " + product + ": " + issue)
    else:
        st.caption("Previsão pontual do modelo " +
                   st.session_state["operational_" + product] +
                   ". Não implica probabilidade de excesso ou ruptura.")
        st.dataframe(frame, hide_index=True, use_container_width=True)
    return frame is not None


def rows_from_sim(res):
    ex = (res["cov"] >= LIM).mean(axis=0)
    ru = (res["lost"] > 0).mean(axis=0)
    evaluated = np.asarray(res.get("evaluated",
                     np.ones(len(res["months"]), bool)), dtype=bool)
    stock = np.percentile(res["stock"], 50, axis=0)
    cover = np.nanmedian(res["cov"], axis=0)
    rows = []
    for j, month in enumerate(res["months"]):
        window = bool(res["active"][j])
        deadline = month - res["ltm"]
        e = float(ex[j]) if evaluated[j] else None
        r = float(ru[j])
        rows.append({
            "Período": month,
            "Mês": label(month),
            "Excesso (%)": round(e*100,1) if e is not None else np.nan,
            "Ruptura (%)": round(r*100,1),
            "Cobertura P50 (dias)": round(float(cover[j])) if evaluated[j] else np.nan,
            "Estoque P50 (un.)": round(float(stock[j])),
            "Previsão (un.)": round(float(res["center"][j])),
            "Janela crítica": window,
            "Cobertura avaliável": bool(evaluated[j]),
            "Alerta excesso": bool(window and e is not None and e>LIMIT_ALERT),
            "Alerta ruptura": bool(window and r>LIMIT_ALERT),
            "Aviso excesso": bool(window and e is not None and LIMIT_WARN<e<=LIMIT_ALERT),
            "Aviso ruptura": bool(window and LIMIT_WARN<r<=LIMIT_ALERT),
            "Prazo do lote": label(deadline),
        })
    return pd.DataFrame(rows)


def eligible_lots(res, close):
    """Adapta o diagnóstico compartilhado ao formato histórico do simulador."""
    return [{
        "índice": lot["index"], "mês": lot["month"], "volume": lot["units"],
        "prazo": lot["deadline"], "alterável": lot["available_for_analysis"],
        "mês_limite": lot["boundary"], "situação": lot["situation"],
    } for lot in future_lots(res, close)]


def supply_plan_table(res, close):
    """Mostra inclusive meses sem lote positivo, para explicar por que não há corte."""
    values = []
    future = {lot["index"]: lot for lot in future_lots(res, close)}
    for j, month in enumerate(res["months"]):
        if month <= close:
            continue
        volume = float(res["production"][j])
        lot = future.get(j)
        values.append({
            "Mês de entrega/produção": label(month),
            "Produção planejada (un.)": round(volume) if np.isfinite(volume) else None,
            "Mês-limite pelo LT": label(lot["deadline"]) if lot else "—",
            "Situação": lot["situation"] if lot else
                        ("Sem lote positivo registrado" if np.isfinite(volume) and volume <= 0
                         else "Volume inválido / ausente"),
        })
    return pd.DataFrame(values)


def classify_action(res, close, risk_month, risk_type):
    lots = eligible_lots(res, close)
    timely = [lot for lot in lots if lot["alterável"] and lot["mês"] <= risk_month]
    if timely:
        if all(lot["mês_limite"] for lot in timely):
            return "Confirmar fornecedor", (
                "Lote no mês-limite estimado pelo lead time. "
                "Simular é possível; mudar depende da data exata de corte."
            )
        return "Avaliar fornecedor", (
            "Existe lote positivo antes do risco e ainda com prazo teórico futuro. "
            "Confirmar possibilidade contratual."
        )
    if risk_type == "excesso":
        if not lots:
            return "Avaliação comercial", (
                "Nenhuma produção futura positiva está no Triângulo; o excesso "
                "não se resolve cancelando lotes inexistentes."
            )
        if any(lot["mês"] > risk_month for lot in lots):
            return "Ação comercial + revisar futuro", (
                "Os lotes chegam após o primeiro excesso: não eliminam o estoque "
                "já acumulado, mas podem ser revistos para meses posteriores."
            )
        return "Avaliação comercial", (
            "Os lotes anteriores ao excesso passaram do prazo teórico. "
            "Confirmar exceções junto ao fornecedor."
        )
    return "Monitorar e avaliar alocação", (
        "Não há lote positivo com prazo teórico que chegue antes deste mês de ruptura."
    )


def risk_plot(res, rowset, column, color, light="#f2bdb5"):
    """Barra escura = alerta, clara = aviso, cinza = sem gatilho/fora do período."""
    vals = rowset[column].to_numpy(float)
    active = rowset["Janela crítica"].to_numpy(bool)
    colors=[]
    for i,v in enumerate(vals):
        if not active[i] or not np.isfinite(v):
            colors.append("#d8d8d6")
        elif v>100*LIMIT_ALERT:
            colors.append(color)
        elif v>100*LIMIT_WARN:
            colors.append(light)
        else:
            colors.append("#d8d8d6")
    texts=[chance_txt(v/100) if np.isfinite(v) else "não avaliado" for v in vals]
    fig=go.Figure()
    fig.add_trace(go.Bar(
        x=rowset["Mês"],y=np.nan_to_num(vals),marker_color=colors,text=texts,
        textposition="outside",hovertemplate="%{x}: %{text}<extra></extra>",
    ))
    fig.add_hline(y=100*LIMIT_WARN,line_width=1,line_dash="dot",line_color="#777",
                  annotation_text="Aviso 2,5%",annotation_position="top left")
    fig.add_hline(y=100*LIMIT_ALERT,line_width=1,line_dash="dash",line_color="#333",
                  annotation_text="Alerta 20%",annotation_position="top left")
    finite=vals[np.isfinite(vals)]
    ymax=max(30,float(finite.max())*1.25) if len(finite) else 30
    fig.update_layout(
        template="plotly_white",height=315,margin=dict(l=8,r=12,t=25,b=10),
        paper_bgcolor="white",plot_bgcolor="white",
        yaxis=dict(title="Chance simulada (%)",range=[0,ymax]),
        xaxis=dict(title=None),showlegend=False,font=dict(color="#222"))
    return fig


def timeline_markup(panels, close):
    months = [close+i for i in range(1, 8)]
    cols = len(months)+1
    elements = ['<div class="timeline" style="grid-template-columns:100px repeat(7,minmax(72px,1fr))">']
    elements.append('<div class="timeline-cell timeline-head timeline-product">Produto</div>')
    for month in months:
        elements.append('<div class="timeline-cell timeline-head">' + label(month) + '</div>')
    for product in MODEL:
        elements.append('<div class="timeline-cell timeline-product">' + product + '</div>')
        res = panels.get(product)
        if res is None:
            elements.extend(['<div class="timeline-cell">—</div>'] * len(months))
            continue
        by_month = {row["Período"]:row for _,row in rows_from_sim(res).iterrows()}
        lots = eligible_lots(res, close)
        for month in months:
            dots=[]
            item = by_month.get(month)
            if item is not None and item["Alerta excesso"]:
                dots.append('<span class="tdot tdot-e" title="Alerta de excesso (>20%)">E</span>')
            elif item is not None and item["Aviso excesso"]:
                dots.append('<span class="tdot tdot-e" style="opacity:.4" title="Aviso de excesso (>2,5%)">e</span>')
            if item is not None and item["Alerta ruptura"]:
                dots.append('<span class="tdot tdot-r" title="Alerta de ruptura (>20%)">R</span>')
            elif item is not None and item["Aviso ruptura"]:
                dots.append('<span class="tdot tdot-r" style="opacity:.4" title="Aviso de ruptura (>2,5%)">r</span>')
            if any(lot["prazo"] == month and lot["alterável"] for lot in lots):
                dots.append('<span class="tdot tdot-p" title="Prazo de lote">P</span>')
            elements.append('<div class="timeline-cell">' + (''.join(dots) or '·') + '</div>')
    elements.append('</div>')
    return ''.join(elements)


def scenario_plan(res, index, action):
    plan = res["production"].copy()
    volume = plan[index]
    if action == "Reduzir 25%":
        plan[index] = volume*.75
    elif action == "Reduzir 50%":
        plan[index] = volume*.5
    elif action == "Cancelar lote":
        plan[index] = 0
    elif action == "Aumentar 25%":
        plan[index] = volume*1.25
    elif action == "Adiar 1 mês":
        if index + 1 >= len(plan):
            return None
        plan[index] = 0
        plan[index+1] += volume
    elif action == "Antecipar 1 mês":
        if index - 1 < 0:
            return None
        plan[index] = 0
        plan[index-1] += volume
    return plan


if st.session_state.get("nav_page") not in NAV:
    st.session_state["nav_page"] = NAV[0]
if st.session_state.get("product_view") not in PRODUCT_VIEWS:
    st.session_state["product_view"] = PRODUCT_VIEWS[0]
if st.session_state.get("results_view") not in RESULT_VIEWS:
    st.session_state["results_view"] = RESULT_VIEWS[0]

with st.sidebar:
    st.markdown("## Smart Launch")
    st.caption("L'Oréal | Decisões de abastecimento")
    st.divider()
    nav = st.radio("Navegação", NAV, key="nav_page", label_visibility="collapsed")
    st.divider()
    st.markdown("**Dados do fechamento**")
    uploaded_sidebar = st.file_uploader("Carregar / atualizar Triângulo", type=["xlsx"], key="sidebar_upload")
    update_uploaded_file(uploaded_sidebar)
    st.caption("O arquivo é usado apenas na sessão. Hospedagem pública não deve receber dados confidenciais sem controle de acesso.")

file = st.session_state.get("triangulo_file_bytes")
if file is None:
    st.title("Central de decisões")
    st.write("Identifique excesso de estoque, verifique se ainda há prazo e compare alternativas sem criar rupturas.")
    explain_empty()
    file = st.session_state.get("triangulo_file_bytes")
    if file is None:
        st.stop()

try:
    base, blocks = load_data(file)
except Exception as exc:
    st.error("Não foi possível validar o arquivo: " + str(exc))
    st.caption("Esperado: aba Base, uma ou mais abas PRODUTO N e, quando aplicável, abas BENCH NOME_N.")
    st.stop()

if "data_digest" not in st.session_state:
    st.session_state["data_digest"] = hashlib.sha256(file).hexdigest()
if st.session_state.get("selected_product") not in MODEL:
    st.session_state["selected_product"] = next(iter(MODEL))
for product in MODEL:
    st.session_state.setdefault("operational_"+product, MODEL[product])

revisions = None
for product, sheet in SHEETS.items():
    data = blocks[sheet]
    revs = set(data["PV"].index)&set(data["PROD"].index)&set(data["EST"].index)
    valid = {rev for rev in revs if rev-1 in data["EST"].columns}
    revisions = valid if revisions is None else revisions | valid
revisions = sorted(revisions or [])
if not revisions:
    st.error("Nenhuma revisão válida entre PV, produção e estoque dos produtos carregados. Confira a auditoria da base; não foram gerados alertas.")
    st.stop()

if nav == "Central de decisões":
    st.markdown('<p class="sl-kicker">SUPPLY CHAIN DECISION CENTER · MONTHLY CLOSING</p>',
                unsafe_allow_html=True)
    st.title("Central de decisões")
    st.caption("Launch Decision Center · Risco, timing e alternativas para revisão do planner.")
    filter_a, filter_b, filter_c, filter_d = st.columns([1.05,1.05,.9,1.1])
    with filter_a:
        st.selectbox("PRODUCT", list(MODEL), key="selected_product")
    with filter_b:
        st.selectbox("CLOSING · PLAN REVISION", revisions,
                     index=len(revisions)-1, format_func=label, key="selected_revision")
    with filter_c:
        st.selectbox("HORIZON", ["3M","6M","All"], index=1, key="executive_horizon")
    with filter_d:
        st.selectbox("VIEW", ["Executive","Planner","Analyst"],
                     index=0, key="executive_mode")
else:
    with st.sidebar:
        st.selectbox("Revisão do plano", revisions, index=len(revisions)-1,
                     format_func=label, key="selected_revision")
        st.selectbox("Produto analisado", list(MODEL), key="selected_product")
review = st.session_state["selected_revision"]
close = review - 1
chosen = st.session_state["selected_product"]
method = st.session_state.get("simulation_method", DEFAULT_METHOD)
persistent = bool(st.session_state.get("simulation_persistent",False))

results = {}
errors = {}
rankings = {}
for product in MODEL:
    try:
        _detail, _rank, _winner = evaluate_models(product, close, blocks, forecast, known)
        rankings[product] = (_detail, _rank, _winner)
    except Exception as exc:
        rankings[product] = (pd.DataFrame(), pd.DataFrame(), None)
        errors["rank_"+product] = str(exc)
    try:
        results[product] = simulate(product, close, blocks, base, method, persistent,
                                    operational_model=st.session_state["operational_"+product])
    except Exception as exc:
        results[product] = None
        errors[product] = str(exc)

ready_count = sum(x is not None for x in results.values())
status = "Processamento completo" if ready_count==len(MODEL) else "Processamento parcial"
file_name = st.session_state.get("triangulo_file_name","Triângulo carregado na sessão")
with st.sidebar:
    st.caption("Fechamento: " + label(close) + " · Revisão: " + label(review))
    st.caption(status + " · " + file_name)
    if ready_count < len(MODEL):
        with st.expander("Diagnóstico de simulações indisponíveis"):
            st.warning("Não calculado não significa risco zero.")
            for product in MODEL:
                if results[product] is None:
                    st.write("**" + product + ":** " + errors.get(product, "Dados insuficientes"))
            st.caption("As vendas do mês m são recuperadas na revisão m+1. Pelo menos dois erros históricos são necessários para simular.")

page = nav
if nav == "Análise do produto":
    st.title("Decisão de abastecimento · " + chosen)
    st.caption("Fechamento " + label(close) + " · Modelo em uso: " +
               st.session_state["operational_" + chosen] +
               " · Resultados condicionais aos dados e às premissas do Triângulo.")
    current = results[chosen]
    if current is None:
        st.warning("Não há probabilidade confiável para " + chosen +
                   ": " + errors.get(chosen, "Evidência insuficiente"))
        show_available_forecast(chosen, close, blocks)
    else:
        summary = card_summary(chosen, current, close)
        frame_product = rows_from_sim(current)
        active = frame_product[frame_product["Janela crítica"]]
        ex_valid=active[active["Excesso (%)"].notna()]
        ex_peak = ex_valid.loc[ex_valid["Excesso (%)"].idxmax()] if not ex_valid.empty else None
        ru_peak = active.loc[active["Ruptura (%)"].idxmax()] if not active.empty else None
        a,b,c = st.columns(3)
        a.metric("Maior chance de excesso", chance_txt(ex_peak["Excesso (%)"]/100)
                 if ex_peak is not None else "não avaliado")
        b.metric("Maior chance de ruptura", chance_txt(ru_peak["Ruptura (%)"]/100)
                 if ru_peak is not None else "não avaliado")
        c.metric("Lotes futuros positivos", summary.get("future_lot_count", 0))
        st.caption("**Produção e prazo:** " + summary["supply_note"])
        if summary["alert"]:
            st.info("**Próximo encaminhamento: " + summary["action"] + ".** " + summary["suggested"])
            st.caption("Primeiro risco: " + summary["type"].lower() + " em " +
                       label(summary["first_month"]) + " · Pico do mesmo tipo: " +
                       f'{summary["peak_probability"]*100:.1f}%' +
                       " em " + label(summary["peak_month"]) +
                       ". Prazos calculados pelo lead time são teóricos.")
        elif summary.get("warning"):
            st.info("**Aviso: acompanhar.** "+summary["message"]+
                    " Primeiro aviso: "+summary["warning_type"].lower()+" em "+
                    label(summary["warning_month"])+".")
        else:
            st.info("Sem alerta ou aviso na janela crítica; reavaliar mensalmente.")
        st.caption(CHANCE_NOTE)
        if ex_peak is not None and ru_peak is not None:
            st.caption("Excesso: pico em " + str(ex_peak["Mês"]) +
                       " · Ruptura: pico em " + str(ru_peak["Mês"]) +
                       ". Podem ocorrer em meses diferentes ou em cenários distintos.")
    selection = st.radio("O que deseja avaliar?", PRODUCT_VIEWS,
                         key="product_view", horizontal=True)
    page = {
        "Decisão e alternativas": "Impacto operacional",
        "Riscos por mês": "Riscos de estoque",
        "Previsão × Oficial": "Previsão e modelos",
        "Simular lote específico": "Simulador de decisões",
    }[selection]
elif nav == "Resultados e confiabilidade":
    st.title("Resultados e confiabilidade")
    st.caption("Evidências do TCC, limitações e histórico reconstruído — sem confundir simulação com ganho realizado.")
    choice = st.radio("O que deseja consultar?", RESULT_VIEWS,
                      key="results_view", horizontal=True)
    page = {
        "Valor demonstrado": "Valor demonstrado",
        "Validação por fechamento": "Validação histórica dos alertas",
        "Metodologia e auditoria": "Histórico e metodologia",
    }[choice]
else:
    page = "Visão geral"

if page == "Visão geral":
    render_executive_dashboard(
        product=chosen,
        close=close,
        blocks=blocks,
        results=results,
        errors=errors,
        rankings=rankings,
        ready_count=ready_count,
        horizon=st.session_state.get("executive_horizon", "6M"),
        mode=st.session_state.get("executive_mode", "Executive"),
        on_open_simulator=lambda: navigate("Impacto operacional", chosen),
        on_open_analytics=lambda: navigate("Previsão e modelos", chosen),
    )

elif page == "Atualização mensal":
    st.subheader("Auditoria da base enviada")
    st.success("Estrutura básica do Triângulo reconhecida: " + file_name)
    checks=[]
    for product,sheet in SHEETS.items():
        b=blocks[sheet]
        counts={k:len(b[k].index) if k in b else 0 for k in ("PV","PROD","EST")}
        checks.append({"Produto":product,"PV (revisões)":counts["PV"],
                       "Produção (revisões)":counts["PROD"],
                       "Estoque (revisões)":counts["EST"],
                       "Simulação": "Disponível" if results[product] is not None else "Indisponível",
                       "Motivo":errors.get(product,"")})
    st.dataframe(pd.DataFrame(checks),hide_index=True,use_container_width=True)
    c1,c2,c3=st.columns(3)
    c1.metric("Fechamento selecionado",label(close))
    c2.metric("Revisão utilizada",label(review))
    c3.metric("Produtos com simulação",f"{ready_count}/{len(MODEL)}")
    st.info("O Excel deve conter as revisões anteriores. Este protótipo não salva arquivos nem decisões de maneira permanente.")
    st.caption("Como o Triângulo funciona: o realizado de mar/26 é recuperado "
               "na revisão abr/26. Para simular um fechamento histórico, mantenha "
               "todas as revisões originais e escolha a revisão correspondente "
               "no menu lateral, sem apagar as linhas posteriores.")
    with st.expander("Vendas conhecidas por produto"):
        for product,sheet in SHEETS.items():
            observed=known(blocks[sheet]["PV"],close)
            st.markdown("**"+product+"**")
            if observed.empty:
                st.caption("Sem vendas realizadas neste fechamento.")
            else:
                st.dataframe(pd.DataFrame({"Mês":[label(x) for x in observed.index],
                                           "Vendido (un.)":observed.values}),hide_index=True)
    st.caption("Identificador do arquivo (SHA-256): " + st.session_state["data_digest"][:16] +
               "… · O arquivo é processado no servidor da sessão, que deve ter acesso protegido.")

elif page == "Previsão e modelos":
    st.subheader("Previsão e modelos")
    st.write("Reavaliar mensalmente o erro histórico sem alterar silenciosamente a previsão operacional.")
    product=chosen
    detail,ranking,winner=rankings[product]
    operational=st.session_state["operational_"+product]
    m1,m2,m3=st.columns(3)
    m1.metric("Produto analisado",product)
    m2.metric("Modelo em uso",operational)
    m3.metric("Melhor no backtest atual",winner or "Não elegível")
    st.caption("Comparação experimental: MEA-P, MEA, Oficial e Naive nos mesmos pares origem/alvo, h1–h3.")
    if ranking.empty:
        st.warning("Não há pares comparáveis suficientes para determinar um vencedor neste fechamento.")
    else:
        st.dataframe(ranking,hide_index=True,use_container_width=True)
        st.warning("A elegibilidade deste ranking reduzido ainda precisa ser homologada contra os 49 modelos e o protocolo final do notebook do TCC.")
        if winner and winner!=operational:
            st.info("Novo vencedor observado: " + winner +
                    ". O modelo operacional permanece " + operational + " até aprovação.")
            st.button("Aprovar mudança para "+winner, type="primary",
                      on_click=approve_model,args=(product,winner,close))
        else:
            st.success("Nenhuma troca operacional sugerida neste fechamento.")
        if operational != MODEL[product]:
            st.button("Restaurar modelo inicial do TCC",on_click=approve_model,
                      args=(product,MODEL[product],close))
    res=results[product]
    if res is not None:
        st.subheader("Vendas realizadas × previsão Oficial × Smart Launch")
        realized=known(blocks[SHEETS[product]]["PV"],close)
        try:
            official=forecast(product,res["months"],close,blocks,model="Oficial")
        except (ValueError,KeyError,IndexError,TypeError):
            official=None
        st.plotly_chart(
            forecast_figure(
                realized, res["months"], res["center"], official, res["dm"],
                close, label, critical_count=res["window"]
            ), use_container_width=True
        )
        if official is None:
            st.info("Previsão Oficial indisponível nesta revisão; "
                    "somente a previsão operacional pôde ser exibida.")
        st.caption("Histórico realizado conhecido no fechamento, sem usar vendas posteriores. "
                   "Faixa P10–P90 = percentis das mesmas trajetórias simuladas para demanda; "
                   "não é intervalo estatístico calibrado. "
                   "A área sombreada indica a janela crítica estimada pelo lead time.")
    if not detail.empty:
        with st.expander("Inspecionar cada erro de validação"):
            st.dataframe(detail,hide_index=True,use_container_width=True)

elif page == "Riscos de estoque":
    st.subheader("Evolução dos riscos por mês")
    product=chosen
    res=results[product]
    if res is None:
        st.warning("Não há simulação probabilística válida para " + product + ": " +
                   errors.get(product, "Sem informação suficiente"))
        st.info("Uma previsão central pode existir mesmo quando o histórico de "
                "erros ainda não permite calcular probabilidades.")
        show_available_forecast(product, close, blocks)
        st.stop()
    frame=rows_from_sim(res)
    st.write("Produto "+product+" · modelo "+st.session_state["operational_"+product]+
             " · "+str(N)+" cenários · "+str(res["window"])+" meses na janela crítica")
    c1,c2,c3=st.columns(3)
    c1.metric("Estoque inicial",fmt(res["e0"])+" un.")
    c2.metric("Desvio-padrão dos erros",fmt(res["sd"])+" un.")
    c3.metric("Erros usados",len(res["errors"]))
    st.subheader("Estoque, produção e cobertura — mês a mês")
    st.caption("Estoque e cobertura = medianas das trajetórias simuladas. "
               "Produção = plano carregado; vendas = previsão central. "
               "Fluxos mensais e saldo de estoque são mostrados em painéis separados.")
    st.plotly_chart(stock_flow_figure(res,label,coverage_limit=LIM),
                    use_container_width=True)
    st.caption("Cobertura ≥ 180 dias é a referência de excesso. "
               "Mês sem cobertura futura suficiente aparece sem ponto, "
               "e não como risco zero.")
    ex_col,ru_col=st.columns(2)
    with ex_col:
        with st.container(border=True):
            st.markdown("#### Chance de estoque acima de seis meses")
            st.caption("Cobertura ≥ 180 dias · linha pontilhada: aviso 2,5%; "
                       "tracejada: alerta 20%. Último mês sem cobertura futura: não avaliado.")
            st.plotly_chart(risk_plot(res,frame,"Excesso (%)","#b42318"),use_container_width=True)
    with ru_col:
        with st.container(border=True):
            st.markdown("#### Chance de venda perdida (ruptura)")
            st.caption("Venda não atendida · linha pontilhada: aviso 2,5%; "
                       "tracejada: alerta 20%.")
            st.plotly_chart(risk_plot(res,frame,"Ruptura (%)","#d39b24"),use_container_width=True)
    st.subheader("Riscos e encaminhamentos por mês")
    st.caption(CHANCE_NOTE)
    display=frame[["Mês","Previsão (un.)","Estoque P50 (un.)",
                   "Cobertura P50 (dias)","Excesso (%)","Ruptura (%)",
                   "Janela crítica","Aviso excesso","Aviso ruptura",
                   "Alerta excesso","Alerta ruptura"]]
    st.dataframe(display,hide_index=True,use_container_width=True)
    flagged=frame[frame["Alerta excesso"]|frame["Alerta ruptura"]]
    if flagged.empty:
        warnings = frame[frame["Aviso excesso"]|frame["Aviso ruptura"]]
        if not warnings.empty:
            st.info("Existem avisos (2,5%–20%), mas nenhum alerta (>20%) "
                    "na janela crítica. Acompanhar no próximo fechamento.")
        else:
            st.info("Sem alerta (>20%) nem aviso (>2,5%) na janela crítica.")
    else:
        for _,row in flagged.iterrows():
            typ="excesso" if row["Alerta excesso"] else "ruptura"
            act,reason=classify_action(res,close,row["Período"],typ)
            st.markdown("**"+row["Mês"]+" · "+typ.capitalize()+"** — "+act+". "+reason)
    st.subheader("Evolução do risco entre fechamentos")
    st.caption("Acompanha a probabilidade estimada para o mesmo mês-alvo conforme novas revisões ficam disponíveis.")
    target=st.selectbox("Mês-alvo",list(res["months"]),format_func=label,key="risk_target")
    past=[]
    for old_review in revisions[-9:]:
        prev_close=old_review-1
        if prev_close>close or target<=prev_close:
            continue
        try:
            past_sim=simulate(product,prev_close,blocks,base,method,persistent,
                              operational_model=st.session_state["operational_"+product])
            if target in past_sim["months"]:
                j=past_sim["months"].index(target)
                if bool(past_sim["active"][j]) and bool(
                    past_sim.get("evaluated", np.ones(len(past_sim["months"]),bool))[j]
                ):
                    past.append({"Fechamento":label(prev_close),
                                 "Excesso (%)":100*float((past_sim["cov"][:,j]>=LIM).mean()),
                                 "Ruptura (%)":100*float((past_sim["lost"][:,j]>0).mean())})
        except (ValueError,KeyError,IndexError):
            pass
    if len(past)>=2:
        pframe=pd.DataFrame(past)
        line=go.Figure()
        for column,color in (("Excesso (%)","#b42318"),("Ruptura (%)","#d39b24")):
            line.add_trace(go.Scatter(x=pframe["Fechamento"],y=pframe[column],
                                      mode="lines+markers",name=column,
                                      line=dict(color=color,width=3)))
        line.update_layout(template="plotly_white",height=280,margin=dict(l=8,r=8,t=15,b=10),
                           yaxis_title="Probabilidade (%)")
        st.plotly_chart(line,use_container_width=True)
    else:
        st.info("Ainda não há fechamentos históricos suficientes com simulação válida para mostrar a evolução deste mês-alvo.")

elif page == "Simulador de decisões":
    st.subheader("Simular uma intervenção específica")
    product=chosen
    res=results[product]
    if res is None:
        st.warning("A simulação não está disponível: "+errors.get(product,"Dados insuficientes"))
        st.stop()
    st.caption("Produto "+product+" · Fechamento "+label(close)+
               " · lead time arredondado: "+str(res["ltm"])+" meses.")
    status=supply_diagnosis(res,close)
    lots=eligible_lots(res,close)
    st.markdown("**Situação do plano de produção**")
    st.info(status["guidance"])
    with st.expander("Ver lotes planejados e meses sem produção", expanded=not bool(lots)):
        st.dataframe(supply_plan_table(res,close),hide_index=True,use_container_width=True)
        st.caption("Lotes positivos do Triângulo; pedidos não registrados e dias "
                   "exatos de corte não são conhecidos pela ferramenta.")
    open_lots=[lot for lot in lots if lot["alterável"]]
    if not open_lots:
        if not lots:
            st.warning("Não há lote positivo futuro no horizonte carregado. "
                       "Não existe produção registrada a cancelar; a análise deve "
                       "considerar o estoque acumulado e eventual ação comercial.")
        else:
            st.warning("Existem lotes positivos futuros, mas seus prazos teóricos "
                       "já passaram. Confirmar exceções com Suprimentos.")
    else:
        if status["boundary"]:
            st.warning("Lotes no mês-limite aparecem para simulação hipotética. "
                       "A mudança só pode ser solicitada após verificar a data "
                       "real de corte do fornecedor.")
        st.success(str(len(open_lots)) + " lote(s) para avaliação: prazo futuro "
                   "ou mês-limite sujeito a confirmação. Nenhuma alteração é executada.")
        names={lot["índice"]: label(lot["mês"])+" · "+fmt(lot["volume"])+" un. · prazo "+label(lot["prazo"])
               for lot in open_lots}
        selected=st.selectbox("Lote para análise",list(names),format_func=lambda i:names[i])
        selected_lot=next(lot for lot in open_lots if lot["índice"]==selected)
        st.write("**Mês-limite estimado:** "+label(selected_lot["prazo"]))
        if selected_lot["mês_limite"]:
            st.warning("Este fechamento coincide com o mês-limite: não é possível "
                       "afirmar que a mudança ainda será aceita sem data de corte.")
        actions=["Manter lote","Reduzir 25%","Reduzir 50%","Cancelar lote","Aumentar 25%"]
        if selected+1<len(res["months"]):
            actions.append("Adiar 1 mês")
        if selected>0 and res["months"][selected-1]-res["ltm"]>=close:
            actions.append("Antecipar 1 mês")
        choice=st.radio("Comparar alternativa",actions,horizontal=True,key="lot_action")
        plan=scenario_plan(res,selected,choice)
        if plan is not None:
            base_risk=impacts(res,product,res["production"],{"excesso":0,"ruptura":0})
            alternative=impacts(res,product,plan,base_risk)
            comparison=pd.DataFrame([
                {"Indicador":"Quantidade do lote (un.)","Plano atual":fmt(selected_lot["volume"]),
                 "Alternativa":fmt(plan[selected])},
                {"Indicador":"Risco de excesso em algum mês da janela","Plano atual":f'{base_risk["excesso"]:.1%}',
                 "Alternativa":f'{alternative["excesso"]:.1%}'},
                {"Indicador":"Risco de ruptura em algum mês da janela","Plano atual":f'{base_risk["ruptura"]:.1%}',
                 "Alternativa":f'{alternative["ruptura"]:.1%}'},
                {"Indicador":"Prazo teórico","Plano atual":label(selected_lot["prazo"]),
                 "Alternativa":label(selected_lot["prazo"])},
            ])
            st.subheader("Plano atual × alternativa")
            st.dataframe(comparison,hide_index=True,use_container_width=True)
            st.caption("As probabilidades representam risco em pelo menos um mês da janela, não o maior percentual mensal. As alternativas usam exatamente as mesmas 1.000 trajetórias de demanda.")
            st.warning("Cenário matemático, não autorização de alteração. Confirme contratos, capacidade, insumos e lotes mínimos antes de agir.")
        else:
            st.warning("Esta ação não cabe no horizonte de planejamento disponível.")
    st.button("Comparar impacto em unidades e fill rate",key="impact_from_sim",
              on_click=navigate,args=("Impacto operacional",product))

elif page == "Impacto operacional":
    st.subheader("Alternativas de abastecimento")
    st.write("Quanto uma alteração de lote **poderia reduzir o excesso** — e qual risco de perda de vendas ela acrescenta.")
    st.caption("Análise prospectiva de cenários do fechamento " + label(close) +
               ". Benefícios simulados, não economia ou redução real comprovada.")
    product=chosen
    res=results[product]
    if res is None:
        st.warning(
            "Sem simulação probabilística válida para "+product+": "+
            errors.get(product,"Dados insuficientes.")
        )
        st.info("Sem uma sacola de demanda válida, não é possível quantificar "
                "excesso evitado, vendas perdidas adicionais ou fill rate simulado.")
        show_available_forecast(product,close,blocks)
        st.stop()

    st.markdown("**Compare o impacto de lotes futuros registrados no Triângulo.** "
                "Prazo futuro ou mês-limite não significa alteração autorizada.")
    evaluated=np.asarray(res.get("evaluated",np.ones(len(res["months"]),bool)),dtype=bool)
    active_months=[(i,m) for i,m in enumerate(res["months"])
                   if bool(res["active"][i]) and bool(evaluated[i])]
    if not active_months:
        st.warning("Não há mês com cobertura de excesso avaliável na janela crítica. "
                   "O último mês do horizonte precisa de demanda posterior; "
                   "não interprete cobertura ausente como risco zero.")
        st.stop()
    excess_probs=(np.asarray(res["cov"])>=LIM).mean(axis=0)
    excess_alerts=[i for i,m in active_months if excess_probs[i] > LIMIT_ALERT]
    default_target=excess_alerts[0] if excess_alerts else active_months[0][0]
    valid_targets=[i for i,m in active_months]
    month_idx=st.selectbox(
        "Mês-alvo para medir o estoque excedente",
        options=valid_targets,index=valid_targets.index(default_target),
        format_func=lambda idx:label(res["months"][idx]),
        key="impact_target"
    )
    status=supply_diagnosis(res,close)
    eligible=editable_lots(res,close)
    initial=outcome_metrics(res,res["production"],month_idx)
    st.caption(
        "Excesso em unidades = estoque final do mês-alvo menos demanda simulada dos "
        "seis meses seguintes (se positivo). Não somamos meses de excesso, "
        "para evitar dupla contagem do mesmo estoque."
    )
    baseline_cols=st.columns(3)
    baseline_cols[0].metric("Excesso esperado · plano atual",fmt(initial["expected_excess_units"])+" un.")
    baseline_cols[1].metric("Vendas perdidas · plano atual",fmt(initial["expected_lost_units"])+" un.")
    baseline_cols[2].metric("Fill rate · plano atual",f'{initial["fill_rate_pct"]:.1f}%')
    if initial["extrapolated_months"]:
        st.warning(
            f'{initial["extrapolated_months"]} dos 6 meses após o alvo estão além do '
            "horizonte simulado; para calcular o excesso, o motor repete a última "
            "demanda simulada. Interprete a quantidade excedente como aproximação."
        )
    st.caption("Vendas perdidas e fill rate são calculados somente sobre os "
               "meses da janela crítica, usando a mesma demanda em todos os planos.")
    st.markdown("**Diagnóstico de abastecimento:** " + status["situation"])
    st.caption(status["guidance"])
    with st.expander("Ver plano futuro, inclusive meses sem produção", expanded=not bool(status["lots"])):
        st.dataframe(supply_plan_table(res,close),hide_index=True,use_container_width=True)
        st.caption("O plano carregado não comprova a inexistência de outros pedidos "
                   "ou contratos. A simulação não cancela lotes automaticamente.")
    if not eligible:
        if not status["lots"]:
            st.warning(
                "Não há lotes positivos futuros no Triângulo até " +
                (label(status["last_month"]) if status["last_month"] is not None else
                 "o fim do horizonte") +
                ". O excesso esperado resulta do estoque e da demanda projetada, "
                "não de um lote futuro a cancelar. Avalie ações comerciais."
            )
        else:
            st.warning(
                "Há produção futura registrada, mas todos os meses-limite estão "
                "antes do fechamento. Não indicamos cortes como executáveis; "
                "confirme possíveis exceções com Suprimentos."
            )
    else:
        if status["boundary"]:
            st.caption("Lotes cujo mês-limite coincide com o fechamento podem ser "
                       "comparados hipoteticamente. A data contratual deve ser confirmada.")
        lot_names={
            lot["index"]:label(lot["month"])+" · "+fmt(lot["units"])+" un. · prazo "+label(lot["deadline"])
            for lot in eligible
        }
        chosen_lot=st.selectbox(
            "Lote com prazo teórico aberto",list(lot_names),
            format_func=lambda i:lot_names[i],key="impact_lot"
        )
        lot=next(x for x in eligible if x["index"]==chosen_lot)
        st.caption("Elegibilidade por competência mensal: antes do mês-limite ou "
                   "no próprio mês-limite (dependendo da data exata). "
                   "Contrato, capacidade e corte diário precisam de confirmação.")
        if lot["boundary"]:
            st.warning("Mês-limite do lote coincide com o fechamento. "
                       "Esta comparação NÃO comprova que o fornecedor aceitará a alteração.")
        if lot["month"] > res["months"][month_idx]:
            st.info("Este lote chega após o mês-alvo. Reduzi-lo não retira o estoque "
                    "já existente naquele mês; escolha um alvo posterior para estudar "
                    "seu efeito na acumulação futura.")
        candidates,baseline=evaluate_lot_options(res,chosen_lot,month_idx)
        limits=tcc_lot_limits(res,chosen_lot)
        in_window=bool(res["active"][chosen_lot])
        with st.container(border=True):
            st.markdown("**Maior corte pelo critério do TCC**")
            if not in_window:
                st.caption("Este lote chega fora da janela crítica. Os limites "
                           "de corte devem ser interpretados somente dentro da "
                           "janela de decisão validada.")
            else:
                l1,l2=st.columns([1,2])
                l1.metric(
                    "Corte máximo (passos de 5%)",
                    ("−"+str(limits["max_cut_pct"])+"%") if limits["max_cut_pct"] else "Nenhum",
                    help="Maior redução contínua na grade de 5% antes de criar "
                         "novo sinal de ruptura ou aumentar a chance mensal de "
                         "ruptura em mais de 2,5 pontos percentuais."
                )
                l2.caption(
                    fmt(limits["max_cut_units"])+" unidades de "+
                    fmt(lot["units"])+" planejadas. A regra para no primeiro "
                    "passo que viola o limite; não equivale a uma recomendação "
                    "economicamente ótima nem confirma viabilidade contratual."
                )
        st.markdown("#### Escolha visualmente o ajuste do lote")
        cut_options = [0,5,10,15,25,50,100]
        cut_choice = st.select_slider(
            "Redução / cancelamento do lote (%)",
            options=cut_options, value=0, key="impact_cut_pct",
            help="A grade usa as mesmas alternativas simuladas pelo motor do TCC. "
                 "100% corresponde a cancelar o lote, não a uma ação autorizada."
        )
        reduction_name = ("Manter plano" if cut_choice == 0 else
                          "Cancelar lote" if cut_choice == 100 else
                          f"Reduzir {cut_choice}%")
        other_options=[name for name in candidates["Alternativa"]
                       if str(name).startswith("Aumentar ")]
        if other_options:
            with st.expander("Outras alternativas (aumento de lote)"):
                use_increase=st.checkbox("Comparar um aumento de produção",
                                         key="impact_compare_increase")
                increase_choice=st.selectbox("Aumento a comparar",other_options,
                                             key="impact_increase_choice")
            chosen_option=increase_choice if use_increase else reduction_name
        else:
            chosen_option=reduction_name
        selected=candidates[candidates["Alternativa"]==chosen_option].iloc[0]
        if not bool(selected["Dentro do critério do TCC"]):
            st.warning("Esta alternativa viola o critério de proteção do serviço: "
                       "cria sinal novo ou eleva a chance de ruptura além de 2,5 "
                       "pontos em algum mês. É apresentada para comparação, "
                       "não como corte recomendado.")
        elif chosen_option != "Manter plano":
            st.info("Esta alternativa permanece dentro do critério simulado do "
                    "TCC, sujeito à confirmação de lead time, contratos e "
                    "quantidades mínimas.")
        st.subheader("Efeito da alternativa selecionada")
        row1=st.columns(4)
        excess_change=float(selected["Excesso potencialmente evitado (un.)"])
        lost_change=float(selected["Vendas perdidas adicionais (un.)"])
        service_change=float(selected["Fill rate simulado (%)"])-baseline["fill_rate_pct"]
        row1[0].metric("Excesso potencialmente evitado",f'{excess_change:+,.0f} un.'.replace(",","."),help="Diferença entre excedente esperado no plano atual e na alternativa, no mesmo mês-alvo.")
        row1[1].metric("Vendas perdidas adicionais",f'{lost_change:+,.0f} un.'.replace(",","."),help="Diferença nas perdas esperadas totais da janela crítica.")
        row1[2].metric("Fill rate projetado",f'{float(selected["Fill rate simulado (%)"]):.1f}%',
                       delta=f'{service_change:+.1f} p.p.',delta_color="normal")
        row1[3].metric("Prazo teórico do lote",label(lot["deadline"]))
        st.caption(
            "A mesma sacola de "+str(len(res["dm"]))+" trajetórias de demanda é reutilizada "
            "em todas as alternativas. A previsão e as probabilidades não são dados reais futuros."
        )
        st.markdown("#### O equilíbrio entre reduzir excesso e preservar atendimento")
        st.plotly_chart(tradeoff_figure(candidates,chosen_option),
                        use_container_width=True)
        st.caption("Cada ponto é uma alternativa calculada, sem valores ilustrativos. "
                   "Verde = dentro do critério simulado do TCC; vermelho = fora do critério. "
                   "O losango mostra a seleção. Nenhum ponto significa corte aprovado.")
        with st.expander("Detalhes da análise: fronteira entre excesso e vendas perdidas"):
            min_fill=st.slider(
                "Meta mínima de fill rate para exploração (%)",
                min_value=70,max_value=100,value=95,step=1,key="impact_min_fill"
            )
            st.caption(
                "Meta ilustrativa ajustável, **não** é uma política aprovada pela L'Oréal. "
                "O painel não escolhe nem executa automaticamente uma alternativa."
            )
            frame=candidates.copy()
            frame["Cumpre meta hipotética"]=frame["Fill rate simulado (%)"]>=float(min_fill)
            fig=go.Figure()
            for _,row in frame.iterrows():
                is_current=row["Alternativa"]=="Manter plano"
                selected_here=row["Alternativa"]==chosen_option
                fig.add_trace(go.Scatter(
                    x=[float(row["Excesso esperado no mês-alvo (un.)"])],
                    y=[float(row["Vendas perdidas esperadas na janela (un.)"])],
                    mode="markers+text",
                    text=[row["Alternativa"]] if selected_here or is_current else [""],
                    textposition="top center",
                    name=row["Alternativa"],
                    marker=dict(
                        size=17 if selected_here else 11,
                        color=("#111111" if is_current else
                               "#167848" if row["Cumpre meta hipotética"] else "#be3322"),
                        symbol="diamond" if selected_here else "circle",
                        line=dict(width=1,color="#fff"),
                    ),
                    hovertemplate=(
                        "<b>"+row["Alternativa"]+"</b><br>Excesso esperado: %{x:,.0f} un."
                        "<br>Vendas perdidas: %{y:,.0f} un.<extra></extra>"
                    ),
                    showlegend=False,
                ))
            fig.update_layout(
                template="plotly_white",height=380,
                xaxis_title="Estoque excedente esperado no mês-alvo (un.)",
                yaxis_title="Vendas perdidas esperadas na janela (un.)",
                margin=dict(l=15,r=15,t=25,b=20),
                paper_bgcolor="#ffffff",plot_bgcolor="#ffffff"
            )
            st.plotly_chart(fig,use_container_width=True)
            st.caption("Pontos verdes cumprem a meta exploratória de fill rate; vermelhos, não. "
                       "O losango destaca a alternativa selecionada. "
                       "Uma alternativa não dominada apresenta uma troca potencial entre "
                       "excesso e perdas; isso não significa custo mínimo ou decisão ótima.")
            show=[
                "Alternativa","Quantidade do lote (un.)",
                "Excesso esperado no mês-alvo (un.)",
                "Excesso potencialmente evitado (un.)",
                "Vendas perdidas esperadas na janela (un.)",
                "Vendas perdidas adicionais (un.)",
                "Fill rate simulado (%)","Risco excesso no mês-alvo (%)",
                "Risco ruptura no mês-alvo (%)",
                "Não dominada (excesso × perda)","Cumpre meta hipotética"
            ]
            display=frame[show].copy()
            int_cols=[
                "Quantidade do lote (un.)","Excesso esperado no mês-alvo (un.)",
                "Excesso potencialmente evitado (un.)",
                "Vendas perdidas esperadas na janela (un.)",
                "Vendas perdidas adicionais (un.)",
            ]
            for col in int_cols:
                display[col]=display[col].round(0).astype(int)
            st.dataframe(display,hide_index=True,use_container_width=True)
            if not bool(selected["Não dominada (excesso × perda)"]):
                st.info("A alternativa selecionada é dominada: existe outra com "
                        "excesso esperado e vendas perdidas iguais ou menores.")
            if float(selected["Fill rate simulado (%)"])<min_fill:
                st.warning("A alternativa está abaixo da meta exploratória de fill rate. "
                           "Não há justificativa para recomendá-la automaticamente.")
        st.download_button(
            "Exportar comparação (CSV)",
            frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="impacto_"+product+"_"+label(close).replace("/","-")+".csv",
            mime="text/csv"
        )
        resumo_decisao=pd.DataFrame([
            {"Campo":"Fechamento", "Valor":label(close)},
            {"Campo":"Produto", "Valor":product},
            {"Campo":"Modelo operacional", "Valor":st.session_state["operational_"+product]},
            {"Campo":"Mês-alvo do excesso", "Valor":label(res["months"][month_idx])},
            {"Campo":"Lote avaliado", "Valor":label(lot["month"])},
            {"Campo":"Prazo teórico", "Valor":label(lot["deadline"])},
            {"Campo":"Alternativa selecionada", "Valor":chosen_option},
            {"Campo":"Excesso esperado sem alteração (un.)",
             "Valor":round(float(baseline["expected_excess_units"]))},
            {"Campo":"Excesso potencialmente evitado (un.)",
             "Valor":round(float(selected["Excesso potencialmente evitado (un.)"]))},
            {"Campo":"Vendas perdidas adicionais (un.)",
             "Valor":round(float(selected["Vendas perdidas adicionais (un.)"]))},
            {"Campo":"Fill rate simulado (%)",
             "Valor":round(float(selected["Fill rate simulado (%)"]),2)},
            {"Campo":"Status", "Valor":"Cenário hipotético — não executado"},
            {"Campo":"Pendências",
             "Valor":"Validar capacidade, lotes mínimos, contratos, custos, serviço e prazo real"},
        ])
        arquivo_excel = BytesIO()
        with pd.ExcelWriter(arquivo_excel, engine="openpyxl") as escritor:
            resumo_decisao.to_excel(escritor,sheet_name="Resumo para reuniao",index=False)
            frame.to_excel(escritor, sheet_name="Todas alternativas", index=False)
        st.download_button(
            "Baixar análise para reunião (Excel)",
            arquivo_excel.getvalue(),
            file_name="decisao_"+product+"_"+label(close).replace("/","-")+".xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.caption("As alternativas são comparadas com o plano sem alteração usando "
               "os mesmos cenários. Não existe escolha automática de lote ou custo ótimo.")
    with st.expander("Comparação estatística e histórico da antecedência"):
        st.subheader("4. Valor adicional frente à referência atual")
        st.write(
            "O benefício operacional acima compara a **alternativa de lote** com o "
            "**plano de produção sem alteração**, sob as mesmas trajetórias simuladas. "
            "Não é uma comparação com uma política de compras oficial que não foi fornecida."
        )
        detail,rank,winner=rankings[product]
        model=st.session_state["operational_"+product]
        comparison=historical_mape_vs_official(detail,model)
        if comparison is None:
            st.info(
                "Ainda não há previsões históricas comparáveis do modelo operacional "
                "e da previsão Oficial, com os mesmos pares origem e mês-alvo."
            )
        else:
            k1,k2,k3=st.columns(3)
            k1.metric("MAPE do modelo em uso",f'{comparison["mape_operacional"]:.1f}%')
            k2.metric("MAPE da previsão Oficial",f'{comparison["mape_oficial"]:.1f}%')
            k3.metric("Diferença (Oficial − modelo)",f'{comparison["delta_pp"]:+.1f} p.p.')
            st.caption(str(comparison["pares"])+" previsões comparáveis nos mesmos pares "
                       "origem/alvo. Comparação de previsão reduzida (4 modelos), "
                       "não prova melhoria do estoque ou superioridade generalizável.")
        st.subheader("5. Avisos que chegaram antes do lead time")
        key=("impact_history",st.session_state["data_digest"],product,close,model)
        if st.session_state.get("impact_history_key")!=key:
            try:
                _, historic_alerts,_=reconstruct_history(
                    product,close,blocks,base,model=model,max_origins=8,max_horizon=9,
                    method=DEFAULT_METHOD,persistent=False
                )
                first=first_alerts(historic_alerts)
                st.session_state["impact_history_count"]=(
                    len(first),
                    int(first["Emitido em tempo pelo LT"].sum()) if not first.empty else 0
                )
                st.session_state["impact_history_error"]=None
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                st.session_state["impact_history_count"]=(0,0)
                st.session_state["impact_history_error"]=str(exc)
            st.session_state["impact_history_key"]=key
        total,timely=st.session_state["impact_history_count"]
        if total:
            tm1,tm2=st.columns(2)
            tm1.metric("Alertas únicos reconstruídos",total)
            tm2.metric("Em tempo pelo lead time",f"{timely}/{total} · {timely/total*100:.1f}%")
        else:
            st.info("Não há alertas históricos verificáveis para calcular a taxa de "
                    "antecedência com a metodologia e os fechamentos selecionados.")
        if st.session_state.get("impact_history_error"):
            st.caption("Diagnóstico da reconstrução: "+
                       st.session_state["impact_history_error"])
        st.caption(
            "A primeira emissão de cada tipo de alerta por mês-alvo é contada uma vez. "
            "O prazo é apenas teórico, e esta é uma reconstrução retrospectiva com "
            "modelo fixo — não um registro permanente do que a L'Oréal decidiu."
        )
        st.button("Abrir validação histórica completa",
                  on_click=navigate,args=("Validação histórica dos alertas",product))
        st.warning(
            "Não existe evidência de redução real de estoque, economia financeira ou "
            "ganho de serviço sem execução/validação operacional. "
            "Ajustar produção exige confirmação do fornecedor, capacidade, custos, "
            "restrições contratuais e política de serviço da L'Oréal."
        )


elif page == "Valor demonstrado":
    st.subheader("O que foi comprovado — e o que ainda falta validar")
    st.caption("RESULTADOS RETROSPECTIVOS DO TCC · cinco lançamentos, três episódios de "
               "excesso · Valores fixos do estudo, que NÃO se atualizam com o Triângulo enviado.")
    a,b,c=st.columns(3)
    a.metric("Episódios antecipados pelo Smart Launch","2 de 3")
    b.metric("Episódios antecipados pela regra Oficial","0 de 3")
    c.metric("Precisão dos alertas fora da amostra","48%")
    st.caption("Um episódio é considerado antecipado quando o alerta chega antes do "
               "lead time do primeiro mês de excesso. A regra do plano Oficial usa a "
               "mesma base, sinalizando cobertura a partir de 180 dias. "
               "A precisão de 48% indica que ainda existem muitos falsos positivos.")

    st.markdown("#### Por que usar o Smart Launch junto ao plano oficial?")
    st.write("A previsão por analogia funciona como uma **segunda opinião** quando "
             "o lançamento ainda tem poucas vendas. A camada de simulação serve "
             "principalmente para testar se um corte de produção cria risco de ruptura. "
             "O sistema não substitui o plano oficial nem executa mudanças no fornecedor.")
    st.markdown("**Previsão por produto no estudo (MAPE; menor é melhor)**")
    accuracy=pd.DataFrame([
        {"Produto":"P1","MEA (%)":79,"MEA-P (%)":58,"Oficial (%)":124,
         "Melhor na comparação":"MEA-P"},
        {"Produto":"P2","MEA (%)":23,"MEA-P (%)":35,"Oficial (%)":31,
         "Melhor na comparação":"MEA"},
        {"Produto":"P3","MEA (%)":74,"MEA-P (%)":52,"Oficial (%)":45,
         "Melhor na comparação":"Oficial"},
    ])
    st.dataframe(accuracy,hide_index=True,use_container_width=True)
    st.caption("Tabela 4.2 do TCC. A MEA-P foi concebida depois de analisar "
               "resultados iniciais; os resultados de P1 a P3 são exploratórios. "
               "O Plano Oficial permaneceu a melhor previsão no P3.")

    st.markdown("#### A diferença prática está no momento da decisão")
    st.write("No estudo, a previsão por analogia identificou riscos que a regra do "
             "plano oficial ainda não sinalizava. Nos dois episódios adicionais "
             "fora da amostra, os primeiros alertas chegaram com seis e oito meses "
             "de antecedência, antes do prazo teórico de fornecimento.")
    st.caption("Comparação do estudo: episódios de excesso identificados (2/3 versus "
               "0/3), não um teste de superioridade estatística universal. "
               "As antecedências de seis e oito meses são dos dois episódios adicionais.")
    st.markdown("#### Conferir o valor incremental com o Triângulo enviado")
    st.write("Compare, para um mesmo mês de excesso **verificável**, quando teria "
             "surgido o primeiro alerta pela previsão em uso e pela previsão Oficial, "
             "aplicando a **mesma regra de risco do Smart Launch** às duas. "
             "Isso não é uma reconstrução de decisões reais da L'Oréal.")
    historical_product=st.selectbox(
        "Produto para comparação retrospectiva",list(MODEL),
        key="incremental_product"
    )
    historical_close=latest_verifiable_close(blocks,historical_product)
    model_now=st.session_state["operational_"+historical_product]
    st.caption("Modelo em uso: "+model_now+
               " · Referência: previsão Oficial + simulador Smart Launch. "
               "Mesmas revisões, até oito origens e horizonte de nove meses.")
    if historical_close is None:
        st.info("Não há fechamento verificável para o produto selecionado.")
    else:
        comparison_key=(
            st.session_state["data_digest"],historical_product,
            str(historical_close),model_now
        )
        if st.button("Comparar primeiros alertas com a previsão Oficial",
                     key="run_incremental"):
            try:
                with st.spinner("Reconstruindo as duas previsões em origens iguais..."):
                    sm_projections,sm_alerts,_=reconstruct_history(
                        historical_product,historical_close,blocks,base,
                        model=model_now,max_origins=8,max_horizon=9,
                        method=DEFAULT_METHOD,persistent=False
                    )
                    if model_now == "Oficial":
                        official_alerts=sm_alerts
                    else:
                        _,official_alerts,_=reconstruct_history(
                            historical_product,historical_close,blocks,base,
                            model="Oficial",max_origins=8,max_horizon=9,
                            method=DEFAULT_METHOD,persistent=False
                        )
                    compared=compare_verified_excess(
                        sm_projections,sm_alerts,official_alerts
                    )
                st.session_state["incremental_result"]=compared
                st.session_state["incremental_result_key"]=comparison_key
                st.session_state.pop("incremental_error",None)
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                st.session_state["incremental_error"]=str(exc)
                st.session_state.pop("incremental_result_key",None)
        if st.session_state.get("incremental_error") and st.session_state.get(
            "incremental_result_key")!=comparison_key:
            st.warning("Comparação não disponível: "+
                       st.session_state["incremental_error"])
        if st.session_state.get("incremental_result_key")==comparison_key:
            compared=st.session_state["incremental_result"]
            if compared.empty:
                st.info("Nenhum mês com excesso verificável foi encontrado nesse "
                        "recorte. Não é correto concluir que o risco não existiu.")
            else:
                m1,m2,m3=st.columns(3)
                m1.metric("Meses com excesso verificável",len(compared))
                m2.metric("Smart: aviso com oportunidade teórica",
                          int(compared["Smart: oportunidade pelo LT"].sum()))
                m3.metric("Oficial*: aviso com oportunidade teórica",
                          int(compared["Oficial*: oportunidade pelo LT"].sum()))
                st.dataframe(compared,hide_index=True,use_container_width=True)
                st.caption("O aviso é o primeiro para cada mês-alvo, dentro do "
                           "recorte reconstruído. Antecedência = mês-alvo menos "
                           "fechamento do primeiro alerta. Oportunidade = prazo pelo "
                           "lead time, incluindo mês-limite sujeito à data de corte. "
                           "Não comprova que o pedido seria alterável.")
                data_cmp=compared.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Baixar comparação dos alertas (CSV)",data_cmp,
                    file_name="comparacao_alertas_"+historical_product+".csv",
                    mime="text/csv"
                )
            if model_now=="Oficial":
                st.info("Neste produto o modelo operacional já é o Oficial. "
                        "As duas colunas representam a mesma previsão; "
                        "não há um modelo alternativo para comparar.")
    st.caption("*Oficial significa a previsão registrada no Triângulo combinada "
               "ao motor de riscos do Smart Launch, e NÃO a política completa de "
               "decisão executada pela empresa.")
    d,e=st.columns(2)
    d.metric("B_1 · redução potencial no pior mês","83%")
    e.metric("C_2 · redução potencial no pior mês","46%")
    st.caption("Exercícios contrafactuais: cortes hipotéticos sobre lotes que ainda "
               "poderiam mudar, supondo vendas inalteradas. Não incluem contratos, "
               "lotes mínimos nem restrições completas de fornecedores.")

    st.markdown("#### O que impede uma promessa de economia?")
    st.warning("Não foi demonstrada redução real de estoque atribuível ao Smart Launch. "
               "No P1, os lotes ainda modificáveis foram posteriormente cancelados "
               "pela própria L'Oréal. Não há dados suficientes para calcular economias "
               "financeiras nem validação prospectiva de decisões executadas.")
    st.write("**Confiabilidade:** o método sinalizou a tempo dois dos três episódios, "
             "mas a precisão de alertas nos benchmarks foi de 48%. "
             "O nível de alerta de 20% foi estabelecido após observar parte dos resultados. "
             "Isso torna necessário recalibrar e validar a regra em novos lançamentos.")
    st.caption("Os números aqui são evidências históricas do capítulo 4 do TCC. "
               "O diagnóstico no painel de decisões é recalculado com o Excel carregado.")
    st.button("Verificar alertas de um fechamento",
              on_click=navigate,args=("Validação histórica dos alertas",chosen))

elif page == "Validação histórica dos alertas":
    st.subheader("Alertas reconstruídos por fechamento")
    st.write("O que o Smart Launch previa em cada fechamento, o que foi registrado posteriormente e se o fornecedor ainda poderia receber uma alteração.")
    st.info(
        "Esta é uma **reconstrução retrospectiva** com as revisões do Triângulo, "
        "não uma auditoria de alertas efetivamente salvos no passado. "
        "A aplicação ainda não guarda as previsões emitidas e os modelos aprovados em cada fechamento."
    )
    st.caption(
        "A previsão e as probabilidades são recalculadas usando somente a revisão da origem. "
        "Os realizados futuros entram apenas na verificação, nunca na previsão original."
    )
    v1,v2,v3=st.columns([1,1,1])
    with v1:
        product=st.selectbox("Produto",list(MODEL),index=list(MODEL).index(chosen),key="validation_product")
    last_close=latest_verifiable_close(blocks,product)
    selectable=[rev-1 for rev in available_origin_reviews(blocks,product,last_close)] if last_close is not None else []
    if not selectable:
        st.warning("Não existem revisões históricas suficientes para avaliar este produto.")
        st.stop()
    with v2:
        verification_close=st.selectbox(
            "Verificar com dados até",selectable,index=len(selectable)-1,
            format_func=label,key="validation_asof"
        )
    with v3:
        max_origins=st.selectbox(
            "Fechamentos reconstruídos",[4,8,12,24],index=1,key="validation_origins"
        )
    horizon=st.select_slider("Horizonte máximo por previsão (meses)",[3,6,9,12],value=9,
                            key="validation_horizon")
    level=st.radio("Contar a partir de",[
        "Alerta (chance simulada > 20%)",
        "Aviso (chance simulada > 2,5%)",
    ],horizontal=True,key="validation_level")
    level_threshold=LIMIT_ALERT if level.startswith("Alerta") else LIMIT_WARN
    initial_model=MODEL[product]
    chosen_operational=st.session_state["operational_"+product]
    model_choices=[initial_model]
    if chosen_operational!=initial_model:
        model_choices.append(chosen_operational)
    model=st.selectbox("Modelo para reconstruir as previsões",model_choices,
                       key="validation_model")
    st.caption(
        "Modelo congelado para fins de comparação. Caso a seleção do modelo tenha mudado "
        "ao longo dos meses, este histórico não recupera automaticamente a escolha feita à época."
    )
    with st.spinner("Reconstituindo fechamentos históricos sem usar dados futuros na previsão..."):
        projections, alerts, gaps=reconstruct_history(
            product, verification_close, blocks, base, model=model,
            max_origins=max_origins, max_horizon=horizon,
            method=DEFAULT_METHOD, persistent=False,threshold=level_threshold
        )
    earliest=first_alerts(alerts)
    verified=(
        earliest[earliest["Status observado"].isin([EVENT_YES, EVENT_NO])]
        if not earliest.empty else earliest
    )
    confirmed=(verified["Status observado"]==EVENT_YES).sum() if not verified.empty else 0
    false_alarms=(verified["Status observado"]==EVENT_NO).sum() if not verified.empty else 0
    timely=int(earliest["Emitido em tempo pelo LT"].sum()) if not earliest.empty else 0
    metrics=st.columns(4)
    metrics[0].metric("Primeiros alertas",len(earliest))
    metrics[1].metric("Excessos verificáveis",int(confirmed) if len(verified) else "—")
    metrics[2].metric("Alertas de excesso não confirmados",int(false_alarms) if len(verified) else "—")
    metrics[3].metric("Alertas com prazo teórico aberto",timely if not earliest.empty else "—")
    st.caption("Filtro atual: " + level + ". Avisos e alertas não devem ser misturados "
               "com resultados do estudo que utilizaram outro limiar.")
    st.caption(
        "Os resultados contam **meses-alvo × tipo de risco distintos**, usando a primeira emissão "
        "para evitar contabilizar o mesmo problema repetido em revisões sobrepostas. "
        "Status de excesso só é verificável se o estoque estiver registrado e a demanda futura "
        "realizada permitir decidir o limite de 180 dias. Prazo aberto pelo LT não confirma "
        "possibilidade contratual de alteração."
    )
    st.subheader("Primeiro alerta por mês-alvo")
    if earliest.empty:
        st.warning(
            "Nenhum alerta probabilístico pôde ser reconstruído nas revisões selecionadas. "
            "Isso não significa ausência de excesso ou ruptura."
        )
    else:
        status_cols=[
            "Fechamento","Mês-alvo","Tipo de alerta","Probabilidade do alerta (%)",
            "Previsão no fechamento (un.)","Venda realizada (un.)",
            "Estoque na revisão posterior (un.)","Cobertura com realizados",
            "Status observado","Antecedência (meses)",
            "Próximo prazo","Status de oportunidade"
        ]
        st.dataframe(earliest[status_cols],hide_index=True,use_container_width=True)
        st.caption(
            "A classificação de ruptura permanece não verificável enquanto não houver "
            "dados de vendas perdidas efetivamente realizadas. Estoque zerado, isoladamente, "
            "não prova demanda não atendida."
        )
    st.subheader("Previsão original reconstruída × realizado")
    if projections.empty:
        st.warning("Não existem previsões históricas reconstruíveis com os critérios atuais.")
    else:
        st.caption(
            "O erro percentual só é calculado quando existe venda realizada positiva. "
            "O estoque é o valor da coluna do mês-alvo na revisão seguinte (m+1), "
            "não o estoque projetado na data do alerta."
        )
        shown=[
            "Fechamento","Mês-alvo","Horizonte","Modelo reconstruído",
            "Previsão no fechamento (un.)","Venda realizada (un.)",
            "Erro absoluto (un.)","Erro percentual (%)",
            "Estoque na revisão posterior (un.)",
            "Cobertura com realizados","Verificação de excesso",
            "Prob. excesso (%)","Prob. ruptura (%)"
        ]
        st.dataframe(projections[shown],
                     hide_index=True,use_container_width=True)
        s1,s2=st.columns(2)
        with s1:
            if not alerts.empty:
                target_options=sorted(set(alerts["_alvo"]))
            else:
                target_options=sorted(set(projections["_alvo"]))
            selected_target=st.selectbox("Acompanhar um mês-alvo",target_options,format_func=label)
        with s2:
            chart_type=st.selectbox("Tipo de probabilidade",["Excesso","Ruptura"])
        chart_source=projections[projections["_alvo"]==selected_target].sort_values("_origem")
        risk_col="Prob. excesso (%)" if chart_type=="Excesso" else "Prob. ruptura (%)"
        chart_source=chart_source.dropna(subset=[risk_col])
        if not chart_source.empty:
            fchart=go.Figure()
            fchart.add_trace(go.Scatter(
                x=chart_source["Fechamento"],y=chart_source[risk_col],
                name=chart_type,mode="lines+markers",
                line=dict(color="#b42318" if chart_type=="Excesso" else "#d69b14",width=3)
            ))
            fchart.add_hline(y=2.5,line_dash="dash",line_color="#595959",
                             annotation_text="Gatilho 2,5%",annotation_position="top left")
            fchart.update_layout(template="plotly_white",height=295,
                                 yaxis_title="Probabilidade (%)",
                                 xaxis_title="Fechamento da previsão",
                                 margin=dict(l=20,r=15,t=24,b=15),showlegend=False)
            st.plotly_chart(fchart,use_container_width=True)
        else:
            st.info("Este mês-alvo ainda não tem probabilidades históricas válidas.")
    if not alerts.empty:
        with st.expander("Todas as emissões históricas, inclusive alertas repetidos"):
            detail_cols=[
                "Fechamento","Mês-alvo","Tipo de alerta",
                "Probabilidade do alerta (%)","Status observado",
                "Status de oportunidade","Antecedência (meses)"
            ]
            st.dataframe(alerts[detail_cols],hide_index=True,use_container_width=True)
    if not gaps.empty:
        with st.expander("Fechamentos sem previsão ou sem simulação completa"):
            st.dataframe(gaps,hide_index=True,use_container_width=True)
    st.subheader("Exportar validação")
    left,right=st.columns(2)
    if not projections.empty:
        csv_projection=projections.drop(columns=["_origem","_alvo"]).to_csv(
            index=False
        ).encode("utf-8-sig")
        left.download_button(
            "Baixar previsões × realizados (CSV)",csv_projection,
            file_name="validacao_previsoes_"+product+".csv",mime="text/csv"
        )
    if not earliest.empty:
        csv_alerts=earliest.drop(columns=["_origem","_alvo"]).to_csv(
            index=False
        ).encode("utf-8-sig")
        right.download_button(
            "Baixar primeiros alertas (CSV)",csv_alerts,
            file_name="validacao_alertas_"+product+".csv",mime="text/csv"
        )
    st.warning(
        "Validação exploratória. As probabilidades foram geradas com poucos erros históricos "
        "e não têm calibração comprovada. Sem seis meses futuros realizados (ou esgotamento "
        "observado antes disso), não é correto declarar excesso confirmado ou descartado. "
        "O estoque apresentado é um registro de revisão posterior cujo significado "
        "operacional deve ser confirmado com a L'Oréal."
    )

elif page == "Histórico e metodologia":
    st.subheader("Metodologia, parâmetros e auditoria")
    st.write("Parâmetros, rastreabilidade e limitações do Smart Launch.")
    with st.expander("Auditoria dos dados enviados", expanded=False):
        diagnostics=[]
        for p,sheet in SHEETS.items():
            b=blocks[sheet]
            diagnostics.append({
                "Produto":p,
                "Revisões PV":len(b["PV"].index),
                "Revisões PROD":len(b["PROD"].index),
                "Revisões EST":len(b["EST"].index),
                "Simulação":"Válida" if results[p] is not None else "Indisponível",
                "Observação":errors.get(p,""),
            })
        st.dataframe(pd.DataFrame(diagnostics),hide_index=True,use_container_width=True)
        st.caption("Dados comerciais processados na sessão, não publicados no repositório.")
    st.subheader("Registro desta sessão")
    st.caption("Fechamento "+label(close)+" · Arquivo "+file_name)
    approvals=st.session_state.get("approvals",[])
    if approvals:
        st.dataframe(pd.DataFrame(approvals),hide_index=True,use_container_width=True)
    else:
        st.info("Nenhuma mudança de modelo aprovada nesta sessão.")
    st.warning("Registros não persistem entre sessões. Não representam trilha de auditoria empresarial.")
    st.subheader("Premissas de simulação")
    st.selectbox("Distribuição de erros",["Normal (0, s)","Bootstrap centralizado"],key="simulation_method")
    st.checkbox("Erro persistente entre meses (sensibilidade)",key="simulation_persistent")
    st.markdown("""
**Método principal do TCC:** previsão por analogia MEA / MEA-P ou plano Oficial,
erro aditivo Normal(0,s), 1.000 trajetórias, estoque com vendas perdidas e
cobertura pelo consumo futuro. Excesso se cobertura ≥ 180 dias, ruptura se
venda perdida > 0. Os alertas são aplicados apenas dentro da janela crítica
e quando o evento supera o limite de 2,5% dos cenários (aviso), e **alerta** se supera 20%.

**Janela crítica:** teto(lead time em semanas × 7/30) +
teto(cobertura-alvo / 30) + 1 mês.

**Limitações:** poucos erros de arranque, previsões históricas sobrepostas,
distribuição Normal não comprovada e restrições operacionais de fornecedor
não incorporadas. A regra de seleção de modelos da aba Previsão é uma
versão reduzida experimental e precisa de homologação.
""")
    export=[]
    for product,res in results.items():
        if res is not None:
            frame=rows_from_sim(res)
            frame.insert(0,"Produto",product)
            export.append(frame.drop(columns=["Período"]))
    if export:
        data_csv=pd.concat(export,ignore_index=True).to_csv(index=False).encode("utf-8-sig")
        st.download_button("Exportar riscos do fechamento (CSV)",data_csv,
                           file_name="smartlaunch_"+label(close).replace("/","-")+".csv",
                           mime="text/csv")
        arquivo_excel = BytesIO()
        with pd.ExcelWriter(arquivo_excel, engine="openpyxl") as escritor:
            pd.concat(export, ignore_index=True).to_excel(
                escritor, sheet_name="Riscos do fechamento", index=False
            )
        st.download_button(
            "Exportar riscos do fechamento (Excel)",
            arquivo_excel.getvalue(),
            file_name="smartlaunch_"+label(close).replace("/","-")+".xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.caption("Dados confidenciais não são publicados no GitHub. Implantação empresarial requer autenticação, armazenamento privado, homologação dos cálculos e política de retenção.")
