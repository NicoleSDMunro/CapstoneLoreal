"""Motor analítico Smart Launch: extraído da aplicação anterior sem alteração das regras."""
import io
import math
import re
import zlib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import openpyxl
from smartlaunch_monthly import evaluate_models


MONTHS={"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,"jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}
NAMES={v:k for k,v in MONTHS.items()}
MODEL={"P1":"MEA-P","P2":"MEA","P3":"Oficial"}
ANALOG={"P1":["BENCH A_1","BENCH B_1"],"P2":["BENCH C_2"],"P3":["BENCH D_3","BENCH E_3"]}
SHEETS={"P1":"PRODUTO 1","P2":"PRODUTO 2","P3":"PRODUTO 3"}
SEED=20261021
N=1000
LIM=180
# O ZIP do TCC usa dois níveis distintos: aviso e alerta para tomada de decisão.
AVISO=0.025
ALERTA=0.20
# Margem aproximada de simulação Monte Carlo com 1.000 trajetórias; não mede
# incerteza total do modelo.
MARGEM_MC=0.025
AUMENTO_MAX_RUPTURA=0.025
CHAVE_SORTEIO={"MEA-P":"3C-P · 3C com índice de pipe","MEA":"3C","Oficial":"Oficial"}


def nivel(p):
    """Separa alerta (>20%), aviso (>2,5%) e não avaliado."""
    if p is None or not np.isfinite(p):
        return "não avaliado"
    return "alerta" if p>ALERTA else "aviso" if p>AVISO else "—"


def chance_txt(p):
    """Exibe chances simuladas sem casas decimais excessivamente precisas."""
    if p is None or not np.isfinite(p):
        return "não avaliado"
    v=100*p
    if v<1: return "< 1%"
    if v>99: return "> 99%"
    return f"{v:.0f}%"

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

def discover_products(wb):
    """Descobre todos os SKUs pelo nome das abas; mantém as escolhas históricas P1–P3."""
    discovered = {}
    for sheet in wb.sheetnames:
        match = re.fullmatch(r"PRODUTO\s+(\d+)", sheet.strip(), flags=re.IGNORECASE)
        if match:
            product = "P" + str(int(match.group(1)))
            discovered[product] = sheet
    if not discovered:
        raise ValueError("Nenhuma aba PRODUTO N encontrada na planilha.")
    ordered = sorted(discovered, key=lambda p: int(p[1:]))
    new_analog = {}
    for product in ordered:
        suffix = product[1:]
        new_analog[product] = sorted(
            name for name in wb.sheetnames
            if re.fullmatch(r"BENCH\s+.+_" + re.escape(suffix), name.strip(), flags=re.IGNORECASE)
        )
    previous_models = dict(MODEL)
    SHEETS.clear()
    SHEETS.update({p: discovered[p] for p in ordered})
    ANALOG.clear()
    ANALOG.update(new_analog)
    MODEL.clear()
    MODEL.update({p: previous_models.get(p, "MEA" if new_analog[p] else "Oficial")
                  for p in ordered})


def load_data(content):
    wb=openpyxl.load_workbook(io.BytesIO(content),read_only=True,data_only=True)
    discover_products(wb)
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
    # A MEA-P histórica foi calibrada com os benchmarks dos três produtos
    # originais. Adicionar novos SKUs não pode alterar retroativamente o pipe.
    reference = set(sum((ANALOG.get(p, []) for p in ("P1","P2","P3")), []))
    if not reference:
        reference = set(sum(ANALOG.values(), []))
    return {b:known(blocks[b]["PV"],c) for b in reference}

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
    """Forward cover com 30 dias/mês; último mês é não avaliado.

    Conforme o ZIP ajustado, a cobertura final exige ao menos um mês
    de demanda futura dentro do horizonte; NaN não é risco zero.
    """
    out=np.full(e.shape,np.nan)
    n,h=e.shape
    for j in range(h-1):
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
    # Mesmo esquema de sorteio do notebook: seed + CRC32 de
    # produto, fechamento e nome interno do modelo, por mês.
    model_used=operational_model or MODEL[p]
    chave=f"{p}{c}{CHAVE_SORTEIO.get(model_used,model_used)}est"
    rng=np.random.default_rng(SEED+zlib.crc32(chave.encode())%100000)
    def draw():
        if method=="Normal (0, s)":
            return rng.normal(0.0,sd,N)
        return rng.choice(errors-errors.mean(),N)
    if persistent:
        eps=np.repeat(draw()[:,None],len(months),axis=1)
    else:
        eps=np.column_stack([draw() for _ in months])
    dm=np.maximum(center+eps,0)
    stock,lost,cov=balance(e0,production,dm)
    days,lt=base[p];ltm=math.ceil(lt*7/30);window=ltm+math.ceil(days/30)+1
    active=np.array([j<window for j in range(len(months))])
    evaluated=np.array([j<len(months)-1 for j in range(len(months))])
    return dict(months=months,production=production,e0=e0,center=center,errors=errors,sd=sd,dm=dm,stock=stock,lost=lost,cov=cov,active=active,ltm=ltm,window=window,
                evaluated=evaluated,model=model_used)

def impacts(res,p,new_plan,baseline):
    s,l,c=balance(res["e0"],new_plan,res["dm"])
    win=res["active"]
    return dict(excesso=float((c[:,win]>=LIM).any(axis=1).mean()),ruptura=float((l[:,win]>0).any(axis=1).mean()),
                delta_excesso=float((c[:,win]>=LIM).any(axis=1).mean()-baseline["excesso"]),
                delta_ruptura=float((l[:,win]>0).any(axis=1).mean()-baseline["ruptura"]))

def fmt(n):return f"{n:,.0f}".replace(",",".")


