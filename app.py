import re
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Capstone L'Oréal | Rolling Forecast", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: radial-gradient(circle at top, #17202b 0%, #060606 45%, #000 100%); color: #f6f6f6; }
.block-container { padding-top: 1.4rem; max-width: 1180px; }
[data-testid="stSidebar"] { background: #101010; border-right: 1px solid #262626; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.hero-title { font-size: 46px; font-weight: 800; letter-spacing: -1px; margin-bottom: 4px; }
.hero-subtitle { color: #a9a9a9; font-size: 16px; margin-bottom: 18px; }
.phone-frame { background:#030303; border:1px solid #2a2a2a; border-radius:28px; padding:26px; box-shadow:0 30px 80px rgba(0,0,0,.55), inset 0 0 0 1px rgba(255,255,255,.03); }
.product-card, .top-panel, .chart-card { background:#121212; border:1px solid #292929; border-radius:16px; padding:20px 24px; box-shadow: inset 0 1px 0 rgba(255,255,255,.04); }
.product-grid { display:grid; grid-template-columns: repeat(5, 1fr); gap:12px; }
.small-label { color:#727272; font-size:12px; text-transform:uppercase; letter-spacing:1.3px; font-weight:700; }
.small-value { color:#fff; font-size:22px; font-weight:800; margin-top:6px; }
.good { color:#16a37b; } .warn { color:#facc15; } .bad { color:#ef4444; }
.review-title { font-size:23px; font-weight:800; margin-bottom:18px; } .review-accent { color: var(--accent); }
.month-row button { border-radius:8px !important; border:1px solid #343434 !important; background:#171717 !important; color:#d6d6d6 !important; font-weight:700 !important; }
.month-row button[kind="primary"] { background: var(--accent) !important; color:#050505 !important; border-color: var(--accent) !important; }
.metric-card { min-height:124px; background:linear-gradient(180deg,#171717,#101010); border:1px solid #2a2a2a; border-radius:12px; padding:22px 24px; box-shadow: inset 0 1px 0 rgba(255,255,255,.05), 0 12px 28px rgba(0,0,0,.25); }
.metric-card.danger { border-top:4px solid #ef4444; }
.metric-label { color:#737373; font-size:13px; text-transform:uppercase; letter-spacing:1.5px; font-weight:700; }
.metric-value { color:#fff; font-size:32px; font-weight:800; margin-top:10px; line-height:1.05; }
.metric-value.accent { color: var(--accent); }
.metric-delta { color:#8f8f8f; font-size:14px; margin-top:8px; line-height:1.35; }
.section-title { color:#8f8f8f; text-transform:uppercase; letter-spacing:2.2px; font-size:16px; font-weight:700; margin:28px 0 12px; }
.alert-box { background:linear-gradient(90deg,rgba(239,68,68,.25),rgba(239,68,68,.06)); border-left:7px solid #ff4d4d; border-radius:12px; padding:20px 24px; color:#fff; font-size:18px; line-height:1.55; margin-bottom:10px; }
.warn-box { background:linear-gradient(90deg,rgba(250,204,21,.20),rgba(250,204,21,.05)); border-left:7px solid #facc15; border-radius:12px; padding:20px 24px; color:#fff; font-size:18px; line-height:1.55; margin-bottom:10px; }
.success-box { background:linear-gradient(90deg,rgba(22,163,123,.25),rgba(22,163,123,.06)); border-left:7px solid #16a37b; border-radius:12px; padding:20px 24px; color:#fff; font-size:18px; line-height:1.55; margin-bottom:10px; }
</style>
""", unsafe_allow_html=True)

MESES = ["jun/25","jul/25","ago/25","set/25","out/25","nov/25","dez/25","jan/26","fev/26","mar/26","abr/26","mai/26","jun/26"]
REVISOES = MESES[:9]
PRODUTOS = list("ABCDEFGHIJKLMNOP")
MONTH_MAP = {"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,"jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}


def mes_to_period(x):
    s = str(x).strip().lower()
    m = re.search(r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[\-/ ]?(\d{2,4})", s)
    if not m: return None
    ano = int(m.group(2)); ano = 2000 + ano if ano < 100 else ano
    return pd.Period(year=ano, month=MONTH_MAP[m.group(1)], freq="M")


def period_label(p):
    inv = {v:k for k,v in MONTH_MAP.items()}
    return f"{inv[p.month]}/{str(p.year)[-2:]}"


def find_header_row(raw):
    for i in range(min(len(raw), 30)):
        vals = [mes_to_period(v) for v in raw.iloc[i].tolist()]
        if sum(v is not None for v in vals) >= 5:
            return i
    return None


def find_blocks(raw):
    blocks = {}
    for i in range(len(raw)):
        text = " ".join([str(v).upper() for v in raw.iloc[i].tolist() if pd.notna(v)])
        if "PV" in text and ("SELL" in text or "SEL" in text): blocks["PV"] = i
        elif "PRODU" in text: blocks["Producao"] = i
        elif "ESTOQUE" in text: blocks["Estoque"] = i
    return blocks


def parse_product_sheet(xls, product):
    raw = pd.read_excel(xls, sheet_name=product, header=None)
    blocks = find_blocks(raw)
    if len(blocks) < 3:
        raise ValueError(f"Não encontrei os 3 blocos PV, Produção e Estoque na aba {product}.")
    long_parts = []
    ordered = sorted(blocks.items(), key=lambda kv: kv[1])
    for idx, (var, start) in enumerate(ordered):
        end = ordered[idx+1][1] if idx+1 < len(ordered) else len(raw)
        sub = raw.iloc[start+1:end].dropna(how="all")
        hrel = find_header_row(sub.reset_index(drop=True))
        if hrel is None: continue
        header_idx = sub.index[hrel]
        header = raw.iloc[header_idx]
        target_cols = [(j, mes_to_period(v)) for j, v in enumerate(header.tolist()) if mes_to_period(v) is not None]
        label_col = max(0, target_cols[0][0]-1)
        for r in range(header_idx+1, end):
            rev_p = mes_to_period(raw.iat[r, label_col])
            if rev_p is None: continue
            for j, targ_p in target_cols:
                val = pd.to_numeric(raw.iat[r, j], errors="coerce")
                if pd.notna(val):
                    long_parts.append({"Produto": product, "Variavel": var, "Revisao": period_label(rev_p), "Mes": period_label(targ_p), "Valor": float(val), "RealizadoProxy": rev_p == targ_p})
    return pd.DataFrame(long_parts)


def parse_base_sheet(xls):
    try:
        base = pd.read_excel(xls, sheet_name="Base")
    except Exception:
        return pd.DataFrame()
    base.columns = [str(c).strip() for c in base.columns]
    return base


def parse_bom_sheet(xls):
    try:
        bom = pd.read_excel(xls, sheet_name="BOM")
    except Exception:
        return pd.DataFrame()
    bom.columns = [str(c).strip() for c in bom.columns]
    return bom


def col_like(df, keys):
    for c in df.columns:
        s = str(c).lower()
        if all(k.lower() in s for k in keys): return c
    return None


def produto_info(base_df, bom_df, produto, estoque_final):
    info = {"Origem":"-", "CoberturaTargetDias":75, "HBdias":"-", "LTSemanas":16, "Demanda":"-", "EstoqueFinal":estoque_final}
    if not base_df.empty:
        pcol = col_like(base_df, ["produto"]) or base_df.columns[0]
        row = base_df[base_df[pcol].astype(str).str.upper().str.strip().eq(produto.upper())]
        if not row.empty:
            row = row.iloc[0]
            for key, names in {"Origem":["origem"], "CoberturaTargetDias":["cobertura"], "HBdias":["hb"], "Demanda":["demanda"]}.items():
                c = col_like(base_df, names)
                if c is not None and pd.notna(row[c]): info[key] = row[c]
    if not bom_df.empty:
        pcol = col_like(bom_df, ["produto"]) or bom_df.columns[0]
        ltcol = col_like(bom_df, ["lt"]) or col_like(bom_df, ["lead"])
        if ltcol is not None:
            rows = bom_df[bom_df[pcol].astype(str).str.upper().str.strip().eq(produto.upper())]
            vals = pd.to_numeric(rows[ltcol], errors="coerce").dropna()
            if len(vals): info["LTSemanas"] = float(vals.max())
    return info


def example_long():
    rows=[]; rng=np.random.default_rng(7)
    for p in list("ABCDE"):
        mult = 1 - .06*(ord(p)-65)
        for rev_i, rev in enumerate(REVISOES):
            pv = np.array([300,250,260,450,520,470,360,330,180,340,290,280,450])*1000*mult*(1+.035*rev_i)
            prod = np.array([310,260,390,680,700,370,210,450,270,350,410,380,240])*1000*mult*(1+.02*rev_i)
            est = np.array([200,180,330,570,760,650,500,630,720,730,850,970,740])*1000*mult*(1+.04*rev_i)
            for var, arr in [("PV",pv),("Producao",prod),("Estoque",est)]:
                for mes, val in zip(MESES, arr):
                    rows.append({"Produto":p,"Variavel":var,"Revisao":rev,"Mes":mes,"Valor":float(val*rng.normal(1,.04)),"RealizadoProxy":rev==mes})
    base = pd.DataFrame({"Produto":list("ABCDE"),"Origem":["Interno","Terceiro","Interno","Terceiro","Interno"],"Cobertura Target":[75,90,60,80,75],"HB":[20,25,15,20,30],"Cenário de Demanda":["Aumento","Queda","Aumento","Estável","Queda"]})
    bom = pd.DataFrame({"Produto":["A","A","B","B","C","D","E"],"Insumo":["I1","I2","I1","I3","I2","I4","I5"],"LT semanas":[16,12,8,11,18,9,10]})
    return pd.DataFrame(rows), base, bom


def format_num(v):
    v=float(v)
    if abs(v)>=1_000_000: return f"{v/1_000_000:.1f}M"
    if abs(v)>=1_000: return f"{v/1_000:.0f}k"
    return f"{v:.0f}"


def cor_revisao(rev):
    return "#16a37b" if str(rev).startswith("jul") else "#e5533f" if str(rev).startswith("ago") else "#f4c21f"


def metric_card(label, value, delta="", accent=False, danger=False):
    cls = "metric-card danger" if danger else "metric-card"
    vcls = "metric-value accent" if accent else "metric-value"
    st.markdown(f'<div class="{cls}"><div class="metric-label">{label}</div><div class="{vcls}">{value}</div><div class="metric-delta">{delta}</div></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Base de dados")
    arquivo = st.file_uploader("Suba o Excel: Base de Dados - PUC (1).xlsx", type=["xlsx"])
    usar_exemplo = st.toggle("Usar base exemplo", value=True)
    st.caption("O app lê as abas Base, BOM e as abas dos produtos A–P com matrizes de rolling forecast.")

if arquivo is not None:
    xls = pd.ExcelFile(arquivo)
    base_df, bom_df = parse_base_sheet(xls), parse_bom_sheet(xls)
    produtos_disponiveis = [s for s in xls.sheet_names if str(s).strip().upper() in PRODUTOS]
    partes=[]
    erros=[]
    for p in produtos_disponiveis:
        try: partes.append(parse_product_sheet(xls, p.strip().upper()))
        except Exception as e: erros.append(str(e))
    if not partes:
        st.error("Não consegui extrair as abas de produto. Verifique se existem abas A até P com os blocos PV, Produção e Estoque.")
        if erros: st.code("\n".join(erros[:5]))
        st.stop()
    long_df = pd.concat(partes, ignore_index=True)
elif usar_exemplo:
    long_df, base_df, bom_df = example_long()
else:
    st.info("Suba sua base Excel no menu lateral ou ative a base exemplo.")
    st.stop()

st.markdown('<div class="hero-title">Capstone L’Oréal</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-subtitle">Smart Launch & Responsiveness to Growth — análise exploratória de rolling forecast e supply chain.</div>', unsafe_allow_html=True)

produtos = sorted(long_df["Produto"].unique())
produto = st.selectbox("Produto", produtos)
revisoes = [m for m in REVISOES if m in set(long_df[long_df["Produto"]==produto]["Revisao"])] or sorted(long_df[long_df["Produto"]==produto]["Revisao"].unique())
if "revisao" not in st.session_state or st.session_state.revisao not in revisoes:
    st.session_state.revisao = revisoes[-1]

base_prod = long_df[long_df["Produto"]==produto]
rev = st.session_state.revisao
accent = cor_revisao(rev)
st.markdown(f"<style>:root{{--accent:{accent};}}</style>", unsafe_allow_html=True)

pivot = base_prod[base_prod["Revisao"]==rev].pivot_table(index="Mes", columns="Variavel", values="Valor", aggfunc="sum").reindex(MESES).reset_index()
estoque_final = pivot["Estoque"].dropna().iloc[-1] if "Estoque" in pivot and len(pivot["Estoque"].dropna()) else 0
info = produto_info(base_df, bom_df, produto, estoque_final)
lt_sem = float(pd.to_numeric(info["LTSemanas"], errors="coerce") if pd.notna(info["LTSemanas"]) else 16)
lt_dias = int(round(lt_sem*7)); lt_meses = lt_dias/30
ct_dias = float(pd.to_numeric(info["CoberturaTargetDias"], errors="coerce") if pd.notna(info["CoberturaTargetDias"]) else 75)

st.markdown('<div class="product-card"><div class="product-grid">', unsafe_allow_html=True)
lt_class = "bad" if lt_sem > 16 else "warn" if lt_sem > 10 else "good"
ct_class = "bad" if lt_dias > ct_dias else "good"
est_class = "bad" if estoque_final < 0 else "good"
for label, val, cls in [("Origem", info["Origem"], ""),("LT máx insumo", f"{lt_sem:.0f} sem | {lt_meses:.1f}m | {lt_dias}d", lt_class),("Cobertura Target", f"{ct_dias:.0f}d", ct_class),("Demanda projetada", info["Demanda"], ""),("Estoque final proj.", format_num(estoque_final), est_class)]:
    st.markdown(f'<div><div class="small-label">{label}</div><div class="small-value {cls}">{val}</div></div>', unsafe_allow_html=True)
st.markdown('</div></div>', unsafe_allow_html=True)

st.markdown('<div class="phone-frame">', unsafe_allow_html=True)
st.markdown(f'<div class="top-panel"><div class="review-title">REVISAO: <span class="review-accent">{rev}</span></div>', unsafe_allow_html=True)
cols = st.columns(len(revisoes), gap="small")
st.markdown('<div class="month-row">', unsafe_allow_html=True)
for i, mes in enumerate(revisoes):
    with cols[i]:
        if st.button(mes, key=f"rev_{mes}", type="primary" if mes == rev else "secondary", use_container_width=True):
            st.session_state.revisao = mes
            st.rerun()
st.markdown('</div></div>', unsafe_allow_html=True)

pv_total = pivot["PV"].sum() if "PV" in pivot else 0
prev_idx = revisoes.index(rev)-1 if rev in revisoes else -1
if prev_idx >= 0:
    prev = base_prod[base_prod["Revisao"]==revisoes[prev_idx]].pivot_table(index="Mes", columns="Variavel", values="Valor", aggfunc="sum").reindex(MESES)
    var_pv = (pivot.set_index("Mes")["PV"] - prev["PV"]) / prev["PV"].replace(0, np.nan)
    meses_acima = int((var_pv.abs() > .10).sum())
    delta_total = (pv_total - prev["PV"].sum()) / prev["PV"].sum()
    delta_txt = f"{delta_total*100:+.0f}% vs anterior"
else:
    var_pv = pd.Series(dtype=float); meses_acima = 0; delta_txt = "Revisão base"

c1,c2,c3,c4 = st.columns(4)
with c1: metric_card("REVISÃO", rev, "", accent=True)
with c2: metric_card("PV TOTAL", format_num(pv_total), delta_txt)
with c3: metric_card("MESES >10%", f"{meses_acima}m", "Volatilidade do PV", danger=meses_acima>=5)
with c4: metric_card("EST. FINAL", format_num(estoque_final), MESES[-1], danger=estoque_final<0)

st.markdown(f'<div class="section-title">PV - PRODUCAO - ESTOQUE - {rev.upper()}</div>', unsafe_allow_html=True)
st.markdown('<div class="chart-card">', unsafe_allow_html=True)
fig = go.Figure()
for var, color, dash, name in [("PV","#5aa2ff","solid","PV (Sell In)"),("Producao","#3fc69b","dash","Produção"),("Estoque","#e9855b","dot","Estoque")]:
    if var in pivot:
        fig.add_trace(go.Scatter(x=pivot["Mes"], y=pivot[var], mode="lines+markers", name=name, line=dict(width=4, color=color, dash=dash), marker=dict(size=8)))
if rev in MESES:
    fig.add_vline(x=rev, line_width=2, line_dash="dash", line_color="#6b7280")
fig.update_layout(paper_bgcolor="#121212", plot_bgcolor="#121212", font=dict(color="#8f8f8f", size=14), height=530, margin=dict(l=35,r=25,t=30,b=40), legend=dict(orientation="h", y=-.18, x=.18, font=dict(size=15,color="#d0d0d0")), xaxis=dict(gridcolor="#242424"), yaxis=dict(gridcolor="#242424"))
st.plotly_chart(fig, use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown(f'<div class="section-title">CONCLUSOES AUTOMATICAS - PRODUTO {produto} - {rev.upper()}</div>', unsafe_allow_html=True)
alerts=[]
if estoque_final < 0: alerts.append(("alert-box", "Ruptura projetada", "estoque final negativo em jun/26."))
if lt_dias > ct_dias: alerts.append(("alert-box", "Risco estrutural", f"LT ({lt_dias}d) maior que Cobertura Target ({ct_dias:.0f}d)."))
if "Producao" in pivot and "PV" in pivot and ((pivot["Producao"].fillna(0)==0) & (pivot["PV"].fillna(0)>0)).any(): alerts.append(("alert-box", "Produção zerada com PV positivo", "há demanda planejada sem produção associada."))
if meses_acima > 0: alerts.append(("warn-box", "Revisão instável", f"{meses_acima} meses tiveram variação de PV superior a 10% vs revisão anterior."))
if not alerts: alerts.append(("success-box", "OK", "Forecast estável, sem alerta crítico nos parâmetros atuais."))
for cls,title,msg in alerts:
    st.markdown(f'<div class="{cls}"><strong>{title}:</strong> {msg}</div>', unsafe_allow_html=True)

st.markdown('<div class="section-title">TABELA DE VARIACAO VS REVISAO ANTERIOR</div>', unsafe_allow_html=True)
if prev_idx >= 0:
    atual = pivot.set_index("Mes")[[c for c in ["PV","Producao","Estoque"] if c in pivot]]
    anterior = prev[[c for c in ["PV","Producao","Estoque"] if c in prev]]
    tab = ((atual - anterior) / anterior.replace(0, np.nan) * 100).round(1).reset_index()
    st.dataframe(tab, use_container_width=True)
else:
    st.info("Revisão base: não existe mês anterior para comparar.")

with st.expander("Ver dados extraídos"):
    st.dataframe(base_prod, use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)
