"""
Reglas de pensión de vejez de la Ley 100 de 1993: RAIS (AFP) y RPM (Colpensiones).

Todo en pesos reales. ``smmlv`` es el salario mínimo real del año en que la persona llega a la
edad de pensión.

**RAIS** (arts. 35, 64, 65 y 66):

1. *Capital suficiente*: el saldo financia una pensión vitalicia de al menos 1 SMMLV que crece
   con el SMMLV → mesada = saldo / F (indexada al IPC).
2. *Garantía de pensión mínima*: si no, y tiene la edad y las semanas → mesada = 1 SMMLV; el
   Estado paga la diferencia (``costo_garantia``).
3. *Devolución de saldos*: si no cumple ninguna → recibe el saldo.

**RPM** (arts. 21, 33, 34, 35 y 37):

1. Con la edad y las semanas: mesada = r · IBL, con r = 65,5 − 0,5·s (entre 55 % y 65 %),
   s = IBL / SMMLV, más 1,5 puntos por cada 50 semanas adicionales (hasta +15 y como máximo el
   80 % del IBL), con piso de 1 SMMLV y tope de 25 SMMLV.
2. Sin las semanas: indemnización sustitutiva = IBC semanal promedio × semanas × 13 %.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import parametros
from .decumulation import factor_anualidad

ESTADOS_RAIS = ["capital_suficiente", "garantia_minima", "devolucion"]
ESTADOS_RPM = ["pension", "indemnizacion"]


def semanas_requeridas(regimen: str, sexo: str, anio: int) -> float:
    """Semanas exigidas en ``anio``: ``regimen`` es ``"rais"`` (garantía de pensión mínima) o ``"rpm"``."""
    p = parametros()
    reglas = p["rais"]["garantia_pension_minima"] if regimen == "rais" else p["rpm"]
    if sexo.lower() == "hombre":
        return float(reglas["semanas_hombre"])
    m = reglas["semanas_mujer"]
    if anio < m["anio_base"]:
        return float(m["hasta_2025"])
    return float(max(m["minimo"], m["valor_base"] - m["reduccion_anual"] * (anio - m["anio_base"])))


def edad_pension(regimen: str, sexo: str) -> int:
    p = parametros()
    reglas = p["rais"]["garantia_pension_minima"] if regimen == "rais" else p["rpm"]
    return int(reglas["edad"][sexo.lower()])


def rais(saldo: np.ndarray, semanas: np.ndarray, *, edad: float, sexo: str, anio: int, smmlv: float,
         tasa: float | None = None, crecimiento_smmlv: float | None = None,
         conyuge: tuple[str, float] | None = None) -> pd.DataFrame:
    """Resultado en el RAIS al pedir la pensión a ``edad`` en ``anio``, una fila por simulación."""
    g = parametros()["supuestos"]["crecimiento_real_smmlv"] if crecimiento_smmlv is None else crecimiento_smmlv
    saldo, semanas = np.asarray(saldo, float), np.asarray(semanas, float)
    f = factor_anualidad(edad, sexo, tasa, 0.0, conyuge)
    f_min = factor_anualidad(edad, sexo, tasa, g, conyuge)          # pensión mínima, crece con el SMMLV
    capital_minimo = smmlv * f_min

    suficiente = saldo >= capital_minimo
    garantia = ~suficiente & (edad >= edad_pension("rais", sexo)) & (semanas >= semanas_requeridas("rais", sexo, anio))
    estado = np.select([suficiente, garantia], ESTADOS_RAIS[:2], ESTADOS_RAIS[2])
    return pd.DataFrame({
        "estado": pd.Categorical(estado, categories=ESTADOS_RAIS),
        "mesada": np.select([suficiente, garantia], [saldo / f, np.full_like(saldo, smmlv)], 0.0),
        "devolucion": np.where(suficiente | garantia, 0.0, saldo),
        "costo_garantia": np.where(garantia, capital_minimo - saldo, 0.0),
        "saldo": saldo,
        "semanas": semanas,
    })


def ibl(ibc: np.ndarray, cotiza: np.ndarray, semanas: np.ndarray, meses: int = 120) -> np.ndarray:
    """
    Ingreso base de liquidación (art. 21): promedio del IBC real de los últimos ``meses`` meses
    cotizados, o de toda la vida laboral si es mayor y hay al menos 1.250 semanas.
    """
    ibc, cotiza = np.asarray(ibc, float), np.asarray(cotiza, bool)
    n = cotiza.sum(axis=1)
    # meses cotizados contados desde el final: el último mes cotizado es 1
    orden = np.cumsum(cotiza[:, ::-1], axis=1)[:, ::-1]
    ultimos = cotiza & (orden <= meses)
    prom_10 = np.where(n > 0, (ibc * ultimos).sum(axis=1) / np.maximum(ultimos.sum(axis=1), 1), 0.0)
    prom_vida = np.where(n > 0, (ibc * cotiza).sum(axis=1) / np.maximum(n, 1), 0.0)
    umbral = parametros()["rpm"]["semanas_ibl_toda_la_vida"]
    return np.where(np.asarray(semanas) >= umbral, np.maximum(prom_10, prom_vida), prom_10)


def tasa_reemplazo_rpm(ibl_: np.ndarray, semanas: np.ndarray, semanas_minimas: float, smmlv: float) -> np.ndarray:
    """Porcentaje del IBL (art. 34): r = 65,5 − 0,5·s acotado a [55, 65] + 1,5 por cada 50 semanas extra."""
    s = np.asarray(ibl_, float) / smmlv
    r = np.clip(65.5 - 0.5 * s, 55.0, 65.0)
    extra = 1.5 * np.clip(np.floor((np.asarray(semanas, float) - semanas_minimas) / 50), 0, 10)
    return np.minimum(r + extra, 80.0) / 100


def rpm(ibc: np.ndarray, cotiza: np.ndarray, *, edad: float, sexo: str, anio: int, smmlv: float,
        semanas_previas: float | np.ndarray = 0.0) -> pd.DataFrame:
    """
    Resultado en el RPM al llegar a ``edad`` en ``anio``, una fila por simulación.

    ``ibc`` y ``cotiza`` cubren el periodo simulado; ``semanas_previas`` suma las semanas ya
    cotizadas antes (cuyo IBC no se conoce: el IBL usa solo el periodo simulado).
    """
    p = parametros()
    sem_mes = p["supuestos"]["semanas_por_mes"]
    cotiza = np.asarray(cotiza, bool)
    semanas = semanas_previas + cotiza.sum(axis=1) * sem_mes
    req = semanas_requeridas("rpm", sexo, anio)
    base = ibl(ibc, cotiza, semanas)
    tasa = tasa_reemplazo_rpm(base, semanas, req, smmlv)
    mesada = np.clip(tasa * base, smmlv, 25 * smmlv)
    cumple = (edad >= edad_pension("rpm", sexo)) & (semanas >= req)
    # indemnización sustitutiva: IBC semanal promedio (de toda la vida) × semanas × % de cotización
    n = np.maximum(cotiza.sum(axis=1), 1)
    ibc_semanal = (np.asarray(ibc, float) * cotiza).sum(axis=1) / n / sem_mes
    indemnizacion = ibc_semanal * semanas * p["rpm"]["indemnizacion_pct"]
    return pd.DataFrame({
        "estado": pd.Categorical(np.where(cumple, "pension", "indemnizacion"), categories=ESTADOS_RPM),
        "mesada": np.where(cumple, mesada, 0.0),
        "indemnizacion": np.where(cumple, 0.0, indemnizacion),
        "ibl": base,
        "tasa_reemplazo_ibl": np.where(cumple, mesada / np.maximum(base, 1), 0.0),
        "semanas": semanas,
    })
