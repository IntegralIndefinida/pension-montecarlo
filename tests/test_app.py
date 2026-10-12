"""Pruebas de la app de Streamlit (sin navegador, con streamlit.testing)."""

from pathlib import Path

import pytest

testing = pytest.importorskip("streamlit.testing.v1")
APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def _app():
    at = testing.AppTest.from_file(APP, default_timeout=180)
    at.run()
    return at


def test_la_app_corre_y_muestra_los_indicadores():
    at = _app()
    assert not at.exception
    etiquetas = [m.label for m in at.metric]
    assert "Probabilidad de pensionarte (AFP)" in etiquetas and len(etiquetas) == 4
    assert all(m.value not in ("—", "") for m in at.metric)


def test_cambiar_el_perfil_vuelve_a_simular():
    at = _app()
    antes = [m.value for m in at.metric]
    at.slider(key="edad").set_value(45)
    at.number_input(key="semanas").set_value(900)
    at.radio(key="sexo").set_value("Hombre")
    at.run()
    assert not at.exception
    assert [m.value for m in at.metric] != antes


def test_escenarios_y_sensibilidad():
    at = _app()
    at.select_slider(key="n_sims").set_value(1_000)
    at.run()
    at.button(key="btn_escenarios").click()
    at.run()
    assert not at.exception
    at.button(key="btn_tornado").click()
    at.run()
    assert not at.exception
    assert len(at.dataframe) >= 3     # resumen, escenarios y sensibilidad


def test_semanas_incoherentes_muestran_un_error_claro():
    at = _app()
    at.slider(key="edad").set_value(20)
    at.number_input(key="semanas").set_value(250)   # casi todo el tiempo desde los 15 años, y no cotiza hoy
    at.radio(key="cotiza_hoy").set_value("No")
    at.run()
    assert not at.exception
