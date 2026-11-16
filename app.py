"""Entrada Streamlit: reexecuta a interface em cada rerun (sem cache de import)."""
from pathlib import Path
import runpy
import sys

# Remove módulos do Smart Launch já carregados, para que uma atualização do GitHub
# nunca misture arquivo novo com módulo antigo na memória do Streamlit Cloud.
for nome in [m for m in sys.modules if m.startswith("smartlaunch_")]:
    del sys.modules[nome]

runpy.run_path(str(Path(__file__).with_name("smartlaunch_ui.py")), run_name="__main__")
