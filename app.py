"""Smart Launch Streamlit entrypoint.

Launch Decision Center is the default executive view. The extended classic
workspace remains available with ?classic=1. No business decisions are
executed automatically.
"""
from pathlib import Path
import runpy
import sys
import streamlit as st

for name in list(sys.modules):
    if name.startswith("smartlaunch_"):
        del sys.modules[name]

classic = str(st.query_params.get("classic", "")).lower() in ("1", "true", "sim")
page = "smartlaunch_ui.py" if classic else "smartlaunch_dashboard.py"
runpy.run_path(str(Path(__file__).with_name(page)), run_name="__main__")
