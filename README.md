# Smart Launch | Supply Chain Decision Center

Executive decision-support dashboard for the L'Oréal case study. This repository is **CapstoneLoreal**, not CapstoneLorealClean.

## Start

Install dependencies from requirements.txt and run:

    streamlit run app.py

Upload a planning workbook from the sidebar, select SKU and planning version, and inspect the conditional forecast, risk and intervention assessment. The app is desktop-first.

## Excel input layouts

The app accepts three workbook layouts. All date columns can contain dates or Portuguese monthly labels such as jun/26.

1. One sheet per SKU (for example P1, A_1) with a PV monthly-version matrix. If the same sheet contains distinct **PV**, **PP**, and **PE** block headers, the app detects them. The first monthly-header row should contain at least three target-month columns. Each subsequent row starts with a planning-version month.
2. Product/block sheets: P1_PV, P1_PP, P1_PE, B_1_PV, etc. Each tab contains the same planning-version x target-month matrix.
3. Normalized sheets PV, PP and PE with columns **produto, fechamento, mes_alvo, valor**. This is the simplest stable integration format.

Optional **Base** and **BOM** sheets supply lead time and target stock coverage. If required parameters are not discovered, the sidebar exposes editable values. For the three case-study products P1/P2/P3, default values are sourced from the dissertation and must be confirmed against the actual workbook. For new SKUs, example defaults are clearly marked.

If PV is present without production or inventory, the forecast still works. Conditional stock risk and lot actions are deliberately unavailable until PP, PE or explicit manual scenario inputs are provided. An xlsx workbook with many product tabs is supported; there is no hard-coded three-product limit.

## Analysis and interpretation

- **Preprocessing:** forecasts and realized sales are separated by planning-version origin; the value of month t is read from version t+1.
- **Forecast:** MEA and MEA-P are implemented alongside official and traditional models. Early model ranking uses eligible rolling-origin errors and MAPE. A prelaunch projection without sufficient own-sales data is labelled provisional.
- **Uncertainty:** 1,000 Normal(0,s) scenarios from known historical residuals, with an optional centered bootstrap. Where own errors are unavailable, the app may generate exploratory multiplicative scenarios from cross-benchmark log errors. The two approaches must not be equated.
- **Inventory:** stock and lost sales are simulated using the closing balance and planned receipts; forward cover depletes successive future demands using a 30-day convention.
- **Alerts:** conditional probabilities of excess/rupture relative to the configured coverage and alert thresholds; the 20% alert level is exploratory, not independently calibrated.
- **Actionability:** one-lot interventions require a decision deadline outside lead time, and are assessed using identical simulated demand across alternatives. The screening checks no new stockout warning and no increase greater than 2.5 percentage points in any month's probability.
- **Trade-off:** excess avoided, additional lost sales and fill rate are compared in physical units. No monetary optimum is claimed without cost data.

Export the current forecast, evidence, alternatives and assumptions to Excel.

## Alignment limitations

The supplied thesis v5 describes 49 forecasting configurations, a specific notebook, retrospective verification of alert precision, and frozen-model out-of-sample benchmark testing. The current web implementation is an independent interactive frontend and **does not claim numeric equivalence** to the thesis tables until both are run on the same Triângulo version and reconciled. Its parsers support the listed layouts; a differently structured original corporate Triângulo may require a connector/adapter.

This is a decision-support tool: no recommendation is an authorized production instruction. Contract terms, minimum lots, changing supplier lead times, fulfillment rules and prospective validation remain planner responsibilities.

## Tests

    python -m unittest discover -s tests -v

CI also checks Python compilation on pushes to main.
