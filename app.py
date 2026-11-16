from pathlib import Path
import html
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forecasting import (
    MODELS, plabel, read_base_table, read_bom, product_meta,
    parse_pv_sheet, realized_from_matrix, forecast_model, build_audit,
    choose_model, evaluated_until,
)

st.set_page_config(page_title="Smart Launch | Launch Decision Center", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:Inter,sans-serif}
.stApp{background:#f3f6fa;color:#142338}
.block-container{padding-top:2.1rem;max-width:1360px;padding-bottom:4rem}
[data-testid="stSidebar"]{background:#102d49}
[data-testid="stSidebar"] *{color:#f4f8fc}
[data-testid="stSidebar"] [data-baseweb="select"] *{color:#152b42}
[data-testid="stSidebar"] [data-testid="stFileUploader"]{border-radius:10px}
[data-testid="stHeader"]{background:transparent}
#MainMenu,footer{visibility:hidden}
.kicker{font-size:11px;color:#2564c4;letter-spacing:2px;font-weight:800}
.heading{font-size:34px;letter-spacing:-1px;line-height:1.1;font-weight:800;color:#172c46;margin:6px 0}
.subtitle{color:#718197;font-size:13px;margin-bottom:22px}
.hero{background:linear-gradient(115deg,#102c46,#1c466c);border-radius:17px;padding:25px 29px;color:white;margin-bottom:16px}
.hero .tag{font-size:10px;letter-spacing:1.5px;color:#aecbe8;font-weight:800}
.hero .big{font-size:26px;line-height:1.2;font-weight:800;margin:9px 0}
.hero .desc{font-size:13px;line-height:1.65;color:#d4e3f0}
.kpi{min-height:132px;padding:18px;background:white;border:1px solid #e9eef4;border-radius:14px;box-shadow:0 6px 18px rgba(30,55,80,.04);margin-bottom:5px}
.kpi .name{font-size:10px;font-weight:800;color:#728197;text-transform:uppercase;letter-spacing:.8px}
.kpi .number{font-size:29px;font-weight:800;color:#172c46;margin:12px 0 5px}
.kpi .detail{font-size:11px;color:#8a98a8}
.sec{color:#6e7f92;font-size:11px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;margin:23px 0 9px}
.panel{background:white;border:1px solid #e8edf4;border-radius:15px;padding:20px;margin-bottom:12px;box-shadow:0 6px 18px rgba(30,55,80,.04)}
.panel h3{margin:0 0 4px;font-size:17px;color:#213650}
.panel p{margin:4px 0 13px;color:#8794a6;font-size:12px}
.notice{background:#edf4fc;border-left:3px solid #478cf8;padding:12px 14px;border-radius:5px;color:#345270;font-size:12px;line-height:1.6}
.pill{border-radius:30px;background:#e9f4ff;color:#2466bb;font-size:11px;font-weight:800;padding:5px 10px}
</style>
""", unsafe_allow_html=True)

def esc(v):
    return html.escape(str(v))

def fmt_num(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{float(v):,.0f}".replace(",", ".")

def fmt_pct(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{100*float(v):.1f}%".replace(".", ",")

def kpi(title, value, detail):
    st.markdown('<div class="kpi"><div class="name">'+esc(title)+'</div><div class="number">'+esc(value)+'</div><div class="detail">'+esc(detail)+'</div></div>', unsafe_allow_html=True)

def panel_title(title, detail=""):
    st.markdown('<div class="panel"><h3>'+esc(title)+'</h3><p>'+esc(detail)+'</p>', unsafe_allow_html=True)

def fig_style(fig, height=320):
    fig.update_layout(height=height, margin=dict(l=8,r=8,t=16,b=28),
        paper_bgcolor="white",plot_bgcolor="white",
        font=dict(family="Inter",color="#61748b",size=11),
        legend=dict(orientation="h",y=-.24,x=0),
        hovermode="x unified")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#edf1f6",zeroline=False)
    return fig

DEFAULT = Path(__file__).with_name("Base de Dados - PUC (2).xlsx")
with st.sidebar:
    st.markdown("### SMART LAUNCH")
    st.caption("L'Oréal · Supply Chain Intelligence")
    st.divider()
    st.subheader("1 · Carregar planilha")
    upload = st.file_uploader("Arquivo Excel (.xlsx)", type=["xlsx"])
    if upload:
        st.success("Planilha carregada nesta sessão")
        source = upload
    elif DEFAULT.exists():
        source = DEFAULT
        st.caption("Usando base de demonstração do repositório. Envie outra planilha para substituir.")
    else:
        source = None
        st.caption("Envie a planilha de produtos para começar.")

if source is None:
    st.markdown('<div class="kicker">SUPPLY CHAIN INTELLIGENCE</div><div class="heading">Launch Decision Center</div><div class="subtitle">Envie uma planilha Excel usando o menu lateral.</div>',unsafe_allow_html=True)
    st.info("O painel identifica automaticamente as abas de produtos e permite alternar entre elas sem limite fixo de três SKUs.")
    st.stop()

try:
    xls = pd.ExcelFile(source)
    base = read_base_table(xls) if "Base" in xls.sheet_names else pd.DataFrame()
    bom = read_bom(xls) if "BOM" in xls.sheet_names else pd.DataFrame()
    excluded = {"BASE", "BOM", "README", "INSTRUCOES", "INSTRUÇÕES", "PARAMETROS", "PARÂMETROS"}
    candidates = [s for s in xls.sheet_names if s.strip().upper() not in excluded]
    products = {}
    problems = {}
    for sheet in candidates:
        try:
            m = parse_pv_sheet(xls,sheet)
            if m.shape[0] and m.shape[1]:
                products[sheet]=m
        except Exception as error:
            problems[sheet]=str(error)
except Exception as error:
    st.error("A planilha não pôde ser lida: "+str(error))
    st.stop()

if not products:
    st.error("Não foram encontradas abas com uma matriz de previsão mensal válida.")
    with st.expander("Diagnóstico da planilha"):
        st.write(problems)
    st.stop()

with st.sidebar:
    st.divider()
    st.subheader("2 · Selecionar produto")
    product = st.selectbox("Produto / SKU", list(products.keys()))
    st.caption(str(len(products))+" produtos reconhecidos automaticamente.")
    st.subheader("3 · Selecionar fechamento")
    matrix = products[product]
    closures = list(matrix.index)
    closure = st.selectbox("Versão do planejamento",closures,index=len(closures)-1,format_func=plabel)
    st.divider()
    st.caption("Indicadores do painel correspondem apenas ao produto e fechamento selecionados.")
    with st.expander("Qualidade da importação"):
        st.write("Abas reconhecidas:", len(products))
        st.write("Abas não reconhecidas:", len(problems))
        if problems: st.json(problems)

meta = product_meta(base,bom,product)
realized = realized_from_matrix(matrix)
known = realized[realized.index < closure]
audit = build_audit(matrix,realized,14)
decision = choose_model(audit,closure)
best = decision.get("model")
official_future = matrix.loc[closure]
official_future = official_future[official_future.index > closure].dropna().astype(float)
target_periods = [p for p in matrix.columns if p > closure]
horizon = min(12,len(target_periods))
future = target_periods[:horizon]

if best and len(known):
    selected = forecast_model(best,known.values,horizon)
elif len(known):
    selected = forecast_model("Naive",known.values,horizon)
else:
    selected = None
used_model = best or ("Naive (provisório)" if selected is not None else "Sem modelo")

st.markdown('<div class="kicker">SUPPLY CHAIN INTELLIGENCE</div><div class="heading">Launch Decision Center</div><div class="subtitle">Antecipação de risco e suporte à decisão de abastecimento · '+esc(product)+' · '+esc(plabel(closure))+'</div>',unsafe_allow_html=True)

if best:
    htitle = "Previsão selecionada: "+best
    msg = "Seleção feita com erros históricos conhecidos até o fechamento selecionado. Avalie a divergência frente ao planejamento oficial antes de decidir sobre produção."
else:
    htitle = "Monitoramento em construção"
    msg = "Não há histórico comparável suficiente para selecionar um modelo vencedor de forma validada neste fechamento. A projeção ingênua, quando disponível, é mostrada apenas como referência."
st.markdown('<div class="hero"><div class="tag">SMART LAUNCH · RECOMENDAÇÃO</div><div class="big">'+esc(htitle)+'</div><div class="desc">'+esc(msg)+'</div></div>',unsafe_allow_html=True)

st.markdown('<div class="sec">Resumo executivo</div>',unsafe_allow_html=True)
cs = st.columns(5)
with cs[0]: kpi("Produto selecionado",product,"SKU da aba da planilha")
with cs[1]: kpi("Modelo de referência",used_model,"Validação rolante, quando possível")
with cs[2]: kpi("Lead time",fmt_num(meta["lt_weeks"])+" sem","Da aba Base / BOM")
with cs[3]: kpi("Cobertura alvo",fmt_num(meta["cobertura"])+" dias","Meta informada na base")
with cs[4]: kpi("Realizados disponíveis",str(len(known)),"Antes do fechamento escolhido")

a,b = st.columns([1.7,1])
with a:
    panel_title("Demand Forecast","Previsão oficial versus modelo selecionado · dados da planilha")
    fig = go.Figure()
    if len(known):
        fig.add_trace(go.Scatter(x=[str(p) for p in known.index], y=known.values,
            mode="lines+markers",name="Demanda realizada",line=dict(color="#173c5e",width=3)))
    if len(official_future):
        fig.add_trace(go.Scatter(x=[str(p) for p in official_future.index],
            y=official_future.values,mode="lines+markers",name="Plano oficial",
            line=dict(color="#e5a62d",width=2,dash="dash")))
    if selected is not None:
        fig.add_trace(go.Scatter(x=[str(p) for p in future],
            y=selected,mode="lines+markers",name=used_model,
            line=dict(color="#367df7",width=3)))
    st.plotly_chart(fig_style(fig),use_container_width=True)
    st.markdown("</div>",unsafe_allow_html=True)
with b:
    panel_title("Leitura do planejamento","Comparação das próximas demandas projetadas")
    if selected is not None and future:
        compare = pd.DataFrame({"Mês":[plabel(p) for p in future],
                "Smart Launch":[float(v) for v in selected],
                "Oficial":[float(official_future[p]) if p in official_future.index else np.nan for p in future]})
        compare["Diferença"] = compare["Smart Launch"]-compare["Oficial"]
        st.dataframe(compare.style.format({"Smart Launch":"{:,.0f}","Oficial":"{:,.0f}","Diferença":"{:+,.0f}"},na_rep="—"),
            use_container_width=True,hide_index=True,height=330)
    else:
        st.info("Sem dados para comparação de projeções neste fechamento.")
    st.markdown("</div>",unsafe_allow_html=True)

st.markdown('<div class="sec">Risk Monitor</div>',unsafe_allow_html=True)
a,b = st.columns(2)
with a:
    panel_title("Monitor de excesso e ruptura","Não confundir divergência de previsão com probabilidade de excesso")
    st.markdown('<div class="notice"><b>Aguardando dados de estoque e entradas planejadas.</b> A matriz PV informa previsões de demanda, mas não permite, sozinha, calcular cobertura futura, probabilidades Monte Carlo ou ruptura. Esses indicadores só devem ser habilitados quando suas variáveis operacionais forem fornecidas.</div>',unsafe_allow_html=True)
    st.markdown("</div>",unsafe_allow_html=True)
with b:
    panel_title("Inventory Coverage Outlook","Cobertura futura comparada com o limite operacional")
    st.info("Necessário: estoque inicial por SKU, recebimentos mensais, consumo projetado e política de cobertura.")
    if pd.notna(meta["cobertura"]):
        st.caption("Cobertura alvo cadastrada para "+product+": "+fmt_num(meta["cobertura"])+" dias.")
    st.markdown("</div>",unsafe_allow_html=True)

st.markdown('<div class="sec">Decision Simulator</div>',unsafe_allow_html=True)
a,b = st.columns(2)
with a:
    panel_title("Lot Intervention Frontier","Avaliação do que ainda pode ser alterado com lead time")
    st.info("Para identificar lotes ajustáveis, a planilha deve informar lotes programados, datas de compromisso e condições de cancelamento ou redução.")
    st.markdown("</div>",unsafe_allow_html=True)
with b:
    panel_title("Recommended Alternatives","Comparação de impacto e viabilidade de ações")
    st.info("Nenhuma redução ou cancelamento é recomendado sem simular o estoque e verificar os compromissos de fornecimento.")
    st.markdown("</div>",unsafe_allow_html=True)

st.markdown('<div class="sec">Why Smart Launch?</div>',unsafe_allow_html=True)
a,b = st.columns([1.2,1])
with a:
    panel_title("Validação histórica dos modelos","Erros conhecidos no fechamento · sem uso de dados futuros")
    ev = evaluated_until(audit,closure,max_h=3)
    ev = ev[ev["realizado"].notna()].copy() if not ev.empty else ev
    if not ev.empty:
        ev["erro_abs"] = ev["erro"].abs()
        report = ev.groupby("modelo",as_index=False).agg(MAE=("erro_abs","mean"),Avaliações=("erro_abs","size"))
        report = report.sort_values("MAE")
        fig=go.Figure(go.Bar(x=report["modelo"],y=report["MAE"],marker_color="#367df7"))
        fig.update_layout(yaxis_title="Erro médio absoluto")
        st.plotly_chart(fig_style(fig,275),use_container_width=True)
        st.dataframe(report.style.format({"MAE":"{:,.0f}"}),hide_index=True,use_container_width=True)
        st.caption("Comparação descritiva: modelos podem ter números distintos de previsões avaliadas. A seleção do modelo utiliza a rotina de comparação comum existente no código.")
    else:
        st.info("Ainda não existem resultados históricos suficientes neste fechamento.")
    st.markdown("</div>",unsafe_allow_html=True)
with b:
    panel_title("Evidence Quality","O que os dados demonstram — e o que ainda não demonstram")
    st.write("**Integridade temporal:** os realizados são conhecidos apenas na versão seguinte.")
    st.write("**Rastreabilidade:** produto, versão, previsão e modelo ficam visíveis.")
    st.write("**Precisão de alertas:** não avaliada com a base PV isolada.")
    st.write("**Validação prospectiva:** pendente de novas observações.")
    st.markdown("</div>",unsafe_allow_html=True)

st.caption("Smart Launch é um sistema de apoio à decisão. Projeções não equivalem a pedidos ou alterações automáticas no plano. O painel não inventa estoques, probabilidades de risco ou lotes de produção ausentes do arquivo.")
