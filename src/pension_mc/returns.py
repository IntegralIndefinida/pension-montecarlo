"""
Generadores de rentabilidades reales mensuales de los fondos de pensiones obligatorias.

Todos devuelven un objeto :class:`Rentabilidades` con un arreglo ``(n_sims, n_meses, n_fondos)``
de rentabilidades **reales** mensuales simples, simuladas conjuntamente para los cuatro fondos
(el mismo mes histórico o la misma realización para todos), de modo que se conserva la
correlación entre fondos.

Generadores:

1. :func:`bootstrap_estacionario`: remuestrea bloques de meses históricos de longitud
   aleatoria (Politis y Romano, 1994). Conserva colas, correlación entre fondos y la
   autocorrelación de corto plazo.
2. :func:`t_multivariada`: log-rentabilidades i.i.d. con distribución t de Student
   multivariada (colas gruesas), con media y covarianza históricas.
3. :func:`escenarios_deterministas`: rentabilidad constante (pesimista / base / optimista)
   tomada de los percentiles de la rentabilidad anualizada simulada.

Ambos generadores estocásticos aceptan ``media_objetivo``: reemplaza la media histórica por
una rentabilidad real anual elegida, sin tocar la volatilidad ni la correlación. Con solo
~10 años de historia, el error estándar de la media anual es de ~2-3 puntos, así que la
media es el supuesto más incierto del modelo y conviene someterlo a sensibilidad.

``incertidumbre_media=True`` lleva esa incertidumbre a la simulación: cada trayectoria usa su
propia media, sorteada de la distribución muestral del promedio histórico, N(media, S / T),
con la correlación entre fondos. A horizontes largos domina sobre la volatilidad mensual.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .config import DATA_PROCESSED, parametros

FONDOS = ["mayor_riesgo", "moderado", "conservador", "retiro_programado"]
AFP_POR_DEFECTO = "Protección"
TANDA = 2_000  # simulaciones por tanda, para acotar la memoria de los intermedios en float64


@dataclass
class Rentabilidades:
    """Rentabilidades reales mensuales simuladas: ``r[sim, mes, fondo]``."""

    r: np.ndarray
    fondos: list[str]
    metodo: str

    @property
    def n_sims(self) -> int:
        return self.r.shape[0]

    @property
    def n_meses(self) -> int:
        return self.r.shape[1]

    def fondo(self, nombre: str) -> np.ndarray:
        """Rentabilidades ``(n_sims, n_meses)`` de un fondo."""
        return self.r[:, :, self.fondos.index(nombre)]

    def portafolio(self, pesos: np.ndarray) -> np.ndarray:
        """
        Rentabilidad ``(n_sims, n_meses)`` de un portafolio rebalanceado cada mes.

        ``pesos`` es ``(n_fondos,)`` (fijos) o ``(n_meses, n_fondos)`` (p. ej. la trayectoria
        de multifondos por edad); cada fila suma 1.
        """
        pesos = np.asarray(pesos, dtype=np.float64)
        if pesos.ndim == 1:
            pesos = np.broadcast_to(pesos, (self.n_meses, len(self.fondos)))
        if not np.allclose(pesos.sum(axis=1), 1):
            raise ValueError("Cada fila de pesos debe sumar 1")
        return np.einsum("ntk,tk->nt", self.r, pesos, optimize=True)

    def anualizada(self, r_mensual: np.ndarray) -> np.ndarray:
        """Rentabilidad real anual geométrica de cada trayectoria ``(n_sims,)``."""
        return np.expm1(np.log1p(r_mensual).mean(axis=1) * 12)


# --------------------------------------------------------------------------- Datos históricos
def historico(afp: str = AFP_POR_DEFECTO, fondos=FONDOS) -> pd.DataFrame:
    """Rentabilidades reales mensuales históricas ``(fecha × fondo)`` de una AFP."""
    m = pd.read_parquet(DATA_PROCESSED / "rentabilidad_mensual.parquet")
    m = m[(m["afp"] == afp) & m["fondo"].isin(fondos)].dropna(subset=["r_real"])
    if m.empty:
        raise ValueError(f"No hay rentabilidades para {afp!r}")
    return m.pivot(index="fecha", columns="fondo", values="r_real")[list(fondos)]


def _log_hist(hist: pd.DataFrame | np.ndarray) -> np.ndarray:
    return np.log1p(np.asarray(hist, dtype=np.float64))


def _ajustar_media(x: np.ndarray, fondos, media_objetivo: dict[str, float] | None) -> np.ndarray:
    """Recentra las log-rentabilidades para que su media equivalga a la rentabilidad real anual pedida."""
    if not media_objetivo:
        return x
    x = x.copy()
    for fondo, anual in media_objetivo.items():
        j = list(fondos).index(fondo)
        x[:, j] += np.log1p(anual) / 12 - x[:, j].mean()
    return x


def _desvio_media(x: np.ndarray, n_sims: int, activo: bool, rng: np.random.Generator) -> np.ndarray:
    """Desvío ``(n_sims, 1, n_fondos)`` de la media mensual por trayectoria, ~ N(0, S / T)."""
    if not activo:
        return np.zeros((n_sims, 1, x.shape[1]))
    cov_media = np.cov(x, rowvar=False) / len(x)
    return rng.multivariate_normal(np.zeros(x.shape[1]), cov_media, n_sims)[:, None, :]


# --------------------------------------------------------------------------- Bootstrap
def largo_bloque_optimo(x: np.ndarray) -> float:
    """
    Largo medio de bloque óptimo para el bootstrap estacionario de una serie.

    Politis y White (2004), con la corrección de Patton, Politis y White (2009). Usa un núcleo
    de tapa plana y elige el ancho de banda con la regla de autocorrelaciones no significativas.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    e = x - x.mean()
    kn = max(5, int(np.log10(n)))
    m_max = int(np.ceil(np.sqrt(n))) + kn
    acv = np.array([e[k:] @ e[: n - k] / n for k in range(m_max + 1)])
    rho = np.abs(acv[1:] / acv[0])
    umbral = 2 * np.sqrt(np.log10(n) / n)

    m_hat = next((m for m in range(m_max - kn + 1) if (rho[m : m + kn] < umbral).all()), None)
    m = m_max if m_hat is None else min(2 * max(m_hat, 1), m_max)

    k = np.arange(1, m + 1)
    lam = np.where(k / m <= 0.5, 1.0, 2 * (1 - k / m))
    g = 2 * np.sum(lam * k * acv[1 : m + 1])
    g0 = acv[0] + 2 * np.sum(lam * acv[1 : m + 1])
    b = (g**2 / g0**2) ** (1 / 3) * n ** (1 / 3)
    return float(np.clip(b, 1.0, np.ceil(min(3 * np.sqrt(n), n / 3))))


def indices_bootstrap(n_hist: int, n_sims: int, n_meses: int, largo_bloque: float,
                      rng: np.random.Generator) -> np.ndarray:
    """
    Índices ``(n_sims, n_meses)`` del bootstrap estacionario (circular).

    Cada mes, con probabilidad ``1 / largo_bloque`` empieza un bloque nuevo en un mes histórico
    al azar; si no, continúa con el mes histórico siguiente.
    """
    p = 1.0 / largo_bloque
    idx = np.empty((n_sims, n_meses), dtype=np.int32)
    idx[:, 0] = rng.integers(0, n_hist, n_sims)
    for t in range(1, n_meses):
        nuevo = rng.random(n_sims) < p
        idx[:, t] = np.where(nuevo, rng.integers(0, n_hist, n_sims), (idx[:, t - 1] + 1) % n_hist)
    return idx


def bootstrap_estacionario(hist: pd.DataFrame, n_sims: int, n_meses: int, *,
                           largo_bloque: float | None = None,
                           media_objetivo: dict[str, float] | None = None,
                           incertidumbre_media: bool = False,
                           seed: int | None = None) -> Rentabilidades:
    """
    Remuestrea meses históricos (todos los fondos a la vez) en bloques de largo aleatorio.

    ``largo_bloque`` por defecto es el promedio entre fondos del largo óptimo de Politis-White.
    """
    rng = np.random.default_rng(seed)
    x = _ajustar_media(_log_hist(hist), hist.columns, media_objetivo)
    if largo_bloque is None:
        largo_bloque = float(np.mean([largo_bloque_optimo(x[:, j]) for j in range(x.shape[1])]))
    idx = indices_bootstrap(len(x), n_sims, n_meses, largo_bloque, rng)
    delta = _desvio_media(x, n_sims, incertidumbre_media, rng)
    r = np.empty((n_sims, n_meses, x.shape[1]), dtype=np.float32)
    for i in range(0, n_sims, TANDA):
        r[i : i + TANDA] = np.expm1(x[idx[i : i + TANDA]] + delta[i : i + TANDA])
    metodo = f"bootstrap estacionario (bloque medio {largo_bloque:.1f} meses)"
    return Rentabilidades(r, list(hist.columns), metodo + (" + incertidumbre de la media" if incertidumbre_media else ""))


# --------------------------------------------------------------------------- t multivariada
def ajustar_nu(x: np.ndarray, grilla=None) -> float:
    """
    Grados de libertad de una t multivariada por máxima verosimilitud perfilada.

    La matriz de escala se fija para que la covarianza implícita sea la muestral:
    ``escala = S · (ν − 2) / ν``.
    """
    grilla = np.r_[np.arange(2.5, 10, 0.25), np.arange(10, 31, 1), 50, 100] if grilla is None else grilla
    mu, s = x.mean(axis=0), np.cov(x, rowvar=False)
    ll = [stats.multivariate_t(loc=mu, shape=s * (nu - 2) / nu, df=nu).logpdf(x).sum() for nu in grilla]
    return float(grilla[int(np.argmax(ll))])


def t_multivariada(hist: pd.DataFrame, n_sims: int, n_meses: int, *,
                   nu: float | None = None,
                   media_objetivo: dict[str, float] | None = None,
                   incertidumbre_media: bool = False,
                   seed: int | None = None) -> Rentabilidades:
    """Log-rentabilidades i.i.d. t multivariada con media y covarianza históricas."""
    rng = np.random.default_rng(seed)
    x = _ajustar_media(_log_hist(hist), hist.columns, media_objetivo)
    nu = ajustar_nu(x) if nu is None else nu
    mu, s = x.mean(axis=0), np.cov(x, rowvar=False)
    chol = np.linalg.cholesky(s * (nu - 2) / nu)
    k = x.shape[1]
    delta = _desvio_media(x, n_sims, incertidumbre_media, rng)
    r = np.empty((n_sims, n_meses, k), dtype=np.float32)
    for i in range(0, n_sims, TANDA):
        n = min(TANDA, n_sims - i)
        z = rng.standard_normal((n, n_meses, k)) @ chol.T
        w = np.sqrt(rng.chisquare(nu, (n, n_meses, 1)) / nu)
        r[i : i + n] = np.expm1(mu + delta[i : i + n] + z / w)
    metodo = f"t multivariada (ν = {nu:g})"
    return Rentabilidades(r, list(hist.columns), metodo + (" + incertidumbre de la media" if incertidumbre_media else ""))


# --------------------------------------------------------------------------- Deterministas
def escenarios_deterministas(sim: Rentabilidades, percentiles=(10, 50, 90)) -> pd.DataFrame:
    """
    Rentabilidad real anual constante por fondo para escenarios pesimista / base / optimista.

    Son los percentiles de la rentabilidad anualizada de las trayectorias simuladas, así que
    dependen del horizonte: a más meses, menos dispersión entre escenarios.
    """
    nombres = ["pesimista", "base", "optimista"] if len(percentiles) == 3 else [f"p{p}" for p in percentiles]
    filas = {f: np.percentile(sim.anualizada(sim.fondo(f)), percentiles) for f in sim.fondos}
    return pd.DataFrame(filas, index=pd.Index(nombres, name="escenario")).T


def constante(anual: dict[str, float], n_meses: int, fondos=FONDOS) -> Rentabilidades:
    """Una sola trayectoria con rentabilidad real anual constante por fondo."""
    mensual = np.array([(1 + anual[f]) ** (1 / 12) - 1 for f in fondos])
    r = np.broadcast_to(mensual, (1, n_meses, len(fondos))).astype(np.float32)
    return Rentabilidades(r, list(fondos), "determinista")


# --------------------------------------------------------------------------- Multifondos
def _escalon(tabla: list[list[float]], edad: np.ndarray) -> np.ndarray:
    edades = np.array([e for e, _ in tabla], dtype=float)
    valores = np.array([v for _, v in tabla], dtype=float)
    return valores[np.searchsorted(edades, edad, side="right") - 1]


def pesos_por_defecto(edad_inicial: float, sexo: str, n_meses: int) -> np.ndarray:
    """
    Pesos ``(n_meses, 4)`` sobre ``FONDOS`` para un afiliado que no elige fondo.

    Aplica la asignación por defecto (mayor riesgo → moderado, Decreto 959 de 2018) y la
    convergencia al conservador (art. 2.6.11.1.6 del Decreto 2555 de 2010), según la edad
    cumplida en cada mes. El fondo de retiro programado no se usa en la acumulación.
    """
    sexo = sexo.lower()
    mf = parametros()["multifondos"]
    edad = np.floor(edad_inicial + np.arange(n_meses) / 12)
    conservador = _escalon(mf["conservador_minimo"][sexo], edad)
    mayor_riesgo = np.minimum(_escalon(mf["mayor_riesgo_por_defecto"][sexo], edad), 1 - conservador)
    moderado = 1 - conservador - mayor_riesgo
    return np.column_stack([mayor_riesgo, moderado, conservador, np.zeros(n_meses)])


def pesos_fijos(fondo: str, n_meses: int, fondos=FONDOS) -> np.ndarray:
    """Pesos ``(n_meses, n_fondos)`` con todo el saldo en un solo fondo."""
    p = np.zeros((n_meses, len(fondos)))
    p[:, list(fondos).index(fondo)] = 1.0
    return p
