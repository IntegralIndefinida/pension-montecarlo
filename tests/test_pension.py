"""Pruebas de acumulación, desacumulación y reglas de los regímenes."""

import numpy as np
import pytest

from pension_mc import accumulation as A
from pension_mc import decumulation as D
from pension_mc import regimes as G
from pension_mc.config import ARTEFACTOS


@pytest.fixture
def mortalidad_lineal(monkeypatch):
    """l(x) cae linealmente de 1.000 a los 60 años a 0 a los 70 (para ambos sexos)."""
    edades = np.arange(15, 112, dtype=float)
    lx = np.interp(edades, [15, 60, 70], [1000, 1000, 0])
    monkeypatch.setattr(D, "_lx", lambda sexo: (edades, lx))
    D.factor_anualidad.cache_clear()
    yield
    D.factor_anualidad.cache_clear()


# --------------------------------------------------------------------------- Desacumulación
def test_supervivencia_interpola_linealmente(mortalidad_lineal):
    p = D.supervivencia(60, "Mujer")
    assert p[0] == 1 and p[60] == pytest.approx(0.5) and p[120] == pytest.approx(0)


def test_factor_sin_interes_es_la_suma_de_supervivencias(mortalidad_lineal):
    # Σ_{m=0}^{120} (1 − m/120) = 60,5 meses-persona
    assert D.factor_anualidad(60, "Hombre", tasa=0.0) == pytest.approx(13 / 12 * 60.5)


def test_factor_responde_a_tasa_crecimiento_y_conyuge(mortalidad_lineal):
    base = D.factor_anualidad(62, "Hombre", tasa=0.04)
    assert D.factor_anualidad(62, "Hombre", tasa=0.06) < base
    assert D.factor_anualidad(62, "Hombre", tasa=0.04, crecimiento=0.01) > base
    assert D.factor_anualidad(62, "Hombre", tasa=0.04, conyuge=("Mujer", 60)) > base
    np.testing.assert_allclose(D.mesada(np.array([base * 2]), 62, "Hombre", tasa=0.04), [2.0])


@pytest.mark.skipif(not (ARTEFACTOS / "mortalidad_rv08.parquet").exists(), reason="sin datos RV08")
def test_factor_con_rv08_coincide_con_la_esperanza_de_vida():
    import pandas as pd
    D.factor_anualidad.cache_clear()
    t = pd.read_parquet(ARTEFACTOS / "mortalidad_rv08.parquet").set_index(["sexo", "edad"])
    for sexo, edad in [("Mujer", 57), ("Hombre", 62)]:
        anios = D.factor_anualidad(edad, sexo, tasa=0.0) * 12 / 13 / 12
        # pagos anticipados mensuales: e(x) completa + ~1/24 de año
        assert anios == pytest.approx(t.loc[(sexo, edad), "ex"] + 1 / 24, abs=0.1)


# --------------------------------------------------------------------------- Acumulación
def test_aportes_y_voluntarios():
    ibc = np.array([[1000.0, 1000.0, 2000.0]])
    cotiza = np.array([[True, False, True]])
    np.testing.assert_allclose(A.aportes(ibc, cotiza), [[115.0, 0.0, 230.0]])
    np.testing.assert_allclose(A.aportes(ibc, cotiza, voluntario_pct=0.05), [[165.0, 0.0, 330.0]])


def test_saldo_sin_rentabilidad_y_con_rentabilidad_constante():
    a = np.ones((2, 12))
    np.testing.assert_allclose(A.saldo(a, np.zeros((2, 12)))[:, -1], 12)
    r = 0.01
    final = A.saldo(a, np.full((2, 12), r), saldo_inicial=100)[:, -1]
    esperado = 100 * (1 + r) ** 12 + ((1 + r) ** 12 - 1) / r
    np.testing.assert_allclose(final, esperado)


def test_mensualizar():
    np.testing.assert_array_equal(A.mensualizar(np.array([[1, 2]])), [[1] * 12 + [2] * 12])


# --------------------------------------------------------------------------- Requisitos
@pytest.mark.parametrize("regimen, sexo, anio, esperado", [
    ("rpm", "Mujer", 2025, 1300), ("rpm", "Mujer", 2026, 1250), ("rpm", "Mujer", 2030, 1150),
    ("rpm", "Mujer", 2036, 1000), ("rpm", "Mujer", 2050, 1000), ("rpm", "Hombre", 2040, 1300),
    ("rais", "Mujer", 2025, 1150), ("rais", "Mujer", 2026, 1135), ("rais", "Mujer", 2035, 1000),
    ("rais", "Hombre", 2040, 1150),
])
def test_semanas_requeridas(regimen, sexo, anio, esperado):
    assert G.semanas_requeridas(regimen, sexo, anio) == esperado


# --------------------------------------------------------------------------- RAIS
def test_rais_clasifica_capital_garantia_y_devolucion(mortalidad_lineal):
    smmlv = 100.0
    f_min = D.factor_anualidad(57, "Mujer", 0.04, 0.01)
    f = D.factor_anualidad(57, "Mujer", 0.04, 0.0)
    saldo = np.array([3 * smmlv * f, 0.5 * smmlv * f_min, 0.5 * smmlv * f_min])
    semanas = np.array([300.0, 1100.0, 900.0])
    r = G.rais(saldo, semanas, edad=57, sexo="Mujer", anio=2040, smmlv=smmlv, tasa=0.04, crecimiento_beneficios=0.01)
    assert list(r["estado"]) == ["capital_suficiente", "garantia_minima", "devolucion"]
    np.testing.assert_allclose(r["mesada"], [300.0, 100.0, 0.0])
    np.testing.assert_allclose(r["costo_garantia"], [0, 0.5 * smmlv * f_min, 0])
    np.testing.assert_allclose(r["devolucion"], [0, 0, saldo[2]])


def test_rais_sin_edad_no_hay_garantia(mortalidad_lineal):
    r = G.rais(np.array([0.0]), np.array([2000.0]), edad=50, sexo="Hombre", anio=2040, smmlv=100.0, tasa=0.04)
    assert r["estado"].iloc[0] == "devolucion"


# --------------------------------------------------------------------------- RPM
def test_tasa_de_reemplazo_rpm():
    smmlv = 1.0
    t = G.tasa_reemplazo_rpm(np.array([1.0, 10.0, 25.0, 1.0, 1.0, 20.0]),
                             np.array([1300, 1300, 1300, 1600, 2500, 2500]), 1300, smmlv)
    np.testing.assert_allclose(t, [0.65, 0.605, 0.55, 0.74, 0.80, 0.705])  # 70,5 %: tope inferior legal


def test_ibl_ultimos_diez_anios_o_toda_la_vida():
    ibc = np.array([[3.0] * 60 + [1.0] * 120] * 2)
    cotiza = np.ones_like(ibc, dtype=bool)
    sem = np.array([1000.0, 1300.0])
    np.testing.assert_allclose(G.ibl(ibc, cotiza, sem), [1.0, (180 + 120) / 180])
    # meses sin cotizar no cuentan: los últimos 120 cotizados
    cotiza2 = cotiza.copy(); cotiza2[0, -60:] = False
    assert G.ibl(ibc, cotiza2, np.array([0.0, 0.0]))[0] == pytest.approx((60 * 3 + 60 * 1) / 120)


def test_rpm_pension_con_piso_e_indemnizacion():
    smmlv = 100.0
    meses = 400
    ibc = np.full((2, meses), 100.0)
    cotiza = np.ones((2, meses), dtype=bool)
    cotiza[1, :200] = False                                   # 200 meses ≈ 857 semanas
    r = G.rpm(ibc, cotiza, edad=62, sexo="Hombre", anio=2040, smmlv=smmlv)
    assert list(r["estado"]) == ["pension", "indemnizacion"]
    assert r["mesada"].iloc[0] == pytest.approx(smmlv)        # 65 % del IBL < mínimo → piso
    semanas = 200 * 30 / 7
    assert r["indemnizacion"].iloc[1] == pytest.approx(100 / (30 / 7) * semanas * 0.13)


def test_rpm_reproduce_un_caso_real_liquidado_por_un_tribunal():
    """
    Tribunal Superior de Valledupar, rad. 20001-31-05-001-2020-00138-01 (Valle Martínez vs.
    Colpensiones): pensión de 2018, IBL de $3.002.929, SMMLV de $781.242 y 1.323 semanas
    (mínimo 1.300). El tribunal confirma r = 65,50 − 0,50·3,84 = 63,58 % y una mesada inicial
    de $1.909.262; las 23 semanas extra no alcanzan un tramo de 50.
    """
    ibl, smmlv = 3_002_929.0, 781_242.0
    r = G.tasa_reemplazo_rpm(np.array([ibl]), np.array([1323.0]), 1300, smmlv)[0]
    assert round(r * 100, 2) == 63.58
    assert ibl * round(r, 4) == pytest.approx(1_909_262, abs=1)


def test_rais_usa_el_crecimiento_regulatorio_de_beneficios_por_defecto(mortalidad_lineal):
    from pension_mc.config import parametros
    g = parametros()["rais"]["crecimiento_beneficios_capital"]
    saldo = np.array([1.001, 0.999]) * 100.0 * D.factor_anualidad(57, "Mujer", 0.04, g)
    r = G.rais(saldo, np.array([0.0, 0.0]), edad=57, sexo="Mujer", anio=2040, smmlv=100.0, tasa=0.04)
    assert list(r["estado"]) == ["capital_suficiente", "devolucion"]
