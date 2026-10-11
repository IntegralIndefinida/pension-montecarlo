"""
Acumulación del saldo en la cuenta de ahorro individual (RAIS).

Mes a mes, en pesos reales:

    saldo[t] = saldo[t−1] · (1 + r[t]) + aporte[t]
    aporte[t] = cotiza[t] · (11,5 % · IBC[t] + voluntario[t])

El aporte entra al final del mes. ``r`` es la rentabilidad real del portafolio (multifondos).
"""

from __future__ import annotations

import numpy as np

from .config import parametros


def mensualizar(anual: np.ndarray) -> np.ndarray:
    """Repite cada valor anual 12 veces sobre el último eje: ``(…, n_anios)`` → ``(…, 12·n_anios)``."""
    return np.repeat(np.asarray(anual), 12, axis=-1)


def aportes(ibc: np.ndarray, cotiza: np.ndarray, *, voluntario_pct: float = 0.0,
            salario: np.ndarray | None = None) -> np.ndarray:
    """
    Aporte mensual a la cuenta individual ``(n_sims, n_meses)``.

    ``voluntario_pct`` es un aporte voluntario adicional, como fracción del salario, en los meses
    en que la persona cotiza.
    """
    tasa = parametros()["cotizacion"]["reparto_rais"]["cuenta_individual"]
    a = tasa * np.asarray(ibc, dtype=np.float64)
    if voluntario_pct:
        a = a + voluntario_pct * np.asarray(ibc if salario is None else salario, dtype=np.float64)
    return np.where(cotiza, a, 0.0)


def saldo(aportes: np.ndarray, rentabilidad: np.ndarray, saldo_inicial: float | np.ndarray = 0.0) -> np.ndarray:
    """Saldo al final de cada mes ``(n_sims, n_meses)``."""
    n, t = aportes.shape
    out = np.empty((n, t))
    s = np.broadcast_to(np.asarray(saldo_inicial, dtype=np.float64), (n,)).copy()
    for k in range(t):
        s = s * (1 + rentabilidad[:, k]) + aportes[:, k]
        out[:, k] = s
    return out
