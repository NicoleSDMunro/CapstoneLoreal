"""Smart Launch decision engine.

This module separates scientific calculations from the Streamlit presentation.
Inputs are planning versions; risks are conditional, not validated probabilities.
"""
from dataclasses import dataclass
import math
import re
import unicodedata
from datetime import timedelta
import numpy as np
import pandas as pd

from forecasting import (MODELS, as_period, forecast_model,
                         realized_from_matrix, product_meta, read_base_table, read_bom)

MONTHS = {"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,"jul":7,
          "ago":8,"set":9,"out":10,"nov":11,"dez":12,
          "feb":2,"apr":4,"may":5,"aug":8,"sep":9,"oct":10,"dec":12}

def month(value):
    if isinstance(value, pd.Period):
        return value.asfreq("M")
    if isinstance(value, (pd.Timestamp, __import__("datetime").datetime)):
        return pd.Period(value, freq="M")
    if pd.isna(value):
        return None
    result=as_period(value)
    if result is not None:
        return result
    s=str(value).strip().lower()
    try:
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}",s):
            return pd.Period(pd.Timestamp(s),freq="M")
        if re.fullmatch(r"\d{4}[-/]\d{1,2}",s):
            return pd.Period(s.replace("/","-"),freq="M")
        if re.fullmatch(r"\d{1,2}[-/]\d{4}",s):
            a,b=re.split(r"[-/]",s)
            return pd.Period(year=int(b),month=int(a),freq="M")
        if re.fullmatch(r"[a-z]{3}[-/ ]\d{2,4}",s):
            p=s[:3]; y=int(re.findall(r"\d+",s)[0])
            if p in MONTHS: return pd.Period(year=2000+y if y<100 else y,month=MONTHS[p],freq="M")
    except (ValueError,TypeError):
        pass
    return None

def normalize(v):
    s=unicodedata.normalize("NFKD",str(v).lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()

@dataclass
class Matrices:
    pv: pd.DataFrame
    pp: pd.DataFrame | None = None
    pe: pd.DataFrame | None = None

def parse_matrix(raw):
    """Read version x target-month matrix with a repeated Portuguese or Excel month header."""
    header=None
    for i in range(min(len(raw),22)):
        periods=[month(v) for v in raw.iloc[i].tolist()]
        if len([v for v in periods if v is not None]) >= 3:
            header=i
            break
    if header is None:
        raise ValueError("Nenhum cabeçalho de meses encontrado")
    columns=[(j,month(v)) for j,v in enumerate(raw.iloc[header].tolist())
             if month(v) is not None]
    left=columns[0][0]
    records=[]
    for i in range(header+1,len(raw)):
        version=None
        for j in range(max(0,left-3),left):
            parsed=month(raw.iat[i,j])
            if parsed is not None:
                version=parsed
        if version is None:
            if records: break
            continue
        record={"_versao":version}
        for j,p in columns:
            value=pd.to_numeric(raw.iat[i,j],errors="coerce")
            if pd.notna(value): record[p]=float(value)
        records.append(record)
    if not records:
        raise ValueError("Matriz sem linhas de versões")
    df=pd.DataFrame(records).drop_duplicates("_versao",keep="last").set_index("_versao").sort_index()
    df=df.reindex(sorted([c for c in df if isinstance(c,pd.Period)]),axis=1)
    df.columns=pd.PeriodIndex(df.columns,freq="M")
    return df.astype(float)

def detect_blocks(raw):
    """Detect explicit PV/PP/PE blocks on a per-product worksheet."""
    found={}
    markers={"PV":("pv","plano de vendas","previsao de vendas","sales plan"),
             "PP":("pp","plano de producao","producao planejada","production plan","producao"),
             "PE":("pe","plano de estoque","estoque projetado","inventory plan","estoque")}
    starts=[]
    for i in range(len(raw)):
        snippets=[normalize(x) for x in raw.iloc[i,:min(5,raw.shape[1])].tolist() if pd.notna(x)]
        for kind,values in markers.items():
            if any(s==v or s.startswith(v+" ") or s.startswith(v+"(") or
                   s.startswith(v+" (") or s.startswith(v+":") for s in snippets for v in values):
                starts.append((i,kind))
                break
    for idx,(start,kind) in enumerate(starts):
        end=starts[idx+1][0] if idx+1<len(starts) else len(raw)
        try:
            found[kind]=parse_matrix(raw.iloc[start:end].reset_index(drop=True))
        except ValueError:
            continue
    return found

def long_format_matrix(df):
    names={normalize(col):col for col in df.columns}
    def choose(*opts):
        for key in opts:
            if key in names: return names[key]
        return None
    sku=choose("produto","sku","product")
    version=choose("fechamento","versao","versao do plano","closing")
    target=choose("mes alvo","mes_alvo","mes","target","target month")
    value=choose("valor","volume","quantidade","value")
    if not all(x is not None for x in [sku,version,target,value]):
        return {}
    rows=df[[sku,version,target,value]].copy()
    rows.columns=["sku","version","target","value"]
    rows["version"]=rows["version"].map(month)
    rows["target"]=rows["target"].map(month)
    rows["value"]=pd.to_numeric(rows["value"],errors="coerce")
    rows=rows.dropna(subset=["sku","version","target","value"])
    result={}
    for prod,g in rows.groupby("sku"):
        g=g.drop_duplicates(["version","target"],keep="last")
        result[str(prod).strip()]=g.pivot(index="version",columns="target",values="value").sort_index()
    return result

def read_triangle(source):
    """Supported layouts: product worksheets containing PV/PP/PE blocks;
    product-specific *_PV/*_PP/*_PE; or normalized PV/PP/PE long-format tabs.
    Older PV-only files are admitted but their decision metrics stay unavailable.
    """
    xls=pd.ExcelFile(source)
    sheets={normalize(s):s for s in xls.sheet_names}
    groups={}
    reserved={"base","bom","readme","instrucoes","parametros","analogs","analogos"}
    typed={}
    for sheet in xls.sheet_names:
        low=normalize(sheet)
        m=re.match(r"(.+?)[ _-]+(pv|pp|pe)$",low,re.I)
        if m:
            typed.setdefault(m.group(1).upper(),{})[m.group(2).upper()]=sheet
    for sku,parts in typed.items():
        blocks={}
        for kind,sheet in parts.items():
            raw=pd.read_excel(xls,sheet_name=sheet,header=None)
            try: blocks[kind]=parse_matrix(raw)
            except ValueError: pass
        if "PV" in blocks: groups[sku]=Matrices(blocks["PV"],blocks.get("PP"),blocks.get("PE"))
    for kind in ("pv","pp","pe"):
        if kind in sheets:
            df=pd.read_excel(xls,sheet_name=sheets[kind])
            for sku,mat in long_format_matrix(df).items():
                if sku not in groups: groups[sku]=Matrices(pd.DataFrame())
                setattr(groups[sku],kind,mat)
    for sheet in xls.sheet_names:
        low=normalize(sheet)
        if low in reserved or low in ("pv","pp","pe") or any(sheet in v.values() for v in typed.values()):
            continue
        if sheet in groups: continue
        raw=pd.read_excel(xls,sheet_name=sheet,header=None)
        blocks=detect_blocks(raw)
        if "PV" not in blocks:
            try: blocks["PV"]=parse_matrix(raw)
            except ValueError: continue
        groups[sheet]=Matrices(blocks["PV"],blocks.get("PP"),blocks.get("PE"))
    groups={k:v for k,v in groups.items() if v.pv is not None and not v.pv.empty}
    base=read_base_table(xls) if "base" in sheets else pd.DataFrame()
    bom=read_bom(xls) if "bom" in sheets else pd.DataFrame()
    return groups,base,bom

def canonical_product(name):
    s=normalize(name)
    compact=re.sub(r"[^a-z0-9]","",s)
    m=re.fullmatch(r"(?:produto|product|sku)?p?(\d+)",compact)
    if m:return "P"+str(int(m.group(1)))
    return compact.upper()

def canonical_benchmark(name):
    s=normalize(name)
    compact=re.sub(r"[^a-z0-9]","",s)
    m=re.fullmatch(r"(?:benchmark|bench|analog|analogo)?([a-z])(\d+)?",compact)
    if m and m.group(1) not in ("p",):
        return m.group(1).upper()+"_"+(m.group(2) or "1")
    return compact.upper()

def available_analogs(product, groups):
    """Match case-study benchmark aliases including 'PRODUTO 1' and 'Benchmark A'."""
    defaults={"P1":["A_1","B_1"],"P2":["C_2"],"P3":["D_3","E_3"]}
    expected=defaults.get(canonical_product(product),[])
    selected=[]
    for benchmark in expected:
        for name in groups:
            if name!=product and canonical_benchmark(name)==benchmark:
                selected.append(name)
                break
    return selected

def realized(group):
    return realized_from_matrix(group.pv)

def planned_launch(matrix, origin):
    """First positive sell-in known by this planning version, not first future month.
    A July closing for a December launch must continue to refer to December.
    """
    if origin not in matrix.index:return None
    known=realized_from_matrix(matrix)
    sold=known[(known.index<origin)&(known>0)]
    if len(sold):return min(sold.index)
    earlier=[v for v in matrix.index if v<=origin]
    if not earlier:return None
    first=matrix.loc[min(earlier)].dropna()
    initial=first[first>0]
    if len(initial):return min(initial.index)
    current=matrix.loc[origin].dropna()
    future=current[(current.index>=origin)&(current>0)]
    return min(future.index) if len(future) else None

def indices_for_analog(series):
    y=series[series>0].sort_index()
    if len(y)<6:return {}
    base=np.log10(y.iloc[3:])
    if not len(base): return {}
    return {k:float(np.log10(y.iloc[k-1])-base.mean()) for k in (1,2,3)}

def analog_series(analog,groups,origin,launch):
    hist=realized(groups[analog])
    cutoff=origin if launch is None else min(origin,launch)
    return hist[(hist.index<cutoff)&(hist>0)].sort_index()

def analog_forecast(groups,sku,analogs,origin,launch,h=3,pipe=False):
    """Equal-weight geometric levels; own actuals only when known before the origin.
    Pipe indices are estimated from analogous launches, not the target's future."""
    own=realized(groups[sku]); own=own[(own.index<origin)&(own>0)]
    series=[analog_series(a,groups,origin,launch) for a in analogs if a in groups]
    series=[s for s in series if len(s)]
    if not series:return None
    base_logs=[]
    pipe_indices=[]
    if pipe:
        pipe_indices=[indices_for_analog(s) for s in series]
    pipe_log={k:float(np.mean([p[k] for p in pipe_indices if k in p])) for k in (1,2,3)
              if any(k in p for p in pipe_indices)}
    for idx,old in enumerate(series):
        augmented=np.log10(old.values).astype(float)
        if pipe:
            for k in (1,2,3):
                if k in pipe_log and len(augmented)>=k:
                    augmented[k-1]-=pipe_log[k]
        if len(own):
            new_log=np.log10(own.values)
            if pipe and launch is not None:
                for j,p in enumerate(own.index):
                    life=int(p.ordinal-launch.ordinal)+1
                    if life in pipe_log: new_log[j]-=pipe_log[life]
            augmented=np.concatenate([augmented,new_log])
        base_logs.append(float(np.mean(augmented)))
    level=float(np.mean(base_logs))
    out=[]
    for step in range(1,h+1):
        # Version JUL/26 is issued after JUN/26 closes and forecasts JUL/26 (h=1).
        target=origin+step-1
        life=int(target.ordinal-launch.ordinal)+1 if launch is not None else None
        out.append(10.0**(level + (pipe_log.get(life,0.0) if pipe else 0.0)))
    return np.asarray(out,dtype=float)

def candidate(groups,sku,analogs,origin,launch,method,h=3):
    history=realized(groups[sku])
    history=history[history.index<origin]
    if method=="Oficial":
        if origin not in groups[sku].pv.index:return None
        s=groups[sku].pv.loc[origin]
        vals=[s.get(origin+k-1,np.nan) for k in range(1,h+1)]
        return np.asarray(vals,dtype=float)
    if method in ("MEA","MEA-P"):
        return analog_forecast(groups,sku,analogs,origin,launch,h,pipe=method=="MEA-P")
    if len(history):
        return forecast_model(method,history.values,h)
    return None

def rolling_audit(groups,sku,analogs,closure,launch):
    rows=[]
    pv=groups[sku].pv
    truth=realized(groups[sku])
    for origin in pv.index:
        if origin>=closure:continue
        for meth in ["Oficial","MEA","MEA-P",*MODELS]:
            launch_at_origin=planned_launch(pv,origin) or launch
            pred=candidate(groups,sku,analogs,origin,launch_at_origin,meth,3)
            if pred is None:continue
            for h,guess in enumerate(pred,1):
                t=origin+h-1
                if t>=closure or t not in truth.index or pd.isna(guess) or truth[t]<=0:continue
                rows.append({"origin":origin,"target":t,"h":h,"model":meth,
                             "forecast":float(guess),"actual":float(truth[t]),
                             "error":float(truth[t]-guess),"ape":abs(float(truth[t]-guess))/truth[t]*100})
    return pd.DataFrame(rows)

def rank_models(audit):
    if audit.empty:return pd.DataFrame(),None
    official=set(zip(audit.loc[audit.model=="Oficial","origin"],
                     audit.loc[audit.model=="Oficial","target"]))
    if not official:return pd.DataFrame(),None
    records=[]
    for name,g in audit.groupby("model"):
        pairs=set(zip(g.origin,g.target))
        if not official.issubset(pairs):continue
        subset=g[[pair in official for pair in zip(g.origin,g.target)]]
        if len(subset)<2:continue
        records.append({"Model":name,"MAPE %":subset.ape.mean(),
                        "MAE":subset.error.abs().mean(),"N":len(subset)})
    if not records:return pd.DataFrame(),None
    table=pd.DataFrame(records).sort_values(["MAPE %","Model"]).reset_index(drop=True)
    return table,str(table.iloc[0]["Model"])

def forecast_path(groups,sku,analogs,closure,launch,model,horizon):
    pred=candidate(groups,sku,analogs,closure,launch,model,horizon)
    if pred is None or len(pred)!=horizon:return None
    pred=np.asarray(pred,dtype=float)
    if not np.all(np.isfinite(pred)):return None
    return np.maximum(pred,0)

def forecast_residuals(audit,model):
    if audit.empty or not model:return np.array([])
    a=audit[audit.model==model]
    return a["error"].to_numpy(dtype=float)

def monte_carlo(forecast,errors,n=1000,distribution="Normal (0, s)",seed=20261021):
    if forecast is None or len(errors)<2:
        return None
    std=np.std(errors,ddof=1)
    if not np.isfinite(std):return None
    rng=np.random.default_rng(seed)
    if distribution=="Bootstrap centralizado":
        centered=errors-np.mean(errors)
        draws=rng.choice(centered,size=(n,len(forecast)),replace=True)
    else:
        draws=rng.normal(loc=0.0,scale=std,size=(n,len(forecast)))
    return np.maximum(np.asarray(forecast,dtype=float)[None,:]+draws,0)

def production_plan(group,closure,periods):
    if group.pp is None or closure not in group.pp.index:return None
    series=group.pp.loc[closure]
    return np.array([max(float(series.get(p,0) or 0),0)
                     if pd.notna(series.get(p,np.nan)) else 0 for p in periods],dtype=float)

def opening_stock(group,closure):
    # JUL/26 version is the June closing. The first simulated period is July.
    # Initial inventory is the recorded June balance, not projected July ending stock.
    previous=closure-1
    if group.pe is None or closure not in group.pe.index or previous not in group.pe.columns:
        return None
    x=group.pe.loc[closure,previous]
    return float(x) if pd.notna(x) and x>=0 else None

def forward_cover(stock,demand,step):
    """Forward cover by sequential depletion, with last demand repeated past the horizon."""
    count=demand.shape[1]
    remaining=stock[:,step].astype(float).copy()
    cover=np.zeros(len(remaining),dtype=float)
    last=np.maximum(demand[:,-1],0)
    for j in range(step+1,count):
        d=np.maximum(demand[:,j],0)
        positive=d>0
        days=np.divide(remaining,d,out=np.zeros_like(remaining),where=positive)
        cover+=np.where(remaining<=0,0,np.where(positive,np.minimum(days,1)*30,30))
        remaining=np.maximum(remaining-d,0)
    # Model convention: repeat last known forecast until depletion, capped to 60 months.
    extended=np.divide(remaining,last,out=np.full_like(remaining,np.inf),where=last>0)
    cover+=np.where(remaining>0,np.minimum(extended,60)*30,0)
    return cover

def simulate_inventory(open_stock,receipts,demand):
    demand=np.asarray(demand,dtype=float)
    n,h=demand.shape
    stock=np.zeros((n,h))
    lost=np.zeros((n,h))
    carry=np.full(n,float(open_stock))
    for t in range(h):
        available=carry+receipts[t]
        lost[:,t]=np.maximum(demand[:,t]-available,0)
        carry=np.maximum(available-demand[:,t],0)
        stock[:,t]=carry
    covers=np.column_stack([forward_cover(stock,demand,t) for t in range(h)])
    return stock,lost,covers

def excess_units(stock,demand,limit_months=6):
    # For each month compare stock to forecast consumption of the next six months.
    n,h=demand.shape
    outs=np.zeros((n,h))
    for j in range(h):
        known=demand[:,j+1:min(h,j+1+limit_months)].sum(axis=1)
        repeat=max(0,limit_months-max(0,min(h,j+1+limit_months)-(j+1)))
        consume=known+repeat*demand[:,-1]
        outs[:,j]=np.maximum(stock[:,j]-consume,0)
    return outs

def metrics(open_stock,receipts,demand,limit=180,window=None):
    stock,lost,cover=simulate_inventory(open_stock,receipts,demand)
    num=demand.shape[1] if window is None else min(demand.shape[1],window)
    excess=np.nanmean(cover[:,:num]>=limit,axis=0)
    risk_lost=np.nanmean(lost[:,:num]>0,axis=0)
    cover50=np.nanmedian(cover[:,:num],axis=0)
    excess_curve=excess_units(stock,demand)[:,:num].mean(axis=0)
    total_demand=demand[:,:num].sum()
    fill=1.0-lost[:,:num].sum()/total_demand if total_demand>0 else np.nan
    return {"stock":stock,"lost":lost,"cover":cover,
            "excess_risk":excess,"stockout_risk":risk_lost,
            "median_cover":cover50,"fill_rate":fill,
            "excess_worst":float(np.max(excess_curve)) if len(excess_curve) else 0.0,
            "lost_mean":float(lost[:,:num].sum(axis=1).mean()),
            "excess_curve":excess_curve}

def deadline(receipt_month,lead_weeks):
    date=receipt_month.to_timestamp(how="start")
    return date-timedelta(days=7*float(lead_weeks))

def actionable_lots(closure,months,receipts,lead_weeks):
    if pd.isna(lead_weeks):return []
    asof=(closure-1).to_timestamp(how="end")
    return [(i,p,float(receipts[i]),deadline(p,lead_weeks))
            for i,p in enumerate(months)
            if receipts[i]>0 and deadline(p,lead_weeks)>asof]

def compare_alternative(base,initial,receipts,demand,index,change,limit,window):
    mod=np.array(receipts,dtype=float).copy()
    mod[index]=max(mod[index]*(1+change/100),0)
    test=metrics(initial,mod,demand,limit,window)
    p_old=base["stockout_risk"]
    p_new=test["stockout_risk"]
    new_signal=np.any((p_old<=0.025)&(p_new>0.025))
    large_jump=np.any((p_new-p_old)>0.025+1e-10)
    admissible=not (new_signal or large_jump)
    return {"change":change,"excess_avoided":base["excess_worst"]-test["excess_worst"],
            "lost_extra":test["lost_mean"]-base["lost_mean"],
            "fill":test["fill_rate"],"stockout_risk":float(np.max(p_new)),
            "excess_risk":float(np.max(test["excess_risk"])),
            "admissible":admissible,"test":test}

def critical_window(lead_weeks,cover_target,horizon):
    if pd.isna(lead_weeks) or pd.isna(cover_target):return horizon
    return min(horizon,int(math.ceil((float(lead_weeks)*7+float(cover_target)+30)/30)))


def benchmark_log_errors(groups,analogs,closure):
    """Exploratory pre-launch error pool from cross-benchmark predictions.
    Only benchmarks whose histories were available by closure and older peers
    are used. These log errors do NOT constitute independent prospective tests.
    """
    rows=[]
    histories={b:realized(groups[b]) for b in analogs if b in groups}
    for benchmark,s in histories.items():
        positive=s[(s>0)&(s.index<closure)].sort_index()
        if len(positive)<3: continue
        launch=positive.index[0]
        older=[k for k,v in histories.items() if k!=benchmark
               and len(v[(v>0)&(v.index<launch-1)])>0]
        if not older:continue
        # Forecast first launch month from its own plan version (issued after the prior close).
        prev=analog_forecast(groups,benchmark,older,launch,launch,h=3,pipe=False)
        if prev is None:continue
        for h in range(3):
            target=launch+h
            if target in positive.index and prev[h]>0:
                rows.append(float(np.log(positive[target]/prev[h])))
    return np.asarray(rows,dtype=float)

def scenarios_from_benchmarks(forecast,log_errors,n=1000,seed=20261021):
    """Early monitoring uses the separately documented multiplicative assumption."""
    if forecast is None or len(log_errors)<2:return None
    std=float(np.std(log_errors,ddof=1))
    rng=np.random.default_rng(seed)
    errors=rng.normal(0.0,std,size=(n,len(forecast)))
    return np.maximum(forecast[None,:]*np.exp(np.clip(errors,-10,10)),0)


def compare_reschedule(base,initial,receipts,demand,index,new_index,limit,window):
    """Move a single lot to an eligible future month; use exactly the same demand draws."""
    if new_index<0 or new_index>=len(receipts) or new_index==index:
        raise ValueError("Lot destination outside the projected horizon")
    mod=np.array(receipts,dtype=float).copy()
    amount=mod[index]
    mod[index]=0
    mod[new_index]+=amount
    test=metrics(initial,mod,demand,limit,window)
    old=base["stockout_risk"]
    new=test["stockout_risk"]
    admissible=not (np.any((old<=0.025)&(new>0.025)) or
                    np.any((new-old)>0.025+1e-10))
    return {"excess_avoided":base["excess_worst"]-test["excess_worst"],
            "lost_extra":test["lost_mean"]-base["lost_mean"],
            "fill":test["fill_rate"],"stockout_risk":float(np.max(new)),
            "excess_risk":float(np.max(test["excess_risk"])),
            "admissible":admissible,"test":test}


def available_plan_horizon(group,closure):
    """Count contiguous monthly targets starting with the version month.
    Version JUL/26 includes JUL/26 as h=1, not AUG/26.
    """
    if closure not in group.pv.index:return 0
    series=group.pv.loc[closure]
    possible=series[(series.index>=closure)&series.notna()]
    if possible.empty:return 0
    last=max(possible.index)
    count=0
    for n in range(int(last.ordinal-closure.ordinal)+1):
        target=closure+n
        if target not in series.index or pd.isna(series[target]):break
        count+=1
    return count

def data_readiness(group,closure,forecast,scenario,initial,receipts):
    """Explicit reasons that a dashboard value is unavailable."""
    messages=[]
    if group.pp is None:
        messages.append("Production block (PP) not detected")
    elif closure not in group.pp.index:
        messages.append("PP has no row for selected closing")
    if group.pe is None:
        messages.append("Inventory block (PE) not detected")
    elif closure not in group.pe.index:
        messages.append("PE has no row for selected closing")
    elif closure-1 not in group.pe.columns or pd.isna(group.pe.loc[closure,closure-1]):
        messages.append("Previous month's closing stock is not recorded in the selected version")
    if forecast is None:messages.append("Selected model has no complete forecast within planning horizon")
    if scenario is None:messages.append("Insufficient residuals for 1,000 demand scenarios")
    if receipts is None and group.pp is not None:messages.append("Production receipts unavailable for selected months")
    if initial is None and group.pe is not None:messages.append("Initial stock unavailable for selected closing")
    return messages
