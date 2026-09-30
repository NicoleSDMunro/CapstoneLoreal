import math
import re
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import Holt, SimpleExpSmoothing

MONTHS_PT={1:"jan",2:"fev",3:"mar",4:"abr",5:"mai",6:"jun",7:"jul",8:"ago",9:"set",10:"out",11:"nov",12:"dez"}
MONTH_NUM={v:k for k,v in MONTHS_PT.items()}
MODELS=["Naive","MM2","SES","MM3","Holt"]
SIMPLICITY={"Naive":0,"MM2":1,"SES":2,"MM3":3,"Holt":4}
HORIZONS=[1,2,3]
MIN_ERRORS=2
SMALL_N=4
TIE_TOL=.05

def as_period(value):
    if isinstance(value,pd.Period): return value.asfreq("M")
    m=re.search(r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[/\- ]?(\d{2,4})",str(value).strip().lower())
    if not m: return None
    y=int(m.group(2)); y=y+2000 if y<100 else y
    return pd.Period(year=y,month=MONTH_NUM[m.group(1)],freq="M")

def plabel(p):
    return f"{MONTHS_PT[p.month].upper()}/{str(p.year)[-2:]}"

def read_base_table(xls):
    raw=pd.read_excel(xls,sheet_name="Base",header=None)
    h=None
    for i in range(min(15,len(raw))):
        row=[str(x).lower() for x in raw.iloc[i].tolist() if pd.notna(x)]
        if any(x.strip()=="produto" for x in row) and any("cobertura" in x for x in row):
            h=i; break
    if h is None: return pd.DataFrame()
    df=raw.iloc[h:,1:6].copy()
    df.columns=[str(x).strip() if pd.notna(x) else f"col_{j}" for j,x in enumerate(df.iloc[0])]
    return df.iloc[1:].dropna(how="all").reset_index(drop=True)

def read_bom(xls):
    try:
        df=pd.read_excel(xls,sheet_name="BOM")
        df.columns=[str(c).strip() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()

def find_col(df,parts):
    for c in df.columns:
        t=str(c).lower()
        if all(p.lower() in t for p in parts): return c
    return None

def product_meta(base,bom,product):
    out={"origem":"—","cobertura":np.nan,"lt_weeks":np.nan}
    if not base.empty:
        pc=find_col(base,["produto"])
        row=base[base[pc].astype(str).str.strip().str.upper().eq(product.upper())] if pc else pd.DataFrame()
        if not row.empty:
            row=row.iloc[0]
            oc=find_col(base,["origem"]); cc=find_col(base,["cobertura","target"]); lc=find_col(base,["maior","lt"])
            if oc and pd.notna(row[oc]): out["origem"]=str(row[oc])
            if cc: out["cobertura"]=pd.to_numeric(row[cc],errors="coerce")
            if lc: out["lt_weeks"]=pd.to_numeric(row[lc],errors="coerce")
    if pd.isna(out["lt_weeks"]) and not bom.empty:
        pc=find_col(bom,["produto"]); lc=find_col(bom,["lead","time"]) or find_col(bom,["lt"])
        if pc and lc:
            vals=pd.to_numeric(bom[bom[pc].astype(str).str.strip().str.upper().eq(product.upper())][lc],errors="coerce").dropna()
            if len(vals): out["lt_weeks"]=float(vals.max())
    return out

def parse_pv_sheet(xls,product):
    raw=pd.read_excel(xls,sheet_name=product,header=None)
    h=None
    for i in range(min(10,len(raw))):
        if sum(as_period(v) is not None for v in raw.iloc[i].tolist())>=5:
            h=i; break
    if h is None: raise ValueError(f"Aba {product}: cabeçalho mensal não encontrado.")
    targets=[(j,as_period(v)) for j,v in enumerate(raw.iloc[h].tolist()) if as_period(v) is not None]
    label_col=max(0,targets[0][0]-1)
    rows=[]
    for r in range(h+1,len(raw)):
        origin=as_period(raw.iat[r,label_col])
        if origin is None:
            if rows: break
            continue
        item={"origin":origin}
        for j,t in targets:
            v=pd.to_numeric(raw.iat[r,j],errors="coerce")
            if pd.notna(v): item[t]=float(v)
        rows.append(item)
    if not rows: raise ValueError(f"Aba {product}: matriz de PV vazia.")
    m=pd.DataFrame(rows).set_index("origin").sort_index()
    m.columns=pd.PeriodIndex(m.columns,freq="M")
    return m

def realized_from_matrix(matrix):
    """Realizado de um mês = valor desse mês na versão seguinte.
    Ex.: realizado jun/25 = coluna jun/25 da linha/versão jul/25.
    A diagonal é a previsão oficial feita no próprio mês, não o realizado.
    """
    vals={}
    origins=set(matrix.index)
    for target in matrix.columns:
        next_version=target+1
        if next_version in origins and pd.notna(matrix.loc[next_version,target]):
            vals[target]=float(matrix.loc[next_version,target])
    return pd.Series(vals,dtype=float).sort_index()

def model_available(model,n):
    return {"Naive":n>=1,"MM2":n>=2,"MM3":n>=3,"SES":n>=2,"Holt":n>=3}[model]

def forecast_model(model,history,h):
    y=pd.Series(history,dtype=float).dropna()
    if not model_available(model,len(y)): return None
    if model=="Naive": return np.repeat(float(y.iloc[-1]),h)
    if model=="MM2": return np.repeat(float(y.iloc[-2:].mean()),h)
    if model=="MM3": return np.repeat(float(y.iloc[-3:].mean()),h)
    try:
        if model=="SES":
            fit=SimpleExpSmoothing(y.values,initialization_method="estimated").fit(optimized=True)
        else:
            fit=Holt(y.values,initialization_method="estimated",damped_trend=False).fit(optimized=True)
        return np.asarray(fit.forecast(h),dtype=float)
    except Exception:
        return None

def build_audit(matrix,realized,max_h=14):
    rows=[]
    for origin in matrix.index:
        # Na versão/origem t, o realizado de t ainda não existe.
        # Só são conhecidos realizados estritamente anteriores à origem.
        hist=realized[realized.index<origin]
        if len(hist)>0:
            for model in MODELS:
                if not model_available(model,len(hist)): continue
                pred=forecast_model(model,hist.values,max_h)
                if pred is None: continue
                for h,v in enumerate(pred,1):
                    target=origin+h
                    actual=float(realized[target]) if target in realized.index else np.nan
                    rows.append({"fechamento":origin,"modelo":model,"origem_previsao":origin,"horizonte":h,
                                 "mes_alvo":target,"previsto":float(v),"realizado":actual,
                                 "erro":actual-float(v) if pd.notna(actual) else np.nan,
                                 "benchmark":False,"n_historico_origem":len(hist)})
        for target in matrix.columns:
            if target<=origin: continue
            v=matrix.loc[origin,target]
            if pd.isna(v): continue
            h=int(target.ordinal-origin.ordinal)
            actual=float(realized[target]) if target in realized.index else np.nan
            rows.append({"fechamento":origin,"modelo":"L'Oréal oficial","origem_previsao":origin,"horizonte":h,
                         "mes_alvo":target,"previsto":float(v),"realizado":actual,
                         "erro":actual-float(v) if pd.notna(actual) else np.nan,
                         "benchmark":True,"n_historico_origem":len(hist)})
    return pd.DataFrame(rows)

def evaluated_until(audit,closure,model=None,max_h=3):
    # O realizado do mês-alvo t só fica conhecido na versão t+1.
    df=audit[(audit.origem_previsao<closure)&(audit.mes_alvo<closure)&audit.realizado.notna()&(audit.horizonte<=max_h)].copy()
    return df[df.modelo.eq(model)] if model else df

def compatible_metrics(audit,closure):
    ev=evaluated_until(audit,closure,max_h=3)
    candidates=[m for m in MODELS if ev.loc[ev.modelo.eq(m),"erro"].notna().sum()>=MIN_ERRORS]
    if len(candidates)<2: return pd.DataFrame(),candidates,0
    keysets={}
    for m in candidates:
        s=ev[ev.modelo.eq(m)]
        keysets[m]=set(zip(s.origem_previsao,s.mes_alvo,s.horizonte))
    common=set.intersection(*(keysets[m] for m in candidates))
    if not common: return pd.DataFrame(),candidates,0
    rows=[]
    for m in candidates:
        s=ev[ev.modelo.eq(m)].copy()
        s=s[[tuple(x) in common for x in zip(s.origem_previsao,s.mes_alvo,s.horizonte)]]
        rows.append({"modelo":m,"MAE":s.erro.abs().mean(),"Bias":s.erro.mean(),"n":len(s),
                     "std":s.erro.std(ddof=1) if len(s)>1 else np.nan,"horizontes":s.horizonte.nunique()})
    return pd.DataFrame(rows).sort_values(["MAE","modelo"]).reset_index(drop=True),candidates,len(common)

def choose_model(audit,closure):
    metrics,candidates,n=compatible_metrics(audit,closure)
    if metrics.empty or n<MIN_ERRORS:
        return {"model":None,"status":"insufficient","message":"Ainda não há histórico suficiente para comparar modelos de forma coerente.","metrics":metrics,"common_n":n}
    ranked=metrics.sort_values("MAE").copy()
    best=ranked.iloc[0]; second=ranked.iloc[1] if len(ranked)>1 else None
    model=best.modelo; close=False
    if second is not None and best.MAE>0: close=(second.MAE-best.MAE)/best.MAE<=TIE_TOL
    note=""
    if n<SMALL_N and close:
        tied=ranked[ranked.MAE<=best.MAE*(1+TIE_TOL)]
        model=min(tied.modelo,key=lambda m:SIMPLICITY[m])
        note="A diferença de MAE é pequena e a amostra ainda é limitada; a parcimônia favorece o modelo mais simples entre os praticamente empatados."
    elif n<SMALL_N:
        note="A indicação é provisória porque a amostra de erros ainda é pequena."
    elif close:
        note="O menor MAE está muito próximo do segundo colocado; interprete a diferença com cautela."
    mae=float(metrics.loc[metrics.modelo.eq(model),"MAE"].iloc[0])
    return {"model":model,"status":"provisional" if n<SMALL_N else "selected",
            "message":f"Com os dados disponíveis até {plabel(closure)}, {model} apresenta o menor MAE comparável entre os modelos avaliáveis.",
            "note":note,"metrics":metrics,"common_n":n,"mae":mae}

def horizon_metrics(audit,closure):
    ev=evaluated_until(audit,closure,max_h=3); rows=[]
    for h in HORIZONS:
        hdf=ev[ev.horizonte.eq(h)]
        eligible=[m for m in MODELS if len(hdf[hdf.modelo.eq(m)])]
        if not eligible: continue
        sets={m:set(zip(hdf.loc[hdf.modelo.eq(m),"origem_previsao"],hdf.loc[hdf.modelo.eq(m),"mes_alvo"])) for m in eligible}
        common=set.intersection(*(sets[m] for m in eligible))
        if not common: continue
        for m in eligible+["L'Oréal oficial"]:
            s=hdf[hdf.modelo.eq(m)].copy()
            if s.empty: continue
            s=s[[tuple(x) in common for x in zip(s.origem_previsao,s.mes_alvo)]]
            if len(s): rows.append({"modelo":m,"horizonte":f"M-{h}","MAE":s.erro.abs().mean(),"n":len(s)})
    return pd.DataFrame(rows)

def maturity_history(audit,realized,closures=None):
    rows=[]
    closures=list(closures) if closures is not None else list(realized.index+1)
    for c in closures:
        d=choose_model(audit,c)
        rows.append({"fechamento":c,"historico":int((realized.index<c).sum()),"modelo":d["model"] or "—",
                     "MAE":d.get("mae",np.nan),"n":d.get("common_n",0),"status":d["status"]})
    return pd.DataFrame(rows)

def cumulative_history(audit,realized,closures=None):
    rows=[]
    closures=list(closures) if closures is not None else list(realized.index+1)
    for c in closures:
        m,_,_=compatible_metrics(audit,c)
        for _,r in m.iterrows():
            rows.append({"fechamento":c,"modelo":r.modelo,"MAE":r.MAE,"n":r.n})
    return pd.DataFrame(rows)

def critical_window_months(meta):
    cov=float(meta["cobertura"]) if pd.notna(meta["cobertura"]) else 0
    lt=float(meta["lt_weeks"]) if pd.notna(meta["lt_weeks"]) else 0
    days=lt*7+cov+30
    return int(math.ceil(days/30)) if days>0 else None

def validate_audit(audit,realized):
    checks={}
    checks["Erro só após realizado"]=bool(audit.loc[audit.realizado.notna(),"mes_alvo"].isin(realized.index).all())
    checks["Horizonte consistente"]=bool(((audit.mes_alvo.map(lambda p:p.ordinal)-audit.origem_previsao.map(lambda p:p.ordinal))==audit.horizonte).all())
    checks["Sem alvo na origem"]=bool((audit.mes_alvo>audit.origem_previsao).all())
    checks["Origens imutáveis"]=not audit.duplicated(["modelo","origem_previsao","horizonte","mes_alvo"]).any()
    ok=True
    for model,w in [("Naive",1),("MM2",2),("MM3",3)]:
        for origin in audit.loc[audit.modelo.eq(model),"origem_previsao"].unique():
            hist=realized[realized.index<origin]; exp=hist.iloc[-w:].mean()
            vals=audit[(audit.modelo.eq(model))&(audit.origem_previsao.eq(origin))].previsto
            if len(vals) and not np.allclose(vals.values,exp,rtol=1e-8,atol=1e-8): ok=False
    checks["Naive/MM2/MM3 sem futuro"]=ok
    return checks
