"""
Trayectorias salariales estocásticas de los cotizantes.

Modelo para el log del salario **latente** (real, en pesos de 2026) de la persona ``i`` a la edad ``a``:

    ln w*_ia = f_k(a) + g·t + α_i + z_ia,      z_ia = ρ_e z_i,a-1 + ε_ia,   z_i,17 = 0
    α_i ~ N(0, σα_e²),   ε_ia ~ N(0, σε_e²)

- ``f_k`` es un perfil cuadrático en la edad para cada tipo ``k`` = educación × sexo.
- ``g`` es el crecimiento real de la productividad (supuesto, ``config/parametros.yaml``).
- ``α`` es la heterogeneidad permanente y ``z`` un choque persistente AR(1); sus parámetros
  dependen del tipo ``k``.

El salario observado es ``w = max(w*, SMMLV)``: un tercio de los cotizantes gana el mínimo
(muchos declaran el mínimo más el auxilio de transporte, que no hace parte del IBC). Por eso la
ecuación se estima como un **Tobit heterocedástico** censurado en el mínimo + auxilio, con
``ln σ_k(a)`` cuadrático en la edad. Luego ``(σα, σε, ρ)`` se identifican con el crecimiento de
la varianza con la edad (Deaton y Paxson, 1994):

    σ_k(a)² = σα_k² + σε_k² · (1 − ρ_k^{2(a−17)}) / (1 − ρ_k²)

Los salarios se simulan con frecuencia anual: el salario de un año rige sus 12 meses.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy import optimize, special, stats

from .config import ARTEFACTOS, DATA_PROCESSED, parametros

EDUCACION = {"Ninguno": "Primaria o menos", "Primaria": "Primaria o menos", "Secundaria": "Secundaria",
             "Media": "Media", "Superior": "Superior"}
NIVELES = ["Primaria o menos", "Secundaria", "Media", "Superior"]
SEXOS = ["Hombre", "Mujer"]
EDAD_MIN, EDAD_MAX = 18, 65
EDAD_ENTRADA = 17          # z = 0 antes de entrar al mercado laboral
UMBRAL_CENSURA = 1.05      # un salario declarado <= 1,05 SMMLV se trata como "gana el mínimo"
HOLGURA_AUXILIO = 0.02     # en la GEIH: ingreso <= (1 + auxilio/SMMLV + 0,02) SMMLV gana el mínimo
ARCHIVO = ARTEFACTOS / "modelo_salarial.json"


def _e(edad):
    """Edad centrada y escalada para el polinomio: (edad − 40) / 10."""
    return (np.asarray(edad, dtype=np.float64) - 40) / 10


# --------------------------------------------------------------------------- Muestra
def muestra(geih: pd.DataFrame, ipc: pd.DataFrame) -> pd.DataFrame:
    """
    Cotizantes de 18 a 65 años con ingreso laboral positivo, en pesos reales de la última fecha del IPC.

    ``y`` es el log del ingreso real, ``c`` el log del umbral de censura (mínimo + auxilio de
    transporte + 2 % del mínimo, en pesos reales) y ``censurado`` marca a quienes no lo superan.
    """
    d = geih[(geih["cotiza"] == 1) & (geih["ingreso_laboral"] > 0) & geih["edad"].between(EDAD_MIN, EDAD_MAX)]
    d = d[["anio", "mes", "fex", "sexo", "edad", "nivel_educativo", "ingreso_laboral", "smlv", "ratio_smlv"]].copy()
    d["educ"] = d["nivel_educativo"].astype(str).map(EDUCACION)
    d["sexo"] = d["sexo"].astype(str)
    p = ipc.assign(anio=ipc["fecha"].dt.year, mes=ipc["fecha"].dt.month)[["anio", "mes", "ipc"]]
    d = d.merge(p, on=["anio", "mes"], how="left")
    deflactor = ipc["ipc"].iloc[-1] / d["ipc"]
    auxilio = d["anio"].map(parametros()["auxilio_transporte"]["valores"])
    umbral = 1 + auxilio / d["smlv"] + HOLGURA_AUXILIO
    d["y"] = np.log(d["ingreso_laboral"] * deflactor)
    d["c"] = np.log(d["smlv"] * deflactor * umbral)
    d["censurado"] = d["ratio_smlv"] <= umbral
    return d.dropna(subset=["educ", "y"]).reset_index(drop=True)


# --------------------------------------------------------------------------- Diseño
def _tipos():
    return [(e, s) for e in NIVELES for s in SEXOS]


def matriz_media(educ, sexo, edad, anio, anios) -> np.ndarray:
    """Columnas: [1, e, e²] por tipo educación × sexo, más efectos de año (base: el primero)."""
    educ, sexo = np.asarray(educ), np.asarray(sexo)
    e = _e(edad)
    cols = []
    for ed, sx in _tipos():
        m = ((educ == ed) & (sexo == sx)).astype(np.float64)
        cols += [m, m * e, m * e**2]
    anio = np.broadcast_to(np.asarray(anio), e.shape)
    cols += [(anio == a).astype(np.float64) for a in anios[1:]]
    return np.column_stack(cols)


def matriz_escala(educ, sexo, edad) -> np.ndarray:
    """Columnas: [1, e, e²] por tipo educación × sexo (para ln σ)."""
    educ, sexo = np.asarray(educ), np.asarray(sexo)
    e = _e(edad)
    cols = []
    for ed, sx in _tipos():
        m = ((educ == ed) & (sexo == sx)).astype(np.float64)
        cols += [m, m * e, m * e**2]
    return np.column_stack(cols)


def clave(educ: str, sexo: str) -> str:
    return f"{educ}|{sexo}"


# --------------------------------------------------------------------------- Tobit
def tobit(y, c, censurado, X, Z, peso=None, x0=None) -> tuple[np.ndarray, np.ndarray, optimize.OptimizeResult]:
    """
    Tobit heterocedástico censurado por la izquierda, por máxima verosimilitud.

    ``y* = Xβ + exp(Zγ)·u``, ``u ~ N(0, 1)``. Si ``censurado``, solo se sabe que ``y* <= c``.
    Devuelve ``(β, γ, resultado)``.
    """
    y, c, cen = np.asarray(y, float), np.asarray(c, float), np.asarray(censurado, bool)
    w = np.ones(len(y)) if peso is None else np.asarray(peso, float)
    w = w / w.mean()
    kx = X.shape[1]

    if x0 is None:
        nc = ~cen
        b0 = np.linalg.lstsq(X[nc] * np.sqrt(w[nc])[:, None], y[nc] * np.sqrt(w[nc]), rcond=None)[0]
        g0 = np.linalg.lstsq(Z, np.full(len(y), np.log(np.std(y[nc] - X[nc] @ b0))), rcond=None)[0]
        x0 = np.r_[b0, g0]

    def nll(theta):
        b, g = theta[:kx], theta[kx:]
        mu, ls = X @ b, Z @ g
        s = np.exp(ls)
        r = (y - mu) / s
        h = (c - mu) / s
        ll = np.where(cen, special.log_ndtr(h), -ls - 0.5 * np.log(2 * np.pi) - 0.5 * r**2)
        lam = np.exp(stats.norm.logpdf(h) - special.log_ndtr(h))
        d_mu = np.where(cen, -lam / s, r / s)
        d_ls = np.where(cen, -lam * h, r**2 - 1)
        grad = np.r_[X.T @ (w * d_mu), Z.T @ (w * d_ls)]
        return -(w @ ll) / len(y), -grad / len(y)

    res = optimize.minimize(nll, x0, jac=True, method="L-BFGS-B", options={"maxiter": 2_000, "gtol": 1e-8})
    if not res.success:
        raise RuntimeError(f"Tobit no convergió: {res.message}")
    return res.x[:kx], res.x[kx:], res


# --------------------------------------------------------------------------- Varianza por edad
def varianza_ar(edad, sigma_alpha, sigma_eps, rho):
    """Varianza de α + z a la edad dada, con z = 0 a los 17 años."""
    n = np.asarray(edad, float) - EDAD_ENTRADA
    if rho >= 1:
        return sigma_alpha**2 + sigma_eps**2 * n
    return sigma_alpha**2 + sigma_eps**2 * (1 - rho ** (2 * n)) / (1 - rho**2)


def ajustar_ar(edades, varianzas) -> tuple[float, float, float]:
    """Ajusta (σα, σε, ρ) a un perfil de varianza por edad (mínimos cuadrados en logaritmos)."""
    edades, v = np.asarray(edades, float), np.asarray(varianzas, float)

    def resid(p):
        return np.log(varianza_ar(edades, *p)) - np.log(v)

    x0 = [np.sqrt(v[0]) * 0.8, np.sqrt(max(v[-1] - v[0], 1e-4) / 10), 0.9]
    r = optimize.least_squares(resid, x0, bounds=([1e-4, 1e-4, 0.0], [5.0, 5.0, 0.995]))
    return tuple(float(x) for x in r.x)


# --------------------------------------------------------------------------- Modelo
@dataclass
class ModeloSalarial:
    """Parámetros estimados; ``beta`` y ``gamma`` siguen el orden de ``matriz_media`` y ``matriz_escala``."""

    beta: list[float]
    gamma: list[float]
    anios: list[int]
    ar: dict[str, tuple[float, float, float]]     # "educación|sexo" -> (σα, σε, ρ)
    pesos_de: str                                 # descripción de la unidad monetaria
    n_obs: int = 0
    proporcion_censurada: float = 0.0
    log_verosimilitud: float = 0.0
    extra: dict = field(default_factory=dict)

    # ---- perfiles
    def log_media(self, edad, sexo: str, educ: str) -> np.ndarray:
        """E[ln w*] del perfil de corte transversal del último año estimado (sin crecimiento)."""
        edad = np.atleast_1d(np.asarray(edad, float))
        X = matriz_media(np.full(edad.shape, educ), np.full(edad.shape, sexo), edad, self.anios[-1], self.anios)
        return X @ np.asarray(self.beta)

    def sigma(self, edad, sexo: str, educ: str) -> np.ndarray:
        """Desviación estándar del ln w* latente según el Tobit."""
        edad = np.atleast_1d(np.asarray(edad, float))
        Z = matriz_escala(np.full(edad.shape, educ), np.full(edad.shape, sexo), edad)
        return np.exp(Z @ np.asarray(self.gamma))

    # ---- simulación
    def simular(self, edad: float, sexo: str, educ: str, n_anios: int, n_sims: int, *,
                salario_actual: float | None = None, smmlv_actual: float | None = None,
                crecimiento: float | None = None, seed: int | None = None) -> np.ndarray:
        """
        Salarios latentes anuales ``(n_sims, n_anios)`` en pesos reales, desde la edad ``edad``.

        Sin ``salario_actual``, la persona se sortea de la distribución de su tipo. Con él, se
        condiciona: el desvío actual ``u = ln w − f(a)`` se reparte entre α y z en proporción a
        sus varianzas. Si el salario es el mínimo (``<= smmlv_actual``), ``u`` se sortea de la
        normal truncada por debajo de ese umbral. Para obtener el salario observado, aplique
        ``np.maximum(w, smmlv)``.
        """
        rng = np.random.default_rng(seed)
        g = parametros()["supuestos"]["crecimiento_real_productividad"] if crecimiento is None else crecimiento
        s_a, s_e, rho = self.ar[clave(educ, sexo)]
        edades = edad + np.arange(n_anios)
        f = self.log_media(np.minimum(edades, EDAD_MAX), sexo, educ)   # el perfil se estimó hasta los 65
        v_z = varianza_ar(edad, 0.0, s_e, rho)
        v_u = s_a**2 + v_z

        if salario_actual is None:
            alpha = rng.normal(0, s_a, n_sims)
            z = rng.normal(0, np.sqrt(v_z), n_sims)
        else:
            if smmlv_actual is not None and salario_actual <= smmlv_actual * UMBRAL_CENSURA:
                tope = (np.log(smmlv_actual * UMBRAL_CENSURA) - f[0]) / np.sqrt(v_u)
                u = stats.truncnorm.rvs(-np.inf, tope, scale=np.sqrt(v_u), size=n_sims, random_state=rng)
            else:
                u = np.full(n_sims, np.log(salario_actual) - f[0])
            # α | u ~ N(u·σα²/v_u, σα²·v_z/v_u) y z = u − α
            alpha = u * s_a**2 / v_u + rng.normal(0, np.sqrt(s_a**2 * v_z / v_u), n_sims)
            z = u - alpha

        out = np.empty((n_sims, n_anios))
        for k in range(n_anios):
            if k:
                z = rho * z + rng.normal(0, s_e, n_sims)
            out[:, k] = f[k] + k * np.log1p(g) + alpha + z
        return np.exp(out)

    # ---- persistencia
    def guardar(self, ruta=ARCHIVO) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta=ARCHIVO) -> "ModeloSalarial":
        d = json.loads(ruta.read_text(encoding="utf-8"))
        d["ar"] = {k: tuple(v) for k, v in d["ar"].items()}
        return cls(**d)


def estimar(geih: pd.DataFrame | None = None, ipc: pd.DataFrame | None = None,
            edades_ajuste=range(20, 65), guardar: bool = True) -> ModeloSalarial:
    """Estima el Tobit y los parámetros (σα, σε, ρ) por tipo, y guarda el modelo (si ``guardar``)."""
    geih = pd.read_parquet(DATA_PROCESSED / "geih_pensiones.parquet") if geih is None else geih
    ipc = pd.read_parquet(DATA_PROCESSED / "ipc_mensual.parquet") if ipc is None else ipc
    d = muestra(geih, ipc)
    anios = sorted(d["anio"].unique().tolist())
    X = matriz_media(d["educ"], d["sexo"], d["edad"], d["anio"], anios)
    Z = matriz_escala(d["educ"], d["sexo"], d["edad"])
    beta, gamma, res = tobit(d["y"], d["c"], d["censurado"], X, Z, peso=d["fex"])

    m = ModeloSalarial(beta.tolist(), gamma.tolist(), anios, {},
                       pesos_de=f"pesos de {ipc['fecha'].iloc[-1]:%Y-%m} (IPC)",
                       n_obs=len(d), proporcion_censurada=float(np.average(d["censurado"], weights=d["fex"])),
                       log_verosimilitud=float(-res.fun * len(d)))
    edades = np.asarray(list(edades_ajuste))
    for e, s in _tipos():
        m.ar[clave(e, s)] = ajustar_ar(edades, m.sigma(edades, s, e) ** 2)
    if guardar:
        m.guardar()
    return m


# --------------------------------------------------------------------------- IBC
def smmlv_real(n_anios: int, crecimiento: float | None = None) -> np.ndarray:
    """SMMLV de cada año desde 2026, en pesos de 2026, con crecimiento real constante."""
    p = parametros()
    g = p["supuestos"]["crecimiento_real_smmlv"] if crecimiento is None else crecimiento
    return p["smmlv"]["valores"][2026] * (1 + g) ** np.arange(n_anios)


def ibc(salario: np.ndarray, smmlv: np.ndarray, independiente: bool = False) -> np.ndarray:
    """
    Ingreso base de cotización: el salario (o el 40 % del ingreso de un independiente),
    con piso de 1 SMMLV y tope de 25 SMMLV. ``smmlv`` se alinea con la última dimensión.
    """
    c = parametros()["cotizacion"]
    base = salario * (c["ibc_independientes_pct_ingreso"] if independiente else 1.0)
    return np.clip(base, c["ibc_min_smmlv"] * smmlv, c["ibc_max_smmlv"] * smmlv)
