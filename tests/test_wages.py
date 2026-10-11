"""Pruebas del modelo salarial (datos sintéticos)."""

import numpy as np
import pytest

from pension_mc import wages as W


def test_tobit_recupera_parametros_con_censura_y_heterocedasticidad():
    rng = np.random.default_rng(0)
    n = 40_000
    edad = rng.uniform(18, 65, n)
    e = (edad - 40) / 10
    X = np.column_stack([np.ones(n), e, e**2])
    Z = np.column_stack([np.ones(n), e])
    beta, gamma = np.array([14.5, 0.3, -0.1]), np.array([np.log(0.5), 0.15])
    y_lat = X @ beta + np.exp(Z @ gamma) * rng.standard_normal(n)
    c = np.full(n, 14.3)
    cen = y_lat <= c
    y = np.where(cen, c, y_lat)
    assert 0.2 < cen.mean() < 0.5

    b, g, _ = W.tobit(y, c, cen, X, Z)
    np.testing.assert_allclose(b, beta, atol=0.02)
    np.testing.assert_allclose(g, gamma, atol=0.03)


def test_ajustar_ar_recupera_parametros():
    edades = np.arange(20, 65)
    v = W.varianza_ar(edades, 0.35, 0.12, 0.93)
    np.testing.assert_allclose(W.ajustar_ar(edades, v), (0.35, 0.12, 0.93), rtol=1e-3)


def test_varianza_ar_paseo_aleatorio():
    assert W.varianza_ar(27, 0.3, 0.1, 1.0) == pytest.approx(0.09 + 0.01 * 10)


def _modelo(anios=(2025,)):
    """Perfil plano de 15 (ln pesos) para todos los tipos; σα = 0,3, σε = 0,1, ρ = 0,9."""
    n_tipos = len(W.NIVELES) * len(W.SEXOS)
    beta = [v for _ in range(n_tipos) for v in (15.0, 0.0, 0.0)] + [0.0] * (len(anios) - 1)
    gamma = [0.0] * 3 * n_tipos
    ar = {W.clave(e, s): (0.3, 0.1, 0.9) for e, s in W._tipos()}
    return W.ModeloSalarial(beta, gamma, list(anios), ar, pesos_de="prueba")


def test_simular_sin_condicionar_reproduce_media_y_varianza():
    m = _modelo()
    w = m.simular(30, "Mujer", "Media", n_anios=20, n_sims=40_000, crecimiento=0.0, seed=1)
    lw = np.log(w)
    assert lw.mean() == pytest.approx(15.0, abs=0.01)
    for k in (0, 10, 19):
        assert lw[:, k].var() == pytest.approx(W.varianza_ar(30 + k, 0.3, 0.1, 0.9), rel=0.03)


def test_simular_condicionado_parte_del_salario_actual_y_revierte():
    m = _modelo()
    w0 = np.exp(15.5)
    w = m.simular(30, "Hombre", "Superior", n_anios=30, n_sims=20_000, salario_actual=w0, crecimiento=0.0, seed=2)
    np.testing.assert_allclose(w[:, 0], w0)
    # E[u_k | u_0]: la parte de α se mantiene y la de z decae a ritmo ρ^k
    v_z = W.varianza_ar(30, 0.0, 0.1, 0.9)
    s_a2 = 0.09
    esperado = 0.5 * (s_a2 + v_z * 0.9**29) / (s_a2 + v_z)
    assert np.log(w[:, -1]).mean() - 15.0 == pytest.approx(esperado, abs=0.01)


def test_simular_salario_minimo_sortea_por_debajo_del_umbral():
    m = _modelo()
    smmlv = np.exp(14.9)
    w = m.simular(40, "Mujer", "Primaria o menos", n_anios=5, n_sims=5_000, salario_actual=smmlv,
                  smmlv_actual=smmlv, crecimiento=0.0, seed=3)
    assert (w[:, 0] <= smmlv * W.UMBRAL_CENSURA + 1e-6).all()
    assert w[:, 0].std() > 0


def test_crecimiento_real_desplaza_el_perfil():
    m = _modelo()
    w0 = m.simular(30, "Mujer", "Media", n_anios=11, n_sims=20_000, crecimiento=0.0, seed=4)
    w2 = m.simular(30, "Mujer", "Media", n_anios=11, n_sims=20_000, crecimiento=0.02, seed=4)
    np.testing.assert_allclose(np.log(w2[:, 10] / w0[:, 10]), 10 * np.log(1.02))


def test_ibc_piso_tope_e_independientes():
    smmlv = np.array([1.0, 1.0, 1.0, 1.0])
    salario = np.array([0.5, 2.0, 30.0, 4.0])
    np.testing.assert_allclose(W.ibc(salario, smmlv), [1.0, 2.0, 25.0, 4.0])
    np.testing.assert_allclose(W.ibc(salario, smmlv, independiente=True), [1.0, 1.0, 12.0, 1.6])


def test_matriz_media_indicadores_y_efectos_de_anio():
    X = W.matriz_media(["Media", "Superior"], ["Mujer", "Hombre"], [40, 50], [2024, 2025], [2023, 2024, 2025])
    assert X.shape == (2, 3 * 8 + 2)
    tipos = W._tipos()
    i = tipos.index(("Media", "Mujer"))
    np.testing.assert_allclose(X[0, 3 * i : 3 * i + 3], [1, 0, 0])
    np.testing.assert_allclose(X[0, -2:], [1, 0])
    np.testing.assert_allclose(X[1, -2:], [0, 1])
    assert X[0].sum() == pytest.approx(2)


def test_guardar_y_cargar(tmp_path):
    m = _modelo()
    ruta = tmp_path / "m.json"
    m.guardar(ruta)
    m2 = W.ModeloSalarial.cargar(ruta)
    assert m2.ar == m.ar and m2.beta == m.beta


def test_matriz_escala_por_tipo():
    Z = W.matriz_escala(["Superior", "Media"], ["Mujer", "Hombre"], [40, 50])
    assert Z.shape == (2, 3 * 8)
    i = W._tipos().index(("Superior", "Mujer"))
    np.testing.assert_allclose(Z[0, 3 * i : 3 * i + 3], [1, 0, 0])
    assert Z[0].sum() == pytest.approx(1)
