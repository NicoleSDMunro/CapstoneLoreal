"""Smart Launch — painel operacional. Dados carregados somente na sessão (sem salvar arquivos)."""
import io
import math
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import openpyxl
from smartlaunch_monthly import evaluate_models
import hashlib

st.set_page_config(page_title="Smart Launch | L'Oréal", page_icon="📦", layout="wide")
st.markdown("""<style>
 .stApp{background:#f6f7f9;color:#17202a}
[data-testid="stMetric"]{background:#ffffff;border:1px solid #dce2e8;padding:14px;border-radius:10px}
h1,h2,h3{letter-spacing:-.03em}
div[data-testid="stAlert"]{border-radius:8px}
</style>""",unsafe_allow_html=True)

MONTHS={"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,"jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}
NAMES={v:k for k,v in MONTHS.items()}
MODEL={"P1":"MEA-P","P2":"MEA","P3":"Oficial"}
ANALOG={"P1":["BENCH A_1","BENCH B_1"],"P2":["BENCH C_2"],"P3":["BENCH D_3","BENCH E_3"]}
SHEETS={"P1":"PRODUTO 1","P2":"PRODUTO 2","P3":"PRODUTO 3"}
SEED=20261021
N=1000
LIM=180

def period(v):
    if isinstance(v,pd.Period): return v
    if isinstance(v,pd.Timestamp): return v.to_period("M")
    s=str(v).strip().lower()
    m=re.match(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s*[/ -]\s*(20\d{2}|\d{2})$",s)
    if not m:return None
    y=int(m.group(2))
    return pd.Period(year=2000+y if y<100 else y,month=MONTHS[m.group(1)],freq="M")

def label(p):
    return f"{NAMES[p.month]}/{str(p.year)[-2:]}"

def parse_blocks(ws):
    """Layout original: títulos PV / PRODUÇÃO / ESTOQUE e linha Mes/Ano antes de cada triângulo."""
    blocks={}; kind=None; header={}
    for row in ws.iter_rows(values_only=True):
        first=row[0] if row else None
        p=period(first)
        if isinstance(first,str) and p is None:
            s=first.strip().upper()
            if "ESTOQUE" in s:kind="EST"
            elif "PRODU" in s:kind="PROD"
            elif s.startswith("PV"):kind="PV"
            if kind and ("ESTOQUE" in s or "PRODU" in s or s.startswith("PV")):
                blocks.setdefault(kind,{})
            if s=="MES/ANO":
                parsed={j:period(x) for j,x in enumerate(row) if period(x) is not None}
                # A linha seguinte também se chama Mes/Ano, mas traz descrições.
                # Não apagar os meses do cabeçalho válido.
                if parsed: header=parsed
            continue
        if p is not None and kind and header:
            blocks[kind][p]={m:float(row[j] or 0) for j,m in header.items() if j<len(row) and isinstance(row[j],(int,float))}
    return {key:pd.DataFrame.from_dict(v,orient="index").sort_index() for key,v in blocks.items()}

def read_base(wb):
    if "Base" not in wb.sheetnames:raise ValueError('Arquivo incompatível: falta a aba "Base". Envie o Triangulo_Produtos_V2.xlsx da metodologia final, não a base antiga A–P.')
    rows=list(wb["Base"].values)
    for row in rows:
        cells=[str(x).strip().lower() if x is not None else "" for x in row]
        if "produto" in cells and any("cobertura" in x for x in cells):
            ip=cells.index("produto")
            ic=next(i for i,x in enumerate(cells) if "cobertura" in x)
            il=next((i for i,x in enumerate(cells) if "lt" in x),None)
            if il is None:continue
            result={}
            for r in rows[rows.index(row)+1:]:
                raw=str(r[ip]).strip() if ip<len(r) else ""
                key="P"+raw.replace("P","").replace(".0","")
                if key in MODEL and isinstance(r[ic],(float,int)) and isinstance(r[il],(float,int)):
                    result[key]=(float(r[ic]),float(r[il]))
            if result:return result
    raise ValueError("Não foi possível encontrar LT e cobertura por produto na aba Base.")

def load_data(content):
    wb=openpyxl.load_workbook(io.BytesIO(content),read_only=True,data_only=True)
    missing=[s for s in list(SHEETS.values())+sorted(set(sum(ANALOG.values(),[]))) if s not in wb.sheetnames]
    if missing:raise ValueError("A planilha não é o Triangulo_Produtos_V2.xlsx do TCC final. Abas ausentes: "+", ".join(missing)+". Não use a Base de Dados - PUC (2).xlsx antiga (A–P).")
    base=read_base(wb)
    missingbase=[p for p in MODEL if p not in base]
    if missingbase:raise ValueError("Sem LT/cobertura na aba Base: "+", ".join(missingbase))
    blocks={s:parse_blocks(wb[s]) for s in list(SHEETS.values())+sorted(set(sum(ANALOG.values(),[])))}
    for p,s in SHEETS.items():
        if any(k not in blocks[s] for k in ("PV","PROD","EST")):
            raise ValueError(f"{s}: são necessários os blocos PV, PRODUÇÃO e ESTOQUE.")
    wb.close()
    return base,blocks

def known(pv,c):
    """Realizado m = valor da coluna m na revisão m+1 (conhecido no fechamento c)."""
    vals={}
    for m in pv.columns:
        if m<=c and m+1 in pv.index:
            x=pv.loc[m+1,m]
            if pd.notna(x):vals[m]=float(x)
    s=pd.Series(vals,dtype=float).sort_index()
    suspect=pd.Period("2025-09",freq="M")
    if suspect in s and s[suspect]==0 and suspect-1 in s and suspect+1 in s:
        s[suspect]=(s[suspect-1]+s[suspect+1])/2
    pos=s[s>0]
    return s[s.index>=pos.index[0]] if not pos.empty else pd.Series(dtype=float)

def analog_series(blocks,c):
    return {b:known(blocks[b]["PV"],c) for b in set(sum(ANALOG.values(),[]))}

def pipe_index(blocks,c):
    ix=[]
    for b,s in analog_series(blocks,c).items():
        a=np.log10(s.to_numpy(float)) if len(s) and (s>0).all() else np.array([])
        if len(a)>=6:ix.append(a[:3]-a[3:].mean())
    if not ix:raise ValueError("São necessários benchmarks com pelo menos 6 vendas conhecidas para estimar o pipe.")
    return np.mean(ix,axis=0)

def forecast(p,months,c,blocks,model=None):
    model=model or MODEL[p]
    sheet=SHEETS[p]; own=known(blocks[sheet]["PV"],c)
    historical=known(blocks[sheet]["PV"],max(blocks[sheet]["PV"].index))
    start=historical.index.min() if not historical.empty else None
    if start is None or pd.isna(start):raise ValueError(f"{p}: sem venda realizada.")
    if model=="Naive":
        if own.empty:raise ValueError(f"{p}: Naive exige vendas conhecidas.")
        return np.repeat(float(own.iloc[-1]),len(months))
    if model=="Oficial":
        pv=blocks[sheet]["PV"]
        v=c+1
        if v not in pv.index:raise ValueError(f"Não existe revisão {label(v)} para {p}.")
        return np.array([float(pv.loc[v,m]) if m in pv.columns and pd.notna(pv.loc[v,m]) else np.nan for m in months])
    benches=ANALOG[p]
    if model=="MEA-P":indexes=pipe_index(blocks,c)
    else:indexes=np.zeros(3)
    ys=np.log10(own.to_numpy(float)) if len(own) and (own>0).all() else np.array([])
    ys=ys.copy()
    ys[:min(3,len(ys))]-=indexes[:min(3,len(ys))]
    levels=[]
    cutoff=min(c,start-1)
    for b in benches:
        s=known(blocks[b]["PV"],cutoff)
        if len(s)==0 or (s<=0).any():continue
        bs=np.log10(s.to_numpy(float))
        bs[:min(3,len(bs))]-=indexes[:min(3,len(bs))]
        levels.append(np.concatenate([bs,ys]).mean())
    if not levels:raise ValueError(f"{p}: benchmark insuficiente para {model}.")
    level=np.mean(levels)
    return np.array([10**(level+(indexes[(m-start).n] if 0<=(m-start).n<3 else 0)) for m in months])

def history_errors(p,c,blocks,model=None):
    """Backtest mensal h=1..3 somente com alvos realizados e origens passadas.
    Sacola de arranque (origens com 3 a 5 meses conhecidos), como no piloto."""
    pv=blocks[SHEETS[p]]["PV"]
    last=known(pv,c)
    if last.empty:return np.array([]),0
    start=last.index.min()
    rows=[]
    for n in (3,4,5):
        origin=start+n-1
        if origin>=c:continue
        months=[origin+h for h in (1,2,3)]
        try:fc=forecast(p,months,origin,blocks,model=model)
        except (ValueError,KeyError):continue
        for m,f in zip(months,fc):
            if m in last.index and np.isfinite(f):
                rows.append(float(last.loc[m])-float(f))
    return np.asarray(rows,dtype=float),len(rows)

def coverage(e,dm):
    """Forward cover, 30 dias/mês; extrapolação após último mês pela última demanda."""
    out=np.zeros_like(e)
    n,h=e.shape
    for j in range(h):
        stock=e[:,j].copy()
        days=np.zeros(n)
        active=stock>0
        future=np.concatenate([dm[:,j+1:],np.maximum(dm[:,-1:],1e-9)],axis=1)
        for k in range(future.shape[1]):
            d=np.maximum(future[:,k],1e-9)
            partial=active & (stock<=d)
            days[partial]+=30*stock[partial]/d[partial]
            active[partial]=False
            days[active]+=30
            stock[active]-=d[active]
        if active.any():
            days[active]+=30*stock[active]/np.maximum(dm[active,-1],1e-9)
        out[:,j]=days
    return out

def balance(e0,plan,dm):
    n,h=dm.shape
    stock=np.empty_like(dm);lost=np.empty_like(dm)
    e=np.full(n,float(e0))
    for j in range(h):
        avail=np.maximum(e+plan[j],0)
        lost[:,j]=np.maximum(dm[:,j]-avail,0)
        e=np.maximum(avail-dm[:,j],0)
        stock[:,j]=e
    return stock,lost,coverage(stock,dm)

def simulate(p,c,blocks,base,method="Normal (0, s)",persistent=False,operational_model=None):
    sheet=SHEETS[p]
    b=blocks[sheet]
    review=c+1
    pv=b["PV"]
    months=[m for m in sorted(pv.columns) if m>c and m in b["PROD"].columns]
    if review not in b["PROD"].index or review not in b["EST"].index:
        raise ValueError(f"Sem produção/estoque na revisão {label(review)}.")
    if c not in b["EST"].columns:raise ValueError("Sem estoque inicial no fechamento.")
    if not months:raise ValueError("Não existem meses futuros nesta revisão.")
    production=np.array([float(b["PROD"].loc[review,m]) for m in months])
    e0=float(b["EST"].loc[review,c])
    center=forecast(p,months,c,blocks,model=operational_model)
    if not np.isfinite(center).all():raise ValueError("Faltam previsões centrais na revisão.")
    errors,num=history_errors(p,c,blocks,model=operational_model)
    if num<2:raise ValueError(f"Apenas {num} erros de arranque conhecidos. Simulação indisponível (mínimo 2).")
    sd=float(np.std(errors,ddof=1))
    rng=np.random.default_rng(SEED+int(p[1:])*1000+c.ordinal)
    if method=="Normal (0, s)":
        eps=rng.normal(0,sd,(N,1 if persistent else len(months)))
    else:
        eps=rng.choice(errors,size=(N,1 if persistent else len(months)),replace=True)-errors.mean()
    if persistent:eps=np.repeat(eps,len(months),axis=1)
    dm=np.maximum(center+eps,0)
    stock,lost,cov=balance(e0,production,dm)
    days,lt=base[p];ltm=math.ceil(lt*7/30);window=ltm+math.ceil(days/30)+1
    active=np.array([j<window for j in range(len(months))])
    return dict(months=months,production=production,e0=e0,center=center,errors=errors,sd=sd,dm=dm,stock=stock,lost=lost,cov=cov,active=active,ltm=ltm,window=window)

def impacts(res,p,new_plan,baseline):
    s,l,c=balance(res["e0"],new_plan,res["dm"])
    win=res["active"]
    return dict(excesso=float((c[:,win]>=LIM).any(axis=1).mean()),ruptura=float((l[:,win]>0).any(axis=1).mean()),
                delta_excesso=float((c[:,win]>=LIM).any(axis=1).mean()-baseline["excesso"]),
                delta_ruptura=float((l[:,win]>0).any(axis=1).mean()-baseline["ruptura"]))

def fmt(n):return f"{n:,.0f}".replace(",",".")


# A interface é separada dos cálculos: dados -> previsão -> cenários -> riscos -> ação.
st.title("SMART LAUNCH")
st.caption("L'Oréal | Inteligência de abastecimento para novos lançamentos")
st.caption("Versão 2026.11.11 · Modelos reavaliados mensalmente · Dados só na sessão")

with st.sidebar:
    st.markdown("### Smart Launch")
    st.caption("Um fechamento por vez. Sem usar informação futura.")
    st.divider()
    st.caption("**Modelos inicialmente aprovados**")
    st.write("P1 · MEA-P")
    st.write("P2 · MEA (provisório)")
    st.write("P3 · Oficial")
    st.caption("1.000 cenários · Normal(0,s) · 180 dias")
    st.divider()
    st.caption("Dados empresariais: evite hospedagem pública sem controle de acesso.")

# Iniciar na visão geral, mas oferecer a atualização em uma área dedicada.
tab_overview, tab_models, tab_decisions, tab_data, tab_method = st.tabs(
    ["📊 Visão geral", "📈 Modelos", "🎛️ Decisões", "📥 Atualização mensal", "📚 Metodologia e histórico"]
)
file = st.session_state.get("triangulo_file_bytes")
file_label = st.session_state.get("triangulo_file_name","")
with tab_data:
    st.subheader("1 · Atualização mensal")
    st.write("Carregue uma versão atualizada do triângulo. Escolha o produto e o fechamento; o sistema utiliza a revisão do mês seguinte.")
    uploaded=st.file_uploader("Arquivo Excel — Triangulo Produtos V2.xlsx",type=["xlsx"],key="triangulo_upload")
    if uploaded is not None:
        candidate=uploaded.getvalue()
        if candidate != st.session_state.get("triangulo_file_bytes"):
            st.session_state["triangulo_file_bytes"]=candidate
            st.session_state["triangulo_file_name"]=uploaded.name
            st.session_state.pop("smartlaunch_review",None)
        file=candidate
        file_label=uploaded.name
    if file is not None:
        st.success(f"Arquivo carregado na sessão: {file_label} · {len(file)/1024:.0f} KB")
    else:
        st.info("Nenhum arquivo carregado. Após selecionar o Excel, a visão geral será preenchida.")
with tab_overview:
    if file is None:
        st.info("Para começar: abra **📥 Atualização de dados**, carregue o triângulo e selecione um fechamento.")
with tab_models:
    if file is None:
        st.info("Carregue a planilha para reavaliar os modelos no fechamento selecionado.")
with tab_decisions:
    if file is None:
        st.info("Primeiro, carregue o triângulo na aba **Atualização de dados**.")
with tab_method:
    st.subheader("Como o painel decide")
    st.markdown("""
    **Fluxo:** validar dados → prever demanda → simular 1.000 cenários → calcular estoque/cobertura → detectar alertas → testar ações.

    - **Reavaliação mensal:** comparar MEA-P, MEA, Oficial e Naive em pares comuns origem/alvo (h1–h3). O ranking complementar deve ser homologado com o protocolo e a lista definitiva do notebook antes do uso empresarial. A troca operacional requer aprovação explícita.
    - **Incerteza padrão:** erro aditivo Normal(0, desvio-padrão amostral dos erros do arranque); demanda limitada a zero.
    - **Estoque:** \`max(0, estoque anterior + produção − demanda)\`. A venda que não couber no estoque é perdida.
    - **Cobertura:** forward cover, consumindo a demanda dos próximos meses; após a última projeção, repete-se o último mês.
    - **Excesso:** P97,5 da cobertura ≥ 180 dias. **Ruptura:** P97,5 da venda perdida > 0.
    - **Janela crítica:** \`ceil(LT em semanas × 7/30) + ceil(cobertura-alvo/30) + 1\` mês.
    - **Ações em lotes:** testes teóricos com lead time; contratos, lotes mínimos e disponibilidade não estão modelados.
    """)
    st.warning("A simulação usa poucos erros de previsões sobrepostas. As probabilidades não são garantias nem equivalem a intervalos estatísticos calibrados.")
    st.caption("Método de previsão, risco e gatilhos: TCC Smart Launch, novembro/2026. A apresentação em quatro áreas é uma decisão de interface.")

if file is None:
    st.stop()

try:
    base,blocks=load_data(file)
except Exception as exc:
    with tab_data:
        st.error(f"Não foi possível ler o arquivo: {exc}")
        st.caption("Esperado: Base, PRODUTO 1–3, BENCH A_1, BENCH B_1, BENCH C_2, BENCH D_3, BENCH E_3.")
    st.stop()

# Auditoria exibida antes do processamento, para facilitar erros de cada revisão.
with tab_data:
    checks=[]
    for pkey,sheet_name in SHEETS.items():
        b=blocks.get(sheet_name,{})
        indices={k:set(b[k].index) if k in b else set() for k in ("PV","PROD","EST")}
        intersection=set.intersection(*indices.values())
        checks.append({"Produto":pkey,"Vendas (revisões)":len(indices["PV"]),
                       "Produção (revisões)":len(indices["PROD"]),
                       "Estoque (revisões)":len(indices["EST"]),
                       "Revisões compatíveis":len(intersection)})
    st.markdown("#### Auditoria do triângulo")
    st.dataframe(pd.DataFrame(checks),hide_index=True,use_container_width=True)
    if any(row["Revisões compatíveis"] == 0 for row in checks):
        st.warning("A leitura encontrou revisões vazias. Confira a versão r5 acima; o processamento desta versão não usa cache.")

controls=st.columns([1,2])
with controls[0]:
    p=st.selectbox("Produto",list(MODEL),format_func=lambda x:f"{x} · {MODEL[x]}",key="smartlaunch_product")
sheet=SHEETS[p]
data=blocks[sheet]
revlist=sorted(set(data["PV"].index)&set(data["PROD"].index)&set(data["EST"].index))
if not revlist:
    with tab_data:
        st.error(f"Não há revisões compatíveis para {p}. Examine a auditoria acima.")
    st.stop()
with controls[1]:
    # Só revisões com estoque de fechamento na coluna anterior e meses futuros no plano.
    validrevs=[r for r in revlist if r-1 in data["EST"].columns and any(m>r-1 for m in data["PV"].columns)]
    options=validrevs or revlist
    if "smartlaunch_review" in st.session_state and st.session_state["smartlaunch_review"] not in options:
        del st.session_state["smartlaunch_review"]
    review=st.selectbox("Revisão do plano (fechamento do mês anterior)",options,index=len(options)-1,
                        format_func=label,key="smartlaunch_review")
c=review-1

with tab_data:
    d1,d2,d3=st.columns(3)
    d1.metric("Produto",p)
    d2.metric("Fechamento",label(c))
    d3.metric("Revisão utilizada",label(review))
    st.caption("A revisão selecionada deve ter realizado conhecido até o mês anterior. Nenhum arquivo foi enviado ao repositório.")
    st.info("Histórico de uploads e aprovações é mantido somente nesta sessão. Reabra o Excel histórico para reprocessar outra competência; persistência segura depende de infraestrutura privada.")
    with st.expander("Histórico de vendas conhecido neste fechamento"):
        st.dataframe(pd.DataFrame({"Mês":[label(m) for m in known(data["PV"],c).index],
                                   "Vendido":known(data["PV"],c).to_numpy()}),hide_index=True,use_container_width=True)

with tab_method:
    st.markdown("#### Parâmetros do produto")
    target,ltweeks=base[p]
    months_lt=math.ceil(ltweeks*7/30)
    critical=months_lt+math.ceil(target/30)+1
    st.write(f"{p}: lead time = {ltweeks:g} semanas ({months_lt} meses arredondados), cobertura-alvo = {target:g} dias; janela crítica = {critical} meses.")
    st.markdown("#### Sensibilidades — não mudam o modelo central")
    sim_method=st.selectbox("Distribuição dos erros",["Normal (0, s)","Bootstrap centralizado"],key="sim_method")
    sim_persistent=st.checkbox("Mesmo erro persistente entre meses",value=False,key="sim_persistent")

# A comparação usa apenas alvos realizados até o fechamento selecionado.
detail,ranking,winner=evaluate_models(p,c,blocks,forecast,known)
key="operational_"+p
if key not in st.session_state:
    st.session_state[key]=MODEL[p]
operational=st.session_state[key]
with tab_models:
    st.subheader("Modelos · comparação mensal")
    st.caption(f"Produto {p} · fechamento {label(c)} · todos os candidatos nos mesmos pares origem/alvo e horizontes h1–h3.")
    a,b,d=st.columns(3)
    a.metric("Modelo operacional",operational)
    b.metric("Melhor no teste mensal",winner or "Não elegível")
    d.metric("Modelos comparados",len(ranking))
    if ranking.empty:
        st.warning("Sem previsões históricas comparáveis; mantenha o modelo operacional.")
    else:
        st.dataframe(ranking,hide_index=True,use_container_width=True)
        st.caption("Elegibilidade mínima operacional desta versão: ≥3 previsões em ≥2 origens; critério complementar ainda não homologado com o notebook final. MEA-P/MEA/Oficial/Naive são um subconjunto dos modelos do TCC.")
        if not detail.empty:
            plot=go.Figure()
            for name,group in detail.groupby("Modelo"):
                g=group.groupby("Origem",as_index=False)["APE"].mean()
                plot.add_trace(go.Scatter(x=g["Origem"],y=g["APE"],mode="lines+markers",name=name))
            plot.update_layout(height=300,yaxis_title="MAPE por origem (%)",margin=dict(l=10,r=10,t=12,b=10))
            st.plotly_chart(plot,use_container_width=True)
    if winner and winner!=operational:
        st.warning(f"Novo vencedor experimental: {winner}. O modelo operacional continua {operational} até sua aprovação.")
        if st.button(f"Aprovar {winner} para {p}",key="approve_model_"+p):
            st.session_state[key]=winner
            st.session_state.setdefault("model_approvals",[]).append({"Produto":p,"Fechamento":label(c),"Anterior":operational,"Aprovado":winner})
            st.rerun()
    if operational!=MODEL[p] and st.button("Restaurar modelo inicial do TCC",key="restore_"+p):
        st.session_state[key]=MODEL[p]
        st.rerun()
    st.info("Aprovação nesta versão vale apenas durante a sessão atual. Para uso corporativo, implementar autenticação, permissões e histórico durável.")
with tab_method:
    st.markdown("#### Histórico de aprovações nesta sessão")
    approvals=st.session_state.get("model_approvals",[])
    if approvals:st.dataframe(pd.DataFrame(approvals),hide_index=True,use_container_width=True)
    else:st.caption("Nenhuma mudança aprovada nesta sessão.")

# Recalcular cenários no fechamento: toda ação compara a mesma sacola de 1.000 trajetórias.
try:
    result=simulate(p,c,blocks,base,sim_method,sim_persistent,operational_model=operational)
    issue=None
except Exception as exc:
    result=None
    issue=str(exc)

if result is None:
    with tab_overview:
        st.warning(f"Há previsão, mas a simulação não está disponível neste fechamento: {issue}")
        try:
            future=[m for m in sorted(data["PV"].columns) if m>c]
            estimates=forecast(p,future,c,blocks,model=operational)
            st.dataframe(pd.DataFrame({"Mês":[label(m) for m in future],
                                       "Previsão (un.)":np.round(estimates)}),
                         hide_index=True,use_container_width=True)
        except Exception as err:
            st.error(f"Não foi possível gerar previsão: {err}")
    with tab_decisions:
        st.warning("Sem cenários probabilísticos suficientes, não é possível comparar alternativas de lotes.")
    st.stop()

res=result
labs=[label(m) for m in res["months"]]
q=lambda v:np.percentile(v,[2.5,50,97.5],axis=0)
demand=q(res["dm"])
stock=q(res["stock"])
cover=q(res["cov"])
ex=(res["cov"]>=LIM).mean(axis=0)
rupt=(res["lost"]>0).mean(axis=0)
active=res["active"]
ltm=res["ltm"]
baseline=impacts(res,p,res["production"],{"excesso":0,"ruptura":0})
action_records=[]
for j,m in enumerate(res["months"]):
    triggers=bool(active[j] and (ex[j]>.025 or rupt[j]>.025))
    supplier_ex=any(k>=ltm and k<=j and res["production"][k]>0 for k in range(len(res["months"])))
    if not triggers:
        response="Monitorar"
    elif ex[j]>.025:
        response="Fornecedor" if supplier_ex else "Comercial"
    else:
        response="Fornecedor" if supplier_ex else "Monitorar / alocar"
    action_records.append({
        "Mês":label(m),"Demanda prevista":round(res["center"][j]),
        "Demanda P2,5":round(demand[0,j]),"Demanda P97,5":round(demand[2,j]),
        "Estoque P50":round(stock[1,j]),"Cobertura P50 (dias)":round(cover[1,j]),
        "Excesso (%)":round(100*float(ex[j]),1),"Ruptura (%)":round(100*float(rupt[j]),1),
        "Janela crítica":"Sim" if active[j] else "Não","Encaminhamento":response})
monthly=pd.DataFrame(action_records)
risk_months=monthly[(monthly["Janela crítica"]=="Sim") & ((monthly["Excesso (%)"]>2.5)|(monthly["Ruptura (%)"]>2.5))]
with tab_overview:
    st.markdown("#### 2–4 · Previsão, risco e prioridades")
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Modelo de previsão",operational)
    m2.metric("Estoque inicial",fmt(res["e0"])+" un.")
    m3.metric("Meses com gatilho",len(risk_months))
    m4.metric("Erros conhecidos",len(res["errors"]))
    if p=="P2":
        st.warning("P2: modelo MEA provisório. A validação no arranque tem amostra insuficiente.")
    if risk_months.empty:
        st.success("Não há gatilhos na janela crítica para o fechamento selecionado.")
    else:
        primary=risk_months.iloc[0]
        st.warning(f"Primeiro gatilho: {primary['Mês']} · excesso {primary['Excesso (%)']:.1f}% · ruptura {primary['Ruptura (%)']:.1f}% · encaminhamento: {primary['Encaminhamento']}.")
    st.caption(f"Fechamento {label(c)} · revisão {label(review)} · janela crítica {res['window']} meses · Normal(0,s) por padrão")
    st.markdown("#### Demanda prevista e incerteza")
    figure=go.Figure()
    figure.add_trace(go.Scatter(x=labs,y=demand[2],mode="lines",line=dict(width=0),hoverinfo="skip",showlegend=False))
    figure.add_trace(go.Scatter(x=labs,y=demand[0],mode="lines",line=dict(width=0),fill="tonexty",fillcolor="rgba(239,157,75,0.18)",name="Faixa P2,5–P97,5"))
    figure.add_trace(go.Scatter(x=labs,y=res["center"],mode="lines+markers",name=f"Previsão {operational}",line=dict(color="#f2aa58",width=3)))
    figure.add_trace(go.Scatter(x=labs,y=demand[1],mode="lines",name="P50 cenários",line=dict(color="#d0d0d0",dash="dot")))
    figure.update_layout(template="plotly_white",height=320,margin=dict(l=12,r=12,b=20,t=15))
    st.plotly_chart(figure,use_container_width=True)
    st.markdown("#### Riscos e encaminhamento por mês")
    display_cols=["Mês","Demanda prevista","Estoque P50","Cobertura P50 (dias)","Excesso (%)","Ruptura (%)","Janela crítica","Encaminhamento"]
    st.dataframe(monthly[display_cols],hide_index=True,use_container_width=True)
    st.caption("Gatilhos usam o percentil 97,5; a probabilidade é a fração dos 1.000 cenários. Alertas são apoio à decisão, não previsões certas.")

with tab_decisions:
    st.subheader("5–6 · Alternativas de abastecimento e plano de ação")
    st.write(f"Fechamento: **{label(c)}** · Produto: **{p}** · Lead time arredondado: **{ltm} meses**")
    st.caption("Só lotes fora do lead time são elegíveis pelo critério temporal. A possibilidade contratual de alteração deve ser validada com a L'Oréal.")
    batches=[]
    for j,m in enumerate(res["months"]):
        vol=res["production"][j]
        if vol<=0:continue
        batches.append({"Mês":label(m),"Volume (un.)":round(vol),"Prazo teórico":label(m-ltm),
                        "Disponível pelo LT":"Sim" if j>=ltm else "Não"})
    if batches:
        st.dataframe(pd.DataFrame(batches),hide_index=True,use_container_width=True)
    else:
        st.info("Nenhum lote de produção futura identificado nesta revisão.")
    possible=[j for j,v in enumerate(res["production"]) if v>0 and j>=ltm]
    if not possible:
        st.warning("Nenhum lote elegível ao ajuste pelo lead time neste fechamento. Avaliar ações comerciais ou monitoramento.")
    else:
        chosen=st.selectbox("Escolha o lote a avaliar",possible,
                            format_func=lambda j:f"{label(res['months'][j])} · {fmt(res['production'][j])} unidades",
                            key="chosen_batch")
        variations={"Manter":0,"Reduzir 25%":-0.25,"Reduzir 50%":-0.5,"Cancelar":-1.0,
                    "Aumentar 25%":0.25,"Adiar 1 mês":"adiar","Antecipar 1 mês":"antecipar"}
        comparison=[]
        for action,modifier in variations.items():
            plan=res["production"].copy()
            if modifier=="adiar":
                if chosen+1>=len(plan):continue
                plan[chosen+1]+=plan[chosen]
                plan[chosen]=0
            elif modifier=="antecipar":
                if chosen-1<ltm:continue
                plan[chosen-1]+=plan[chosen]
                plan[chosen]=0
            else:plan[chosen]*=(1+modifier)
            metrics=impacts(res,p,plan,baseline)
            comparison.append({"Alternativa":action,"Risco de excesso":f"{metrics['excesso']:.1%}",
                               "Risco de ruptura":f"{metrics['ruptura']:.1%}",
                               "Δ excesso (p.p.)":round(metrics["delta_excesso"]*100,1),
                               "Δ ruptura (p.p.)":round(metrics["delta_ruptura"]*100,1)})
        st.markdown("#### Comparação com o plano atual")
        st.dataframe(pd.DataFrame(comparison),hide_index=True,use_container_width=True)
        st.caption("Comparação com os mesmos cenários em toda alternativa. Resultados em toda a janela crítica, não apenas no mês selecionado.")
        st.markdown("#### Explorar ajustes de 5 em 5%")
        adjustment=st.slider("Ajuste no volume do lote",min_value=-100,max_value=100,value=0,step=5,format="%d%%")
        alternative=res["production"].copy()
        alternative[chosen]*=1+adjustment/100
        compare=impacts(res,p,alternative,baseline)
        c1,c2=st.columns(2)
        c1.metric("Excesso na janela",f"{compare['excesso']:.1%}",delta=f"{compare['delta_excesso']*100:+.1f} p.p.",delta_color="inverse")
        c2.metric("Ruptura na janela",f"{compare['ruptura']:.1%}",delta=f"{compare['delta_ruptura']*100:+.1f} p.p.",delta_color="inverse")
        st.caption("Não significa corte ótimo nem autorização para modificar a ordem. Confirme capacidade, contratos e lote mínimo.")
    st.markdown("#### Encaminhamentos indicados pelos gatilhos")
    if risk_months.empty:st.info("Nenhum encaminhamento emergencial detectado.")
    else:st.dataframe(risk_months[["Mês","Excesso (%)","Ruptura (%)","Encaminhamento"]],hide_index=True,use_container_width=True)
    st.warning("A ferramenta não decide pelo planejador. Registre a decisão e confirme com Supply Planning, Comercial e fornecedores, conforme o caso.")

with tab_method:
    st.markdown("#### Auditoria estatística")
    st.write(f"Erros disponíveis no fechamento: {len(res['errors'])}; desvio-padrão: {fmt(res['sd'])} unidades; viés amostral: {fmt(np.mean(res['errors']))} unidades.")
    st.caption("O viés é mostrado, mas não aplicado como correção automática à previsão.")
    with st.expander("Ver sacola de erros"):
        st.dataframe(pd.DataFrame({"Erro (un.)":res["errors"]}),hide_index=True,use_container_width=True)
    st.markdown("#### Exportação")
    st.download_button("Exportar análise mensal (CSV)",monthly.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"smartlaunch_{p}_{label(c).replace('/','-')}.csv",mime="text/csv")
