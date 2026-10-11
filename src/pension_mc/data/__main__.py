"""
Descarga y procesa todos los insumos del simulador.

    python -m pension_mc.data                      # todo
    python -m pension_mc.data --solo ipc mortalidad
    python -m pension_mc.data --force              # vuelve a descargar
    python -m pension_mc.data --anios-geih 2024 2025
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from ..config import DATA_PROCESSED
from . import geih, ipc, mortalidad, rentabilidades, smmlv

PASOS = ["ipc", "rentabilidades", "smmlv", "mortalidad", "geih"]


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m pension_mc.data", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo", nargs="+", choices=PASOS, default=PASOS)
    p.add_argument("--force", action="store_true", help="repetir descargas aunque ya existan")
    p.add_argument("--anios-geih", nargs="+", type=int, default=list(geih.ANIOS))
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("pension_mc.data")

    serie_ipc = None
    if "ipc" in a.solo:
        ipc.descargar(a.force)
        serie_ipc = ipc.procesar()
        log.info("IPC: %d meses (%s a %s)", len(serie_ipc), serie_ipc.fecha.min().date(), serie_ipc.fecha.max().date())
    if serie_ipc is None and {"rentabilidades", "smmlv"} & set(a.solo):
        serie_ipc = pd.read_parquet(DATA_PROCESSED / "ipc_mensual.parquet")

    if "rentabilidades" in a.solo:
        rentabilidades.descargar(a.force)
        d, m = rentabilidades.procesar(serie_ipc)
        log.info("Valor de unidad: %d filas diarias, %d mensuales", len(d), len(m))
    if "smmlv" in a.solo:
        s = smmlv.procesar(serie_ipc)
        log.info("SMMLV: %d a %d", s.anio.min(), s.anio.max())
    if "mortalidad" in a.solo:
        mortalidad.descargar(a.force)
        t = mortalidad.procesar()
        log.info("RV08: %d filas, validada", len(t))
    if "geih" in a.solo:
        g = geih.procesar(a.anios_geih)
        log.info("GEIH: %d personas de %d a %d años", len(g), geih.EDAD_MIN, geih.EDAD_MAX)


if __name__ == "__main__":
    main()
