"""Pruebas de los generadores de rentabilidades (datos sintéticos, sin archivos)."""

import numpy as np
import pandas as pd
import pytest

from pension_mc import returns as R


def _hist(n=240, seed=0):
    """Historia sintética de 4 fondos correlacionados con colas t."""
    rng = np.random.default_rng(seed)
    cov = np.array([[4, 3, 2, 2], [3, 3, 2, 2], [2, 2, 2, 1.5], [2, 2, 1.5, 2]]) * 1e-4
    x = rng.multivariate_normal([0.004, 0.003, 0.002, 0.0025], cov, n)
    fechas = pd.date_range("2006-01-31", periods=n, freq="ME")
    return pd.DataFrame(np.expm1(x), index=fechas, columns=R.FONDOS)


def test_bootstrap_remuestrea_meses_completos():
    h = _hist()
    sim = R.bootstrap_estacionario(h, n_sims=50, n_meses=36, largo_bloque=4, seed=1)
    assert sim.r.shape == (50, 36, 4)
    # Cada mes simulado es un mes histórico completo: se conserva la estructura entre fondos
    filas = {tuple(np.round(f, 5)) for f in h.to_numpy(np.float32)}
    assert all(tuple(np.round(f, 5)) in filas for f in sim.r.reshape(-1, 4)[:200])


def test_bootstrap_bloques_contiguos():
    rng = np.random.default_rng(0)
    idx = R.indices_bootstrap(n_hist=100, n_sims=2_000, n_meses=120, largo_bloque=6, rng=rng)
    continua = (idx[:, 1:] == (idx[:, :-1] + 1) % 100).mean()
    assert continua == pytest.approx(1 - 1 / 6 + 1 / 6 / 100, abs=0.01)


def test_media_objetivo_fija_la_rentabilidad_geometrica():
    h = _hist()
    objetivo = {"moderado": 0.04, "conservador": 0.02}
    sim = R.bootstrap_estacionario(h, n_sims=4_000, n_meses=240, largo_bloque=3,
                                   media_objetivo=objetivo, seed=2)
    for f, anual in objetivo.items():
        assert np.median(sim.anualizada(sim.fondo(f))) == pytest.approx(anual, abs=0.002)


def test_incertidumbre_media_ensancha_la_dispersion_de_largo_plazo():
    h = _hist(n=120)
    base = R.bootstrap_estacionario(h, n_sims=3_000, n_meses=480, largo_bloque=2, seed=8)
    inc = R.bootstrap_estacionario(h, n_sims=3_000, n_meses=480, largo_bloque=2, incertidumbre_media=True, seed=8)
    sd_base = base.anualizada(base.fondo("moderado")).std()
    sd_inc = inc.anualizada(inc.fondo("moderado")).std()
    # desvío esperado de la media anual: sd mensual * 12 / sqrt(T)
    sd_media = np.log1p(h["moderado"]).std() * 12 / np.sqrt(len(h))
    assert sd_inc == pytest.approx(np.hypot(sd_base, sd_media), rel=0.1)
    # sin incertidumbre la media de la trayectoria no se desplaza
    assert np.median(base.anualizada(base.fondo("moderado"))) == pytest.approx(
        np.median(inc.anualizada(inc.fondo("moderado"))), abs=0.004)


def test_largo_bloque_crece_con_la_persistencia():
    rng = np.random.default_rng(3)
    iid = rng.standard_normal(500)
    ar = np.zeros(500)
    for t in range(1, 500):
        ar[t] = 0.8 * ar[t - 1] + rng.standard_normal()
    assert R.largo_bloque_optimo(iid) < 3
    assert R.largo_bloque_optimo(ar) > 6


def test_t_multivariada_reproduce_media_y_covarianza():
    h = _hist()
    sim = R.t_multivariada(h, n_sims=2_000, n_meses=60, nu=6, seed=4)
    x = np.log1p(sim.r.reshape(-1, 4).astype(np.float64))
    x_h = np.log1p(h.to_numpy())
    np.testing.assert_allclose(x.mean(axis=0), x_h.mean(axis=0), atol=2e-4)
    np.testing.assert_allclose(np.cov(x, rowvar=False), np.cov(x_h, rowvar=False), rtol=0.06)


def test_ajustar_nu_detecta_colas_gruesas():
    rng = np.random.default_rng(5)
    x_t = rng.standard_t(5, size=(3_000, 2)) * 0.01
    x_n = rng.standard_normal((3_000, 2)) * 0.01
    assert 3 <= R.ajustar_nu(x_t) <= 9
    assert R.ajustar_nu(x_n) >= 20


def test_portafolio_combina_fondos():
    h = _hist()
    sim = R.bootstrap_estacionario(h, n_sims=10, n_meses=12, largo_bloque=2, seed=6)
    pesos = np.array([0.5, 0.5, 0.0, 0.0])
    esperado = 0.5 * sim.fondo("mayor_riesgo") + 0.5 * sim.fondo("moderado")
    np.testing.assert_allclose(sim.portafolio(pesos), esperado, rtol=1e-6)
    with pytest.raises(ValueError):
        sim.portafolio(np.array([0.5, 0.2, 0.0, 0.0]))


def test_escenarios_deterministas_ordenados():
    sim = R.bootstrap_estacionario(_hist(), n_sims=500, n_meses=120, largo_bloque=3, seed=7)
    esc = R.escenarios_deterministas(sim)
    assert (esc["pesimista"] < esc["base"]).all() and (esc["base"] < esc["optimista"]).all()
    det = R.constante(esc["base"].to_dict(), n_meses=120)
    np.testing.assert_allclose(det.anualizada(det.fondo("moderado")), esc.loc["moderado", "base"], rtol=1e-5)


@pytest.mark.parametrize("sexo, edad, esperado", [
    ("mujer", 30, [1.0, 0.0, 0.0]),
    ("mujer", 43, [0.6, 0.4, 0.0]),
    ("mujer", 50, [0.0, 1.0, 0.0]),
    ("mujer", 54, [0.0, 0.4, 0.6]),
    ("mujer", 56, [0.0, 0.0, 1.0]),
    ("hombre", 46, [1.0, 0.0, 0.0]),
    ("hombre", 49, [0.4, 0.6, 0.0]),
    ("hombre", 58, [0.0, 0.6, 0.4]),
    ("hombre", 61, [0.0, 0.0, 1.0]),
])
def test_pesos_por_defecto_siguen_el_decreto(sexo, edad, esperado):
    p = R.pesos_por_defecto(edad, sexo, n_meses=1)[0]
    np.testing.assert_allclose(p[:3], esperado)
    assert p[3] == 0


def test_pesos_por_defecto_cambian_al_cumplir_anios():
    p = R.pesos_por_defecto(41.5, "Mujer", n_meses=24)
    assert p[5, 0] == 1.0      # 41 años y 11 meses
    assert p[6, 0] == 0.8      # cumple 42
    assert p[18, 0] == 0.6     # cumple 43
    np.testing.assert_allclose(p.sum(axis=1), 1)
