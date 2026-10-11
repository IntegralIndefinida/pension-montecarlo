"""Pruebas del motor de simulación (requieren los modelos estimados en data/processed)."""

import numpy as np
import pytest

from pension_mc.config import DATA_PROCESSED

necesita_modelos = pytest.mark.skipif(
    not all((DATA_PROCESSED / f).exists() for f in ("modelo_salarial.json", "modelo_cotizacion.json",
                                                     "rentabilidad_mensual.parquet", "mortalidad_rv08.parquet")),
    reason="requiere los modelos y datos procesados")

N = 800


@pytest.fixture(scope="module")
def S():
    from pension_mc import simulate
    return simulate


def _perfil(S, **kw):
    base = dict(edad=35, sexo="Hombre", educacion="Media", salario=2_500_000, semanas=400, cotiza_hoy=True)
    return S.Perfil(**{**base, **kw})


@necesita_modelos
def test_resultado_consistente(S):
    r = S.simular(_perfil(S), n_sims=N)
    assert len(r.afp) == len(r.colpensiones) == N
    assert r.edad_retiro == 62 and r.anio_retiro == 2026 + 27
    res = r.resumen()
    total = res.afp_p_capital_suficiente + res.afp_p_garantia_minima + res.afp_p_devolucion
    assert total == pytest.approx(1.0)
    assert (r.afp.loc[r.afp.estado != "devolucion", "mesada"] >= r.smmlv_retiro - 1e-6).all()
    assert (r.afp.semanas >= 400).all()


@necesita_modelos
def test_misma_semilla_mismo_resultado(S):
    a = S.simular(_perfil(S), n_sims=N).afp
    b = S.simular(_perfil(S), n_sims=N).afp
    np.testing.assert_array_equal(a.saldo, b.saldo)


@necesita_modelos
def test_aporte_voluntario_aumenta_el_saldo_en_cada_simulacion(S):
    base = S.simular(_perfil(S), n_sims=N).afp.saldo.to_numpy()
    vol = S.simular(_perfil(S, aporte_voluntario_pct=0.05), n_sims=N).afp.saldo.to_numpy()
    assert (vol >= base - 1e-6).all() and (vol > base).mean() > 0.9


@necesita_modelos
def test_laguna_reduce_semanas(S):
    base = S.simular(_perfil(S, edad=25, semanas=0, cotiza_hoy=True), n_sims=N).afp.semanas
    lag = S.simular(_perfil(S, edad=25, semanas=0, cotiza_hoy=True, laguna=(25, 30)), n_sims=N).afp.semanas
    assert lag.mean() < base.mean() - 5 * 52 * 0.3


@necesita_modelos
def test_retirarse_mas_tarde_no_reduce_el_saldo(S):
    p = _perfil(S)
    sup = S.Supuestos(congelar_cotizacion_desde=55)
    a = S.simular(p, sup, n_sims=N).afp
    b = S.simular(S.Perfil(**{**p.__dict__, "edad_retiro": 65}), sup, n_sims=N).afp
    assert b.saldo.median() > a.saldo.median()


@necesita_modelos
@pytest.mark.parametrize("metodo", ["t", "determinista"])
def test_metodos_de_rentabilidad(S, metodo):
    r = S.simular(_perfil(S), S.Supuestos(metodo_rentabilidad=metodo), n_sims=N)
    assert np.isfinite(r.afp.saldo).all()


@necesita_modelos
def test_tasa_tecnica_menor_reduce_la_mesada_del_capital_suficiente(S):
    p = _perfil(S, educacion="Superior", salario=8_000_000, semanas=800)
    alta = S.simular(p, S.Supuestos(tasa_tecnica=0.05), n_sims=N).afp
    baja = S.simular(p, S.Supuestos(tasa_tecnica=0.03), n_sims=N).afp
    sel = (alta.estado == "capital_suficiente") & (baja.estado == "capital_suficiente")
    assert sel.any() and (baja.mesada[sel] < alta.mesada[sel]).all()


@necesita_modelos
def test_edad_de_retiro_invalida(S):
    with pytest.raises(ValueError):
        S.simular(_perfil(S, edad=61.5), n_sims=10)
