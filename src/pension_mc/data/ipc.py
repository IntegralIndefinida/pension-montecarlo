"""Índice de Precios al Consumidor (DANE): serie de empalme mensual, base dic. 2018 = 100."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ..config import DATA_PROCESSED, DATA_RAW
from ._http import descargar as _descargar
from ._http import get

PAGINA = "https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc"
BASE = "https://www.dane.gov.co"
_RE_ANEXO = re.compile(r'href="(/files/operaciones/IPC/[^"]*/anex-IPC-Indices-[^"]*\.xlsx)"')

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def descargar(force: bool = False) -> Path:
    """Busca en la página del DANE el anexo de índices más reciente y lo descarga."""
    m = _RE_ANEXO.search(get(PAGINA).text)
    if not m:
        raise RuntimeError(f"No se encontró el anexo 'anex-IPC-Indices' en {PAGINA}")
    ruta = m.group(1)
    return _descargar(BASE + ruta, DATA_RAW / "ipc" / Path(ruta).name, force=force)


def parsear(crudo: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte la hoja del DANE (meses en filas, años en columnas) a una serie mensual.

    ``crudo`` es la hoja leída con ``header=None``. Devuelve ``fecha`` (fin de mes),
    ``ipc``, ``inflacion_mensual`` e ``inflacion_anual``.
    """
    col0 = crudo.iloc[:, 0].astype(str).str.strip().str.lower()
    fila_mes = col0[col0 == "mes"].index[0]
    anios = pd.to_numeric(crudo.loc[fila_mes].iloc[1:], errors="coerce")

    cuerpo = crudo.loc[fila_mes + 1:]
    cuerpo = cuerpo[cuerpo.iloc[:, 0].astype(str).str.strip().str.lower().isin(MESES)]
    filas = []
    for _, fila in cuerpo.iterrows():
        mes = MESES[str(fila.iloc[0]).strip().lower()]
        for anio, valor in zip(anios, fila.iloc[1:]):
            if pd.notna(anio) and pd.notna(pd.to_numeric(valor, errors="coerce")):
                filas.append((int(anio), mes, float(valor)))

    df = pd.DataFrame(filas, columns=["anio", "mes", "ipc"])
    df["fecha"] = pd.to_datetime(dict(year=df.anio, month=df.mes, day=1)) + pd.offsets.MonthEnd(0)
    df = df.sort_values("fecha").reset_index(drop=True)[["fecha", "ipc"]]
    df["inflacion_mensual"] = df["ipc"].pct_change()
    df["inflacion_anual"] = df["ipc"].pct_change(12)
    return df


def procesar(archivo: Path | None = None) -> pd.DataFrame:
    archivo = archivo or max((DATA_RAW / "ipc").glob("anex-IPC-Indices-*.xlsx"), key=lambda p: p.stat().st_mtime)
    df = parsear(pd.read_excel(archivo, sheet_name=0, header=None))
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATA_PROCESSED / "ipc_mensual.parquet", index=False)
    return df
