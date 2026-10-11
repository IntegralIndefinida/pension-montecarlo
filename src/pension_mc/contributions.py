"""
Densidad de cotización: qué meses cotiza cada persona simulada.

Cadena de Markov mensual de dos estados (cotiza / no cotiza) con heterogeneidad permanente:

    π_i(a) = logística(c_k(a) + β·η_i(a)),   η_i(a) ~ N(0, 1)
    η_i: AR(1) con persistencia anual ρ_η hasta los 30 años; fijo desde entonces
    P(dejar de cotizar) = s_t = μ(a)·(1 − π_i(a)),    μ(a) = μ₀·exp(−κ·(a − 40) / 10)
    P(empezar a cotizar) = f_t, tal que π_i,t+1 = π_i,t·(1 − s_t) + (1 − π_i,t)·f_t

La entrada ``f_t`` hace que la probabilidad marginal de cada persona siga exactamente su
``π_i(a)`` aunque la rotación sea baja; si la tasa cae más rápido de lo que permite ``s_t``,
se aumenta la salida. Con ``π`` constante, ``f = μ·π``: la cadena estacionaria usual.

- ``π_k(a)`` es la proporción de la población del tipo ``k`` (educación × sexo) que cotiza a la
  edad ``a`` en la GEIH; ``c_k(a)`` se elige para que el promedio sobre η la reproduzca.
- ``μ(a)`` fija la persistencia de corto plazo (la autocorrelación mensual del estado es ``1 − μ``);
  con ``κ > 0`` la rotación cae con la edad, como la de los empleos.
- ``β`` fija la heterogeneidad de largo plazo: con β = 0 todos los del mismo tipo tienen la misma
  densidad esperada; con β grande unos cotizan casi siempre y otros casi nunca.
- ``ρ_η`` permite que la propensión a cotizar cambie en la juventud (terminar de estudiar, primer
  empleo formal) y se consolide después de los 30 años (edad elegida por ajuste). Con η permanente, las pocas semanas de un
  joven decidirían casi por completo su futuro (ver notebooks/04_cotizacion.ipynb).

La GEIH es de corte transversal y no identifica ``(μ₀, κ, β, ρ_η)`` por sí sola. Se calibran con:

1. **Rotación de corto plazo** (MinTrabajo): cotizantes del mes / afiliados activos (cotizaron
   en alguno de los últimos 6 meses) ≈ 0,82.
2. **Duración de los periodos por edad** (GEIH, P6426): proporción de cotizantes que lleva 3 años
   o más en su empleo actual, a los 25–44 años (46 %) y a los 45–64 (73 %). Un periodo de
   cotización dura al menos lo que el empleo, así que es una cota inferior: la calibración es
   conservadora en persistencia.

3. **Alguna vez cotizó** (MinTrabajo y GEIH): afiliados / población de 18 a 70 años ≈ 0,77. Es una
   cota superior (el registro incluye afiliados fallecidos o fuera del país); identifica ρ_η.

Los cuatro momentos se reproducen con un error máximo de ~0,02.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import optimize, special

from .config import DATA_PROCESSED, parametros
from .wages import EDUCACION, NIVELES, SEXOS, clave

EDAD_INICIO, EDAD_FIN = 15, 70
ANIOS_TASAS = (2023, 2024, 2025)
ARCHIVO = DATA_PROCESSED / "modelo_cotizacion.json"
_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(40)   # cuadratura para E[f(η)], η ~ N(0, 1)
_GH_W = _GH_W / _GH_W.sum()


def tipos():
    return [(e, s) for e in NIVELES for s in SEXOS]


# --------------------------------------------------------------------------- Tasas de la GEIH
def tasas_observadas(geih: pd.DataFrame, anios=ANIOS_TASAS) -> pd.DataFrame:
    """Proporción ponderada que cotiza por tipo y edad, con el tamaño de muestra y la población."""
    d = geih[geih["anio"].isin(anios) & geih["edad"].between(EDAD_INICIO, EDAD_FIN)].copy()
    d["educ"] = d["nivel_educativo"].astype(str).map(EDUCACION)
    d["sexo"] = d["sexo"].astype(str)
    d = d.dropna(subset=["educ"])
    d["fc"] = d["fex"] * d["cotiza"]
    g = d.groupby(["educ", "sexo", "edad"]).agg(fex=("fex", "sum"), fc=("fc", "sum"), n=("fex", "size")).reset_index()
    g["tasa"] = g["fc"] / g["fex"]
    g["poblacion"] = g["fex"] / (12 * len(anios))
    g["edad"] = g["edad"].astype(int)
    return g.drop(columns="fc")


def suavizar(obs: pd.DataFrame, df_spline: int = 7) -> dict[str, np.ndarray]:
    """
    Curva suave π_k(a) por tipo: logit binomial con spline cúbico natural en la edad,
    ajustado sobre las celdas (tipo, edad) con su tamaño de muestra como peso.
    """
    import statsmodels.api as sm
    from patsy import dmatrix

    edades = np.arange(EDAD_INICIO, EDAD_FIN + 1)
    out = {}
    for e, s in tipos():
        g = obs[(obs["educ"] == e) & (obs["sexo"] == s)].sort_values("edad")
        X = dmatrix(f"cr(edad, df={df_spline})", {"edad": g["edad"]}, return_type="dataframe")
        fit = sm.GLM(g["tasa"].clip(1e-6, 1 - 1e-6), X, family=sm.families.Binomial(),
                     var_weights=g["n"]).fit()
        Xp = dmatrix(X.design_info, {"edad": edades}, return_type="dataframe")
        out[clave(e, s)] = np.asarray(fit.predict(Xp))
    return out


# --------------------------------------------------------------------------- Modelo
def _desplazamiento(pi: np.ndarray, beta: float) -> np.ndarray:
    """c tal que E_η[logística(c + βη)] = π, para cada elemento de ``pi``."""
    if beta == 0:
        return special.logit(pi)
    out = np.empty_like(pi, dtype=float)
    cota = 40 + abs(beta) * np.abs(_GH_X).max()          # el intervalo crece con β
    for i, p in enumerate(np.clip(pi, 1e-6, 1 - 1e-6)):
        f = lambda c: _GH_W @ special.expit(c + beta * _GH_X) - p
        out[i] = optimize.brentq(f, -cota, cota)
    return out


@dataclass
class ModeloCotizacion:
    edades: list[int]
    tasas: dict[str, list[float]]        # "educación|sexo" -> π_k(a) en ``edades``
    mu: float
    beta: float
    calibracion: dict | None = None
    kappa: float = 0.0
    rho_eta: float = 1.0                 # persistencia anual de η (1 = permanente)
    edad_fija_eta: float = 200.0         # desde esta edad η deja de moverse

    def rotacion(self, edad) -> np.ndarray:
        """μ(a) = μ₀·exp(−κ(a − 40)/10), acotada a 1 para que las probabilidades sean válidas."""
        return np.minimum(self.mu * np.exp(-self.kappa * (np.asarray(edad, float) - 40) / 10), 1.0)

    def __post_init__(self):
        self._c = {}

    def desplazamiento(self, sexo: str, educ: str) -> np.ndarray:
        k = clave(educ, sexo)
        if k not in self._c:
            self._c[k] = _desplazamiento(np.asarray(self.tasas[k]), self.beta)
        return self._c[k]

    def prob_individual(self, edad_meses: np.ndarray, sexo: str, educ: str, eta: np.ndarray) -> np.ndarray:
        """π_i en cada mes ``(n_sims, n_meses)``; la edad se interpola linealmente entre años."""
        c = np.interp(edad_meses, self.edades, self.desplazamiento(sexo, educ))
        return special.expit(c[None, :] + self.beta * eta[:, None])

    def simular(self, edad_inicial: float, sexo: str, educ: str, n_meses: int, n_sims: int, *,
                eta: np.ndarray | None = None, estado_inicial: np.ndarray | None = None,
                seed: int | None = None, uniformes: np.ndarray | None = None,
                edad_tope: float | None = None, sin_cotizar: np.ndarray | None = None) -> np.ndarray:
        """
        Estados ``(n_sims, n_meses)``: ``True`` si la persona cotiza ese mes.

        ``eta`` y ``estado_inicial`` permiten continuar una historia (ver :meth:`condicionar`).
        ``uniformes`` (``(n_sims, n_meses)``) permite usar números aleatorios comunes.
        ``edad_tope`` congela la tasa y la rotación en las de esa edad (p. ej. para quien sigue
        trabajando después de los 55). ``sin_cotizar`` (``(n_meses,)`` booleano) fuerza meses sin
        cotizar: la cadena sigue desde "no cotiza", así que la laguna también afecta lo que viene.
        """
        rng = np.random.default_rng(seed)
        eta = rng.standard_normal(n_sims) if eta is None else np.asarray(eta, dtype=float).copy()
        u = rng.random((n_sims, n_meses)) if uniformes is None else uniformes
        edad_mes = edad_inicial + np.arange(n_meses) / 12
        if edad_tope is not None:
            edad_mes = np.minimum(edad_mes, edad_tope)
        forzado = np.zeros(n_meses, bool) if sin_cotizar is None else np.asarray(sin_cotizar, bool)
        c = np.interp(edad_mes, self.edades, self.desplazamiento(sexo, educ))
        mu = self.rotacion(edad_mes)
        phi = self.rho_eta ** (1 / 12)                        # persistencia mensual de η
        movil = phi < 1 and edad_mes[0] < self.edad_fija_eta
        mueve = edad_mes < self.edad_fija_eta
        choques = rng.standard_normal((n_sims, n_meses)) if movil else None
        acotar = lambda z: np.clip(special.expit(z), 1e-9, 1 - 1e-9)
        p1 = acotar(c[0] + self.beta * eta)
        estados = np.empty((n_sims, n_meses), dtype=bool)
        x = u[:, 0] < p1 if estado_inicial is None else np.asarray(estado_inicial, bool)
        x = x & ~forzado[0]
        estados[:, 0] = x
        self._eta_final = eta
        for t in range(1, n_meses):
            p0 = p1
            if movil and mueve[t]:
                eta = phi * eta + np.sqrt(1 - phi**2) * choques[:, t]
            p1 = acotar(c[t] + self.beta * eta)
            sale = mu[t] * (1 - p0)
            entra = (p1 - p0 * (1 - sale)) / (1 - p0)
            cae = entra < 0                       # la tasa baja más rápido que la salida natural
            sale = np.where(cae, 1 - p1 / p0, sale)
            entra = np.clip(entra, 0, 1)
            x = np.where(x, u[:, t] >= sale, u[:, t] < entra) & ~forzado[t]
            estados[:, t] = x
        self._eta_final = eta                                 # η al final (para continuar una historia)
        return estados

    def condicionar(self, edad: float, sexo: str, educ: str, semanas: float, n_sims: int, *,
                    cotiza_hoy: bool | None = None, tolerancia: float = 25.0,
                    seed: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        """
        Muestras de ``(η, estado actual)`` coherentes con las semanas que la persona ya cotizó.

        Simula historias desde los 15 años y conserva las que acumulan ``semanas ± tolerancia``
        (y, si se indica, las que cotizan hoy): un cálculo bayesiano aproximado por rechazo.
        Quien ya cotizó mucho probablemente tiene un η alto y seguirá cotizando.
        """
        rng = np.random.default_rng(seed)
        n_hist = int((edad - EDAD_INICIO) * 12)
        sem_mes = parametros()["supuestos"]["semanas_por_mes"]
        etas, estados = [], []
        aceptadas, intentos = 0, 0
        while aceptadas < n_sims and intentos < 200:
            lote = max(4 * n_sims, 5_000)
            eta = rng.standard_normal(lote)
            h = self.simular(EDAD_INICIO, sexo, educ, n_hist, lote, eta=eta, seed=rng.integers(1 << 32))
            eta_hoy = self._eta_final
            ok = np.abs(h.sum(axis=1) * sem_mes - semanas) <= tolerancia
            if cotiza_hoy is not None:
                ok &= h[:, -1] == cotiza_hoy
            etas.append(eta_hoy[ok]); estados.append(h[ok, -1])
            aceptadas += ok.sum(); intentos += 1
        if aceptadas == 0:
            raise ValueError("Ninguna historia simulada es compatible con esas semanas; aumente la tolerancia")
        eta, est = np.concatenate(etas)[:n_sims], np.concatenate(estados)[:n_sims]
        if len(eta) < n_sims:  # pocas aceptadas: se remuestrean con reemplazo
            i = rng.integers(0, len(eta), n_sims)
            eta, est = eta[i], est[i]
        return eta, est

    # ---- persistencia
    def guardar(self, ruta=ARCHIVO) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta=ARCHIVO) -> "ModeloCotizacion":
        return cls(**json.loads(ruta.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- Calibración
def duracion_en_curso(estados: np.ndarray) -> np.ndarray:
    """Meses consecutivos cotizando hasta cada mes (0 si ese mes no cotiza)."""
    out = np.zeros(estados.shape, dtype=np.int32)
    run = np.zeros(estados.shape[0], dtype=np.int32)
    for t in range(estados.shape[1]):
        run = np.where(estados[:, t], run + 1, 0)
        out[:, t] = run
    return out


GRUPOS_PERIODO = ((25, 44), (45, 64))


def momentos(modelo: ModeloCotizacion, poblacion: dict[str, np.ndarray], *, n_por_tipo: int = 3_000,
             seed: int = 0, edades=(18, 70), grupos_periodo=GRUPOS_PERIODO, meses_periodo: int = 36) -> dict[str, float]:
    """
    Momentos agregados de una población simulada en estado estacionario (sección transversal).

    ``poblacion[tipo]`` es la población por edad en ``modelo.edades``. Devuelve, ponderado por
    población entre ``edades``: la tasa de cotización, ``cotizantes / activos`` (activo = cotizó en
    alguno de los últimos 6 meses) y la proporción que alguna vez cotizó. Para cada grupo de
    ``grupos_periodo`` (clave ``periodo_25_44``, etc.), la proporción de los cotizantes que lleva
    ``meses_periodo`` o más cotizando sin pausa.
    """
    n_meses = (EDAD_FIN - EDAD_INICIO + 1) * 12
    edad_mes = EDAD_INICIO + np.arange(n_meses) / 12
    tot = {"cot": 0.0, "act": 0.0, "alguna": 0.0, "pob": 0.0}
    grupos = {f"periodo_{a}_{b}": (edad_mes >= a) & (edad_mes < b + 1) for a, b in grupos_periodo}
    cot_g, largo_g = dict.fromkeys(grupos, 0.0), dict.fromkeys(grupos, 0.0)
    for j, (e, s) in enumerate(tipos()):
        rng = np.random.default_rng(seed + j)
        x = modelo.simular(EDAD_INICIO, s, e, n_meses, n_por_tipo, eta=rng.standard_normal(n_por_tipo),
                           uniformes=rng.random((n_por_tipo, n_meses)))
        xc = np.cumsum(x, axis=1)
        act = xc - np.concatenate([np.zeros((n_por_tipo, 6)), xc[:, :-6]], axis=1) > 0
        largo = duracion_en_curso(x) >= meses_periodo
        pob_tipo = np.interp(edad_mes, modelo.edades, poblacion[clave(e, s)]) / 12
        pob = np.where((edad_mes >= edades[0]) & (edad_mes < edades[1] + 1), pob_tipo, 0)
        tot["cot"] += pob @ x.mean(axis=0)
        tot["act"] += pob @ act.mean(axis=0)
        tot["alguna"] += pob @ (xc > 0).mean(axis=0)
        tot["pob"] += pob.sum()
        for g, sel in grupos.items():
            pob_g = np.where(sel, pob_tipo, 0)
            cot_g[g] += pob_g @ x.mean(axis=0)
            largo_g[g] += pob_g @ largo.mean(axis=0)
    out = {"tasa": tot["cot"] / tot["pob"], "cotizantes_sobre_activos": tot["cot"] / tot["act"],
           "alguna_vez": tot["alguna"] / tot["pob"]}
    out.update({g: largo_g[g] / cot_g[g] for g in grupos})
    return out


def calibrar(tasas: dict[str, np.ndarray], poblacion: dict[str, np.ndarray], *,
             objetivo_ratio: float = 0.82, objetivos_periodo: dict[tuple[int, int], float] | None = None,
             objetivo_alguna_vez: float | None = None, edad_fija_eta: float = 200.0,
             n_por_tipo: int = 3_000, seed: int = 0, x0=(0.3, 1.0, 7.0, 0.8),
             diff_step: float = 0.05) -> ModeloCotizacion:
    """
    Calibra por simulación (números aleatorios comunes) los parámetros de la cadena:

    - rotación ``μ₀`` y su caída con la edad ``κ`` (κ = 0 si hay un solo grupo de duración);
    - heterogeneidad ``β``;
    - persistencia anual de η, ``ρ_η``, solo si se da ``objetivo_alguna_vez`` (si no, η es permanente).
      η se mueve hasta ``edad_fija_eta`` y queda fijo después.
    """
    objetivos_periodo = objetivos_periodo or {(25, 44): 0.463, (45, 64): 0.726}
    grupos = tuple(objetivos_periodo)
    edades = list(range(EDAD_INICIO, EDAD_FIN + 1))
    tasas = {k: np.asarray(v).tolist() for k, v in tasas.items()}
    con_kappa = len(grupos) > 1
    con_rho = objetivo_alguna_vez is not None

    def modelo(p):
        p = list(p)
        mu, kappa = np.exp(p.pop(0)), (p.pop(0) if con_kappa else 0.0)
        beta = np.exp(p.pop(0))
        rho = 1 - np.exp(p.pop(0)) if con_rho else 1.0
        return ModeloCotizacion(edades, tasas, mu, beta, kappa=kappa, rho_eta=rho,
                                edad_fija_eta=edad_fija_eta if con_rho else 200.0)

    def resid(p):
        m = momentos(modelo(p), poblacion, n_por_tipo=n_por_tipo, seed=seed, grupos_periodo=grupos)
        r = [m["cotizantes_sobre_activos"] - objetivo_ratio,
             *(m[f"periodo_{a}_{b}"] - v for (a, b), v in objetivos_periodo.items())]
        if con_rho:
            r.append(m["alguna_vez"] - objetivo_alguna_vez)
        return r

    x, lb, ub = [np.log(x0[0])], [np.log(1e-3)], [np.log(0.95)]
    if con_kappa:
        x, lb, ub = x + [x0[1]], lb + [-3.0], ub + [5.0]
    x, lb, ub = x + [np.log(x0[2])], lb + [np.log(1e-2)], ub + [np.log(20.0)]
    if con_rho:
        x, lb, ub = x + [np.log(1 - x0[3])], lb + [np.log(1e-4)], ub + [np.log(0.5)]
    r = optimize.least_squares(resid, x0=x, diff_step=diff_step, bounds=(lb, ub))
    m = modelo(r.x)
    mom = momentos(m, poblacion, n_por_tipo=n_por_tipo, seed=seed, grupos_periodo=grupos)
    m.calibracion = {"objetivo_ratio": objetivo_ratio,
                     **{f"objetivo_periodo_{a}_{b}": v for (a, b), v in objetivos_periodo.items()},
                     **({"objetivo_alguna_vez": objetivo_alguna_vez} if con_rho else {}), **mom}
    return m


def objetivo_periodo(geih: pd.DataFrame, anios=ANIOS_TASAS, edades=(35, 54), meses: int = 36) -> float:
    """Proporción de cotizantes con ``edades`` que lleva ``meses`` o más en su empleo actual (P6426)."""
    c = geih[(geih["cotiza"] == 1) & geih["edad"].between(*edades) & geih["anio"].isin(anios)]
    c = c.dropna(subset=["antiguedad_empleo"])
    return float(np.average(c["antiguedad_empleo"] >= meses, weights=c["fex"]))


def poblacion_por_tipo(obs: pd.DataFrame) -> dict[str, np.ndarray]:
    edades = np.arange(EDAD_INICIO, EDAD_FIN + 1)
    return {clave(e, s): obs[(obs["educ"] == e) & (obs["sexo"] == s)].set_index("edad")["poblacion"]
            .reindex(edades, fill_value=0).to_numpy() for e, s in tipos()}


def estimar(geih: pd.DataFrame | None = None, guardar: bool = True, **kwargs) -> tuple[ModeloCotizacion, pd.DataFrame]:
    """Tasas suavizadas de la GEIH + calibración de (μ, β); guarda el modelo (si ``guardar``)."""
    geih = pd.read_parquet(DATA_PROCESSED / "geih_pensiones.parquet") if geih is None else geih
    obs = tasas_observadas(geih)
    tasas = suavizar(obs)
    kwargs.setdefault("objetivos_periodo", {g: objetivo_periodo(geih, edades=g) for g in GRUPOS_PERIODO})
    kwargs.setdefault("objetivo_alguna_vez", 0.77)
    kwargs.setdefault("edad_fija_eta", 30.0)       # mejor ajuste en una rejilla de 25 a 40 años
    kwargs.setdefault("x0", (0.30, 0.58, 6.19, 0.70))
    kwargs.setdefault("diff_step", 0.15)
    m = calibrar(tasas, poblacion_por_tipo(obs), **kwargs)
    if guardar:
        m.guardar()
    return m, obs


def semanas(estados: np.ndarray) -> np.ndarray:
    """Semanas cotizadas acumuladas al final de cada mes."""
    return np.cumsum(estados, axis=-1) * parametros()["supuestos"]["semanas_por_mes"]
