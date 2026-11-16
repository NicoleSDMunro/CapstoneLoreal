"""Smart Launch | Supply Chain Decision Center (Streamlit).

A decision-support interface, not an automatic replenishment system.
"""
from pathlib import Path
from io import BytesIO
import html
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forecasting import plabel, product_meta
from smartlaunch_core import (read_triangle, available_analogs, realized,
    planned_launch, rolling_audit, rank_models, candidate, forecast_path,
    forecast_residuals, monte_carlo, production_plan, opening_stock,
    metrics, critical_window, actionable_lots, compare_alternative,
    benchmark_log_errors, scenarios_from_benchmarks, compare_reschedule,
    available_plan_horizon, data_readiness, canonical_product)

st.set_page_config(page_title="Smart Launch | Decision Center",
                   page_icon="📊",layout="wide",initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif}
.stApp{background:#f5f7fb;color:#172b42}
.block-container{max-width:1900px;padding:1.25rem 2rem 4rem}
[data-testid="stSidebar"]{background:#132d47}
[data-testid="stSidebar"] *{color:#e4ebf3}
[data-testid="stSidebar"] [data-baseweb="select"] *{color:#142b43}
[data-testid="stSidebar"] input{color:#152b43}
[data-testid="stHeader"]{background:transparent}
[data-testid="stMetric"]{background:#fff;border:1px solid #e9edf2;border-radius:12px;padding:10px 15px}
#MainMenu,footer{visibility:hidden}
h1,h2,h3{color:#172d46}
.kicker{font-size:10px;letter-spacing:2px;color:#2a6ccc;font-weight:800}
.heading{font-size:29px;font-weight:800;letter-spacing:-.9px;margin:3px 0 3px;color:#1a2c44}
.subheading{font-size:12px;color:#6e7f90;margin-bottom:13px}
.section-label{font-size:10px;font-weight:800;letter-spacing:1.3px;color:#70829a;text-transform:uppercase;margin:14px 0 8px}
.hero{background:linear-gradient(107deg,#122d46,#1b4569);border-radius:15px;padding:19px 23px;color:#f8fbff;margin:6px 0 13px}
.hero-k{font-size:10px;letter-spacing:1.4px;color:#bbd1e7;font-weight:800;margin-bottom:4px}
.hero-t{font-size:23px;line-height:1.25;font-weight:800;margin:5px 0 7px}
.hero-p{font-size:12px;line-height:1.5;color:#d6e4ee;max-width:1100px}
.response{border-radius:11px;padding:14px 17px;background:#ffffff16;border:1px solid #ffffff27;height:100%}
.response .lbl{font-size:10px;color:#c0d5e9;font-weight:800;letter-spacing:.5px}
.response .rsp{font-size:18px;font-weight:800;margin-top:6px;color:white}
.response .detail{color:#d2e1ef;font-size:11px;line-height:1.5;margin-top:7px}
.kpi{border:1px solid #e7edf4;border-radius:13px;background:#fff;padding:14px 17px;min-height:102px;box-shadow:0 4px 12px #172a4405}
.kpi .label{font-size:10px;letter-spacing:.7px;font-weight:800;text-transform:uppercase;color:#7a8aa0}
.kpi .value{font-size:26px;font-weight:800;color:#172d46;margin:8px 0 2px}
.kpi .description{font-size:11px;color:#8a99aa}
.box-title{font-size:15px;font-weight:800;color:#1b314a;line-height:1.3;margin-top:3px}
.box-subtitle{font-size:11px;color:#8190a2;margin-bottom:8px}
.riskline{background:#fff;border:1px solid #e4edf5;border-radius:10px;padding:9px 13px;margin:4px 0}
.riskline-top{display:flex;justify-content:space-between;font-size:12px;font-weight:700;color:#1c344e}
.riskline-track{height:5px;background:#eaf0f6;border-radius:5px;margin-top:7px;overflow:hidden}
.riskline-fill{height:100%;border-radius:5px;background:#4386e8}
.cover-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-top:11px}
.cover-tile{border:1px solid #e6edf5;border-radius:10px;padding:10px;text-align:center;background:#fff}
.cover-tile .m{font-size:10px;color:#788a9d;text-transform:uppercase;font-weight:800}
.cover-tile .v{font-size:21px;color:#172e48;font-weight:800;margin:7px 0 2px}
.cover-tile .status{font-size:9px;text-transform:uppercase;font-weight:800;color:#657a90}
.note{background:#edf4fe;border-left:3px solid #4288e8;border-radius:5px;padding:10px 13px;color:#34536f;font-size:11px;line-height:1.5;margin-top:10px}
.divider{height:1px;background:#e4ebf4;margin:14px 0}
.stTabs [data-baseweb="tab-list"]{gap:5px}
.stTabs [data-baseweb="tab"]{padding:7px 13px}
</style>
""",unsafe_allow_html=True)

def safe(v): return html.escape(str(v))
def qty(v):
    if v is None or pd.isna(v):return "—"
    if abs(v)>=1e6:return f"{v/1e6:.2f}M"
    if abs(v)>=1000:return f"{v/1e3:.1f}k"
    return f"{v:,.0f}"
def pct(v):
    return "—" if v is None or pd.isna(v) else f"{100*v:.1f}%"
def kpi(title,value,detail):
    st.markdown('<div class="kpi"><div class="label">'+safe(title)+'</div><div class="value">'+safe(value)+'</div><div class="description">'+safe(detail)+'</div></div>',unsafe_allow_html=True)
def section(title,subtitle=""):
    st.markdown('<div class="box-title">'+safe(title)+'</div><div class="box-subtitle">'+safe(subtitle)+'</div>',unsafe_allow_html=True)
def nice_plot(fig,height=276,legend=True):
    fig.update_layout(height=height,paper_bgcolor="white",plot_bgcolor="white",
        margin=dict(l=9,r=10,t=14,b=28),font=dict(family="Inter",size=11,color="#678098"),
        hovermode="x unified",legend=dict(orientation="h",y=-.28,x=0) if legend else dict(visible=False))
    fig.update_yaxes(gridcolor="#edf1f5",zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig

DEFAULT=Path(__file__).with_name("Base de Dados - PUC (2).xlsx")
with st.sidebar:
    st.markdown("### SMART LAUNCH")
    st.caption("Supply Chain · Decision Support")
    st.divider()
    st.markdown("**01 / DATA SOURCE**")
    uploaded=st.file_uploader("Upload monthly Triângulo (.xlsx)",type=["xlsx"])
    if uploaded is not None:
        source=BytesIO(uploaded.getvalue())
        st.success("Workbook received")
    elif DEFAULT.exists():
        source=str(DEFAULT)
        st.info("Legacy example loaded. Upload Triângulo with PV, PP and PE to enable inventory decisions.")
    else:
        source=None
    st.caption("Data stays in the current session.")
if source is None:
    st.markdown('<div class="kicker">SUPPLY CHAIN INTELLIGENCE</div><div class="heading">Launch Decision Center</div>',unsafe_allow_html=True)
    st.info("Upload your monthly Triângulo workbook using the sidebar. Product and planning-version filters will appear automatically.")
    st.stop()

try:
    groups,base,bom=read_triangle(source)
except Exception as err:
    st.error("Unable to read workbook. Check that it contains a PV matrix or normalized PV/PP/PE sheets.")
    st.exception(err)
    st.stop()
if not groups:
    st.error("No valid product planning matrix found. Check worksheet structure.")
    st.stop()

st.markdown('<div class="kicker">SUPPLY CHAIN INTELLIGENCE</div><div class="heading">Launch Decision Center</div><div class="subheading">Demand risk anticipation · planning responsiveness · supplier decision support</div>',unsafe_allow_html=True)
prod_col,close_col,hor_col,view_col=st.columns([1.45,1.3,1.0,1.0],gap="small")
with prod_col:
    product=st.selectbox("PRODUCT / SKU",sorted(groups),key="product")
grp=groups[product]
with close_col:
    versions=list(grp.pv.index)
    closure=st.selectbox("PLANNING VERSION",versions,index=len(versions)-1,format_func=plabel,key="closure")
with hor_col:
    requested_horizon=st.selectbox("HORIZON",options=[3,6,9,12],index=1,format_func=lambda x:f"{x} months")
with view_col:
    view=st.selectbox("DISPLAY MODE",["Executive","Analyst"])

with st.sidebar:
    st.divider()
    st.markdown("**02 / ANALYTICAL ASSUMPTIONS**")
    analog_options=[x for x in sorted(groups) if x!=product]
    defaults=available_analogs(product,groups)
    analogs=st.multiselect("Comparable launches / benchmarks",options=analog_options,default=defaults,
                            help="Select only benchmarks available and comparable at the planning date.")
    launch=planned_launch(grp.pv,closure)
    p_opts=[None]+sorted(set(grp.pv.columns))
    launch=st.selectbox("Planned launch month",p_opts,index=(p_opts.index(launch) if launch in p_opts else 0),
                         format_func=lambda x:"Not specified" if x is None else plabel(x),
                         help="Set to the launch date known in the planning version; do not use future actual sales.")
    distribution=st.selectbox("Demand uncertainty",["Normal (0, s)","Bootstrap centralizado"])
    limit=st.number_input("Excess threshold (days)",min_value=30,max_value=720,value=180,step=30)
    attention=st.slider("Alert level: conditional excess probability",min_value=5,max_value=80,value=20,step=5)
    user_meta=product_meta(base,bom,product)
    canonical=canonical_product(product)
    if (pd.isna(user_meta.get("lt_weeks",np.nan)) or pd.isna(user_meta.get("cobertura",np.nan))) and canonical!=product:
        alias_meta=product_meta(base,bom,canonical)
        for field in ("lt_weeks","cobertura"):
            if pd.isna(user_meta.get(field,np.nan)) and pd.notna(alias_meta.get(field,np.nan)):
                user_meta[field]=alias_meta[field]
    fallback_meta={"P1":(16,70),"P2":(10,90),"P3":(8,59)}
    default_lt,default_cover=fallback_meta.get(canonical,(8,90))
    actual_lt=user_meta.get("lt_weeks",np.nan)
    actual_cover=user_meta.get("cobertura",np.nan)
    known_lt=pd.notna(actual_lt)
    known_cover=pd.notna(actual_cover)
    lead_weeks=st.number_input("Lead time (weeks)",min_value=0.0,max_value=104.0,
             value=float(actual_lt) if known_lt else float(default_lt),step=1.0)
    cover_target=st.number_input("Target coverage (days)",min_value=0.0,max_value=720.0,
             value=float(actual_cover) if known_cover else float(default_cover),step=1.0)
    if not known_lt or not known_cover:
        st.caption("Some operational parameters use editable TCC reference defaults (P1/P2/P3) or illustrative starting values. Confirm them for actual planning.")
    st.divider()
    st.caption(f"Recognized SKUs: {len(groups)} · PV+PP+PE: {sum((g.pp is not None and g.pe is not None) for g in groups.values())}")
    st.caption("These estimates are conditional on models, data and timing assumptions. Planner review required.")

truth=realized(grp)
history=truth[truth.index<closure].tail(9)
audit=rolling_audit(groups,product,analogs,closure,launch)
rank,best=rank_models(audit)
candidate_names=["Automatic (historical MAPE)","Oficial","MEA","MEA-P","Naive","MM2","MM3","SES","Holt"]
if view=="Analyst":
    with st.sidebar:
        manual=st.selectbox("Forecast model",candidate_names)
else:
    manual="Automatic (historical MAPE)"
if manual.startswith("Automatic"):
    if best: chosen=best;selection_reason="Lowest eligible historical MAPE with available observations"
    elif analogs: chosen="MEA-P";selection_reason="Provisional analogy estimate: insufficient historical errors"
    else: chosen="Oficial";selection_reason="Only official planning estimate is available"
else:
    chosen=manual
    selection_reason="Planner-selected method; not the automatic model ranking"

available_horizon=available_plan_horizon(grp,closure)
if available_horizon==0:
    st.error("This closing has no usable future PV months. Select another planning version or check the spreadsheet.")
    st.stop()
horizon=min(requested_horizon,available_horizon)
if horizon<requested_horizon:
    st.info(f"The workbook contains {available_horizon} complete planning months after {plabel(closure)}. "
            f"Analysis was limited to {horizon} months instead of {requested_horizon}; no future months were invented.")
future=[closure+i for i in range(1,horizon+1)]
pred=forecast_path(groups,product,analogs,closure,launch,chosen,horizon)
if pred is None and manual.startswith("Automatic"):
    for fallback in ["MEA","Oficial"]:
        pred=forecast_path(groups,product,analogs,closure,launch,fallback,horizon)
        if pred is not None:
            chosen=fallback;selection_reason="Provisional fallback: selected model unavailable";break

official=candidate(groups,product,analogs,closure,launch,"Oficial",horizon)
errs=forecast_residuals(audit,chosen)
scenarios=monte_carlo(pred,errs,n=1000,distribution=distribution)
scenario_source="Own-product rolling errors" if scenarios is not None else "Unavailable"
if scenarios is None and pred is not None and analogs:
    benchmark_errors=benchmark_log_errors(groups,analogs,closure)
    scenarios=scenarios_from_benchmarks(pred,benchmark_errors,n=1000)
    if scenarios is not None:
        scenario_source="Exploratory cross-benchmark log-normal errors"
initial=opening_stock(grp,closure)
receipts=production_plan(grp,closure,future)
with st.sidebar:
    st.divider()
    st.markdown("**03 / OPTIONAL OPERATIONAL INPUTS**")
    if initial is None:
        if st.checkbox("Enter closing inventory (scenario assumption)",value=False):
            initial=st.number_input("Closing inventory (units)",min_value=0.0,value=0.0,step=1000.0)
            st.caption("Not taken from PE; manually supplied for this scenario.")
    if receipts is None:
        if st.checkbox("Enter planned production (scenario assumption)",value=False):
            df_in=pd.DataFrame({"Month":[plabel(m) for m in future],"Production":[0.0]*len(future)})
            df_out=st.data_editor(df_in,hide_index=True,key=f"plan_{product}_{closure}",
                                  disabled=["Month"],use_container_width=True)
            receipts=np.maximum(pd.to_numeric(df_out["Production"],errors="coerce").fillna(0).to_numpy(),0)
            st.caption("Manual production replaces missing PP data for this scenario.")
    if scenarios is None:
        st.caption("Requires at least two known forecast errors or cross-benchmark log errors. Probabilities are not fabricated.")

problems=data_readiness(grp,closure,pred,scenarios,initial,receipts)
with st.sidebar:
    with st.expander("Import diagnostics · PV / PP / PE",expanded=(len(problems)>0)):
        st.write(f"**Sales (PV):** {'Detected' if grp.pv is not None else 'Missing'}")
        st.write(f"**Production (PP):** {'Detected' if grp.pp is not None else 'Missing'}")
        st.write(f"**Inventory (PE):** {'Detected' if grp.pe is not None else 'Missing'}")
        st.write(f"**Historical forecast errors:** {len(errs)}")
        st.write(f"**Forecast model:** {chosen}")
        st.write(f"**Benchmark selection:** {', '.join(analogs) if analogs else 'None'}")
        for problem in problems:
            st.warning(problem)
window=critical_window(lead_weeks,cover_target,horizon)
calc=metrics(initial,receipts,scenarios,limit,window) if (
        scenarios is not None and receipts is not None and initial is not None) else None
lots=actionable_lots(closure,future,receipts,lead_weeks) if receipts is not None else []
if calc is None:
    response="Planner Review"
    headline="Operational risk assessment incomplete"
    explanation=("; ".join(problems) if problems else "Operational scenario inputs incomplete")+
                ". Check the import diagnostics in the left sidebar; planner review required."
    priority_index=0
else:
    priority_index=int(np.argmax(calc["excess_risk"]))
    risk=float(calc["excess_risk"][priority_index])
    if risk>attention/100:
        headline="Elevated excess exposure detected"
        response="Supplier Review" if lots else "Commercial Action"
    elif risk>0.025:
        headline="Excess exposure · monitor closely"
        response="Monitoring"
    else:
        headline="No elevated excess signal in selected horizon"
        response="Monitoring"
    explanation=(f"{plabel(future[priority_index])}: conditional excess probability {risk:.1%}. "
                 f"{len(lots)} production lots remain outside the configured supplier lead time. "
                 "Any intervention requires planner review.")

c_main,c_response=st.columns([4,1.18],gap="small")
with c_main:
    st.markdown('<div class="hero"><div class="hero-k">SMART LAUNCH RECOMMENDATION · DECISION SUPPORT</div>'
                '<div class="hero-t">'+safe(headline)+'</div><div class="hero-p">'+safe(explanation)+
                '</div><div class="hero-p" style="margin-top:7px">Planner review required · '+safe(selection_reason)+'</div></div>',
                unsafe_allow_html=True)
with c_response:
    st.markdown('<div class="hero"><div class="response"><div class="lbl">RECOMMENDED RESPONSE</div>'
                '<div class="rsp">'+safe(response)+'</div><div class="detail">Decision support only. '
                'Supplier commitments and commercial constraints require confirmation.</div></div></div>',unsafe_allow_html=True)

k=st.columns(5,gap="small")
if calc is not None:
    max_ex=float(np.max(calc["excess_risk"]))
    idx=int(np.argmax(calc["excess_risk"]))
    median=float(calc["median_cover"][idx])
    fill=calc["fill_rate"]
else:
    max_ex=median=fill=None
selected_report=rank[rank["Model"]==chosen] if not rank.empty else pd.DataFrame()
err_label=f"{selected_report.iloc[0]['MAPE %']:.1f}%" if not selected_report.empty else "—"
values=[
    ("EXCESS RISK",pct(max_ex),"Maximum conditional probability"),
    ("MEDIAN COVER",f"{median:.0f} d" if median is not None and np.isfinite(median) else "—",f"vs {limit}-day threshold"),
    ("FORECAST ERROR",err_label,"Historical rolling MAPE · eligible pairs"),
    ("ACTIONABLE LOTS",str(len(lots)) if receipts is not None else "—","Outside supplier lead time"),
    ("FILL RATE",pct(fill),"Expected within critical window")
]
for col,(name,val,detail) in zip(k,values):
    with col:kpi(name,val,detail)

st.markdown('<div class="section-label">01 / Demand intelligence and risk outlook</div>',unsafe_allow_html=True)
left,right=st.columns([1.65,1.0],gap="medium")
with left:
    section("Demand Forecast","Historical actuals · L'Oréal official plan · Smart Launch estimate")
    chart=go.Figure()
    if len(history):
        chart.add_trace(go.Scatter(x=[str(p) for p in history.index],y=history.values,mode="lines+markers",
                                   line=dict(color="#173b5a",width=3),name="Actual",marker=dict(size=6)))
    if official is not None:
        chart.add_trace(go.Scatter(x=[str(p) for i,p in enumerate(future) if np.isfinite(official[i])],
                                   y=[v for v in official if np.isfinite(v)],mode="lines+markers",
                                   line=dict(color="#8d9cac",width=2,dash="dash"),name="Official"))
    if scenarios is not None:
        low=np.percentile(scenarios,2.5,axis=0)
        high=np.percentile(scenarios,97.5,axis=0)
        chart.add_trace(go.Scatter(x=[str(p) for p in future],y=high,mode="lines",
                        line=dict(width=0),hoverinfo="skip",showlegend=False))
        chart.add_trace(go.Scatter(x=[str(p) for p in future],y=low,mode="lines",
                        line=dict(width=0),fill="tonexty",fillcolor="rgba(45,115,215,0.11)",
                        name="P2.5–P97.5"))
    if pred is not None:
        chart.add_trace(go.Scatter(x=[str(p) for p in future],y=pred,mode="lines+markers",
                         line=dict(color="#377dea",width=3),marker=dict(size=6),name=f"Smart Launch · {chosen}"))
    st.plotly_chart(nice_plot(chart,286),use_container_width=True,config={"displayModeBar":True})
with right:
    section("Risk Monitor","Conditional excess and stockout probability · critical window")
    if calc is None:
        st.warning("Risk calculation unavailable: "+("; ".join(problems) if problems else
                   "missing model or operational input")+". Check the sidebar import diagnostics.")
    else:
        idxs=list(range(min(window,6)))
        for i in idxs:
            x=float(calc["excess_risk"][i])
            color="#d8494a" if x>attention/100 else "#e2a12a" if x>0.025 else "#4386e8"
            width=max(1,min(100,100*x))
            st.markdown('<div class="riskline"><div class="riskline-top"><span>'+safe(plabel(future[i]))+
                   ' · Excess</span><span>'+safe(pct(x))+'</span></div>'
                   '<div class="riskline-track"><div class="riskline-fill" style="width:'+str(width)+
                   '%;background:'+color+'"></div></div></div>',unsafe_allow_html=True)
        with st.expander("Stockout risk by month"):
            for i in idxs:
                st.write(f"{plabel(future[i])}: {pct(calc['stockout_risk'][i])}")
st.markdown('<div class="section-label">02 / Inventory coverage outlook</div>',unsafe_allow_html=True)
section("Inventory Coverage Outlook","Sequential forward cover · median across 1,000 scenarios · operational excess threshold")
if calc is None:
    st.info("Projected median cover becomes available after inventory and Monte Carlo inputs are complete.")
else:
    tiles=[]
    for j,p in enumerate(future[:6]):
        v=float(calc["median_cover"][j])
        status="EXCESS" if v>=limit else "WATCH" if v>=0.85*limit else "WITHIN LIMIT"
        tiles.append('<div class="cover-tile"><div class="m">'+safe(plabel(p))+'</div><div class="v">'+
                     (f"{v:.0f}" if np.isfinite(v) else "—")+
                     '</div><div class="status">'+status+'</div></div>')
    st.markdown('<div class="cover-grid">'+"".join(tiles)+'</div>',unsafe_allow_html=True)
    month_choice=st.selectbox("Explore risk month",future[:max(1,window)],format_func=plabel)
    mi=future.index(month_choice)
    st.markdown('<div class="note"><b>'+safe(plabel(month_choice))+'</b> · Conditional excess risk '+pct(calc["excess_risk"][mi])+
                ' · Conditional stockout risk '+pct(calc["stockout_risk"][mi])+
                ' · Median forward cover '+(f"{calc['median_cover'][mi]:.0f}" if np.isfinite(calc["median_cover"][mi]) else "—")+
                ' days. Operational excess limit: '+str(limit)+' days.</div>',unsafe_allow_html=True)

st.markdown('<div class="divider"></div>',unsafe_allow_html=True)
st.markdown('<div class="section-label">03 / Timing → actionability → alternatives → trade-off</div>',unsafe_allow_html=True)
a,b=st.columns([1.5,1.0],gap="medium")
alternatives=[]
with a:
    section("Decision Simulator · Lot Intervention Frontier","One lot at a time · same simulated demand scenarios across all alternatives")
    if calc is None or not lots:
        st.info("No feasible lot simulator for this version. " +
            ("There are no production lots outside the supplier lead time." if calc is not None else
             "Risk inputs are incomplete."))
    else:
        selected_lot=st.selectbox("LOT ELIGIBLE FOR REVIEW",range(len(lots)),
                   format_func=lambda i:f"{plabel(lots[i][1])} · {qty(lots[i][2])} units · deadline {lots[i][3].date()}")
        i,p,units,cutoff=lots[selected_lot]
        change=st.slider("LOT ADJUSTMENT (%)",min_value=-100,max_value=100,value=0,step=5,
            help="Illustrative change to one planned receipt; not an authorized production order.")
        current=compare_alternative(calc,initial,receipts,scenarios,i,change,limit,window)
        x=st.columns(4)
        for column,(label,value) in zip(x,[
            ("Excess avoided",qty(current["excess_avoided"])),
            ("Additional lost sales",qty(current["lost_extra"])),
            ("Expected fill rate",pct(current["fill"])),
            ("Maximum stockout probability",pct(current["stockout_risk"]))
        ]):
            with column:st.metric(label,value)
        status="Admissible under current assumptions" if current["admissible"] else "Service-risk review required"
        st.markdown('<div class="note"><b>'+safe(status)+'</b> · Model-based screening only. '
            'Check supplier agreements, lot minimums and actual change deadlines before acting.</div>',
            unsafe_allow_html=True)
        for amount in [-100,-75,-50,-35,-30,-25,-10,-5,0,5,25,50,100]:
            assessment=compare_alternative(calc,initial,receipts,scenarios,i,amount,limit,window)
            alternatives.append({"Lot":plabel(p),"Action":"Volume adjustment","Adjustment %":amount,
                "Excess avoided":assessment["excess_avoided"],"Additional lost sales":assessment["lost_extra"],
                "Fill rate %":assessment["fill"]*100,"Excess risk %":assessment["excess_risk"]*100,
                "Stockout risk %":assessment["stockout_risk"]*100,
                "Status":"Admissible under current assumptions" if assessment["admissible"] else "Planner review required"})
        for label,shift in [("Postpone one month",1),("Advance one month",-1)]:
            new_index=i+shift
            if 0<=new_index<len(future):
                # Rescheduling is available only if the destination delivery month
                # can still be reached under the configured supplier lead time.
                eligible=actionable_lots(closure,[future[new_index]],
                                        np.array([units],dtype=float),lead_weeks)
                if eligible:
                    assessment=compare_reschedule(calc,initial,receipts,scenarios,i,new_index,limit,window)
                    alternatives.append({"Lot":plabel(p),"Action":label,"Adjustment %":0,
                        "Excess avoided":assessment["excess_avoided"],
                        "Additional lost sales":assessment["lost_extra"],
                        "Fill rate %":assessment["fill"]*100,"Excess risk %":assessment["excess_risk"]*100,
                        "Stockout risk %":assessment["stockout_risk"]*100,
                        "Status":"Admissible under current assumptions" if assessment["admissible"] else "Planner review required"})
        plot=go.Figure()
        for label,color in [("Admissible under current assumptions","#278a67"),("Planner review required","#da9350")]:
            part=[row for row in alternatives if row["Status"]==label]
            plot.add_trace(go.Scatter(x=[r["Additional lost sales"] for r in part],
                  y=[r["Excess avoided"] for r in part],mode="markers+text",
                  text=[f"{r['Adjustment %']:+.0f}%" if r["Action"]=="Volume adjustment" else r["Action"] for r in part],
                  textposition="top center",name=label,marker=dict(size=10,color=color)))
        plot.update_layout(xaxis_title="Additional lost sales (units)",yaxis_title="Excess avoided (units)")
        st.plotly_chart(nice_plot(plot,305),use_container_width=True)
with b:
    section("Recommended Alternatives","Feasibility first · compare both sides of the inventory trade-off")
    if not alternatives:
        st.markdown('<div class="note">No automatic supply action is proposed. '
             'If excess is flagged and no supplier change remains feasible, evaluate commercial '
             'response and monitor the next closing.</div>',unsafe_allow_html=True)
    else:
        options=pd.DataFrame(alternatives)
        sort_filter=st.selectbox("SHOW ALTERNATIVES",["All","Admissible under current assumptions","Planner review required"])
        if sort_filter!="All": options=options[options["Status"]==sort_filter]
        st.dataframe(options[["Action","Adjustment %","Excess avoided","Additional lost sales","Fill rate %","Status"]],
                     hide_index=True,use_container_width=True,height=380,
                     column_config={"Excess avoided":st.column_config.NumberColumn(format="%.0f"),
                                    "Additional lost sales":st.column_config.NumberColumn(format="%.0f"),
                                    "Fill rate %":st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("There is no proven monetary optimum: the frontier compares physical units and conditional service consequences.")

st.markdown('<div class="section-label">04 / Why Smart Launch?</div>',unsafe_allow_html=True)
c1,c2=st.columns(2,gap="medium")
with c1:
    section("Early Warning & Forecast Evidence","Read the evidence at the selected closing, not hindsight results from later versions")
    if rank.empty:
        st.info("No sufficiently comparable historical evaluation was available at this closing.")
    else:
        st.dataframe(rank,hide_index=True,use_container_width=True,
            column_config={"MAPE %":st.column_config.NumberColumn(format="%.1f"),
                           "MAE":st.column_config.NumberColumn(format="%.0f")})
with c2:
    section("Evidence Quality · Decision Trail","Forecast → uncertainty → inventory → timing → action → planner")
    evidence=[
        ("Temporal integrity","Previous planning versions and realized months only"),
        ("Forecast model",chosen),
        ("Historical errors",str(len(errs))+" realized origin–target records"),
        ("Uncertainty",scenario_source+" · 1,000 scenarios" if scenarios is not None else "Not estimable"),
        ("Inventory source","Triângulo PE or explicit manual scenario" if initial is not None else "Missing"),
        ("Production source","Triângulo PP or explicit manual scenario" if receipts is not None else "Missing"),
        ("Decision deadline","Supplier lead time, planning version and monthly receipt"),
        ("Evidence maturity","Exploratory / retrospective; prospective validation pending"),
    ]
    for title,detail in evidence:
        st.markdown(f"**{safe(title)}:** {safe(detail)}")
with st.expander("How Smart Launch works · Model assumptions / methodological limitations",expanded=(view=="Analyst")):
    st.markdown("""
**Model layer.** Analogy is based on logarithmic expanded means. MEA-P adjusts the first
three launch months using available benchmark pipeline-fill indices. Traditional models and
L'Oréal official forecasting provide comparisons. Rolling validation uses up to three months
per origin; the dashboard uses historical MAPE on comparable origin–target pairs.

**Uncertainty.** Main scenario uses 1,000 demand trajectories, normally distributed errors
with mean zero and observed sample standard deviation, clipped at zero. Centered bootstrap
is a sensitivity option. Overlapping errors do not represent independent observations.
Before enough own errors exist, exploratory cross-benchmark log-error scenarios may be used when two or more cross-benchmark residuals can be constructed; otherwise probabilities are unavailable.

**Inventory and risk.** Stock is updated by opening inventory plus planned receipts minus
satisfied demand, recording lost sales separately. Forward cover consumes later months in
sequence; beyond the horizon it repeats the last simulated demand month. Excess means
coverage at or above the configured threshold; stockout means lost demand.

**Interventions.** Only receipts outside lead time can be screened. The simulator holds demand
scenarios fixed and evaluates one lot at a time. An option passes its *model-based screening*
if it creates no new stockout warning and increases no month's conditional stockout probability
by more than 2.5 percentage points. Contractual viability, minimum lots, costs and planner
authorization remain outside the model.

**Evidence limitations.** MEA-P and the 20% operational alert level were developed after
early exploratory findings; neither is independently established as universally superior.
The full 49-configuration TCC notebook, historical backtesting of event alerts and its
out-of-sample benchmark protocol are separate validation artifacts. This dashboard does not
claim to reproduce those statistics without the same original data and code.
""")
export_forecast=pd.DataFrame({"Month":[plabel(p) for p in future],
                              "Smart Launch":pred if pred is not None else [np.nan]*horizon,
                              "Official":official if official is not None else [np.nan]*horizon})
if calc is not None:
    export_risk=pd.DataFrame({"Month":[plabel(p) for p in future[:window]],
        "Excess conditional probability":calc["excess_risk"],
        "Stockout conditional probability":calc["stockout_risk"],
        "Median forward cover (days)":calc["median_cover"]})
else:export_risk=pd.DataFrame()
out=BytesIO()
with pd.ExcelWriter(out,engine="openpyxl") as writer:
    export_forecast.to_excel(writer,sheet_name="Forecast",index=False)
    if not rank.empty:rank.to_excel(writer,sheet_name="Model ranking",index=False)
    if not export_risk.empty:export_risk.to_excel(writer,sheet_name="Risk Monitor",index=False)
    if alternatives:pd.DataFrame(alternatives).to_excel(writer,sheet_name="Lot Alternatives",index=False)
    pd.DataFrame([{"Product":product,"Closing":plabel(closure),"Model":chosen,
                 "Scenario distribution":scenario_source,"Excess threshold":limit,
                 "Alert threshold":attention/100,"Lead time weeks":lead_weeks,
                 "Critical window months":window,"Scenario count":1000 if scenarios is not None else 0,
                 "Evidence":"Conditional; planner review required"}]).to_excel(writer,sheet_name="Audit inputs",index=False)
st.download_button("Export decision evidence (.xlsx)",data=out.getvalue(),
                   file_name=f"smart_launch_{product}_{str(closure).replace('-','_')}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.caption("Smart Launch · Decision Support · Conditional probability · Planner review required. No automatic production order is created.")
