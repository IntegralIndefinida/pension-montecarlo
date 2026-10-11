"""
De saldo a mesada: valor actuarial de una pensión vitalicia con las tablas de mortalidad RV08.

La mesada se paga 13 veces al año (Acto Legislativo 01 de 2005). Se aproxima como 12 pagos
mensuales anticipados de ``13/12`` de la mesada:

    F(x) = (13/12) · Σ_m  v^{m/12} · (1+g)^{m/12} · ₘ/₁₂p_x,       v = 1 / (1 + i)

``F`` es el capital necesario por cada peso de mesada; ``i`` es la tasa técnica real y ``g`` el
crecimiento real de la mesada (0 para pensiones indexadas al IPC; el crecimiento real del SMMLV
para pensiones de salario mínimo). La supervivencia entre edades enteras se interpola linealmente
en ``l(x)`` (distribución uniforme de las muertes). Con cónyuge beneficiario (pensión de
sobrevivientes del 100 %), la probabilidad de pago es ``p_x + p_y − p_x·p_y`` (vidas independientes).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from .config import DATA_PROCESSED, parametros

EDAD_MAXIMA = 111


@lru_cache(maxsize=None)
def _lx(sexo: str) -> tuple[np.ndarray, np.ndarray]:
    t = pd.read_parquet(DATA_PROCESSED / "mortalidad_rv08.parquet")
    t = t[t["sexo"] == sexo.capitalize()].sort_values("edad")
    edades = np.r_[t["edad"].to_numpy(float), EDAD_MAXIMA]
    return edades, np.r_[t["lx"].to_numpy(float), 0.0]


def supervivencia(edad: float, sexo: str, n_meses: int | None = None) -> np.ndarray:
    """``ₘ/₁₂p_x`` para m = 0, 1, …: probabilidad de seguir vivo ``m`` meses después de la edad ``edad``."""
    edades, lx = _lx(sexo)
    n = int((EDAD_MAXIMA - edad) * 12) + 1 if n_meses is None else n_meses
    lm = np.interp(edad + np.arange(n) / 12, edades, lx, right=0.0)
    return lm / np.interp(edad, edades, lx)


@lru_cache(maxsize=4096)
def factor_anualidad(edad: float, sexo: str, tasa: float | None = None, crecimiento: float = 0.0,
                     conyuge: tuple[str, float] | None = None) -> float:
    """
    Capital necesario por cada peso de mesada real de una pensión vitalicia que empieza a ``edad``.

    ``conyuge = (sexo, edad)`` agrega una pensión de sobrevivientes del 100 % para el cónyuge.
    """
    p = parametros()
    i = p["supuestos"]["tasa_tecnica_real"] if tasa is None else tasa
    mesadas = p["rais"]["mesadas_por_anio"]
    px = supervivencia(edad, sexo)
    if conyuge is not None:
        py = supervivencia(conyuge[1], conyuge[0])
        n = max(len(px), len(py))
        px, py = np.pad(px, (0, n - len(px))), np.pad(py, (0, n - len(py)))
        px = px + py - px * py
    m = np.arange(len(px)) / 12
    return float(mesadas / 12 * np.sum(((1 + crecimiento) / (1 + i)) ** m * px))


def mesada(saldo: np.ndarray, edad: float, sexo: str, **kwargs) -> np.ndarray:
    """Mesada real que financia un saldo con una pensión vitalicia indexada al IPC."""
    return np.asarray(saldo) / factor_anualidad(edad, sexo, **kwargs)
