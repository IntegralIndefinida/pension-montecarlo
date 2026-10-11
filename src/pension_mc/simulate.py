"""
Motor de simulación: de un perfil de afiliado a la distribución de su pensión.

    from pension_mc.simulate import Perfil, Supuestos, simular
    r = simular(Perfil(edad=30, sexo="Mujer", educacion="Superior", salario=3_000_000,
                       semanas=250, cotiza_hoy=True))
    r.resumen()

Cada simulación combina, para la misma persona simulada:

1. **Salarios** (paso 4), condicionados en el salario actual.
2. **Meses cotizados** (paso 5), condicionados en las semanas ya cotizadas.
3. **Rentabilidades** (paso 3) del fondo elegido o de la trayectoria de multifondos por defecto.
4. **Reglas de pensión** (paso 6) de las AFP y de Colpensiones.

Todos los montos están en pesos reales de 2026. Cada componente usa una semilla derivada de
``Supuestos.seed`` con ``SeedSequence`` (semillas distintas dan corridas independientes): dos
escenarios con la misma semilla comparten los números aleatorios, así que sus diferencias se deben
al cambio de supuesto y no al ruido de la simulación.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache

import numpy as np
import pandas as pd

from . import accumulation as A
from . import regimes as G
from . import returns as R
from . import wages as W
from .config import parametros
from .contributions import ModeloCotizacion
from .wages import ModeloSalarial

# Calibraciones alternativas de la densidad de cotización (notebooks/04_cotizacion.ipynb)
CALIBRACIONES_COTIZACION = {
    "base": None,                                                  # η se consolida a los 30 años
    "η se consolida a los 25": {"mu": 0.183, "kappa": 0.753, "beta": 4.120, "rho_eta": 0.627, "edad_fija_eta": 25.0},
    "η se consolida a los 35": {"mu": 0.234, "kappa": 0.292, "beta": 6.760, "rho_eta": 0.779, "edad_fija_eta": 35.0},
    "η permanente": {"mu": 0.194, "kappa": 0.828, "beta": 4.091, "rho_eta": 1.0, "edad_fija_eta": 200.0},
    "η permanente, sin duración (A)": {"mu": 0.120, "kappa": 0.0, "beta": 1.441, "rho_eta": 1.0, "edad_fija_eta": 200.0},
}


@dataclass
class Perfil:
    """Datos del afiliado. Montos en pesos de 2026."""

    edad: float
    sexo: str                                  # "Mujer" | "Hombre"
    educacion: str                             # "Primaria o menos" | "Secundaria" | "Media" | "Superior"
    salario: float | None = None               # salario (o ingreso) mensual actual; None: se sortea del tipo
    semanas: float = 0.0                       # semanas ya cotizadas
    saldo: float | None = None                 # saldo actual en la AFP; None: se aproxima con las semanas
    cotiza_hoy: bool | None = None
    independiente: bool = False                # cotiza sobre el 40 % del ingreso
    edad_retiro: float | None = None           # None: edad legal de pensión
    fondo: str | None = None                   # None: multifondos por defecto; o "moderado", etc.
    aporte_voluntario_pct: float = 0.0         # aporte voluntario a la cuenta, fracción del salario
    laguna: tuple[float, float] | None = None  # edades entre las que NO cotiza (experimentos)
    conyuge_diferencia_edad: float | None = None  # edad del cónyuge − edad propia; None: sin beneficiario

    def __post_init__(self):
        self.sexo = self.sexo.capitalize()


@dataclass
class Supuestos:
    afp: str = "Protección"
    metodo_rentabilidad: str = "bootstrap"     # "bootstrap" | "t" | "determinista"
    escenario_determinista: str = "base"       # "pesimista" | "base" | "optimista"
    ajuste_rentabilidad: float = 0.0           # puntos de rentabilidad real anual sobre la histórica
    incertidumbre_media: bool = False
    tasa_tecnica: float | None = None          # None: config (4 %)
    crecimiento_smmlv: float | None = None     # None: config (1 %)
    crecimiento_salarios: float | None = None  # None: config (1 %)
    cotizacion: str = "base"                   # clave de CALIBRACIONES_COTIZACION
    congelar_cotizacion_desde: float | None = None  # edad desde la que se mantiene la tasa de cotización
    seed: int = 2026

    def valor(self, nombre: str) -> float:
        v = getattr(self, nombre)
        clave = {"tasa_tecnica": "tasa_tecnica_real", "crecimiento_smmlv": "crecimiento_real_smmlv",
                 "crecimiento_salarios": "crecimiento_real_productividad"}[nombre]
        return parametros()["supuestos"][clave] if v is None else v


@dataclass
class Resultado:
    perfil: Perfil
    supuestos: Supuestos
    edad_retiro: float
    anio_retiro: int
    smmlv_retiro: float
    afp: pd.DataFrame                          # una fila por simulación (ver regimes.rais)
    colpensiones: pd.DataFrame                 # una fila por simulación (ver regimes.rpm)
    saldo: np.ndarray | None = field(default=None, repr=False)   # (n_sims, n_meses) float32

    @property
    def n_sims(self) -> int:
        return len(self.afp)

    def resumen(self) -> pd.Series:
        """Métricas principales. Mesadas en SMMLV del año de retiro; saldos en millones de pesos de 2026."""
        a, c, sm = self.afp, self.colpensiones, self.smmlv_retiro
        pen_a, pen_c = a["estado"] != "devolucion", c["estado"] == "pension"
        req = G.semanas_requeridas("rais", self.perfil.sexo, self.anio_retiro)
        n = self.n_sims

        def q(x, p):
            return float(np.percentile(x, p)) if len(x) else np.nan

        out = {
            "edad_retiro": self.edad_retiro,
            "anio_retiro": self.anio_retiro,
            "afp_p_pension": pen_a.mean(),
            "afp_p_capital_suficiente": (a["estado"] == "capital_suficiente").mean(),
            "afp_p_garantia_minima": (a["estado"] == "garantia_minima").mean(),
            "afp_p_devolucion": (~pen_a).mean(),
            "afp_mesada_p10": q(a.loc[pen_a, "mesada"] / sm, 10),
            "afp_mesada_p50": q(a.loc[pen_a, "mesada"] / sm, 50),
            "afp_mesada_p90": q(a.loc[pen_a, "mesada"] / sm, 90),
            "afp_mesada_media_total": float((a["mesada"] / sm).mean()),
            "afp_reemplazo_p50": q(a.loc[pen_a, "reemplazo"], 50),
            "afp_saldo_p50_millones": float(np.median(a["saldo"])) / 1e6,
            "afp_costo_garantia_medio_millones": float(a["costo_garantia"].mean()) / 1e6,
            "semanas_p10": q(a["semanas"], 10),
            "semanas_p50": q(a["semanas"], 50),
            "semanas_p90": q(a["semanas"], 90),
            "p_semanas_garantia": float((a["semanas"] >= req).mean()),
            "colpensiones_p_pension": pen_c.mean(),
            "colpensiones_mesada_p50": q(c.loc[pen_c, "mesada"] / sm, 50),
            "colpensiones_reemplazo_p50": q(c.loc[pen_c, "reemplazo"], 50),
            "colpensiones_mesada_media_total": float((c["mesada"] / sm).mean()),
        }
        out["error_estandar_p_pension"] = float(np.sqrt(out["afp_p_pension"] * (1 - out["afp_p_pension"]) / n))
        return pd.Series(out)


# --------------------------------------------------------------------------- Modelos
@lru_cache(maxsize=None)
def _modelos() -> tuple[ModeloSalarial, ModeloCotizacion]:
    return ModeloSalarial.cargar(), ModeloCotizacion.cargar()


@lru_cache(maxsize=None)
def _historico(afp: str) -> pd.DataFrame:
    return R.historico(afp)


def _modelo_cotizacion(nombre: str) -> ModeloCotizacion:
    base = _modelos()[1]
    params = CALIBRACIONES_COTIZACION[nombre]
    if params is None:
        return base
    return ModeloCotizacion(base.edades, base.tasas, params["mu"], params["beta"], kappa=params["kappa"],
                            rho_eta=params["rho_eta"], edad_fija_eta=params["edad_fija_eta"])


def _semillas(seed: int) -> dict[str, int]:
    """Semillas independientes por componente, derivadas de una sola semilla."""
    estado = np.random.SeedSequence(seed).generate_state(4)
    return dict(zip(("salarios", "historia", "cotizacion", "rentabilidad"), (int(x) for x in estado)))


def saldo_aproximado(semanas: float, salario: float, rentabilidad_acumulada: float = 1.25) -> float:
    """Saldo actual aproximado cuando no se conoce: 11,5 % del salario por mes cotizado, más rendimientos."""
    p = parametros()
    meses = semanas / p["supuestos"]["semanas_por_mes"]
    return p["cotizacion"]["reparto_rais"]["cuenta_individual"] * salario * meses * rentabilidad_acumulada


def _rentabilidades(sup: Supuestos, n_sims: int, n_meses: int) -> R.Rentabilidades:
    hist = _historico(sup.afp)
    seed = _semillas(sup.seed)["rentabilidad"]
    media = None
    if sup.ajuste_rentabilidad:
        base = np.expm1(np.log1p(hist).mean() * 12)
        media = {f: float(base[f] + sup.ajuste_rentabilidad) for f in hist.columns}
    if sup.metodo_rentabilidad == "bootstrap":
        return R.bootstrap_estacionario(hist, n_sims, n_meses, media_objetivo=media,
                                        incertidumbre_media=sup.incertidumbre_media, seed=seed)
    if sup.metodo_rentabilidad == "t":
        return R.t_multivariada(hist, n_sims, n_meses, media_objetivo=media,
                                incertidumbre_media=sup.incertidumbre_media, seed=seed)
    if sup.metodo_rentabilidad == "determinista":
        sim = R.bootstrap_estacionario(hist, 4_000, n_meses, media_objetivo=media, seed=seed)
        esc = R.escenarios_deterministas(sim)[sup.escenario_determinista]
        return R.constante(esc.to_dict(), n_meses, fondos=list(hist.columns))
    raise ValueError(f"Método de rentabilidad desconocido: {sup.metodo_rentabilidad}")


# --------------------------------------------------------------------------- Motor
def simular(perfil: Perfil, supuestos: Supuestos | None = None, n_sims: int = 10_000,
            guardar_saldo: bool = False) -> Resultado:
    """Simula ``n_sims`` vidas laborales del perfil hasta la edad de retiro y aplica las reglas de pensión."""
    sup = supuestos or Supuestos()
    semilla = _semillas(sup.seed)
    p = parametros()
    sem_mes = p["supuestos"]["semanas_por_mes"]
    smmlv_hoy = p["smmlv"]["valores"][2026]
    ms, _ = _modelos()
    mc = _modelo_cotizacion(sup.cotizacion)

    edad_legal = G.edad_pension("rais", perfil.sexo)
    edad_retiro = perfil.edad_retiro if perfil.edad_retiro is not None else edad_legal
    n_anios = int(round(edad_retiro - perfil.edad))
    if n_anios < 1:
        raise ValueError("La edad de retiro debe ser al menos un año mayor que la edad actual")
    n_meses = 12 * n_anios
    anio_retiro = 2026 + n_anios

    # 1. Salarios (anuales) e IBC (mensual)
    smmlv = W.smmlv_real(n_anios + 1, sup.valor("crecimiento_smmlv"))
    salario = ms.simular(perfil.edad, perfil.sexo, perfil.educacion, n_anios, n_sims,
                         salario_actual=perfil.salario, smmlv_actual=smmlv_hoy,
                         crecimiento=sup.valor("crecimiento_salarios"), seed=semilla["salarios"])
    salario = np.maximum(salario, smmlv[:-1])
    salario_m = A.mensualizar(salario)
    ibc = A.mensualizar(W.ibc(salario, smmlv[:-1], independiente=perfil.independiente))

    # 2. Meses cotizados, condicionados en la historia
    if perfil.semanas > 0 or perfil.cotiza_hoy is not None:
        eta, estado = mc.condicionar(perfil.edad, perfil.sexo, perfil.educacion, perfil.semanas, n_sims,
                                     cotiza_hoy=perfil.cotiza_hoy, seed=semilla["historia"])
    else:
        eta, estado = None, None
    sin_cotizar = None
    if perfil.laguna is not None:
        edad_mes = perfil.edad + np.arange(n_meses) / 12
        sin_cotizar = (edad_mes >= perfil.laguna[0]) & (edad_mes < perfil.laguna[1])
    cotiza = mc.simular(perfil.edad, perfil.sexo, perfil.educacion, n_meses, n_sims, eta=eta,
                        estado_inicial=estado, seed=semilla["cotizacion"],
                        edad_tope=sup.congelar_cotizacion_desde, sin_cotizar=sin_cotizar)

    # 3. Rentabilidad del portafolio
    rent = _rentabilidades(sup, n_sims, n_meses)
    pesos = (R.pesos_por_defecto(perfil.edad, perfil.sexo, n_meses) if perfil.fondo is None
             else R.pesos_fijos(perfil.fondo, n_meses, rent.fondos))
    r = rent.portafolio(pesos)

    # 4. Saldo
    saldo0 = perfil.saldo
    if saldo0 is None:
        saldo0 = saldo_aproximado(perfil.semanas, perfil.salario or smmlv_hoy) if perfil.semanas else 0.0
    aportes = A.aportes(ibc, cotiza, voluntario_pct=perfil.aporte_voluntario_pct, salario=salario_m)
    trayectoria = A.saldo(aportes, r, saldo0)
    semanas = perfil.semanas + cotiza.sum(axis=1) * sem_mes

    # 5. Reglas de pensión
    conyuge = None
    if perfil.conyuge_diferencia_edad is not None:
        conyuge = ("Hombre" if perfil.sexo == "Mujer" else "Mujer", edad_retiro + perfil.conyuge_diferencia_edad)
    afp = G.rais(trayectoria[:, -1], semanas, edad=edad_retiro, sexo=perfil.sexo, anio=anio_retiro,
                 smmlv=smmlv[-1], tasa=sup.valor("tasa_tecnica"), crecimiento_smmlv=sup.valor("crecimiento_smmlv"),
                 conyuge=conyuge)
    col = G.rpm(ibc, cotiza, edad=edad_retiro, sexo=perfil.sexo, anio=anio_retiro, smmlv=smmlv[-1],
                semanas_previas=perfil.semanas)
    ultimo = salario[:, -min(10, n_anios):].mean(axis=1)
    for d in (afp, col):
        d["reemplazo"] = d["mesada"] / ultimo

    return Resultado(perfil, sup, edad_retiro, anio_retiro, float(smmlv[-1]), afp, col,
                     trayectoria.astype(np.float32) if guardar_saldo else None)


# --------------------------------------------------------------------------- Análisis
def comparar(escenarios: dict[str, tuple[Perfil, Supuestos | None]], n_sims: int = 10_000) -> pd.DataFrame:
    """Resumen de varios escenarios, una columna por escenario."""
    return pd.DataFrame({k: simular(pf, sp, n_sims).resumen() for k, (pf, sp) in escenarios.items()})


def tornado(perfil: Perfil, variaciones: dict[str, tuple[dict, dict]], *, base: Supuestos | None = None,
            metricas=("afp_p_pension", "afp_mesada_media_total"), n_sims: int = 10_000) -> pd.DataFrame:
    """
    Sensibilidad uno a uno. ``variaciones[nombre] = (cambios_bajo, cambios_alto)``; cada dict
    modifica campos de ``Supuestos`` o, con prefijo ``perfil.``, del perfil.
    """
    base = base or Supuestos()
    ref = simular(perfil, base, n_sims).resumen()

    def aplicar(cambios):
        pf = replace(perfil, **{k[7:]: v for k, v in cambios.items() if k.startswith("perfil.")})
        sp = replace(base, **{k: v for k, v in cambios.items() if not k.startswith("perfil.")})
        return simular(pf, sp, n_sims).resumen()

    filas = []
    for nombre, (bajo, alto) in variaciones.items():
        rb, ra = aplicar(bajo), aplicar(alto)
        for m in metricas:
            filas.append({"supuesto": nombre, "metrica": m, "base": ref[m], "bajo": rb[m], "alto": ra[m]})
    t = pd.DataFrame(filas)
    t["rango"] = (t["alto"] - t["bajo"]).abs()
    return t.sort_values(["metrica", "rango"], ascending=[True, False]).reset_index(drop=True)
