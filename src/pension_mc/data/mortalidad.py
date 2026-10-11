"""
Tablas de mortalidad de rentistas válidos RV08 (Superfinanciera, Resolución 1555 de 2010).

Requiere ``pdftotext`` (paquete poppler / poppler-utils).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

from ..config import ARTEFACTOS, DATA_PROCESSED, DATA_RAW
from ._http import descargar as _descargar

URL = "https://www.fasecolda.com/wp-content/uploads/res-1555-2010.pdf"

# Cada fila del PDF trae hombres y mujeres lado a lado: x l(x) d(x) q(x) e(x) x l(x) d(x) q(x) e(x)
_BLOQUE = r"(\d{2,3})\s+([\d,]+)\s+([\d,]+)\s+(\d\.\d+)\s+(\d+\.\d)"
_RE_FILA = re.compile(rf"^\s*{_BLOQUE}\s+{_BLOQUE}\s*$")
COLUMNAS = ["edad", "lx", "dx", "qx", "ex"]


def descargar(force: bool = False) -> Path:
    return _descargar(URL, DATA_RAW / "mortalidad" / "res-1555-2010.pdf", force=force)


def parsear(texto: str) -> pd.DataFrame:
    """Extrae la tabla RV08 del texto (``pdftotext -layout``) de la resolución."""
    filas = []
    for linea in texto.splitlines():
        m = _RE_FILA.match(linea)
        if m:
            g = [s.replace(",", "") for s in m.groups()]
            filas.append(("Hombre", *g[:5]))
            filas.append(("Mujer", *g[5:]))
    df = pd.DataFrame(filas, columns=["sexo", *COLUMNAS])
    df[["edad", "lx", "dx"]] = df[["edad", "lx", "dx"]].astype(int)
    df[["qx", "ex"]] = df[["qx", "ex"]].astype(float)
    return df.sort_values(["sexo", "edad"]).reset_index(drop=True)


def validar(df: pd.DataFrame) -> None:
    """Chequeos de consistencia actuarial; lanza ``ValueError`` si algo no cuadra."""
    for sexo, g in df.groupby("sexo"):
        g = g.set_index("edad")
        if list(g.index) != list(range(15, 111)):
            raise ValueError(f"RV08 {sexo}: edades incompletas")
        if not (g["lx"].shift(-1).iloc[:-1] == (g["lx"] - g["dx"]).iloc[:-1]).all():
            raise ValueError(f"RV08 {sexo}: l(x+1) != l(x) - d(x)")
        if ((g["dx"] / g["lx"] - g["qx"]).abs() > 1e-5).any():
            raise ValueError(f"RV08 {sexo}: q(x) != d(x) / l(x)")
        if g["qx"].iloc[-1] != 1.0:
            raise ValueError(f"RV08 {sexo}: la tabla no cierra en q(110) = 1")


def procesar(archivo: Path | None = None) -> pd.DataFrame:
    archivo = archivo or DATA_RAW / "mortalidad" / "res-1555-2010.pdf"
    texto = subprocess.run(["pdftotext", "-layout", str(archivo), "-"],
                           capture_output=True, text=True, check=True).stdout
    df = parsear(texto)
    validar(df)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATA_PROCESSED / "mortalidad_rv08.parquet", index=False)
    ARTEFACTOS.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ARTEFACTOS / "mortalidad_rv08.parquet", index=False)
    return df
