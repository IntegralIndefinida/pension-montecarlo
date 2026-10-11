"""Salario mínimo anual (serie de ``dane-data``) y su crecimiento real."""

from __future__ import annotations

import pandas as pd
from dane_data.referencias import SMLV

from ..config import DATA_PROCESSED, parametros


def procesar(ipc: pd.DataFrame) -> pd.DataFrame:
    """
    ``anio``, ``smmlv``, ``var_nominal`` y ``var_real``.

    El crecimiento real descuenta la inflación de diciembre del año anterior, que es
    la referencia con la que se negocia el aumento.
    """
    df = pd.DataFrame(sorted(SMLV.items()), columns=["anio", "smmlv"])
    for anio, valor in parametros()["smmlv"]["valores"].items():
        if SMLV.get(anio) != valor:
            raise ValueError(f"SMMLV {anio}: dane-data={SMLV.get(anio)} vs parametros.yaml={valor}")

    dic = ipc[ipc["fecha"].dt.month == 12].assign(anio=lambda d: d["fecha"].dt.year + 1)
    df = df.merge(dic[["anio", "inflacion_anual"]].rename(columns={"inflacion_anual": "inflacion_dic_anterior"}),
                  on="anio", how="left")
    df["var_nominal"] = df["smmlv"].pct_change()
    df["var_real"] = (1 + df["var_nominal"]) / (1 + df["inflacion_dic_anterior"]) - 1

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATA_PROCESSED / "smmlv_anual.parquet", index=False)
    return df
