from pathlib import Path
import re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from forecasting import (
    MODELS, as_period, plabel, read_base_table, read_bom, product_meta,
    parse_pv_sheet, realized_from_matrix, model_available, forecast_model,
    build_audit, evaluated_until, choose_model, horizon_metrics,
    maturity_history, cumulative_history, critical_window_months, validate_audit,
)

st.set_page_config(page_title="Etapa 2 | Seleção Dinâmica do Modelo", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif}.stApp{background:#050505;color:#f5f5f5}
.block-container{padding-top:.5rem;padding-bottom:4rem;max-width:1240px}[data-testid="stHeader"]{background:transparent}#MainMenu,footer{visibility:hidden}
.hero-k{color:#f4c21f;font-size:12px;font-weight:800;letter-spacing:2px;text-transform:uppercase}.hero-t{font-size:34px;line-height:1.03;font-weight:900;letter-spacing:-1.2px;margin-top:7px}.hero-s{color:#9298a3;font-size:14px;max-width:920px;line-height:1.55;margin-top:9px}
.sep{height:1px;background:#222;margin:18px 0 22px}.section{color:#9ca3af;text-transform:uppercase;letter-spacing:1.8px;font-size:13px;font-weight:750;margin:25px 0 10px}
.panel,.card,.choice{background:#101010;border:1px solid #292929;border-radius:10px}.panel{padding:18px;margin-bottom:15px}.card{padding:15px;min-height:102px}.lab{color:#6f7680;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;font-weight:700}.val{color:#fff;font-size:21px;font-weight:850;margin-top:8px}.sub{color:#8f96a3;font-size:12px;margin-top:5px;line-height:1.35}
.choice{padding:24px;border-top:4px solid #f4c21f;background:linear-gradient(145deg,#171717,#0d0d0d)}.choice.bad{border-top-color:#ef6666}.choice .k{color:#8f96a3;font-size:12px;letter-spacing:1.8px;font-weight:800}.choice .m{font-size:42px;font-weight:900;letter-spacing:-1.3px;margin:8px 0}.choice.bad .m{font-size:27px}.choice .txt{color:#c5cad2;font-size:14px;line-height:1.55}.note{display:inline-block;margin-top:10px;padding:5px 10px;border:1px solid rgba(244,194,31,.45);border-radius:999px;color:#f4c21f;background:rgba(244,194,31,.07);font-size:11px;font-weight:800}
.changed{background:linear-gradient(90deg,rgba(91,156,255,.13),rgba(91,156,255,.02));border-left:5px solid #5b9cff;border-radius:8px;padding:15px 18px;margin:10px 0 16px}.changed small{color:#9ca3af}
.badge{display:inline-block;margin-top:8px;padding:4px 8px;border-radius:999px;border:1px solid rgba(69,196,155,.4);background:rgba(69,196,155,.08);color:#45c49b;font-size:11px;font-weight:800}
[data-testid="stSelectbox"] label{color:#8f96a3!important;font-weight:700!important;text-transform:uppercase;letter-spacing:1px;font-size:11px!important}[data-baseweb="select"]>div{background:#151515!important;border-color:#343434!important;color:#fff!important}
div[data-testid="stButton"] button{border:1px solid #333!important;background:#151515!important;color:#cbd1db!important;border-radius:7px!important;font-weight:750!important}div[data-testid="stButton"] button[kind="primary"]{background:#f4c21f!important;border-color:#f4c21f!important;color:#080808!important}div[data-testid="stButton"] button[kind="primary"] p{color:#080808!important}
</style>
""", unsafe_allow_html=True)

FORECAST_H=14

def short(v):
    if v is None or pd.isna(v): return "—"
    v=float(v)
    if abs(v)>=1_000_000: return f"{v/1_000_000:.1f} mi".replace(".",",")
    if abs(v)>=1_000: return f"{v/1_000:.1f} mil".replace(".",",")
    return f"{v:,.0f}".replace(",",".")

def signed(v):
    if v is None or pd.isna(v): return "—"
    return f"{float(v):+,.0f}".replace(",",".")

def card(label,value,sub=""):
    st.markdown(f'<div class="card"><div class="lab">{label}</div><div class="val">{value}</div><div class="sub">{sub}</div></div>',unsafe_allow_html=True)

def layout(fig,h=350,legend=True):
    fig.update_layout(paper_bgcolor="#101010",plot_bgcolor="#101010",font=dict(color="#9ca3af",size=12),height=h,
                      margin=dict(l=18,r=18,t=22,b=36),
                      legend=dict(orientation="h",y=-.22,x=0) if legend else dict(visible=False),
                      hoverlabel=dict(bgcolor="#171717",bordercolor="#2a2a2a",font=dict(color="#fff")))
    fig.update_xaxes(gridcolor="#202020",zerolinecolor="#202020")
    fig.update_yaxes(gridcolor="#202020",zerolinecolor="#202020")
    return fig

st.markdown('<div class="hero-k">TCC · ETAPA 2 · FORECASTING</div><div class="hero-t">COM O QUE EU SABIA NAQUELE MOMENTO,<br>QUAL MODELO EU TERIA ESCOLHIDO?</div><div class="hero-s">Cada fechamento é reconstruído sem usar informação futura. Entra um novo realizado, os erros conhecidos são atualizados, os modelos são comparados novamente e a previsão é refeita.</div><div class="sep"></div>',unsafe_allow_html=True)

DEFAULT=Path(__file__).with_name("Base de Dados - PUC (2).xlsx")
with st.sidebar:
    st.header("Base de dados")
    up=st.file_uploader("Suba a base Excel",type=["xlsx"])
    st.caption("A estrutura esperada é a mesma da base do TCC: Base, BOM e abas A–P.")
source=up if up is not None else (DEFAULT if DEFAULT.exists() else None)
if source is None:
    st.markdown('<div class="panel"><b>Envie a base Excel no menu lateral.</b><br><span style="color:#9ca3af">Assim que o arquivo for carregado, o dashboard monta automaticamente toda a Etapa 2.</span></div>',unsafe_allow_html=True)
    st.stop()

try:
    xls=pd.ExcelFile(source)
    base=read_base_table(xls); bom=read_bom(xls)
    products=sorted([str(s).strip().upper() for s in xls.sheet_names if re.fullmatch(r"[A-Pa-p]",str(s).strip())])
except Exception as e:
    st.error("Não foi possível abrir a base."); st.code(str(e)); st.stop()

product=st.selectbox("Produto",products,index=products.index("L") if "L" in products else 0)
try:
    matrix=parse_pv_sheet(xls,product)
    realized=realized_from_matrix(matrix)
    audit=build_audit(matrix,realized,FORECAST_H)
except Exception as e:
    st.error(f"Não consegui preparar a Etapa 2 para o produto {product}."); st.code(str(e)); st.stop()

meta=product_meta(base,bom,product)
critical=critical_window_months(meta)
closures=list(realized.index)
key=f"closure_{product}"
if key not in st.session_state or st.session_state[key] not in closures:
    st.session_state[key]=closures[min(3,len(closures)-1)]
closure=st.session_state[key]
known=realized[realized.index<=closure]
decision=choose_model(audit,closure)

st.markdown('<div class="section">Produto e maturidade</div>',unsafe_allow_html=True)
c=st.columns(6)
with c[0]: card("Origem",meta["origem"])
with c[1]: card("Histórico disponível",f"{len(known)} meses",f"até {plabel(closure)}")
with c[2]: card("Lead time",f'{float(meta["lt_weeks"]):.0f} sem' if pd.notna(meta["lt_weeks"]) else "—")
with c[3]: card("Cobertura target",f'{float(meta["cobertura"]):.0f} dias' if pd.notna(meta["cobertura"]) else "—")
with c[4]: card("Janela crítica",f"{critical} meses" if critical else "—","LT + cobertura + 1 mês")
with c[5]: card("Último realizado",plabel(realized.index.max()),short(realized.iloc[-1]))

st.markdown('<div class="section">Linha do tempo — fechamento mensal</div>',unsafe_allow_html=True)
l,mid,r=st.columns([1.25,8.5,1.25])
with l:
    if st.button("← MÊS ANTERIOR",use_container_width=True,disabled=closure==closures[0]):
        st.session_state[key]=closures[max(0,closures.index(closure)-1)]; st.rerun()
with r:
    if st.button("PRÓXIMO MÊS →",use_container_width=True,disabled=closure==closures[-1]):
        st.session_state[key]=closures[min(len(closures)-1,closures.index(closure)+1)]; st.rerun()
with mid:
    cc=st.columns(len(closures))
    for i,m in enumerate(closures):
        with cc[i]:
            if st.button(plabel(m),key=f"{product}_{m}",type="primary" if m==closure else "secondary",use_container_width=True):
                st.session_state[key]=m; st.rerun()

st.markdown(f'<div class="panel"><b>FECHAMENTO: {plabel(closure)}</b><br><span style="color:#9ca3af">Histórico disponível neste momento: {len(known)} meses. Tudo depois deste ponto é futuro desconhecido para a decisão.</span></div>',unsafe_allow_html=True)

st.markdown('<div class="section">1 · O que eu sabia neste mês?</div>',unsafe_allow_html=True)
future=realized[realized.index>closure]
fig=go.Figure()
fig.add_trace(go.Scatter(x=[p.to_timestamp() for p in known.index],y=known.values,mode="lines+markers",name="Realizado conhecido",line=dict(color="#f4c21f",width=3)))
if len(future):
    fig.add_trace(go.Scatter(x=[p.to_timestamp() for p in future.index],y=future.values,mode="lines+markers",name="Futuro ainda desconhecido",line=dict(color="#4b5563",width=2,dash="dot"),opacity=.65))
fig.add_vline(x=closure.to_timestamp(),line_dash="dash",line_color="#6b7280")
fig.update_yaxes(title="Demanda")
st.plotly_chart(layout(fig,330),use_container_width=True)

st.markdown('<div class="section">2 · Modelos disponíveis naquele momento</div>',unsafe_allow_html=True)
avail=[m for m in MODELS if model_available(m,len(known))]+["L'Oréal oficial"]
unavail=[m for m in MODELS if not model_available(m,len(known))]
cols=st.columns(len(avail))
req={"Naive":"1 mês","MM2":"2 meses","MM3":"3 meses","SES":"2 meses","Holt":"3 meses","L'Oréal oficial":"benchmark"}
for col,m in zip(cols,avail):
    with col:
        st.markdown(f'<div class="card"><div class="lab">{m}</div><div class="val" style="font-size:17px">DISPONÍVEL</div><div class="sub">mínimo: {req[m]}</div><span class="badge">{"benchmark" if m=="L’Oréal oficial" else "calculável"}</span></div>',unsafe_allow_html=True)
if unavail: st.caption("Ainda indisponíveis por falta de histórico: "+", ".join(unavail)+".")

st.markdown('<div class="section">3 · Modelo indicado neste fechamento</div>',unsafe_allow_html=True)
if decision["model"] is None:
    st.markdown(f'<div class="choice bad"><div class="k">MODELO INDICADO NESTE FECHAMENTO</div><div class="m">AINDA NÃO HÁ HISTÓRICO SUFICIENTE PARA COMPARAÇÃO</div><div class="txt">{decision["message"]} O dashboard não força um vencedor com apenas uma observação isolada.</div></div>',unsafe_allow_html=True)
else:
    note=f'<div class="note">{decision.get("note","")}</div>' if decision.get("note") else ""
    st.markdown(f'<div class="choice"><div class="k">MODELO INDICADO NESTE FECHAMENTO</div><div class="m">{decision["model"]}</div><div class="txt">{decision["message"]}</div>{note}</div>',unsafe_allow_html=True)

idx=closures.index(closure)
if idx>0:
    prev=closures[idx-1]; pdx=choose_model(audit,prev)
    prevm=pdx["model"] or "sem escolha"; curm=decision["model"] or "sem escolha"
    curerr=evaluated_until(audit,closure,decision["model"],1) if decision["model"] else pd.DataFrame()
    bias=curerr.erro.mean() if len(curerr) else np.nan
    f1=forecast_model(decision["model"],known.values,1) if decision["model"] else None
    phrase=f'O modelo mudou de <b>{prevm}</b> para <b>{curm}</b>.' if prevm!=curm else f'<b>{curm}</b> continua sendo o modelo selecionado.'
    st.markdown(f'<div class="changed"><b>O QUE MUDOU DESDE O ÚLTIMO FECHAMENTO?</b><br><small>Entrou o realizado de {plabel(closure)}: {short(realized.loc[closure])} un. · {phrase}<br>MAE anterior: {short(pdx.get("mae",np.nan))} · MAE atual: {short(decision.get("mae",np.nan))} · Bias atual: {signed(bias)} · Nova previsão M-1: {short(f1[0]) if f1 is not None else "—"}</small></div>',unsafe_allow_html=True)

st.markdown('<div class="section">4 · Como o modelo foi escolhido?</div>',unsafe_allow_html=True)
metrics=decision["metrics"]
if metrics.empty:
    st.info("Ainda não existem pelo menos dois modelos com erros realizados suficientes e compatíveis para uma comparação justa.")
else:
    show=metrics.sort_values("MAE").copy()
    colors=["#f4c21f" if m==decision["model"] else "#4b5563" for m in show.modelo]
    fig=go.Figure(go.Bar(x=show.MAE,y=show.modelo,orientation="h",marker_color=colors,
                         customdata=np.stack([show.Bias,show.n],axis=-1),
                         hovertemplate="MAE: %{x:,.0f}<br>Bias: %{customdata[0]:+,.0f}<br>n: %{customdata[1]:.0f}<extra></extra>"))
    fig.update_xaxes(title="MAE em observações compatíveis · menor = melhor"); fig.update_yaxes(categoryorder="total descending")
    st.plotly_chart(layout(fig,315,False),use_container_width=True)
    table=show[["modelo","MAE","Bias","n"]].rename(columns={"modelo":"Modelo","Bias":"Bias (realizado - previsto)"})
    st.dataframe(table,use_container_width=True,hide_index=True)
    st.caption("MAE é o critério principal. Bias, estabilidade entre horizontes, n e simplicidade são diagnósticos; não há score ponderado arbitrário.")

st.markdown('<div class="section">5 · Erros do modelo selecionado até este mês</div>',unsafe_allow_html=True)
if decision["model"]:
    err=evaluated_until(audit,closure,decision["model"],1).sort_values("mes_alvo")
    if len(err):
        fig=go.Figure(go.Bar(x=[p.to_timestamp() for p in err.mes_alvo],y=err.erro,marker_color=["#45c49b" if e>=0 else "#ef6666" for e in err.erro],hovertemplate="Erro: %{y:+,.0f}<extra></extra>"))
        fig.add_hline(y=0,line_color="#777",line_width=1); fig.update_yaxes(title="Erro = realizado - previsão")
        st.plotly_chart(layout(fig,290,False),use_container_width=True)
        c=st.columns(3)
        with c[0]: card("Bias acumulado",signed(err.erro.mean()),"negativo = previsão acima do realizado")
        with c[1]: card("Desvio-padrão",short(err.erro.std(ddof=1)) if len(err)>1 else "—","dos resíduos M-1")
        with c[2]: card("Resíduos disponíveis",str(len(err)),"rolling M-1")
        st.caption("Erro negativo = previsão acima do realizado. Erro positivo = previsão abaixo do realizado.")
    else: st.info("O modelo pode ser calculado, mas ainda não existe erro M-1 realizado para medi-lo.")
else: st.info("Os resíduos aparecerão quando houver histórico suficiente para selecionar um modelo.")

st.markdown('<div class="section">6 · Como a escolha do modelo mudou com o tempo?</div>',unsafe_allow_html=True)
mat=maturity_history(audit,realized)
fig=go.Figure(go.Scatter(x=[p.to_timestamp() for p in mat.fechamento],y=mat.modelo,mode="lines+markers+text",text=mat.modelo,textposition="top center",
                         line=dict(color="#5b9cff",width=2),marker=dict(size=10,color="#f4c21f"),
                         customdata=np.stack([mat.historico,mat.MAE.fillna(-1),mat.n],axis=-1),
                         hovertemplate="Histórico: %{customdata[0]:.0f} meses<br>Modelo: %{y}<br>MAE: %{customdata[1]:,.0f}<br>n: %{customdata[2]:.0f}<extra></extra>"))
fig.add_vline(x=closure.to_timestamp(),line_dash="dash",line_color="#6b7280")
st.plotly_chart(layout(fig,330,False),use_container_width=True)
st.caption("Maturidade = meses de histórico acumulados. Horizonte = quantos meses à frente tentamos prever. São conceitos diferentes.")

st.markdown('<div class="section">7 · Comparação dos modelos ao longo do tempo</div>',unsafe_allow_html=True)
hist=cumulative_history(audit,realized)
if len(hist):
    fig=px.line(hist,x=hist.fechamento.dt.to_timestamp(),y="MAE",color="modelo",markers=True,labels={"x":"Fechamento","modelo":"Modelo"})
    fig.add_vline(x=closure.to_timestamp(),line_dash="dash",line_color="#6b7280")
    st.plotly_chart(layout(fig,380),use_container_width=True)
else: st.info("O gráfico começa quando existem erros compatíveis suficientes.")

st.markdown('<div class="section">8 · Desempenho por horizonte</div>',unsafe_allow_html=True)
hm=horizon_metrics(audit,closure)
if len(hm):
    mae=hm.pivot(index="modelo",columns="horizonte",values="MAE").reindex(columns=["M-1","M-2","M-3"])
    nn=hm.pivot(index="modelo",columns="horizonte",values="n").reindex(columns=["M-1","M-2","M-3"])
    txt=mae.copy().astype(object)
    for rr in txt.index:
        for cc in txt.columns:
            v=mae.loc[rr,cc]; n=nn.loc[rr,cc] if rr in nn.index and cc in nn.columns else np.nan
            txt.loc[rr,cc]="—" if pd.isna(v) else f"{v:,.0f}<br>n={int(n)}"
    fig=go.Figure(go.Heatmap(z=mae.values,x=mae.columns,y=mae.index,text=txt.values,texttemplate="%{text}",
                             colorscale=[[0,"#173f38"],[.5,"#6b5a18"],[1,"#54262a"]],colorbar=dict(title="MAE"),
                             hovertemplate="%{y} · %{x}<br>MAE: %{z:,.0f}<extra></extra>"))
    st.plotly_chart(layout(fig,370,False),use_container_width=True)
    st.caption("n = quantidade de previsões já comparáveis com o realizado. Em cada horizonte, os modelos usam meses-alvo compatíveis. n muito baixo = amostra insuficiente para comparação robusta.")
else: st.info("Ainda não há realizado suficiente para avaliar M-1, M-2 ou M-3.")

st.markdown('<div class="section">9 · Se estivéssemos neste mês, esta seria nossa previsão</div>',unsafe_allow_html=True)
if decision["model"]:
    pred=forecast_model(decision["model"],known.values,FORECAST_H)
    fut=pd.period_range(closure+1,periods=FORECAST_H,freq="M")
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=[p.to_timestamp() for p in known.index],y=known.values,mode="lines+markers",name="Histórico realizado",line=dict(color="#f4c21f",width=3)))
    fig.add_trace(go.Scatter(x=[closure.to_timestamp()]+[p.to_timestamp() for p in fut],y=[known.iloc[-1]]+list(pred),mode="lines+markers",name=f"Previsão · {decision['model']}",line=dict(color="#5b9cff",width=3)))
    if critical: fig.add_vrect(x0=closure.to_timestamp(),x1=(closure+critical).to_timestamp(how="end"),fillcolor="#ef6666",opacity=.08,line_width=0,annotation_text="janela crítica",annotation_position="top left")
    fig.add_vrect(x0=closure.to_timestamp(),x1=fut[-1].to_timestamp(how="end"),fillcolor="#5b9cff",opacity=.035,line_width=0)
    st.plotly_chart(layout(fig,390),use_container_width=True)
    st.caption(f"O horizonte operacional mostrado é de {FORECAST_H} meses. Isso não significa que todos os horizontes longos estejam validados com a mesma robustez.")
else: st.info("Sem comparação suficiente, o dashboard não transforma um modelo em vencedor. O Naive pode servir apenas como referência operacional inicial.")

st.markdown('<div class="section">10 · Saída da Etapa 2 para a Etapa 3</div>',unsafe_allow_html=True)
if decision["model"]:
    res=evaluated_until(audit,closure,decision["model"],1).sort_values("mes_alvo")
    pred=forecast_model(decision["model"],known.values,FORECAST_H)
    c=st.columns(6)
    vals=[("Modelo selecionado",decision["model"],""),("Previsão M-1",short(pred[0]),"unidades"),("Resíduos",str(len(res)),"rolling M-1"),
          ("Bias",signed(res.erro.mean()) if len(res) else "—","média dos resíduos"),("Desvio-padrão",short(res.erro.std(ddof=1)) if len(res)>1 else "—","dos resíduos"),
          ("Janela crítica",f"{critical} meses" if critical else "—","LT + cobertura + 1")]
    for col,(la,va,su) in zip(c,vals):
        with col: card(la,va,su)
    if len(res): st.caption(f"Período dos resíduos: {plabel(res.mes_alvo.min())} a {plabel(res.mes_alvo.max())}. Essas informações são a saída da Etapa 2 para a simulação estocástica da Etapa 3. Este dashboard não calcula estoque, excesso, gatilhos ou Monte Carlo.")
else: st.info("A saída para a Etapa 3 só é consolidada quando existe uma seleção baseada em erros realizados.")

with st.expander("Regra de seleção e tabela de auditoria"):
    st.markdown("""
**Regra explícita**
1. Cada origem usa somente realizados disponíveis até aquele fechamento.
2. Naive usa o último realizado; MM2 os 2 anteriores; MM3 os 3 anteriores; SES e Holt são reajustados em cada origem.
3. Um erro só entra depois que o realizado do mês-alvo existe.
4. A seleção usa MAE em observações compatíveis entre os modelos elegíveis, nos horizontes M-1 a M-3.
5. É preciso haver pelo menos 2 erros compatíveis e 2 modelos comparáveis. Caso contrário, não há vencedor.
6. Quando a amostra é pequena e os MAEs estão praticamente empatados (até 5%), vale a parcimônia: o modelo mais simples entre os empatados é preferido.
7. A previsão oficial L'Oréal é benchmark, não candidato automático à seleção.
""")
    view=audit[audit.origem_previsao<=closure].copy().sort_values(["origem_previsao","modelo","horizonte"])
    view["fechamento"]=view.fechamento.map(plabel); view["origem_previsao"]=view.origem_previsao.map(plabel); view["mes_alvo"]=view.mes_alvo.map(plabel)
    view=view[["fechamento","modelo","origem_previsao","horizonte","mes_alvo","previsto","realizado","erro"]]
    st.dataframe(view,use_container_width=True,hide_index=True)
    st.download_button("Baixar auditoria (.csv)",view.to_csv(index=False).encode("utf-8-sig"),file_name=f"auditoria_etapa2_{product}.csv",mime="text/csv")

checks=validate_audit(audit,realized); ok=all(checks.values())
st.markdown(f'<div class="panel"><b>Validação automática: <span style="color:{"#45c49b" if ok else "#ef6666"}">{"OK" if ok else "REVISAR"}</span></b><br><span style="color:#9ca3af">'+" · ".join([f"{k}: {'✓' if v else '✕'}" for k,v in checks.items()])+'</span></div>',unsafe_allow_html=True)
