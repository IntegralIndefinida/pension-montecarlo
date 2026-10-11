"""Pruebas del modelo de densidad de cotización (tasas sintéticas)."""

import numpy as np
import pandas as pd
import pytest
from scipy import special

from pension_mc import contributions as C
from pension_mc.wages import clave

EDADES = list(range(C.EDAD_INICIO, C.EDAD_FIN + 1))


def _modelo(pi=0.4, mu=0.1, beta=0.0):
    tasas = {clave(e, s): [pi] * len(EDADES) for e, s in C.tipos()}
    return C.ModeloCotizacion(EDADES, tasas, mu, beta)


def test_desplazamiento_reproduce_la_tasa_promedio():
    pi = np.array([0.05, 0.3, 0.7, 0.95])
    for beta in (0.0, 1.0, 3.0, 20.0):
        c = C._desplazamiento(pi, beta)
        media = [C._GH_W @ special.expit(ci + beta * C._GH_X) for ci in c]
        np.testing.assert_allclose(media, pi, atol=1e-8)


@pytest.mark.parametrize("beta", [0.0, 1.5])
def test_cadena_mantiene_la_tasa_estacionaria(beta):
    m = _modelo(pi=0.35, mu=0.08, beta=beta)
    x = m.simular(30, "Mujer", "Media", n_meses=240, n_sims=20_000, seed=1)
    assert x[:, 100:].mean() == pytest.approx(0.35, abs=0.01)


def test_autocorrelacion_mensual_es_uno_menos_mu():
    m = _modelo(pi=0.5, mu=0.2)
    x = m.simular(30, "Hombre", "Media", n_meses=200, n_sims=20_000, seed=2).astype(float)
    a, b = x[:, 50:-1].ravel(), x[:, 51:].ravel()
    assert np.corrcoef(a, b)[0, 1] == pytest.approx(0.8, abs=0.01)


def test_ratio_cotizantes_activos_coincide_con_la_formula_sin_heterogeneidad():
    pi, mu = 0.3, 0.1
    m = _modelo(pi=pi, mu=mu)
    pob = {clave(e, s): np.ones(len(EDADES)) for e, s in C.tipos()}
    mom = C.momentos(m, pob, n_por_tipo=4_000, edades=(30, 70), grupos_periodo=())
    f = mu * pi
    teorico = pi / (1 - (1 - pi) * (1 - f) ** 5)
    assert mom["cotizantes_sobre_activos"] == pytest.approx(teorico, abs=0.01)
    assert mom["tasa"] == pytest.approx(pi, abs=0.01)


def test_heterogeneidad_ensancha_la_distribucion_de_densidades():
    sin = _modelo(pi=0.4, mu=0.1, beta=0.0).simular(20, "Mujer", "Media", 480, 5_000, seed=3).mean(axis=1)
    con = _modelo(pi=0.4, mu=0.1, beta=2.0).simular(20, "Mujer", "Media", 480, 5_000, seed=3).mean(axis=1)
    assert con.std() > 3 * sin.std()
    assert con.mean() == pytest.approx(sin.mean(), abs=0.02)


def test_condicionar_respeta_las_semanas_y_ordena_eta():
    m = _modelo(pi=0.4, mu=0.1, beta=1.5)
    sem_mes = 30 / 7
    eta_alto, _ = m.condicionar(40, "Mujer", "Media", 900, 500, seed=4)
    eta_bajo, _ = m.condicionar(40, "Mujer", "Media", 100, 500, seed=4)
    assert eta_alto.mean() > 0.5 > -0.5 > eta_bajo.mean()
    eta, est = m.condicionar(40, "Mujer", "Media", 500, 300, cotiza_hoy=True, seed=5)
    assert est.all() and len(eta) == 300


def test_semanas_acumuladas():
    x = np.array([[True, False, True, True]])
    np.testing.assert_allclose(C.semanas(x), np.array([[1, 1, 2, 3]]) * 30 / 7, rtol=1e-4)


def test_tasas_observadas_ponderadas():
    geih = pd.DataFrame({"anio": 2025, "edad": [30, 30, 30], "fex": [1.0, 3.0, 2.0], "cotiza": [1, 0, 1],
                         "nivel_educativo": ["Media", "Media", "Primaria"], "sexo": "Mujer"})
    t = C.tasas_observadas(geih, anios=(2025,)).set_index("educ")
    assert t.loc["Media", "tasa"] == pytest.approx(0.25)
    assert t.loc["Primaria o menos", "tasa"] == 1.0
    assert t.loc["Media", "poblacion"] == pytest.approx(4 / 12)


def test_guardar_y_cargar(tmp_path):
    m = _modelo(beta=1.2)
    m.guardar(tmp_path / "c.json")
    m2 = C.ModeloCotizacion.cargar(tmp_path / "c.json")
    assert (m2.mu, m2.beta, m2.tasas) == (m.mu, m.beta, m.tasas)


def test_duracion_en_curso():
    x = np.array([[True, True, False, True, True, True]])
    np.testing.assert_array_equal(C.duracion_en_curso(x), [[1, 2, 0, 1, 2, 3]])


def test_mas_heterogeneidad_alarga_los_periodos():
    pob = {clave(e, s): np.ones(len(EDADES)) for e, s in C.tipos()}
    corto = C.momentos(_modelo(pi=0.4, mu=0.2, beta=0.5), pob, n_por_tipo=1_000)
    largo = C.momentos(_modelo(pi=0.4, mu=0.2, beta=4.0), pob, n_por_tipo=1_000)
    assert largo["periodo_25_44"] > corto["periodo_25_44"] + 0.2


def test_kappa_reduce_la_rotacion_con_la_edad():
    m = _modelo(pi=0.4, mu=0.3)
    m.kappa = 1.0
    np.testing.assert_allclose(m.rotacion([30, 40, 50]), [0.3 * np.e, 0.3, 0.3 / np.e])
    assert m.rotacion(10) == 1.0  # acotada
    pob = {clave(e, s): np.ones(len(EDADES)) for e, s in C.tipos()}
    mom = C.momentos(m, pob, n_por_tipo=1_000)
    assert mom["periodo_45_64"] > mom["periodo_25_44"]


def test_cadena_sigue_una_tasa_que_cambia_con_la_edad_aun_con_poca_rotacion():
    tasa = np.interp(EDADES, [15, 25, 50, 60, 70], [0.0, 0.6, 0.6, 0.1, 0.0])
    tasas = {clave(e, s): list(tasa) for e, s in C.tipos()}
    m = C.ModeloCotizacion(EDADES, tasas, mu=0.02, beta=1.5)
    eta = np.random.default_rng(7).standard_normal(20_000)
    x = m.simular(15, "Mujer", "Media", 55 * 12, 20_000, eta=eta, seed=6)
    objetivo = m.prob_individual(15 + np.arange(55 * 12) / 12, "Mujer", "Media", eta).mean(axis=0)
    assert np.max(np.abs(x.mean(axis=0) - objetivo)) < 0.015


def test_eta_se_mueve_en_la_juventud_y_queda_fijo_despues():
    m = _modelo(pi=0.4, mu=0.1, beta=2.0)
    m.rho_eta, m.edad_fija_eta = 0.5, 35.0
    eta0 = np.random.default_rng(1).standard_normal(2_000)
    m.simular(20, "Mujer", "Media", 12 * 10, 2_000, eta=eta0, seed=2)        # 20 → 30: se mueve
    assert np.corrcoef(eta0, m._eta_final)[0, 1] < 0.2
    assert m._eta_final.std() == pytest.approx(1.0, abs=0.05)               # sigue siendo N(0, 1)
    m.simular(40, "Mujer", "Media", 12 * 10, 2_000, eta=eta0, seed=2)        # 40 → 50: fijo
    np.testing.assert_array_equal(m._eta_final, eta0)


def test_eta_movil_debilita_el_condicionamiento_temprano():
    rigido = _modelo(pi=0.4, mu=0.1, beta=4.0)
    movil = _modelo(pi=0.4, mu=0.1, beta=4.0)
    movil.rho_eta, movil.edad_fija_eta = 0.75, 35.0
    brecha = {}
    for nombre, m in (("rigido", rigido), ("movil", movil)):
        alto, _ = m.condicionar(25, "Hombre", "Media", 300, 400, seed=3)
        bajo, _ = m.condicionar(25, "Hombre", "Media", 0, 400, seed=3)
        brecha[nombre] = alto.mean() - bajo.mean()
    assert brecha["movil"] < brecha["rigido"]
