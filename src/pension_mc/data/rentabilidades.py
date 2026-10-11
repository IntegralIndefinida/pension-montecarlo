"""
Valor de unidad diario de los fondos de pensiones obligatorias (Superfinanciera, vía datos.gov.co).

Dataset ``uawh-cjvi``: un registro por fecha, AFP y fondo, desde el 1 de enero de 2016.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config import DATA_PROCESSED, DATA_RAW
from ._http import get, log

DATASET = "uawh-cjvi"
API = f"https://www.datos.gov.co/resource/{DATASET}.json"
PAGINA = 50_000

# codigo_patrimonio -> fondo (los códigos 1 y 2 son cesantías y se descartan)
FONDOS = {1000: "moderado", 5000: "conservador", 6000: "mayor_riesgo",
          7000: "retiro_programado", 8000: "alternativo"}
AFP = {"proteccion": "Protección", "porvenir": "Porvenir", "colfondos": "Colfondos", "skandia": "Skandia"}


def _nombre_afp(nombre: str) -> str:
    n = nombre.lower().replace("ó", "o")
    return next((v for k, v in AFP.items() if k in n), nombre.strip('" '))


def descargar(force: bool = False) -> Path:
    """Descarga todas las filas de fondos de pensiones (paginando la API de Socrata)."""
    destino = DATA_RAW / "valor_unidad" / "valor_unidad_fpo.csv"
    if destino.exists() and not force:
        log.info("Ya existe %s, se omite la descarga", destino.name)
        return destino
    partes, offset = [], 0
    while True:
        params = {"$where": "codigo_patrimonio >= 1000", "$order": "fecha, codigo_entidad, codigo_patrimonio",
                  "$limit": PAGINA, "$offset": offset}
        filas = get(API, params=params).json()
        if not filas:
            break
        partes.append(pd.DataFrame(filas))
        offset += PAGINA
        log.info("valor de unidad: %d filas", offset - PAGINA + len(filas))
    destino.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(partes, ignore_index=True).to_csv(destino, index=False)
    return destino


def diario(crudo: pd.DataFrame) -> pd.DataFrame:
    """Limpia el valor de unidad diario: ``fecha``, ``afp``, ``fondo``, ``valor_unidad``."""
    df = pd.DataFrame({
        "fecha": pd.to_datetime(crudo["fecha"]).dt.tz_localize(None).dt.normalize(),
        "afp": crudo["nombre_entidad"].map(_nombre_afp),
        "fondo": pd.to_numeric(crudo["codigo_patrimonio"]).map(FONDOS),
        "valor_unidad": pd.to_numeric(crudo["valor_unidad"], errors="coerce"),
    })
    df = df.dropna(subset=["fondo", "valor_unidad"])
    df = df[df["valor_unidad"] > 0]
    return (df.drop_duplicates(["fecha", "afp", "fondo"], keep="last")
              .sort_values(["afp", "fondo", "fecha"]).reset_index(drop=True))


def mensual(diario: pd.DataFrame, ipc: pd.DataFrame) -> pd.DataFrame:
    """
    Rentabilidad mensual nominal y real a partir del último valor de unidad de cada mes.

    ``r_real = (1 + r_nominal) / (1 + inflación mensual) - 1``. El primer mes de cada serie
    queda sin rentabilidad. Se descartan los meses sin dato del último día (el mes en curso):
    la serie es diaria e incluye fines de semana y festivos.
    """
    fin_mes = (diario.assign(dia=diario["fecha"], fecha=diario["fecha"] + pd.offsets.MonthEnd(0))
                     .groupby(["afp", "fondo", "fecha"], as_index=False)
                     .agg(valor_unidad=("valor_unidad", "last"), dia=("dia", "max")))
    fin_mes = fin_mes[fin_mes["dia"] == fin_mes["fecha"]].drop(columns="dia")
    fin_mes["r_nominal"] = fin_mes.groupby(["afp", "fondo"])["valor_unidad"].pct_change()
    fin_mes = fin_mes.merge(ipc[["fecha", "inflacion_mensual"]], on="fecha", how="left")
    fin_mes["r_real"] = (1 + fin_mes["r_nominal"]) / (1 + fin_mes["inflacion_mensual"]) - 1
    return fin_mes.drop(columns="inflacion_mensual")


def procesar(ipc: pd.DataFrame, archivo: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    archivo = archivo or DATA_RAW / "valor_unidad" / "valor_unidad_fpo.csv"
    d = diario(pd.read_csv(archivo))
    m = mensual(d, ipc)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    d.to_parquet(DATA_PROCESSED / "valor_unidad_diario.parquet", index=False)
    m.to_parquet(DATA_PROCESSED / "rentabilidad_mensual.parquet", index=False)
    return d, m
