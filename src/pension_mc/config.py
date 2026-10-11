"""Rutas del proyecto y carga de parámetros normativos."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("PENSION_MC_ROOT", Path(__file__).resolve().parents[2]))
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
PARAMETROS = ROOT / "config" / "parametros.yaml"


@lru_cache(maxsize=None)
def parametros() -> dict:
    """Parámetros de ``config/parametros.yaml`` (ver ``docs/marco_normativo.md``)."""
    with PARAMETROS.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
