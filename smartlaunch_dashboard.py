"""Executive landing for the full Smart Launch decision workspace.

The presentation uses the validated Smart Launch calculation engine without
duplicating formulas or inserting demonstration KPI values. The complete
analytics workspace is rendered by smartlaunch_ui.py; its default view is
the executive risk-to-recommendation dashboard.
"""
from pathlib import Path
import runpy
import streamlit as st

st.session_state.setdefault("nav_page", "Central de decisões")
st.session_state.setdefault("executive_mode", "Executive")
st.session_state.setdefault("executive_horizon", "6M")
runpy.run_path(str(Path(__file__).with_name("smartlaunch_ui.py")), run_name="__main__")
