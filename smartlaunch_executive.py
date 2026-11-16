"""Desktop-first Smart Launch executive decision surface.

The view never invents sample KPIs: it reads the same forecast, risk and inventory
arrays already computed by smartlaunch_core. Planner approval remains external.
"""
import html
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from smartlaunch_core import LIM, N, AVISO, ALERTA, label, known, forecast, MODEL, SHEETS
from smartlaunch_priority import card_summary
from smartlaunch_supply import future_lots, supply_diagnosis
from smartlaunch_impact import (
    editable_lots, outcome_metrics, evaluate_lot_options, tcc_check,
    historical_mape_vs_official,
)
from smartlaunch_visuals import forecast_figure


EXECUTIVE_CSS = """
<style>
/* Desktop layout: real dashboard width rather than a narrow article. */
@media(min-width: 1024px){
  .block-container{max-width:1840px!important;padding-top:1.05rem!important;
      padding-left:2.2rem!important;padding-right:2.2rem!important;}
}
.stApp{background:#F4F7FB!important;color:#102A43;}
[data-testid="stSidebar"]{background:#102A43!important;border-right:1px solid #24455f!important;}
[data-testid="stSidebar"] *{color:#e8f0fb;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:#dce7f7;}
[data-testid="stSidebar"] .stRadio label{color:#e8f0fb;}
[data-testid="stSidebar"] div[data-baseweb="select"] *{color:#102A43;}
[data-testid="stHeader"]{background:#F4F7FB!important;}
h1{font-size:2rem!important;letter-spacing:-.035em!important;margin-bottom:.2rem!important;}
h2,h3{letter-spacing:-.03em!important;color:#102A43!important;}
[data-testid="stMetric"]{background:#fff;border:1px solid #e2e9f3;
  border-radius:12px!important;padding:10px 16px!important;min-height:102px;
  box-shadow:none!important;}
[data-testid="stMetricLabel"]{color:#536881!important;font-size:.82rem!important;}
[data-testid="stMetricValue"]{font-size:1.72rem!important;font-weight:760!important;
  color:#102A43!important;line-height:1.1!important;}
[data-testid="stMetricDelta"]{font-size:.75rem!important;}
[data-testid="stVerticalBlockBorderWrapper"]>div{border:1px solid #e2e9f3!important;
  border-radius:13px!important;box-shadow:none!important;}
[data-testid="stPlotlyChart"]{border:0!important;}
.stButton button{border-radius:8px!important;min-height:37px!important;}
.stButton button[kind="primary"]{background:#2563EB!important;border-color:#2563EB!important;}
.sl-kicker{font-size:11px;font-weight:800;letter-spacing:.11em;color:#4f6a88;margin:0;}
.sl-reco{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(210px,.7fr);
  gap:18px;align-items:center;background:#102A43;color:white;padding:17px 22px;
  border-radius:13px;margin:7px 0 8px;}
.sl-reco .sl-tag{font-size:10px;letter-spacing:.11em;font-weight:800;color:#a6cafa;}
.sl-reco h2{color:white!important;margin:5px 0!important;font-weight:790!important;
  font-size:1.38rem!important;line-height:1.2;}
.sl-reco p{font-size:.87rem;line-height:1.5;color:#dce9f7;margin:5px 0;}
.sl-reco .sl-response{border-left:1px solid #50718a;padding-left:19px;}
.sl-reco .sl-response h3{font-size:1.02rem!important;color:#fff!important;margin:7px 0;}
.sl-reco .sl-response small{color:#bed0e5;font-size:.77rem;}
.sl-process{font-size:11px;color:#5a708a;letter-spacing:.015em;padding:3px 2px 8px;}
.sl-process b{color:#173858;font-weight:780;}
.sl-section{font-size:13px!important;text-transform:uppercase;letter-spacing:.07em;
  font-weight:780!important;color:#102A43;padding-top:4px;margin:0;}
.sl-panel{background:#fff;border:1px solid #e1e9f2;border-radius:12px;padding:9px 12px 1px;}
.sl-panel-title{font-size:12px;font-weight:780;color:#102A43;letter-spacing:.035em;
  padding:2px 0 0;}
.sl-note{font-size:11px;line-height:1.5;color:#61758f;margin:2px 0 8px;}
.sl-subline{display:flex;gap:14px;flex-wrap:wrap;color:#546b84;font-size:12px;padding:3px 1px 9px;}
.sl-step{background:#fff;border:1px solid #e1e9f2;border-radius:12px;
  padding:14px 17px;min-height:90px;margin:4px 0;}
.sl-step strong{color:#102A43;}
.sl-step small{color:#586f88;font-size:12px;line-height:1.5;}
.sl-safe{background:#effaf3;color:#166b3e;padding:4px 8px;border-radius:6px;font-size:11px;}
.sl-exploratory{background:#fff8e8;color:#936316;padding:4px 8px;border-radius:6px;font-size:11px;}
@media(max-width:1050px){
  .sl-reco{grid-template-columns:1fr;}
  .sl-reco .sl-response{border-left:0;border-top:1px solid #50718a;padding:12px 0 0;}
}
</style>
"""


def _number(v):
    return "—" if v is None or not np.isfinite(v) else f"{v:,.0f}".replace(",", ".")


def _percent(v):
    return "—" if v is None or not np.isfinite(v) else f"{float(v):.1f}%".replace(".", ",")


def _future(res, horizon):
    total = len(res["months"])
    return min(total, 3 if horizon == "3M" else 6 if horizon == "6M" else total)


def _risk_frame(res, count):
    months = res["months"][:count]
    active = np.asarray(res["active"][:count], dtype=bool)
    evaluated = np.asarray(res.get("evaluated", np.ones(len(res["months"]), bool))[:count], dtype=bool)
    ex = np.mean(np.asarray(res["cov"][:, :count]) >= LIM, axis=0)*100
    ru = np.mean(np.asarray(res["lost"][:, :count]) > 0, axis=0)*100
    ex[~evaluated] = np.nan
    return pd.DataFrame({"Mês":[label(m) for m in months],
                         "Período":months, "Excesso":ex, "Ruptura":ru,
                         "Crítica":active, "Avaliável":evaluated})


def _risk_plot(frame):
    chart=go.Figure()
    for col, color in (("Excesso","#DC2626"),("Ruptura","#F59E0B")):
        chart.add_trace(go.Bar(
            x=frame["Mês"],y=frame[col],name=col,
            marker_color=color,opacity=.88,
            hovertemplate="%{x}<br>"+col+": %{y:.1f}%<extra></extra>"
        ))
    chart.add_hline(y=20,line_color="#586c85",line_dash="dash",line_width=1,
                    annotation_text="Alerta >20%",annotation_font_size=10)
    chart.update_layout(
        template="plotly_white",height=225,barmode="group",hovermode="x unified",
        font=dict(color="#102A43",size=11),margin=dict(l=4,r=4,t=8,b=12),
        paper_bgcolor="#fff",plot_bgcolor="#fff",
        yaxis=dict(range=[0,105],title=None,ticksuffix="%",gridcolor="#eff3f8"),
        xaxis=dict(title=None,showgrid=False),legend=dict(orientation="h",y=1.18,x=0)
    )
    return chart


def _coverage_plot(res,count):
    xs=[label(m) for m in res["months"][:count]]
    values=[]
    for j in range(count):
        finite=res["cov"][:,j]
        finite=finite[np.isfinite(finite)]
        is_evaluated=bool(res.get("evaluated",np.ones(len(res["months"]),bool))[j])
        values.append(float(np.median(finite)) if len(finite) and is_evaluated else None)
    chart=go.Figure()
    chart.add_trace(go.Scatter(
        x=xs,y=values,mode="lines+markers",name="Median forward cover",
        line=dict(color="#2563EB",width=3),marker=dict(size=7),
        fill="tozeroy",fillcolor="rgba(37,99,235,.065)",
        hovertemplate="%{x}<br>Median cover: %{y:.0f} days<extra></extra>"
    ))
    chart.add_hline(y=LIM,line_color="#DC2626",line_dash="dash",line_width=1.3,
                    annotation_text=str(LIM)+"-day operational threshold",
                    annotation_position="top left",annotation_font_size=10)
    chart.update_layout(
        template="plotly_white",height=158,margin=dict(l=5,r=8,t=3,b=13),
        hovermode="x",showlegend=False,paper_bgcolor="#fff",plot_bgcolor="#fff",
        font=dict(color="#102A43",size=11),
        xaxis=dict(title=None,showgrid=False),
        yaxis=dict(title=None,gridcolor="#eff3f8",rangemode="tozero")
    )
    return chart


def _headline(summary,valid):
    if not valid:
        return "Simulation unavailable", "Review missing evidence before acting", "Planner review required"
    if summary["alert"]:
        risk=summary["type"].lower()
        first=label(summary["first_month"])
        title="High "+("excess" if risk=="excesso" else "stockout")+" risk detected"
        if summary["first_target_has_changeable_lot"]:
            return title, ("Risk indicated for "+first+". A relevant production lot has a theoretical "
                           "change window; verify the supplier cut-off before comparing interventions."), "Evaluate supply alternatives"
        if risk=="excesso":
            return title, ("Risk indicated for "+first+". No relevant lot is changeable "
                           "within the theoretical lead-time window; review commercial actions and monitor."), "Commercial action + monitoring"
        return title, ("Risk indicated for "+first+". No relevant lot is changeable "
                       "before the event; review allocations and exceptions with Supply Chain."), "Review allocation + exceptions"
    if summary.get("warning"):
        return "Early warning — monitor",("Model-based warning indicated for "+
                label(summary["warning_month"])+". Reassess at the next closing."),"Monitor next closing"
    return "No alert in the critical window", "No threshold alert was detected in the evaluated months. Continue monthly monitoring.", "Continue monitoring"


def _decision_trail(summary, res, close, count):
    if not summary or res is None: return
    st.markdown("#### WHY THIS RECOMMENDATION?")
    lots=future_lots(res,close)
    lead=int(res["ltm"])
    peak = summary.get("peak_probability") if summary.get("alert") else summary.get("warning_probability")
    if summary.get("alert"):
        first=label(summary["first_month"])
        month=summary["first_month"]
        usable=[x for x in lots if x["month"]<=month and x["available_for_analysis"]]
        deadline=label(summary["deadline"]) if summary["deadline"] is not None else "—"
        assessment=("Theoretical change window for "+str(len(usable))+" lot(s)"
                    if usable else "No relevant changeable lot before first risk")
        rows=[
            ("01 / RISK", summary["type"]+" · "+_percent(100*peak), "Simulated conditional risk, not a calibrated true probability."),
            ("02 / TIMING", first,"First threshold alert in the critical decision window."),
            ("03 / ACTIONABILITY", assessment,
             str(lead)+"-month rounded lead time; theoretical cut-off "+deadline+". Supplier confirmation required."),
            ("04 / ALTERNATIVES", "Review supply / commercial responses",
             "Compare interventions only when relevant lots remain within a theoretical window."),
            ("05 / TRADE-OFF", "Excess avoided versus lost sales",
             "Evaluate fill rate, shortage risk and inventory under identical demand scenarios."),
            ("06 / RECOMMENDATION", _headline(summary,True)[2],
             "Planner review required before any operational change."),
        ]
    else:
        rows=[
            ("01 / RISK","No critical risk signal","No alert above the exploratory 20% trigger."),
            ("02 / TIMING","Next monthly closing","Monitor changes as actual demand becomes available."),
            ("03 / ACTIONABILITY","No intervention proposed","Do not manufacture a decision when evidence is insufficient."),
            ("04 / ALTERNATIVES","Maintain plan / revisit","Explore alternatives only if new evidence warrants."),
            ("05 / TRADE-OFF","Monitor service and inventory","Avoid unsupported claims of improvement."),
            ("06 / RECOMMENDATION","Planner review required","Decision remains with the planner."),
        ]
    left,right=st.columns(2)
    for i,(stage,title,detail) in enumerate(rows):
        with (left if i%2==0 else right):
            st.markdown(
                '<div class="sl-step"><div class="sl-kicker">'+html.escape(stage)+
                '</div><strong>'+html.escape(title)+'</strong><br><small>'+
                html.escape(detail)+'</small></div>', unsafe_allow_html=True)


def render_executive_dashboard(
    product,close,blocks,results,errors,rankings,ready_count,horizon,mode,
    on_open_simulator,on_open_analytics
):
    """Risk → Timing → Actionability → Alternatives → Trade-off → Recommendation."""
    st.markdown(EXECUTIVE_CSS,unsafe_allow_html=True)
    res=results.get(product)
    summary=card_summary(product,res,close) if res is not None else None
    title,reason,response=_headline(summary,res is not None)
    caption=(f"{product} · Closing {label(close)} · "+
             ("Conditional probability from simulated scenarios" if res is not None
              else "Probability unavailable — missing simulated scenarios"))
    st.markdown('<div class="sl-reco"><div><div class="sl-tag">SMART LAUNCH RECOMMENDATION · DECISION SUPPORT</div>'+
                '<h2>'+html.escape(title)+'</h2><p>'+html.escape(reason)+
                '</p><p>'+html.escape(caption)+'</p></div>'+
                '<div class="sl-response"><div class="sl-tag">RECOMMENDED RESPONSE</div>'+
                '<h3>'+html.escape(response)+'</h3><small>Planner review required<br>'+
                'Admissible only under current assumptions</small></div></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="sl-process"><b>RISK</b> &nbsp;→&nbsp; TIMING &nbsp;→&nbsp; '+
                'ACTIONABILITY &nbsp;→&nbsp; ALTERNATIVES &nbsp;→&nbsp; TRADE-OFF '+
                '&nbsp;→&nbsp; <b>RECOMMENDATION</b></div>',unsafe_allow_html=True)
    if res is not None:
        supplier_window=("First risk: "+label(summary["first_month"]) if summary.get("alert")
                         else "No critical alert")
        supplier_deadline=("Estimated lot deadline: "+label(summary["deadline"])
                           if summary.get("alert") and summary.get("deadline") is not None
                           else "No relevant lot deadline")
        st.markdown('<div class="sl-subline"><span><b>'+html.escape(supplier_window)+
                    '</b></span><span>'+html.escape(supplier_deadline)+
                    '</span><span>Supplier lead time: '+str(res["ltm"])+
                    ' rounded months</span></div>',unsafe_allow_html=True)
    st.markdown('<div class="sl-section">EXECUTIVE KPIs</div>',unsafe_allow_html=True)
    if res is None:
        st.info("Decision Support is incomplete for "+product+": "+errors.get(product,"Insufficient forecast errors")+
                ". Missing simulation is not zero risk.")
        row=st.columns(5)
        for col,key in zip(row,("Excess risk","Median cover","Forecast error","Actionable lots","Fill rate")):
            col.metric(key,"—")
        st.button("Inspect evidence",on_click=on_open_analytics)
        return
    count=_future(res,horizon)
    whole=_risk_frame(res,len(res["months"]))
    critical=whole[whole["Crítica"]]
    ex=critical["Excesso"].dropna()
    ru=critical["Ruptura"].dropna()
    peak_ex=float(ex.max()) if len(ex) else None
    peak_ru=float(ru.max()) if len(ru) else None
    first_alert=summary.get("first_month") if summary.get("alert") else None
    risk_target=(res["months"].index(first_alert) if first_alert in res["months"]
                 else next((i for i,p in enumerate(res["months"])
                            if res["active"][i] and
                            res.get("evaluated",np.ones(len(res["months"]),bool))[i]),0))
    covers=np.asarray(res["cov"][:,risk_target],dtype=float)
    covers=covers[np.isfinite(covers)]
    median_cover=float(np.median(covers)) if len(covers) and bool(
        res.get("evaluated",np.ones(len(res["months"]),bool))[risk_target]) else None
    lots=future_lots(res,close)
    actionable=[x for x in lots if x["available_for_analysis"] and
                (first_alert is None or x["month"]<=first_alert)]
    detail=rankings[product][0] if product in rankings else pd.DataFrame()
    model=st.session_state.get("operational_"+product,MODEL[product])
    accuracy=historical_mape_vs_official(detail,model)
    try:
        outcomes=outcome_metrics(res,res["production"],risk_target)
        service=outcomes["fill_rate_pct"]
    except (ValueError,KeyError,IndexError):
        service=None
    cols=st.columns(5)
    cols[0].metric("Excess risk · peak",_percent(peak_ex),help="Highest model-based monthly excess probability within the critical window.")
    cols[1].metric("Median cover · first risk",(_number(median_cover)+" d") if median_cover is not None else "—",
                   help="Projected median forward cover at the first alerted month, or first evaluable month.")
    cols[2].metric("Forecast error · MAPE",_percent(accuracy["mape_operacional"]) if accuracy else "—",
                   help="Rolling historical MAPE for comparable origin/target pairs. This is not the fixed TCC summary.")
    cols[3].metric("Actionable lots · theoretical",str(len(actionable)),help="Lot deadlines based on rounded monthly lead time, not a contract authorization.")
    cols[4].metric("Fill rate · simulated",_percent(service),help="Scenario-based service within the model critical window; not observed service.")
    if accuracy is not None:
        st.markdown('<div class="sl-subline"><span>Official MAPE: <strong>'+
                    html.escape(_percent(accuracy["mape_oficial"]))+
                    '</strong></span><span>Comparisons: '+str(accuracy["pares"])+
                    ' matched forecast points</span><span>Models are not automatically changed</span></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="sl-subline">Forecast error unavailable for this closing; no comparative superiority is inferred.</div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="sl-section">DEMAND &amp; RISK OUTLOOK</div>',unsafe_allow_html=True)
    c1,c2=st.columns([1.65,1],gap="medium")
    with c1:
        st.markdown('<div class="sl-panel-title">DEMAND FORECAST</div>',unsafe_allow_html=True)
        realized=known(blocks[SHEETS[product]]["PV"],close)
        months=res["months"][:count]
        try:
            official=forecast(product,months,close,blocks,model="Oficial")
        except (ValueError,KeyError,IndexError,TypeError):
            official=None
        fig=forecast_figure(
            realized,months,res["center"][:count],official,res["dm"][:,:count],
            close,label,critical_count=min(res["window"],count),
            percentile_bounds=(2.5,97.5))
        fig.update_layout(height=231,margin=dict(l=10,r=8,t=7,b=35),
                          font=dict(color="#102A43",size=11),
                          legend=dict(orientation="h",y=-.27,x=0,font=dict(size=10)))
        for trace in fig.data:
            if trace.name=="Previsão em uso":trace.name="Smart Launch · "+model
            if trace.name=="Previsão Oficial":trace.line.color="#71849a"
        st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.markdown('<div class="sl-panel-title">RISK MONITOR</div>',unsafe_allow_html=True)
        st.plotly_chart(_risk_plot(_risk_frame(res,count)),use_container_width=True)
    st.markdown('<div class="sl-subline"><span>Forecast interval: simulated P2.5–P97.5, not calibrated</span>'+
                '<span>Risk = conditional scenario frequency</span>'+
                '<span>Alert trigger &gt;20%; watch &gt;2.5% (exploratory)</span></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="sl-section">INVENTORY COVERAGE OUTLOOK</div>',unsafe_allow_html=True)
    st.plotly_chart(_coverage_plot(res,count),use_container_width=True)
    st.markdown('<div class="sl-subline"><span>180 days = operational threshold, not a universal statistical cut-off</span>'+
                '<span>Missing forward cover is not zero risk</span>'+
                '<span>Initial inventory: '+_number(float(res["e0"]))+' units</span>'+
                '<span>Rounded supplier LT: '+str(res["ltm"])+' months</span></div>',
                unsafe_allow_html=True)

    st.divider()
    st.markdown("### Decision Simulator")
    st.caption("Below the executive fold · same "+str(N)+" simulated demand scenarios for each intervention. "+
               "Changes are hypothetical until supplier, commercial and planner approval.")
    editable=editable_lots(res,close)
    if not editable:
        st.info("No theoretically editable production lot in this closing. "
                +supply_diagnosis(res,close)["guidance"]+
                " Consider commercial response and inventory reallocation; do not simulate cancelling a nonexistent lot.")
    else:
        preferred=next((x for x in editable if first_alert is not None and x["month"]<=first_alert),editable[0])
        a,b,c=st.columns([1,1,1.5])
        with a:
            lot_idx=st.selectbox("LOT · delivery month",options=[x["index"] for x in editable],
                                 format_func=lambda i:label(res["months"][i]),
                                 index=[x["index"] for x in editable].index(preferred["index"]),
                                 key="exec_lot")
        with b:
            candidates=[i for i in range(len(res["months"]))
                        if res["active"][i] and res.get("evaluated",np.ones(len(res["months"]),bool))[i]]
            if candidates:
                target=st.selectbox("TARGET MONTH",candidates,
                       index=candidates.index(risk_target) if risk_target in candidates else 0,
                       format_func=lambda i:label(res["months"][i]),key="exec_target")
            else:
                target=None
        with c:
            adjustment=st.slider("LOT ADJUSTMENT (%)",-100,50,0,5,key="exec_adjust",
                                 help="Hypothetical volume change; does not place or amend production orders.")
        lot=next(x for x in editable if x["index"]==lot_idx)
        st.caption("Estimated deadline: "+label(lot["deadline"])+
                   (" · boundary month, exact cut-off unknown" if lot["boundary"] else
                    " · theoretical open window")+
                   ". Supplier and planner review required.")
        if target is None:
            st.warning("No evaluated target month available to compute comparable impact.")
        else:
            baseline_plan=np.asarray(res["production"],dtype=float)
            plan=baseline_plan.copy()
            plan[lot_idx]=round(plan[lot_idx]*(1+adjustment/100))
            base_metrics=outcome_metrics(res,baseline_plan,target)
            alt_metrics=outcome_metrics(res,plan,target)
            check=tcc_check(res,plan)
            admissible=(not check["new_rupture"] and
                         check["max_rupture_rise"]<=.025 if adjustment<0 else
                         not check["new_excess"] if adjustment>0 else True)
            excess_avoided=base_metrics["expected_excess_units"]-alt_metrics["expected_excess_units"]
            additional_lost=alt_metrics["expected_lost_units"]-base_metrics["expected_lost_units"]
            v=st.columns(5)
            v[0].metric("Potential excess reduction",_number(excess_avoided)+" un.")
            v[1].metric("Additional lost sales",_number(additional_lost)+" un.")
            v[2].metric("Fill rate · scenario",_percent(alt_metrics["fill_rate_pct"]))
            v[3].metric("Excess risk · target",_percent(alt_metrics["risk_excess_target_pct"]),
                        delta=(f'{alt_metrics["risk_excess_target_pct"]-base_metrics["risk_excess_target_pct"]:+.1f} p.p.'),
                        delta_color="inverse")
            v[4].metric("Stockout risk · target",_percent(alt_metrics["risk_rupture_target_pct"]),
                        delta=(f'{alt_metrics["risk_rupture_target_pct"]-base_metrics["risk_rupture_target_pct"]:+.1f} p.p.'),
                        delta_color="inverse")
            status=("Admissible under current assumptions" if admissible else
                    "Not admissible under current assumptions")
            st.caption(status+" · Planner review required. "+
                       "Supplier LT and minimum lots may override theoretical eligibility.")
            st.markdown("#### Recommended Alternatives · compare trade-offs")
            options,_=evaluate_lot_options(res,lot_idx,target)
            view=options[["Alternativa","Excesso potencialmente evitado (un.)",
                          "Vendas perdidas adicionais (un.)","Fill rate simulado (%)",
                          "Dentro do critério do TCC",
                          "Não dominada (excesso × perda)"]].copy()
            view["Status"]=np.where(view["Dentro do critério do TCC"],
                                    "Admissible under current assumptions",
                                    "Fails simulated criteria")
            view=view.drop(columns=["Dentro do critério do TCC"])
            st.dataframe(view,hide_index=True,use_container_width=True)
            no_lost=options[(options["Dentro do critério do TCC"])&
                            (options["Vendas perdidas adicionais (un.)"]<=1e-6)&
                            (options["Excesso potencialmente evitado (un.)"]>1e-6)]
            if not no_lost.empty:
                best=no_lost.sort_values("Excesso potencialmente evitado (un.)",ascending=False).iloc[0]
                st.caption("Best trade-off within the *zero additional lost sales* subset: "+
                           str(best["Alternativa"])+". This is a conditional comparison "+
                           "of tested options, not a universal or authorized decision.")
            else:
                st.caption("No tested admissible reduction is free of additional expected lost sales. "
                           "The planner should compare the full frontier.")
            if base_metrics["extrapolated_months"]:
                st.caption("Excess units use an extrapolated six-month demand tail beyond the recorded horizon ("+
                           str(base_metrics["extrapolated_months"])+" month(s)). Interpret as approximate.")
        st.button("Open detailed alternatives and decision frontier",on_click=on_open_simulator)
    st.divider()
    st.markdown("### Why Smart Launch?")
    if mode=="Executive":
        st.write("Smart Launch adds a traceable decision-support layer between forecasting, "
                 "inventory exposure, supplier timing and planner-led action. "
                 "The framework does not execute or approve production changes.")
    st.markdown("#### Early Warning Performance · historical TCC study")
    ea,eb,ec=st.columns(3)
    ea.metric("Smart Launch · alerts before LT","2 / 3")
    eb.metric("Official benchmark · alerts before LT","0 / 3")
    ec.metric("Historical alert precision","48%")
    st.caption("Fixed exploratory/retrospective TCC study results, not recalculated from the uploaded Triângulo. "+
               "Only three observed excess episodes; no prospective validation or realized savings demonstrated.")
    if mode!="Executive":
        _decision_trail(summary,res,close,count)
    if mode=="Analyst":
        st.markdown("### Evidence Quality & Model Assumptions")
        x=st.columns(4)
        x[0].metric("Temporal integrity","Reconstructed")
        x[1].metric("Development choices","Exploratory")
        x[2].metric("Observed alert precision · TCC","48%")
        x[3].metric("Prospective validation","Pending")
        st.caption("The TCC's P1–P3 development informed MEA-P and the exploratory 20% trigger; "
                   "the 48% figure is a historical study result, not recalculated from this upload.")
        with st.expander("MODEL ASSUMPTIONS · validation and limits"):
            st.markdown(
                "- Historical forecast errors are limited and simulated risk is not calibrated.\n"
                "- The base assumption is Normal(0, s) unless changed in the analyst workflow.\n"
                "- Inventory coverage is forward-looking and uses a 180-day operational threshold.\n"
                "- Supplier dates are approximated at a monthly granularity.\n"
                "- No prospective evidence of inventory savings or planner execution is claimed.\n"
                "- MEA-P development outcomes are exploratory, not independent validation.\n"
                "- Partially external historical comparisons are not fully out-of-sample.\n"
                "- Decisions remain with the planner."
            )
    st.button("View model performance, backtesting and evidence",on_click=on_open_analytics)
