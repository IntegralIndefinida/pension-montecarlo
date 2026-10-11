"""Descargas HTTP con caché en disco."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

log = logging.getLogger("pension_mc.data")

HEADERS = {"User-Agent": "Mozilla/5.0 (pension-montecarlo; proyecto académico)"}
TIMEOUT = 120


def get(url: str, **kwargs) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r


def descargar(url: str, destino: Path, force: bool = False) -> Path:
    """Descarga ``url`` a ``destino`` salvo que ya exista (``force`` la repite)."""
    if destino.exists() and not force:
        log.info("Ya existe %s, se omite la descarga", destino.name)
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    log.info("Descargando %s", url)
    tmp = destino.with_suffix(destino.suffix + ".part")
    tmp.write_bytes(get(url).content)
    tmp.replace(destino)
    return destino
