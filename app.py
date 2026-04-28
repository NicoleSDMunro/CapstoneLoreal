import re
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Smart Launch | Supply Chain", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background:#000; color:#f5f5f5; }
.block-container { padding-top: .25rem; max-width: 1188px; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background:#0d0d0d; border-right:1px solid #242424; }
#MainMenu, footer { visibility:hidden; }
.hero-title { font-size:34px; line-height:.92; font-weight:900; letter-spacing:-1.5px; text-transform:uppercase; margin-bottom:10px; color:#fff; white-space:nowrap; overflow:hidden; }
.hero-subtitle { color:#9ca3af; font-size:14px; margin-bottom:18px; }
.sep { height:1px; background:#202020; margin:18px 0 25px; }
.panel { background:#101010; border:1px solid #2a2a2a; border-radius:8px; padding:16px 18px; margin-bottom:14px; }
.product-panel { padding:14px 18px 12px; }
.product-panel .stSelectbox label { color:#9b9b9b !important; text-transform:uppercase; letter-spacing:1.5px; font-size:13px; font-weight:500; }
.product-panel [data-baseweb="select"] > div { background:#151515 !important; border:1px solid #333 !important; border-radius:6px !important; color:#fff !important; min-height:40px; }
.product-panel [data-baseweb="select"] span { color:#fff !important; font-weight:650; }
.struct-grid { display:grid; grid-template-columns: repeat(5,1fr); border:1px solid #2a2a2a; border-radius:8px; overflow:hidden; margin-bottom:26px; background:#101010; }
.struct-cell { padding:16px 16px 14px; min-height:96px; border-right:1px solid #2a2a2a; }
.struct-cell:last-child { border-right:none; }
.label { color:#666; font-size:13px; text-transform:uppercase; letter-spacing:1.5px; font-weight:500; }
.value { color:#fff; font-size:18px; font-weight:800; margin-top:7px; }
.sub { color:#9ca3af; font-size:13px; margin-top:7px; }
.orange { color:#e8a24a; } .red { color:#f05a5f; } .blue { color:#5b9cff; } .green { color:#1ca37e; } .yellow { color:#f4c21f; }
.tabs { display:flex; gap:26px; border-bottom:1px solid #262626; margin:22px 0 20px; }
.tab-active, .tab { padding:0 26px 14px 26px; text-transform:uppercase; letter-spacing:2px; font-size:15px; font-weight:800; }
.tab-active { color:#fff; border-bottom:4px solid #fff; }
.tab { color:#8a8a8a; }
.review-panel { background:#101010; border:1px solid #2a2a2a; border-radius:8px; padding:20px 18px 16px; margin-bottom:14px; }
.review-title { font-size:20px; font-weight:900; letter-spacing:.3px; margin-bottom:18px; }
.month-row button { height:36px; border-radius:4px !important; border:1px solid #303030 !important; background:#161616 !important; color:#a6adb8 !important; font-weight:650 !important; padding:0 !important; }
.month-row button[kind="primary"] { background: var(--accent) !important; color:#050505 !important; border-color: var(--accent) !important; }
.metric-card { min-height:112px; background:#101010; border:1px solid #2a2a2a; border-radius:6px; padding:20px 18px; }
.metric-card.danger { border-top:4px solid #ef4444; }
.metric-label { color:#5e5e5e; font-size:13px; text-transform:uppercase; letter-spacing:1.5px; font-weight:500; }
.metric-value { color:#fff; font-size:26px; font-weight:850; margin-top:12px; line-height:1.05; }
.metric-value.accent { color:var(--accent); }
.metric-delta { color:#9ca3af; font-size:14px; margin-top:8px; }
.section-title { color:#9a9a9a; text-transform:uppercase; letter-spacing:2px; font-size:15px; font-weight:500; margin:18px 0 10px; }
.chart-card { background:#101010; border:1px solid #2a2a2a; border-radius:8px; padding:8px 12px 2px; }
.alert-box,.warn-box,.success-box { border-radius:8px; padding:16px 20px; color:#fff; font-size:16px; line-height:1.5; margin-bottom:10px; }
.alert-box { background:linear-gradient(90deg,rgba(239,68,68,.22),rgba(239,68,68,.05)); border-left:6px solid #ef4444; }
.warn-box { background:linear-gradient(90deg,rgba(250,204,21,.18),rgba(250,204,21,.04)); border-left:6px solid #facc15; }
.success-box { background:linear-gradient(90deg,rgba(22,163,123,.20),rgba(22,163,123,.04)); border-left:6px solid #16a37b; }
</style>
""", unsafe_allow_html=True)

MESES=["jun/25","jul/25","ago/25","set/25","out/25","nov/25","dez/25","jan/26","fev/26","mar/26","abr/26","mai/26","jun/26"]
REVISOES=MESES[:9]; PRODUTOS=list("ABCDEFGHIJKLMNOP")
MONTH_MAP={"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,"jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}

def mes_to_period(x):
    s=str(x).strip().lower(); m=re.search(r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[\-/ ]?(\d{2,4})",s)
    if not m: return None
    ano=int(m.group(2)); ano=2000+ano if ano<100 else ano
    return pd.Period(year=ano,month=MONTH_MAP[m.group(1)],freq="M")
def period_label(p):
    inv={v:k for k,v in MONTH_MAP.items()}; return f"{inv[p.month]}/{str(p.year)[-2:]}"
def find_header_row(raw):
    for i in range(min(len(raw),30)):
        if sum(mes_to_period(v) is not None for v in raw.iloc[i].tolist())>=5: return i
    return None
def find_blocks(raw):
    blocks={}
    for i in range(len(raw)):
        text=" ".join([str(v).upper() for v in raw.iloc[i].tolist() if pd.notna(v)])
        if "PV" in text and ("SELL" in text or "SEL" in text): blocks["PV"]=i
        elif "PRODU" in text: blocks["Producao"]=i
        elif "ESTOQUE" in text: blocks["Estoque"]=i
    return blocks
def parse_product_sheet(xls,product):
    raw=pd.read_excel(xls,sheet_name=product,header=None); blocks=find_blocks(raw)
    if len(blocks)<3: raise ValueError(f"Não encontrei os 3 blocos na aba {product}.")
    out=[]; ordered=sorted(blocks.items(),key=lambda kv:kv[1])
    for idx,(var,start) in enumerate(ordered):
        end=ordered[idx+1][1] if idx+1<len(ordered) else len(raw); sub=raw.iloc[start+1:end].dropna(how="all"); hrel=find_header_row(sub.reset_index(drop=True))
        if hrel is None: continue
        header_idx=sub.index[hrel]; header=raw.iloc[header_idx]
        target_cols=[(j,mes_to_period(v)) for j,v in enumerate(header.tolist()) if mes_to_period(v) is not None]
        label_col=max(0,target_cols[0][0]-1)
        for r in range(header_idx+1,end):
            revp=mes_to_period(raw.iat[r,label_col])
            if revp is None: continue
            for j,tp in target_cols:
                val=pd.to_numeric(raw.iat[r,j],errors="coerce")
                if pd.notna(val): out.append({"Produto":product,"Variavel":var,"Revisao":period_label(revp),"Mes":period_label(tp),"Valor":float(val),"RealizadoProxy":revp==tp})
    return pd.DataFrame(out)
def parse_sheet(xls,name):
    try:
        df=pd.read_excel(xls,sheet_name=name); df.columns=[str(c).strip() for c in df.columns]; return df
    except Exception: return pd.DataFrame()
def col_like(df,keys):
    for c in df.columns:
        if all(k.lower() in str(c).lower() for k in keys): return c
    return None
def produto_info(base_df,bom_df,produto,estoque_final):
    info={"Origem":"Terceiro","CoberturaTargetDias":75,"HBdias":"-","LTSemanas":16,"Demanda":"Queda","EstoqueFinal":estoque_final}
    if not base_df.empty:
        pcol=col_like(base_df,["produto"]) or base_df.columns[0]
        row=base_df[base_df[pcol].astype(str).str.upper().str.strip().eq(produto.upper())]
        if not row.empty:
            row=row.iloc[0]
            for key,names in {"Origem":["origem"],"CoberturaTargetDias":["cobertura"],"HBdias":["hb"],"Demanda":["demanda"]}.items():
                c=col_like(base_df,names)
                if c is not None and pd.notna(row[c]): info[key]=row[c]
    if not bom_df.empty:
        pcol=col_like(bom_df,["produto"]) or bom_df.columns[0]; ltcol=col_like(bom_df,["lt"]) or col_like(bom_df,["lead"])
        if ltcol is not None:
            vals=pd.to_numeric(bom_df[bom_df[pcol].astype(str).str.upper().str.strip().eq(produto.upper())][ltcol],errors="coerce").dropna()
            if len(vals): info["LTSemanas"]=float(vals.max())
    return info
def example_long():
    rows=[]; rng=np.random.default_rng(7)
    for p in list("ABCDE"):
        mult=1-.06*(ord(p)-65)
        for ri,rev in enumerate(REVISOES):
            pv=np.array([240,230,240,430,520,460,420,300,180,230,230,250,260])*1000*mult*(1+.02*ri)
            prod=np.array([230,320,450,620,690,520,380,240,230,240,240,0,0])*1000*mult*(1+.015*ri)
            est=np.array([190,280,480,680,860,930,890,820,840,850,860,840,324])*1000*mult*(1+.01*ri)
            for var,arr in [("PV",pv),("Producao",prod),("Estoque",est)]:
                for mes,val in zip(MESES,arr): rows.append({"Produto":p,"Variavel":var,"Revisao":rev,"Mes":mes,"Valor":float(val*rng.normal(1,.025)),"RealizadoProxy":rev==mes})
    base=pd.DataFrame({"Produto":list("ABCDE"),"Origem":["Terceiro","Interno","Interno","Terceiro","Interno"],"Cobertura Target":[75,90,60,80,75],"HB":[20,25,15,20,30],"Cenário de Demanda":["Queda","Aumento","Aumento","Estável","Queda"]})
    bom=pd.DataFrame({"Produto":["A","A","B","B","C","D","E"],"Insumo":["I1","I2","I1","I3","I2","I4","I5"],"LT semanas":[16,12,8,11,18,9,10]})
    return pd.DataFrame(rows),base,bom
def format_num(v):
    v=float(v)
    if abs(v)>=1_000_000: return f"{v/1_000_000:.1f}M"
    if abs(v)>=1000: return f"{v:,.0f}".replace(",",".")
    return f"{v:.0f}"
def short_num(v):
    v=float(v)
    return f"{v/1_000_000:.1f}M" if abs(v)>=1_000_000 else f"{v/1000:.0f}k" if abs(v)>=1000 else f"{v:.0f}"
def cor_revisao(rev):
    return "#5b9cff" if str(rev).startswith("jun") else "#16a37b" if str(rev).startswith("jul") else "#e5533f" if str(rev).startswith("ago") else "#f4c21f"
def metric_card(label,value,delta="",accent=False,danger=False):
    cls="metric-card danger" if danger else "metric-card"; vcls="metric-value accent" if accent else "metric-value"
    st.markdown(f'<div class="{cls}"><div class="metric-label">{label}</div><div class="{vcls}">{value}</div><div class="metric-delta">{delta}</div></div>',unsafe_allow_html=True)

with st.sidebar:
    st.header("Base de dados")
    arquivo=st.file_uploader("Suba o Excel: Base de Dados - PUC (1).xlsx",type=["xlsx"])
    usar_exemplo=st.toggle("Usar base exemplo",value=True)

if arquivo is not None:
    xls=pd.ExcelFile(arquivo); base_df=parse_sheet(xls,"Base"); bom_df=parse_sheet(xls,"BOM")
    partes=[]
    for p in [s for s in xls.sheet_names if str(s).strip().upper() in PRODUTOS]:
        partes.append(parse_product_sheet(xls,p.strip().upper()))
    if not partes: st.error("Não consegui extrair as abas A–P."); st.stop()
    long_df=pd.concat(partes,ignore_index=True)
elif usar_exemplo:
    long_df,base_df,bom_df=example_long()
else:
    st.info("Suba sua base Excel no menu lateral ou ative a base exemplo."); st.stop()

st.markdown('<div class="hero-title">SMART LAUNCH & RESPONSIVENESS TO GROWTH</div>',unsafe_allow_html=True)
st.markdown('<div class="hero-subtitle">Produtos A–E · Jun/2025-Jun/2026</div>',unsafe_allow_html=True)
st.markdown('<div class="sep"></div>',unsafe_allow_html=True)

produtos=sorted(long_df["Produto"].unique())
base_prod_tmp=long_df[long_df["Revisao"]==REVISOES[-1]]
options=[]
for p in produtos:
    piv=long_df[(long_df["Produto"]==p)&(long_df["Revisao"]==REVISOES[-1])].pivot_table(index="Mes",columns="Variavel",values="Valor",aggfunc="sum").reindex(MESES)
    est=piv["Estoque"].dropna().iloc[-1] if "Estoque" in piv and len(piv["Estoque"].dropna()) else 0
    inf=produto_info(base_df,bom_df,p,est)
    options.append(f"Produto {p} - {inf['Origem']} - Cob.T {float(pd.to_numeric(inf['CoberturaTargetDias'],errors='coerce') or 75):.0f}d - LT {float(pd.to_numeric(inf['LTSemanas'],errors='coerce') or 16):.0f}sem - {inf['Demanda']}")

st.markdown('<div class="panel product-panel">',unsafe_allow_html=True)
sel=st.selectbox("Produto",options,index=0)
st.markdown('</div>',unsafe_allow_html=True)
produto=re.search(r"Produto ([A-P])",sel).group(1)
base_prod=long_df[long_df["Produto"]==produto]
revisoes=[m for m in REVISOES if m in set(base_prod["Revisao"])] or sorted(base_prod["Revisao"].unique())
if "revisao" not in st.session_state or st.session_state.revisao not in revisoes: st.session_state.revisao=revisoes[0]
rev=st.session_state.revisao; accent=cor_revisao(rev)
st.markdown(f"<style>:root{{--accent:{accent};}}</style>",unsafe_allow_html=True)
pivot=base_prod[base_prod["Revisao"]==rev].pivot_table(index="Mes",columns="Variavel",values="Valor",aggfunc="sum").reindex(MESES).reset_index()
est_final=pivot["Estoque"].dropna().iloc[-1] if "Estoque" in pivot and len(pivot["Estoque"].dropna()) else 0
info=produto_info(base_df,bom_df,produto,est_final)
lt_sem=float(pd.to_numeric(info["LTSemanas"],errors="coerce") if pd.notna(info["LTSemanas"]) else 16); lt_dias=int(round(lt_sem*7)); lt_meses=lt_dias/30
ct_dias=float(pd.to_numeric(info["CoberturaTargetDias"],errors="coerce") if pd.notna(info["CoberturaTargetDias"]) else 75); ct_meses=ct_dias/30; ct_sem=ct_dias/7

lt_cls="red" if lt_sem>16 else "orange" if lt_sem>10 else "green"; ct_cls="red" if lt_dias>ct_dias else "green"; dem_cls="red" if "queda" in str(info["Demanda"]).lower() else "green"; est_cls="red" if est_final<0 else ""
st.markdown('<div class="struct-grid">',unsafe_allow_html=True)
for lab,val,sub,cls in [("ORIGEM",info["Origem"],"","orange"),("LT MAX",f"{lt_sem:.0f} sem",f"aprox {lt_meses:.1f}m - {lt_dias}d",lt_cls),("COB. TARGET",f"{ct_dias:.0f}d",f"aprox {ct_meses:.1f}m - {ct_sem:.1f}sem",ct_cls),("DEMANDA",info["Demanda"],"",dem_cls),("EST. FINAL",format_num(est_final),"ultima rev - jun/26",est_cls)]:
    st.markdown(f'<div class="struct-cell"><div class="label">{lab}</div><div class="value {cls}">{val}</div><div class="sub">{sub}</div></div>',unsafe_allow_html=True)
st.markdown('</div>',unsafe_allow_html=True)

st.markdown('<div class="tabs"><div class="tab-active">VISAO POR REVISAO</div><div class="tab">FORECAST ACCURACY (VINTAGE)</div></div>',unsafe_allow_html=True)
st.markdown('<div class="review-panel">',unsafe_allow_html=True)
st.markdown(f'<div class="review-title">REVISAO: <span style="color:var(--accent)">{rev}</span></div>',unsafe_allow_html=True)
cols=st.columns(len(revisoes)+2,gap="small")
with cols[-2]:
    if st.button("<",use_container_width=True):
        i=max(0,revisoes.index(rev)-1); st.session_state.revisao=revisoes[i]; st.rerun()
with cols[-1]:
    if st.button(">",use_container_width=True):
        i=min(len(revisoes)-1,revisoes.index(rev)+1); st.session_state.revisao=revisoes[i]; st.rerun()
st.markdown('<div class="month-row">',unsafe_allow_html=True)
for i,mes in enumerate(revisoes):
    with cols[i]:
        if st.button(mes,key=f"rev_{mes}",type="primary" if mes==rev else "secondary",use_container_width=True):
            st.session_state.revisao=mes; st.rerun()
st.markdown('</div></div>',unsafe_allow_html=True)

pv_total=pivot["PV"].sum() if "PV" in pivot else 0; prev_idx=revisoes.index(rev)-1
if prev_idx>=0:
    prev=base_prod[base_prod["Revisao"]==revisoes[prev_idx]].pivot_table(index="Mes",columns="Variavel",values="Valor",aggfunc="sum").reindex(MESES)
    var_pv=(pivot.set_index("Mes")["PV"]-prev["PV"])/prev["PV"].replace(0,np.nan); meses_acima=int((var_pv.abs()>.10).sum()); delta_total=(pv_total-prev["PV"].sum())/prev["PV"].sum(); delta_txt=f"{delta_total*100:+.0f}% vs anterior"
else:
    prev=None; meses_acima=0; delta_txt="base"

c1,c2,c3,c4=st.columns(4)
with c1: metric_card("REVISAO",rev,"",accent=True)
with c2: metric_card("PV TOTAL",short_num(pv_total),delta_txt)
with c3: metric_card("MESES >10%",f"{meses_acima}m","",danger=meses_acima>=5)
with c4: metric_card("EST. FINAL",format_num(est_final),"jun/2026",danger=est_final<0)

st.markdown(f'<div class="section-title">PV - PRODUCAO - ESTOQUE - {rev.upper()}</div>',unsafe_allow_html=True)
st.markdown('<div class="chart-card">',unsafe_allow_html=True)
fig=go.Figure()
for var,color,dash,name in [("PV","#5b9cff","solid","PV (Sell In)"),("Producao","#45c49b","dash","Producao"),("Estoque","#e7895e","dot","Estoque")]:
    if var in pivot: fig.add_trace(go.Scatter(x=pivot["Mes"],y=pivot[var],mode="lines+markers",name=name,line=dict(width=3,color=color,dash=dash),marker=dict(size=7)))
if rev in MESES: fig.add_vline(x=rev,line_width=1.5,line_dash="dash",line_color="#6b7280")
fig.update_layout(paper_bgcolor="#101010",plot_bgcolor="#101010",font=dict(color="#9ca3af",size=13),height=430,margin=dict(l=30,r=18,t=18,b=35),legend=dict(orientation="h",y=-.22,x=.20,font=dict(size=14,color="#cfd4dc")),xaxis=dict(gridcolor="#202020",zerolinecolor="#202020"),yaxis=dict(gridcolor="#202020",zerolinecolor="#202020"))
st.plotly_chart(fig,use_container_width=True)
st.markdown('</div>',unsafe_allow_html=True)

st.markdown(f'<div class="section-title">CONCLUSAO - PRODUTO {produto} - {rev.upper()}</div>',unsafe_allow_html=True)
alerts=[]
if est_final<0: alerts.append(("alert-box","Ruptura projetada", "estoque final negativo em jun/26."))
if lt_dias>ct_dias: alerts.append(("alert-box","Risco estrutural",f"LT ({lt_dias}d) maior que Cobertura Target ({ct_dias:.0f}d). Demanda surpresa nao pode ser respondida a tempo."))
if meses_acima>0: alerts.append(("warn-box","Revisao instavel",f"{meses_acima} meses tiveram variacao de PV superior a 10% vs revisao anterior."))
if not alerts: alerts.append(("success-box","OK","Forecast estavel, sem alerta critico nos parametros atuais."))
for cls,t,msg in alerts: st.markdown(f'<div class="{cls}"><strong>{t}:</strong> {msg}</div>',unsafe_allow_html=True)

st.markdown('<div class="section-title">VARIACAO VS MES ANTERIOR</div>',unsafe_allow_html=True)
if prev_idx>=0 and prev is not None:
    atual=pivot.set_index("Mes")[[c for c in ["PV","Producao","Estoque"] if c in pivot]]; anterior=prev[[c for c in ["PV","Producao","Estoque"] if c in prev]]
    st.dataframe(((atual-anterior)/anterior.replace(0,np.nan)*100).round(1).reset_index(),use_container_width=True)
else:
    st.info("Revisão base: não existe mês anterior para comparar.")
with st.expander("Ver dados extraídos"):
    st.dataframe(base_prod,use_container_width=True)
