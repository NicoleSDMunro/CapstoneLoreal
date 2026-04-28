import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="Capstone L'Oréal | Dashboard Supply Chain",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --bg: #050505;
    --panel: #111111;
    --panel-2: #151515;
    --border: #262626;
    --muted: #8b8b8b;
    --text: #f6f6f6;
    --red: #ef4444;
    --orange: #c47a1c;
    --green: #16a37b;
}

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: radial-gradient(circle at top, #171717 0%, #050505 45%, #000 100%); color: var(--text); }
.block-container { padding-top: 1.3rem; max-width: 1120px; }
[data-testid="stSidebar"] { background: #0f0f0f; border-right: 1px solid #242424; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

.hero-title { font-size: 48px; font-weight: 800; margin-bottom: 2px; letter-spacing: -1px; }
.hero-subtitle { color: #a6a6a6; font-size: 16px; margin-bottom: 22px; }
.phone-frame {
    background: #030303;
    border: 1px solid #2a2a2a;
    border-radius: 28px;
    padding: 28px;
    box-shadow: 0 30px 80px rgba(0,0,0,.55), inset 0 0 0 1px rgba(255,255,255,.03);
}
.top-panel {
    background: #121212;
    border: 1px solid #292929;
    border-radius: 16px;
    padding: 22px 26px;
    margin-bottom: 24px;
}
.review-title { font-size: 23px; font-weight: 800; letter-spacing: .2px; margin-bottom: 18px; }
.review-accent { color: var(--accent); }
.month-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.month-pill {
    border: 1px solid #292929;
    background: #171717;
    color: #777;
    border-radius: 7px;
    padding: 11px 22px;
    font-size: 16px;
    font-weight: 500;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.02);
}
.month-pill.active {
    color: #060606;
    background: var(--accent);
    border-color: var(--accent);
    font-weight: 800;
}
.metric-card {
    min-height: 124px;
    background: linear-gradient(180deg, #171717 0%, #101010 100%);
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 22px 24px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.05), 0 12px 28px rgba(0,0,0,.25);
}
.metric-card.danger { border-top: 4px solid #ef4444; }
.metric-label { color: #696969; font-size: 14px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600; }
.metric-value { color: #fff; font-size: 33px; font-weight: 800; margin-top: 10px; line-height: 1.05; }
.metric-value.accent { color: var(--accent); }
.metric-delta { color: #8f8f8f; font-size: 14px; margin-top: 8px; line-height: 1.35; }
.section-title { color: #8f8f8f; text-transform: uppercase; letter-spacing: 2.2px; font-size: 16px; font-weight: 600; margin: 28px 0 12px; }
.chart-card {
    background: #121212;
    border: 1px solid #262626;
    border-radius: 16px;
    padding: 10px 14px 2px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
}
.alert-box {
    background: linear-gradient(90deg, rgba(239,68,68,.25), rgba(239,68,68,.06));
    border-left: 7px solid #ff4d4d;
    border-radius: 12px;
    padding: 22px 26px;
    color: #fff;
    font-size: 20px;
    line-height: 1.55;
}
.success-box {
    background: linear-gradient(90deg, rgba(22,163,123,.25), rgba(22,163,123,.06));
    border-left: 7px solid #16a37b;
    border-radius: 12px;
    padding: 22px 26px;
    color: #fff;
    font-size: 20px;
    line-height: 1.55;
}
.stSelectbox label, .stFileUploader label, .stToggle label { color: #d5d5d5 !important; font-weight: 600; }
hr { border-color: #222; }
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
            fator = {"jul/25": .94, "ago/25": 1, "set/25": 1.05}.get(revisao, 1)
            if produto == "Produto B": fator *= .72
            for mes, pv, prod, est in zip(MESES, base_pv, base_prod, base_est):
                dados.append({"Produto": produto, "Revisao": revisao, "Mes": mes, "PV": int(pv*fator*rng.normal(1,.04)), "Producao": int(prod*fator*rng.normal(1,.05)), "Estoque": int(est*fator*rng.normal(1,.06)), "LeadTimeDias": 112, "CoberturaTargetDias": 75})
    return pd.DataFrame(dados)


def ler_arquivo(arquivo):
    return pd.read_csv(arquivo) if arquivo.name.lower().endswith(".csv") else pd.read_excel(arquivo)


def normalizar_colunas(df):
    mapa = {c.lower().strip(): c for c in df.columns}
    rename = {}
    for chave, nome in {"produto":"Produto","revisao":"Revisao","mes":"Mes","pv":"PV","producao":"Producao","estoque":"Estoque"}.items():
        if chave in mapa: rename[mapa[chave]] = nome
    return df.rename(columns=rename)


def format_numero(valor):
    valor = float(valor)
    if abs(valor) >= 1_000_000: return f"{valor/1_000_000:.1f}M"
    if abs(valor) >= 1_000: return f"{valor/1_000:.0f}k"
    return f"{valor:,.0f}"


def cor_revisao(rev):
    if str(rev).startswith("jul"): return "#16a37b"
    if str(rev).startswith("ago"): return "#e5533f"
    return "#c47a1c"


def card(label, value, delta="", accent=False, danger=False):
    cls = "metric-card danger" if danger else "metric-card"
    value_cls = "metric-value accent" if accent else "metric-value"
    st.markdown(f"""
    <div class="{cls}">
        <div class="metric-label">{label}</div>
        <div class="{value_cls}">{value}</div>
        <div class="metric-delta">{delta}</div>
    </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.header("Base de dados")
    arquivo = st.file_uploader("Envie um Excel ou CSV", type=["xlsx", "csv"])
    usar_exemplo = st.toggle("Usar base exemplo", value=True)
    st.caption("Colunas: Produto, Revisao, Mes, PV, Producao, Estoque, LeadTimeDias, CoberturaTargetDias.")

if arquivo is not None:
    df = ler_arquivo(arquivo)
elif usar_exemplo:
    df = exemplo_base()
else:
    st.info("Envie uma base ou ative a base exemplo.")
    st.stop()

df = normalizar_colunas(df)
faltantes = [c for c in ["Produto", "Revisao", "Mes", "PV", "Producao", "Estoque"] if c not in df.columns]
if faltantes:
    st.error(f"A base não possui: {', '.join(faltantes)}")
    st.stop()

for c in ["PV", "Producao", "Estoque"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
if "LeadTimeDias" not in df.columns: df["LeadTimeDias"] = 112
if "CoberturaTargetDias" not in df.columns: df["CoberturaTargetDias"] = 75

st.markdown('<div class="hero-title">Capstone L’Oréal</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-subtitle">Dashboard interativo de revisão, PV/Sell In, produção, estoque e risco de cobertura.</div>', unsafe_allow_html=True)

produtos = sorted(df["Produto"].dropna().unique())
revisoes = list(df["Revisao"].dropna().unique())

f1, f2 = st.columns([1, 1])
with f1:
    produto = st.selectbox("Produto", produtos)
with f2:
    revisao = st.selectbox("Revisão", revisoes, index=len(revisoes)-1 if revisoes else 0)

base = df[(df["Produto"] == produto) & (df["Revisao"] == revisao)].copy()
if base.empty:
    st.warning("Não há dados para os filtros selecionados.")
    st.stop()

accent = cor_revisao(revisao)
st.markdown(f"<style>:root{{--accent:{accent};}}</style>", unsafe_allow_html=True)

pv_total = base["PV"].sum()
estoque_final = base["Estoque"].iloc[-1]
lt = int(base["LeadTimeDias"].iloc[0])
ct = int(base["CoberturaTargetDias"].iloc[0])
variacao = base["PV"].pct_change().fillna(0)
meses_acima_10 = int((variacao.abs() > .10).sum())
delta_texto = f"{variacao.iloc[-1]*100:+.0f}% vs anterior" if len(base) > 1 else ""

st.markdown('<div class="phone-frame">', unsafe_allow_html=True)
st.markdown(f"""
<div class="top-panel">
    <div class="review-title">REVISAO: <span class="review-accent">{revisao}</span></div>
    <div class="month-grid">
        {''.join([f'<div class="month-pill {"active" if m == revisao else ""}">{m}</div>' for m in MESES[:9]])}
    </div>
</div>
""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
with c1: card("REVISAO", revisao, "", accent=True)
with c2: card("PV TOTAL", format_numero(pv_total), delta_texto)
with c3: card("MESES >10%", f"{meses_acima_10}m", "", accent=False, danger=True)
with c4: card("EST. FINAL", format_numero(estoque_final), str(base["Mes"].iloc[-1]))

st.markdown(f'<div class="section-title">PV - PRODUCAO - ESTOQUE - {str(revisao).upper()}</div>', unsafe_allow_html=True)
st.markdown('<div class="chart-card">', unsafe_allow_html=True)
fig = go.Figure()
fig.add_trace(go.Scatter(x=base["Mes"], y=base["PV"], mode="lines+markers", name="PV (Sell In)", line=dict(width=4, color="#5aa2ff"), marker=dict(size=8)))
fig.add_trace(go.Scatter(x=base["Mes"], y=base["Producao"], mode="lines+markers", name="Producao", line=dict(width=4, dash="dash", color="#3fc69b"), marker=dict(size=8)))
fig.add_trace(go.Scatter(x=base["Mes"], y=base["Estoque"], mode="lines+markers", name="Estoque", line=dict(width=4, dash="dot", color="#e9855b"), marker=dict(size=8)))
fig.update_layout(
    paper_bgcolor="#121212", plot_bgcolor="#121212", font=dict(color="#8f8f8f", size=14), height=540,
    margin=dict(l=35, r=25, t=30, b=40), legend=dict(orientation="h", y=-0.18, x=.18, font=dict(size=15, color="#d0d0d0")),
    xaxis=dict(gridcolor="#242424", zerolinecolor="#242424"), yaxis=dict(gridcolor="#242424", zerolinecolor="#242424")
)
st.plotly_chart(fig, use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown(f'<div class="section-title">CONCLUSAO - {produto.upper()} - {str(revisao).upper()}</div>', unsafe_allow_html=True)
if lt > ct:
    st.markdown(f'<div class="alert-box"><strong>Risco estrutural:</strong> LT ({lt}d) maior que Cobertura Target ({ct}d). Demanda surpresa não pode ser respondida a tempo.</div>', unsafe_allow_html=True)
elif estoque_final < pv_total / max(len(base), 1) * .5:
    st.markdown('<div class="alert-box"><strong>Risco de ruptura:</strong> estoque final baixo em relação à média de PV do período.</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="success-box"><strong>Situação controlada:</strong> estoque e cobertura não indicam risco crítico nos parâmetros atuais.</div>', unsafe_allow_html=True)

st.markdown(f'<div class="section-title">VARIACAO VS MES ANTERIOR</div>', unsafe_allow_html=True)
with st.expander("Ver base filtrada e baixar modelo"):
    st.dataframe(base, use_container_width=True)
    modelo = exemplo_base().head(20)
    csv = modelo.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV exemplo", csv, "modelo_capstone_loreal.csv", "text/csv")

st.markdown('</div>', unsafe_allow_html=True)
