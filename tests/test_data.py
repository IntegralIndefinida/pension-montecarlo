"""Pruebas de los parsers y transformaciones de datos (sin red)."""

import numpy as np
import pandas as pd
import pytest

from pension_mc.data import geih, ipc, mortalidad, rentabilidades


# --------------------------------------------------------------------------- IPC
def _hoja_ipc():
    """Imita la hoja del DANE: título, fila 'Mes' con años y meses en filas."""
    filas = [["Total, Índice de Precios al Consumidor (IPC)", None, None],
             [None, None, None],
             ["Mes", 2024.0, 2025.0],
             ["Enero", 100.0, 110.0],
             ["Febrero", 101.0, 111.1],
             ["Diciembre", 108.0, None],
             [None, None, None]]
    return pd.DataFrame(filas)


def test_ipc_parsear_serie_ordenada_y_sin_vacios():
    df = ipc.parsear(_hoja_ipc())
    assert list(df["fecha"].dt.strftime("%Y-%m")) == ["2024-01", "2024-02", "2024-12", "2025-01", "2025-02"]
    assert df["fecha"].dt.is_month_end.all()
    assert df.loc[1, "inflacion_mensual"] == pytest.approx(0.01)


# --------------------------------------------------------------------------- Mortalidad
_TEXTO_RV08 = """
    x       l(x)            d(x)           q(x)   e (x)           x       l(x)            d(x)           q(x)   e0(x)
    15     1,000,000            485    0.000485        64.8       15     1,000,000            272    0.000272       70.0
    16       999,515            496    0.000496        63.9       16       999,728            278    0.000278       69.1
                    SUPERINTENDENCIA FINANCIERA DE COLOMBIA
"""


def test_rv08_parsear_ambos_sexos():
    df = mortalidad.parsear(_TEXTO_RV08)
    assert len(df) == 4
    h = df[(df.sexo == "Hombre") & (df.edad == 16)].iloc[0]
    assert (h.lx, h.dx, h.qx, h.ex) == (999_515, 496, 0.000496, 63.9)
    assert df[(df.sexo == "Mujer") & (df.edad == 15)].iloc[0].lx == 1_000_000


def _tabla_consistente():
    edades = np.arange(15, 111)
    q = np.r_[np.linspace(0.0005, 0.05, len(edades) - 1), 1.0]
    l = [1_000_000]
    for qx in q[:-1]:
        l.append(l[-1] - round(l[-1] * qx))
    l = np.array(l)
    d = np.r_[l[:-1] - l[1:], l[-1]]
    return pd.DataFrame({"sexo": "Hombre", "edad": edades, "lx": l, "dx": d, "qx": d / l, "ex": 1.0})


def test_rv08_validar_acepta_tabla_consistente_y_rechaza_errores():
    t = _tabla_consistente()
    mortalidad.validar(t)
    roto = t.copy()
    roto.loc[10, "dx"] += 1
    with pytest.raises(ValueError):
        mortalidad.validar(roto)


# --------------------------------------------------------------------------- Rentabilidades
def test_rentabilidad_mensual_real_y_descarta_mes_incompleto():
    fechas = pd.date_range("2024-01-01", "2024-03-10", freq="D")
    valor = 100 * 1.001 ** np.arange(len(fechas))
    diario = pd.DataFrame({"fecha": fechas, "afp": "Protección", "fondo": "moderado", "valor_unidad": valor})
    ipc_m = pd.DataFrame({"fecha": pd.to_datetime(["2024-01-31", "2024-02-29"]),
                          "inflacion_mensual": [0.01, 0.01]})

    m = rentabilidades.mensual(diario, ipc_m)
    assert list(m["fecha"].dt.strftime("%Y-%m")) == ["2024-01", "2024-02"]  # marzo está incompleto
    r_feb = 1.001 ** 29 - 1  # 29 días de febrero de 2024
    assert m.loc[1, "r_nominal"] == pytest.approx(r_feb)
    assert m.loc[1, "r_real"] == pytest.approx((1 + r_feb) / 1.01 - 1)


def test_nombre_afp_normaliza_variantes():
    assert rentabilidades._nombre_afp('"Proteccion"') == "Protección"
    assert rentabilidades._nombre_afp('"Colfondos S.A." Y "Colfondos"') == "Colfondos"
    assert rentabilidades._nombre_afp("Skandia Afp - Accai S.A.") == "Skandia"


# --------------------------------------------------------------------------- GEIH
def test_geih_preparar_cotiza_sobre_toda_la_poblacion():
    base = {c: None for c in geih.COLUMNAS}
    filas = [
        {**base, "edad": 30, "ocupado": 1, "posicion_ocupacional": "Empleado particular", "P6920": 1},
        {**base, "edad": 40, "ocupado": 1, "posicion_ocupacional": "Cuenta propia", "P6920": 2},
        {**base, "edad": 65, "ocupado": 1, "posicion_ocupacional": "Cuenta propia", "P6920": 3},
        {**base, "edad": 25, "ocupado": 0, "posicion_ocupacional": None, "P6920": None},
        {**base, "edad": 12, "ocupado": 0, "posicion_ocupacional": None, "P6920": None},  # fuera de rango
    ]
    out = geih.preparar(pd.DataFrame(filas))
    assert len(out) == 4
    assert list(out["cotiza"]) == [1, 0, 0, 0]
    assert list(out["estado_pension"].astype(str)) == ["Cotiza", "No cotiza", "Pensionado", "No ocupado"]
    assert out["independiente"].iloc[1] == 1 and pd.isna(out["independiente"].iloc[3])

