"""Avaliação mensal experimental de modelos, sem dados empresariais persistidos."""
import numpy as np
import pandas as pd

CANDIDATES=("MEA-P","MEA","Oficial","Naive")

def evaluate_models(product, close, blocks, forecast_fn, known_fn):
    """Backtest rolling h1..h3 sem usar alvos posteriores ao fechamento.
    Todos os concorrentes são avaliados nos MESMOS pares origem/alvo.
    Esta é uma implementação complementar; homologar contra o notebook final.
    """
    from smartlaunch_core import SHEETS, ANALOG
    pv=blocks[SHEETS[product]]["PV"]
    actual=known_fn(pv,close)
    if actual.empty:
        return pd.DataFrame(), pd.DataFrame(), None
    start=actual.index.min()
    observations={}
    for origin in sorted(pv.index):
        if origin < start or origin >= close:
            continue
        if not (actual.index<=origin).any():
            continue
        targets=[origin+h for h in (1,2,3) if origin+h in actual.index]
        if not targets:
            continue
        for model in CANDIDATES:
            if model in ("MEA", "MEA-P") and not ANALOG.get(product):
                continue
            try:
                pred=forecast_fn(product,targets,origin,blocks,model=model)
            except (ValueError,KeyError,IndexError,TypeError):
                continue
            for target,value in zip(targets,pred):
                if np.isfinite(value) and np.isfinite(actual[target]) and actual[target]>0:
                    observations[(origin,target,model)]=float(value)
    if not observations:
        return pd.DataFrame(),pd.DataFrame(),None
    pairs=set((o,t) for o,t,m in observations)
    eligible_candidates = tuple(m for m in CANDIDATES if m not in ("MEA","MEA-P") or ANALOG.get(product))
    common=[(o,t) for o,t in sorted(pairs) if all((o,t,m) in observations for m in eligible_candidates)]
    records=[]
    for origin,target in common:
        for model in eligible_candidates:
            actual_value=float(actual[target])
            predicted=observations[(origin,target,model)]
            records.append(dict(Origem=str(origin),Alvo=str(target),Horizonte=(target-origin).n,
                                Modelo=model,Real=actual_value,Previsto=predicted,
                                Erro=actual_value-predicted,
                                APE=100*abs(actual_value-predicted)/actual_value))
    detail=pd.DataFrame(records)
    if detail.empty:
        return detail,pd.DataFrame(),None
    rows=[]
    for model,g in detail.groupby("Modelo",sort=False):
        errors=g["Erro"].to_numpy()
        rows.append({"Modelo":model,"MAPE (%)":round(float(g["APE"].mean()),2),
                     "MAE":round(float(np.abs(errors).mean()),1),
                     "RMSE":round(float(np.sqrt(np.mean(errors**2))),1),
                     "Viés (un.)":round(float(errors.mean()),1),
                     "Previsões":len(g),"Fechamentos":g["Origem"].nunique(),
                     "Meses-alvo":g["Alvo"].nunique(),
                     "Elegível":len(g)>=3 and g["Origem"].nunique()>=2})
    ranking=pd.DataFrame(rows).sort_values(["Elegível","MAPE (%)"],ascending=[False,True]).reset_index(drop=True)
    eligible=ranking[ranking["Elegível"]]
    winner=str(eligible.iloc[0]["Modelo"]) if not eligible.empty else None
    return detail,ranking,winner

def monthly_alert_rows(result, limit=180, threshold=.20, warning=.025):
    """Distingue avisos (>2,5%) de alertas (>20%) na janela crítica."""
    excess=(result["cov"]>=limit).mean(axis=0)
    shortage=(result["lost"]>0).mean(axis=0)
    evaluated=np.asarray(result.get("evaluated",np.ones(len(excess),bool)),dtype=bool)
    rows=[]
    for j,month in enumerate(result["months"]):
        window=bool(result["active"][j])
        excess_valid=bool(evaluated[j])
        e=float(excess[j]) if excess_valid else None
        r=float(shortage[j])
        rows.append({
            "Mês":str(month),"Excesso (%)":round(e*100,1) if e is not None else None,
            "Ruptura (%)":round(r*100,1),
            "Janela crítica":window,
            "Alerta excesso":bool(window and e is not None and e>threshold),
            "Alerta ruptura":bool(window and r>threshold),
            "Aviso excesso":bool(window and e is not None and warning<e<=threshold),
            "Aviso ruptura":bool(window and warning<r<=threshold),
        })
    return pd.DataFrame(rows)
