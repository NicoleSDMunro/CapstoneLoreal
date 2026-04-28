import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="Capstone L'Oréal | Dashboard Supply Chain",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background: #070707; color: #f5f5f5; }
    [data-testid="stSidebar"] { background: #101010; }
    .main-title { font-size: 44px; font-weight: 800; margin-bottom: 0; }
    .subtitle { color: #b8b8b8; font-size: 18px; margin-top: 8px; }
    .card {
        background: linear-gradient(180deg, #171717 0%, #111111 100%);
        border: 1px solid #2a2a2a;
        border-radius: 16px;
        padding: 22px;
        box-shadow: 0 10px 30px rgba(0,0,0,.25);
    }
    .metric-label { color: #898989; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { color: #ffffff; font-size: 32px; font-weight: 800; margin-top: 6px; }
    .metric-delta { color: #a0a0a0; font-size: 14px; margin-top: 2px; }
    .alert-box {
        background: linear-gradient(90deg, rgba(239,68,68,.28), rgba(239,68,68,.08));
        border-left: 6px solid #ef4444;
        border-radius: 12px;
        padding: 20px 24px;
        color: #ffffff;
        font-size: 18px;
        line-height: 1.5;
    }
    .success-box {
        background: linear-gradient(90deg, rgba(16,185,129,.25), rgba(16,185,129,.07));
        border-left: 6px solid #10b981;
        border-radius: 12px;
        padding: 20px 24px;
        color: #ffffff;
        font-size: 18px;
        line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)

MESES = ["jun/25", "jul/25", "ago/25", "set/25", "out/25", "nov/25", "dez/25", "jan/26", "fev/26", "mar/26", "abr/26", "mai/26", "jun/26"]


def exemplo_base():
    dados = []
    revisoes = ["jul/25", "ago/25", "set/25"]
    produtos = ["Produto A", "Produto B"]
    rng = np.random.default_rng(42)

    for produto in produtos:
        for revisao in revisoes:
            base_pv = np.array([300, 250, 260, 450, 520, 470, 360, 330, 180, 340, 290, 280, 450]) * 1000
            base_prod = np.array([310, 260, 390, 680, 700, 370, 210, 450, 270, 350, 410, 380, 240]) * 1000
            base_est = np.array([200, 180, 330, 570, 760, 650, 500, 630, 720, 730, 850, 970, 740]) * 1000

            fator = 1.0
            if revisao == "jul/25":
                fator = 0.94
            elif revisao == "set/25":
                fator = 1.05
            if produto == "Produto B":
                fator *= 0.72

            for mes, pv, prod, est in zip(MESES, base_pv, base_prod, base_est):
                dados.append({
                    "Produto": produto,
                    "Revisao": revisao,
                    "Mes": mes,
                    "PV": int(pv * fator * rng.normal(1, 0.04)),
                    "Producao": int(prod * fator * rng.normal(1, 0.05)),
                    "Estoque": int(est * fator * rng.normal(1, 0.06)),
                    "LeadTimeDias": 112,
                    "CoberturaTargetDias": 75
                })
    return pd.DataFrame(dados)


def ler_arquivo(arquivo):
    if arquivo.name.lower().endswith(".csv"):
        return pd.read_csv(arquivo)
    return pd.read_excel(arquivo)


def normalizar_colunas(df):
    mapa = {c.lower().strip(): c for c in df.columns}
    obrigatorias = {
        "produto": "Produto",
        "revisao": "Revisao",
        "mes": "Mes",
        "pv": "PV",
        "producao": "Producao",
        "estoque": "Estoque"
    }
    rename = {}
    for chave, nome_padrao in obrigatorias.items():
        if chave in mapa:
            rename[mapa[chave]] = nome_padrao
    df = df.rename(columns=rename)
    return df


def format_numero(valor):
    valor = float(valor)
    if abs(valor) >= 1_000_000:
        return f"{valor/1_000_000:.1f}M"
    if abs(valor) >= 1_000:
        return f"{valor/1_000:.0f}k"
    return f"{valor:,.0f}"


def card(label, value, delta=""):
    st.markdown(f"""
    <div class="card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-delta">{delta}</div>
    </div>
    """, unsafe_allow_html=True)


st.markdown('<p class="main-title">Capstone L’Oréal</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Dashboard interativo para análise de PV/Sell In, produção, estoque e risco de cobertura.</p>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Base de dados")
    arquivo = st.file_uploader("Envie um arquivo Excel ou CSV", type=["xlsx", "csv"])
    usar_exemplo = st.toggle("Usar base exemplo", value=True)
    st.caption("Colunas esperadas: Produto, Revisao, Mes, PV, Producao, Estoque, LeadTimeDias, CoberturaTargetDias.")

if arquivo is not None:
    df = ler_arquivo(arquivo)
elif usar_exemplo:
    df = exemplo_base()
else:
    st.info("Envie uma base de dados ou ative a base exemplo para visualizar o dashboard.")
    st.stop()

df = normalizar_colunas(df)
colunas_minimas = ["Produto", "Revisao", "Mes", "PV", "Producao", "Estoque"]
faltantes = [c for c in colunas_minimas if c not in df.columns]
if faltantes:
    st.error(f"A base não possui as colunas obrigatórias: {', '.join(faltantes)}")
    st.stop()

for c in ["PV", "Producao", "Estoque"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

if "LeadTimeDias" not in df.columns:
    df["LeadTimeDias"] = 112
if "CoberturaTargetDias" not in df.columns:
    df["CoberturaTargetDias"] = 75

produtos = sorted(df["Produto"].dropna().unique())
revisoes = list(df["Revisao"].dropna().unique())

c1, c2 = st.columns(2)
with c1:
    produto = st.selectbox("Produto", produtos)
with c2:
    revisao = st.selectbox("Revisão", revisoes, index=len(revisoes)-1 if revisoes else 0)

base = df[(df["Produto"] == produto) & (df["Revisao"] == revisao)].copy()
if base.empty:
    st.warning("Não há dados para os filtros selecionados.")
    st.stop()

pv_total = base["PV"].sum()
producao_total = base["Producao"].sum()
estoque_final = base["Estoque"].iloc[-1]
lt = int(base["LeadTimeDias"].iloc[0])
ct = int(base["CoberturaTargetDias"].iloc[0])

meses_acima_10 = 0
if len(base) > 1:
    variacao = base["PV"].pct_change().abs()
    meses_acima_10 = int((variacao > 0.10).sum())

st.markdown("---")
col1, col2, col3, col4 = st.columns(4)
with col1:
    card("Revisão", revisao, produto)
with col2:
    card("PV Total", format_numero(pv_total), "Volume previsto no período")
with col3:
    card("Meses >10%", f"{meses_acima_10}m", "Variação de PV")
with col4:
    card("Estoque Final", format_numero(estoque_final), str(base["Mes"].iloc[-1]))

st.subheader(f"PV - Produção - Estoque | {revisao}")
fig = go.Figure()
fig.add_trace(go.Scatter(x=base["Mes"], y=base["PV"], mode="lines+markers", name="PV (Sell In)", line=dict(width=4, color="#60a5fa")))
fig.add_trace(go.Scatter(x=base["Mes"], y=base["Producao"], mode="lines+markers", name="Produção", line=dict(width=4, dash="dash", color="#34d399")))
fig.add_trace(go.Scatter(x=base["Mes"], y=base["Estoque"], mode="lines+markers", name="Estoque", line=dict(width=4, dash="dot", color="#fb923c")))
fig.update_layout(
    paper_bgcolor="#111111",
    plot_bgcolor="#111111",
    font=dict(color="#f5f5f5"),
    height=520,
    margin=dict(l=30, r=30, t=40, b=30),
    legend=dict(orientation="h", y=-0.2, x=0.25),
    xaxis=dict(gridcolor="#242424"),
    yaxis=dict(gridcolor="#242424")
)
st.plotly_chart(fig, use_container_width=True)

st.subheader(f"Conclusão automática - {produto} - {revisao}")
if lt > ct:
    st.markdown(f"""
    <div class="alert-box">
        <strong>Risco estrutural:</strong> LT ({lt}d) maior que Cobertura Target ({ct}d). 
        Uma demanda surpresa pode não ser respondida a tempo, exigindo maior atenção ao planejamento de produção e estoque.
    </div>
    """, unsafe_allow_html=True)
elif estoque_final < pv_total / max(len(base), 1) * 0.5:
    st.markdown("""
    <div class="alert-box">
        <strong>Risco de ruptura:</strong> estoque final baixo em relação à média de PV do período.
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="success-box">
        <strong>Situação controlada:</strong> estoque e cobertura não indicam risco crítico nos parâmetros atuais.
    </div>
    """, unsafe_allow_html=True)

with st.expander("Ver base filtrada"):
    st.dataframe(base, use_container_width=True)

with st.expander("Baixar modelo de base"):
    modelo = exemplo_base().head(20)
    st.dataframe(modelo, use_container_width=True)
    csv = modelo.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV exemplo", csv, "modelo_capstone_loreal.csv", "text/csv")
