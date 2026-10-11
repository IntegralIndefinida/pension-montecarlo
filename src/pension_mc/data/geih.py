"""
Extracto de la GEIH para estimar la densidad de cotización y el perfil salarial.

Usa ``dane-data``: los microdatos deben estar descargados (``dane-data estado``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import DATA_PROCESSED
from ._http import log

ANIOS = (2022, 2023, 2024, 2025)  # marco 2018, mismo cuestionario
EDAD_MIN, EDAD_MAX = 15, 70

COLUMNAS = ["anio", "mes", "fex", "sexo", "edad", "nivel_educativo", "zona", "departamento",
            "condicion", "ocupado", "formal", "posicion_ocupacional", "ingreso_laboral",
            "smlv", "ratio_smlv", "horas_semana"]

# P6920: "¿Está cotizando actualmente a un fondo de pensiones?" (solo ocupados)
ESTADO_P6920 = {1: "Cotiza", 2: "No cotiza", 3: "Pensionado"}
INDEPENDIENTES = {"Cuenta propia", "Patrón o empleador"}


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Selecciona columnas y crea las variables de pensión sobre la población de 15 a 70 años."""
    df = df[df["edad"].between(EDAD_MIN, EDAD_MAX)]
    out = df[COLUMNAS].copy()
    p6920 = pd.to_numeric(df["P6920"], errors="coerce")
    ocupado = out["ocupado"] == 1

    # estado_pension cubre a toda la población: los no ocupados no cotizan como trabajadores
    estado = np.where(ocupado, p6920.map(ESTADO_P6920).fillna("Sin dato"), "No ocupado")
    out["estado_pension"] = pd.Categorical(estado, categories=["Cotiza", "No cotiza", "Pensionado",
                                                               "No ocupado", "Sin dato"])
    # cotiza: 1 si es ocupado y cotiza; 0 en cualquier otro caso. Base: población, no ocupados.
    out["cotiza"] = (ocupado & (p6920 == 1)).astype("int8")
    out["independiente"] = out["posicion_ocupacional"].isin(INDEPENDIENTES).astype("int8").where(ocupado)
    # P6426: meses continuos en el empleo actual (cota inferior del periodo de cotización actual)
    p6426 = pd.to_numeric(df["P6426"], errors="coerce") if "P6426" in df else np.nan
    out["antiguedad_empleo"] = pd.Series(p6426, index=df.index).where(ocupado).to_numpy()
    return out.reset_index(drop=True)


def procesar(anios=ANIOS) -> pd.DataFrame:
    import dane_data as dd   # dependencia opcional (extra "datos")

    partes = []
    for anio in anios:
        log.info("GEIH %d: cargando con dane-data", anio)
        partes.append(preparar(dd.geih.load(anio, columns=["P6426"])))
    df = pd.concat(partes, ignore_index=True)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATA_PROCESSED / "geih_pensiones.parquet", index=False)
    return df
