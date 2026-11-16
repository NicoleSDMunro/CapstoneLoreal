"""Teste de navegação das três áreas e processamento sem dados empresariais."""
import runpy
from streamlit.testing.v1 import AppTest

samples = runpy.run_path("tests/test_smoke.py")
at = AppTest.from_file("../app.py", default_timeout=120)

at.run()
assert not at.exception, [str(e) for e in at.exception]
assert len(at.radio) >= 1, "Navegação lateral ausente"

at.session_state["triangulo_file_bytes"] = samples["buf"].getvalue()
at.session_state["triangulo_file_name"] = "triangulo_sintetico.xlsx"
at.run()
assert not at.exception, [str(e) for e in at.exception]
assert any("Central de decisões" in str(t.value) for t in at.title)

# Executive cockpit: desktop filters, six-SKU workbook and deeper analysis.
for label_name in ("PRODUCT", "CLOSING · PLAN REVISION", "HORIZON", "VIEW"):
    assert any(item.label == label_name for item in at.selectbox), label_name
at.session_state["triangulo_file_bytes"] = samples["buf_multi"].getvalue()
at.run()
assert not at.exception, [str(e) for e in at.exception]
product_filter=next(x for x in at.selectbox if x.label == "PRODUCT")
assert "P6" in product_filter.options, product_filter.options
product_filter.set_value("P4").run()
assert not at.exception, [str(e) for e in at.exception]
mode_filter=next(x for x in at.selectbox if x.label == "VIEW")
mode_filter.set_value("Analyst").run()
assert not at.exception, [str(e) for e in at.exception]

nav = next(r for r in at.radio if r.label == "Navegação")
nav.set_value("Análise do produto").run()
assert not at.exception, [str(e) for e in at.exception]
assert any("Decisão de abastecimento" in str(t.value) for t in at.title)

views = [radio for radio in at.radio if radio.label == "O que deseja avaliar?"]
assert len(views) == 1, "Subnavegação de produto não encontrada"
views[0].set_value("Riscos por mês").run()
assert not at.exception, [str(e) for e in at.exception]

views = [radio for radio in at.radio if radio.label == "O que deseja avaliar?"]
views[0].set_value("Previsão × Oficial").run()
assert not at.exception, [str(e) for e in at.exception]
views = [radio for radio in at.radio if radio.label == "O que deseja avaliar?"]
views[0].set_value("Decisão e alternativas").run()
assert not at.exception, [str(e) for e in at.exception]

nav = next(r for r in at.radio if r.label == "Navegação")
nav.set_value("Resultados e confiabilidade").run()
assert not at.exception, [str(e) for e in at.exception]
assert any("Resultados e confiabilidade" in str(t.value) for t in at.title)

print("UI PASS: central, análise do produto, riscos e evidências históricas")
