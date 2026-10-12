"""
Simulador estocástico de pensiones (Monte Carlo) para Colombia.

    streamlit run app/streamlit_app.py

Usa el motor ``pension_mc.simulate`` con los modelos de ``artefactos/``.
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pension_mc import regimes as G
from pension_mc.config import parametros
from pension_mc.decumulation import factor_anualidad
from pension_mc.simulate import CALIBRACIONES_COTIZACION, Perfil, Supuestos, simular, tornado
from pension_mc.wages import NIVELES

st.set_page_config(page_title="Simulador de pensiones · Monte Carlo", page_icon="📈", layout="wide")

# --------------------------------------------------------------------------- Estilo
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
AZUL, NARANJA, AQUA, GRIS = "#2a78d6", "#eb6834", "#1baf7a", "#c3c2b7"
BAJO, ALTO = "#2a78d6", "#e34948"
BANDA_1, BANDA_2, LINEA = "#b7d3f6", "#86b6ef", "#104281"

P = parametros()
SMMLV = P["smmlv"]["valores"][2026]
G_REG = P["rais"]["crecimiento_beneficios_capital"]


def pesos(x: float) -> str:
    return "—" if x is None or not np.isfinite(x) else f"${x:,.0f}".replace(",", ".")


def pct(x: float, d: int = 0) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:.{d}%}".replace(".", ",")


def dec(x: float, d: int = 2) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:.{d}f}".replace(".", ",")


GRAFICO = {"displayModeBar": False}


def estilo(fig: go.Figure, titulo: str, alto: int = 360, **kw) -> go.Figure:
    fig.update_layout(
        template="none", height=alto, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="Inter, system-ui, -apple-system, Segoe UI, sans-serif", color=INK2, size=13),
        title=dict(text=titulo, x=0, xanchor="left", font=dict(color=INK, size=15)),
        margin=dict(l=10, r=20, t=60, b=10),
        legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", font=dict(color=INK2)),
        hoverlabel=dict(bgcolor="white", font_color=INK, bordercolor=GRID),
        separators=",.", **kw)
    fig.update_xaxes(gridcolor=GRID, gridwidth=1, linecolor=GRID, zeroline=False, ticks="", automargin=True)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, linecolor=GRID, zeroline=False, ticks="", automargin=True)
    return fig


# --------------------------------------------------------------------------- Simulación (con caché)
@st.cache_data(show_spinner=False, max_entries=64)
def correr(perfil: dict, supuestos: dict, n_sims: int) -> dict:
    pf, sp = Perfil(**perfil), Supuestos(**supuestos)
    r = simular(pf, sp, n_sims=n_sims, guardar_saldo=True)
    conyuge = None
    if pf.conyuge_diferencia_edad is not None:
        conyuge = ("Hombre" if pf.sexo == "Mujer" else "Mujer", r.edad_retiro + pf.conyuge_diferencia_edad)
    capital = r.smmlv_retiro * factor_anualidad(float(r.edad_retiro), pf.sexo, sp.valor("tasa_tecnica"),
                                                sp.valor("crecimiento_beneficios"), conyuge)
    return {"resumen": r.resumen(), "afp": r.afp, "col": r.colpensiones, "smmlv": r.smmlv_retiro,
            "edad_retiro": r.edad_retiro, "anio": r.anio_retiro, "capital": capital,
            "saldo_q": np.percentile(r.saldo, [10, 25, 50, 75, 90], axis=0)}


@st.cache_data(show_spinner=False, max_entries=16)
def escenarios(perfil: dict, supuestos: dict, n_sims: int) -> pd.DataFrame:
    pf, sp = Perfil(**perfil), Supuestos(**supuestos)
    legal = G.edad_pension("rais", pf.sexo)
    retiro = pf.edad_retiro or legal
    congelar = max(55.0, pf.edad)
    casos = {"Tu escenario": (pf, sp)}
    if pf.aporte_voluntario_pct < 0.05:
        casos["+ aporte voluntario del 5 %"] = (Perfil(**{**perfil, "aporte_voluntario_pct": 0.05}), sp)
    for extra in (3, 5):
        if retiro + extra <= 70:
            casos[f"Retiro {extra} años después ({retiro + extra:.0f})"] = (
                Perfil(**{**perfil, "edad_retiro": retiro + extra}), Supuestos(**{**supuestos, "congelar_cotizacion_desde": congelar}))
    for fondo, nombre in [("mayor_riesgo", "Todo en el fondo de mayor riesgo"), ("conservador", "Todo en el fondo conservador")]:
        if pf.fondo != fondo:
            casos[nombre] = (Perfil(**{**perfil, "fondo": fondo}), sp)
    filas = []
    for nombre, (p, s) in casos.items():
        res = simular(p, s, n_sims=n_sims).resumen()
        filas.append({"escenario": nombre, "P(pensión)": res.afp_p_pension, "P(más que el mínimo)": res.afp_p_capital_suficiente,
                      "Mesada media total (SMMLV)": res.afp_mesada_media_total, "Mesada P90 (SMMLV)": res.afp_mesada_p90})
    return pd.DataFrame(filas).set_index("escenario")


VARIACIONES = {
    "Rentabilidad ±1 punto": ({"ajuste_rentabilidad": -0.01}, {"ajuste_rentabilidad": 0.01}),
    "Tasa técnica 3 % / 5 %": ({"tasa_tecnica": 0.03}, {"tasa_tecnica": 0.05}),
    "Crecimiento real del SMMLV 0 % / 2,5 %": ({"crecimiento_smmlv": 0.0}, {"crecimiento_smmlv": 0.025}),
    "Crecimiento regulatorio de beneficios 1 % / 3,5 %": ({"crecimiento_beneficios": 0.01}, {"crecimiento_beneficios": 0.035}),
    "Crecimiento salarial 0 % / 2 %": ({"crecimiento_salarios": 0.0}, {"crecimiento_salarios": 0.02}),
    "Consolidación laboral a los 25 / 35": ({"cotizacion": "η se consolida a los 25"}, {"cotizacion": "η se consolida a los 35"}),
}


@st.cache_data(show_spinner=False, max_entries=16)
def sensibilidad(perfil: dict, supuestos: dict, n_sims: int) -> pd.DataFrame:
    return tornado(Perfil(**perfil), VARIACIONES, base=Supuestos(**supuestos), n_sims=n_sims,
                   metricas=("afp_p_pension", "afp_p_capital_suficiente", "afp_mesada_media_total"))


# --------------------------------------------------------------------------- Entradas
st.sidebar.title("Tu perfil")
sexo = st.sidebar.radio("Sexo", ["Mujer", "Hombre"], horizontal=True, key="sexo")
edad = st.sidebar.slider("Edad", 18, 60, 30, key="edad")
educacion = st.sidebar.selectbox("Nivel educativo", NIVELES, index=3, key="educacion")
salario = st.sidebar.number_input("Salario o ingreso mensual (pesos)", min_value=0, value=int(2 * SMMLV), step=100_000,
                                  key="salario", help="El IBC tiene piso de 1 SMMLV ($1.750.905 en 2026) y tope de 25 SMMLV.")
st.sidebar.caption(f"= {salario / SMMLV:.2f} SMMLV de 2026".replace(".", ","))
independiente = st.sidebar.checkbox("Soy independiente (cotizo sobre el 40 % del ingreso)", key="independiente")

st.sidebar.subheader("Tu historia")
max_semanas = int((edad - 15) * 52)
semanas = st.sidebar.number_input("Semanas cotizadas hasta hoy", 0, max_semanas, min(250, max_semanas), step=10, key="semanas")
cotiza_hoy = st.sidebar.radio("¿Cotizas actualmente?", ["Sí", "No"], horizontal=True, key="cotiza_hoy") == "Sí"
conoce_saldo = st.sidebar.checkbox("Conozco mi saldo en la AFP", key="conoce_saldo")
saldo = None
if conoce_saldo:
    saldo = float(st.sidebar.number_input("Saldo actual (pesos)", min_value=0, value=0, step=1_000_000, key="saldo"))

st.sidebar.subheader("Tus decisiones")
legal = G.edad_pension("rais", sexo)
edad_retiro = st.sidebar.slider("Edad de retiro", max(legal, edad + 1), 70, max(legal, edad + 1), key="edad_retiro",
                                help=f"La edad legal de pensión es {legal} años. Si te retiras después, el simulador supone que sigues cotizando como a los 55.")
fondos = {"Por defecto (multifondos según la edad)": None, "Moderado": "moderado", "Mayor riesgo": "mayor_riesgo", "Conservador": "conservador"}
fondo = fondos[st.sidebar.selectbox("Fondo", list(fondos), key="fondo")]
voluntario = st.sidebar.slider("Aporte voluntario a la cuenta (% del salario)", 0, 20, 0, key="voluntario") / 100
con_conyuge = st.sidebar.checkbox("Tengo cónyuge beneficiario", key="conyuge")
dif_conyuge = st.sidebar.slider("Edad del cónyuge menos la tuya (años)", -15, 15, -3 if sexo == "Hombre" else 3,
                                key="dif_conyuge") if con_conyuge else None

with st.sidebar.expander("Supuestos avanzados"):
    n_sims = st.select_slider("Simulaciones", [1_000, 2_000, 5_000, 10_000, 20_000], value=5_000, key="n_sims")
    metodo = st.selectbox("Modelo de rentabilidad", ["bootstrap", "t", "determinista"], key="metodo",
                          format_func={"bootstrap": "Bootstrap histórico", "t": "t de Student multivariada", "determinista": "Determinista (mediana)"}.get)
    incertidumbre = st.checkbox("Incertidumbre sobre la rentabilidad promedio", value=True, key="incertidumbre")
    ajuste = st.slider("Ajuste a la rentabilidad real (puntos)", -2.0, 2.0, 0.0, 0.25, key="ajuste") / 100
    tasa = st.slider("Tasa técnica real (%)", 2.0, 6.0, 4.0, 0.25, key="tasa") / 100
    g_smmlv = st.slider("Crecimiento real del SMMLV (%)", 0.0, 3.0, 1.0, 0.25, key="g_smmlv") / 100
    g_ben = st.slider("Crecimiento de beneficios para el capital suficiente (%)", 0.0, 4.0, round(G_REG * 100, 2), 0.01, key="g_ben") / 100
    g_sal = st.slider("Crecimiento real de los salarios (%)", 0.0, 3.0, 1.0, 0.25, key="g_sal") / 100
    calib = st.selectbox("Modelo de cotización", list(CALIBRACIONES_COTIZACION), key="calib",
                         format_func=lambda k: "Base (la situación laboral se consolida a los 30)" if k == "base" else k)
    seed = st.number_input("Semilla", 0, 10_000, 2026, key="seed")

perfil = asdict(Perfil(edad=float(edad), sexo=sexo, educacion=educacion, salario=float(max(salario, 1)), semanas=float(semanas),
                       saldo=saldo, cotiza_hoy=cotiza_hoy, independiente=independiente, edad_retiro=float(edad_retiro),
                       fondo=fondo, aporte_voluntario_pct=voluntario, conyuge_diferencia_edad=dif_conyuge))
supuestos = asdict(Supuestos(metodo_rentabilidad=metodo, incertidumbre_media=incertidumbre, ajuste_rentabilidad=ajuste,
                             tasa_tecnica=tasa, crecimiento_smmlv=g_smmlv, crecimiento_beneficios=g_ben,
                             crecimiento_salarios=g_sal, cotizacion=calib, seed=int(seed),
                             congelar_cotizacion_desde=max(55.0, float(edad)) if edad_retiro > legal else None))

# --------------------------------------------------------------------------- Simulación
st.title("¿Cuál será tu pensión?")
st.caption("Simulador estocástico (Monte Carlo) del sistema pensional colombiano: salarios, semanas cotizadas y rentabilidades "
           "inciertas, reglas de las AFP y de Colpensiones. Montos en pesos de 2026. Ejercicio académico; no es asesoría financiera.")

try:
    with st.spinner(f"Simulando {n_sims:,} vidas laborales…".replace(",", ".")):
        R = correr(perfil, supuestos, n_sims)
except ValueError as e:
    st.error(f"No se pudo simular este perfil: {e}. Revisa que las semanas sean coherentes con tu edad.")
    st.stop()

res, afp, col, sm = R["resumen"], R["afp"], R["col"], R["smmlv"]
pension_afp = afp["estado"] != "devolucion"
pension_col = col["estado"] == "pension"

if 25 <= edad < 35 and calib == "base":
    st.info("**A tu edad la predicción es más incierta.** El modelo supone que la situación laboral se consolida hacia los 30 años; "
            "si se consolidara a los 35, tu probabilidad de pensionarse podría ser bastante menor. Mira la pestaña *Sensibilidad*.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Probabilidad de pensionarte (AFP)", pct(res.afp_p_pension),
          help=f"Proporción de simulaciones con pensión al retirarte a los {R['edad_retiro']:.0f} años: capital suficiente o garantía de pensión mínima.")
en_smmlv = lambda x: f"≈ {x / sm:.2f} SMMLV del año de retiro".replace(".", ",") if np.isfinite(x) else ""
med_afp = afp.loc[pension_afp, "mesada"].median() if pension_afp.any() else np.nan
c2.metric("Mesada mediana si te pensionas (AFP)", pesos(med_afp),
          help="En pesos de 2026 (poder adquisitivo de hoy). El SMMLV es el del año de retiro.")
c2.caption(en_smmlv(med_afp))
c3.metric("Probabilidad de superar el mínimo", pct(res.afp_p_capital_suficiente),
          help="El saldo alcanza para una pensión vitalicia mayor que 1 SMMLV sin ayuda del Estado.")
med_col = col.loc[pension_col, "mesada"].median() if pension_col.any() else np.nan
c4.metric("Mesada mediana en Colpensiones", pesos(med_col),
          help="Misma persona simulada con las reglas del régimen de prima media (comparación).")
c4.caption(en_smmlv(med_col))

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Mi pensión", "¿Cómo termina?", "Escenarios", "Sensibilidad", "Metodología"])

# --------------------------------------------------------------------------- 1. Mi pensión
with tab1:
    q = R["saldo_q"] / 1e6
    meses = q.shape[1]
    edades = edad + np.arange(1, meses + 1) / 12
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edades, y=q[4], line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=edades, y=q[0], fill="tonexty", fillcolor=BANDA_1, line=dict(width=0), name="P10–P90",
                             customdata=q[4], hovertemplate="P10–P90: %{y:,.0f}–%{customdata:,.0f} M<extra></extra>"))
    fig.add_trace(go.Scatter(x=edades, y=q[3], line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=edades, y=q[1], fill="tonexty", fillcolor=BANDA_2, line=dict(width=0), name="P25–P75",
                             customdata=q[3], hovertemplate="P25–P75: %{y:,.0f}–%{customdata:,.0f} M<extra></extra>"))
    fig.add_trace(go.Scatter(x=edades, y=q[2], line=dict(color=LINEA, width=2), name="Mediana",
                             hovertemplate="Mediana: <b>%{y:,.0f} M</b><extra></extra>"))
    fig.add_hline(y=R["capital"] / 1e6, line=dict(color=INK2, width=1, dash="dash"),
                  annotation_text=f"Capital para 1 SMMLV vitalicio: {R['capital'] / 1e6:,.0f} M".replace(",", "."),
                  annotation_position="top left", annotation_font_color=INK2)
    estilo(fig, "Saldo proyectado en tu cuenta de la AFP (millones de pesos de 2026)", 420, hovermode="x unified")
    fig.update_xaxes(title="Edad", hoverformat=".1f")
    fig.update_yaxes(rangemode="tozero")
    st.plotly_chart(fig, use_container_width=True, config=GRAFICO)
    st.caption("Si al retirarte el saldo supera la línea punteada, financias más que el mínimo. Si no, y tienes las semanas, el Estado "
               "completa hasta 1 SMMLV (garantía de pensión mínima); sin las semanas, recibes la devolución del saldo.")

    bins = np.arange(0, max(4.0, float(np.nanpercentile(np.r_[afp.mesada, col.mesada] / sm, 99)) + 0.25), 0.1)
    fig = go.Figure()
    for nombre, d, sel, color in [("AFP", afp, pension_afp, AZUL), ("Colpensiones", col, pension_col, NARANJA)]:
        h, b = np.histogram(d.loc[sel, "mesada"] / sm, bins=bins)
        prob = h / len(d)
        fig.add_trace(go.Scatter(x=b[:-1] + 0.05, y=prob, mode="lines", line=dict(color=color, width=2, shape="hvh"), name=nombre,
                                 hovertemplate=f"{nombre}: " + "%{y:.1%} de las simulaciones<extra></extra>"))
    estilo(fig, "Distribución de la mesada si te pensionas (SMMLV del año de retiro)", 340, hovermode="x unified")
    fig.update_xaxes(title="Mesada en SMMLV", hoverformat=".1f")
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    st.plotly_chart(fig, use_container_width=True, config=GRAFICO)
    st.caption(f"Sin pensión: {pct(1 - res.afp_p_pension)} en la AFP (devolución de saldos) y {pct(1 - res.colpensiones_p_pension)} en "
               "Colpensiones (indemnización sustitutiva). La pensión mínima se ve como el pico en 1 SMMLV.")

# --------------------------------------------------------------------------- 2. ¿Cómo termina?
with tab2:
    filas = {
        "AFP": [(afp.estado == "capital_suficiente").mean(), (afp.estado == "garantia_minima").mean(), (afp.estado == "devolucion").mean()],
        "Colpensiones": [pension_col.mean(), 0.0, (~pension_col).mean()],
    }
    segmentos = [("Pensión (capital propio o Colpensiones)", AZUL), ("Garantía de pensión mínima", NARANJA),
                 ("Sin pensión", GRIS)]
    fig = go.Figure()
    for j, (nombre, color) in enumerate(segmentos):
        v = [filas[k][j] for k in filas]
        fig.add_trace(go.Bar(y=list(filas), x=v, orientation="h", name=nombre, marker=dict(color=color, line=dict(color=SURFACE, width=2)),
                             text=[pct(x) if x >= 0.08 else "" for x in v], textposition="inside", insidetextanchor="middle",
                             textfont=dict(color="white" if color != GRIS else INK), width=0.5,
                             hovertemplate="%{y}: " + nombre + " <b>%{x:.1%}</b><extra></extra>"))
    estilo(fig, f"Cómo termina tu vida laboral al retirarte a los {R['edad_retiro']:.0f} años ({R['anio']})", 260, barmode="stack")
    fig.update_layout(legend_traceorder="normal")
    fig.update_xaxes(tickformat=".0%", range=[0, 1])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    st.plotly_chart(fig, use_container_width=True, config=GRAFICO)

    req_afp = G.semanas_requeridas("rais", sexo, R["anio"])
    req_col = G.semanas_requeridas("rpm", sexo, R["anio"])
    h, b = np.histogram(afp.semanas, bins=np.arange(0, max(afp.semanas.max(), req_col) + 100, 50))
    fig = go.Figure(go.Bar(x=b[:-1] + 25, y=h / len(afp), width=44, marker=dict(color=AZUL, line=dict(width=0)),
                           hovertemplate="%{x:.0f} semanas: %{y:.1%}<extra></extra>", showlegend=False))
    lineas = ([(req_afp, "Requisito AFP y Colpensiones", "top left")] if req_afp == req_col else
              [(req_afp, "AFP", "top left"), (req_col, "Colpensiones", "top right")])
    for v, nombre, pos in lineas:
        fig.add_vline(x=v, line=dict(color=INK2, width=1, dash="dash"),
                      annotation_text=f"{nombre}: {v:,.0f}".replace(",", "."), annotation_position=pos, annotation_font_color=INK2)
    estilo(fig, "Semanas cotizadas al retirarte", 320)
    fig.update_xaxes(title="Semanas")
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True, config=GRAFICO)

    st.markdown("**Resumen en tabla**")
    tabla = pd.DataFrame({
        "Indicador": ["Probabilidad de pensionarse", "Financia más que el mínimo", "Garantía de pensión mínima", "Devolución de saldos",
                      "Mesada mediana si se pensiona", "Mesada P10 – P90 si se pensiona", "Tasa de reemplazo mediana",
                      "Semanas al retiro (P10 – P50 – P90)", "Saldo mediano al retiro", "Costo medio de la garantía para el Estado"],
        "AFP": [pct(res.afp_p_pension), pct(res.afp_p_capital_suficiente), pct(res.afp_p_garantia_minima), pct(res.afp_p_devolucion),
                pesos(med_afp), f"{pesos(res.afp_mesada_p10 * sm)} – {pesos(res.afp_mesada_p90 * sm)}", pct(res.afp_reemplazo_p50),
                f"{res.semanas_p10:,.0f} – {res.semanas_p50:,.0f} – {res.semanas_p90:,.0f}".replace(",", "."),
                pesos(res.afp_saldo_p50_millones * 1e6), pesos(res.afp_costo_garantia_medio_millones * 1e6)],
        "Colpensiones": [pct(res.colpensiones_p_pension), "—", "—", pct(1 - res.colpensiones_p_pension), pesos(med_col), "—",
                         pct(res.colpensiones_reemplazo_p50), "igual", "—", "—"],
    }).set_index("Indicador")
    st.dataframe(tabla, use_container_width=True)
    st.caption(f"Error de Monte Carlo de la probabilidad de pensionarse: ±{res.error_estandar_p_pension * 100:.1f} puntos (1 error estándar).".replace(".", ",", 1))

# --------------------------------------------------------------------------- 3. Escenarios
with tab3:
    st.markdown("¿Qué pasaría si cambias una decisión? Cada escenario usa los mismos números aleatorios, así que las diferencias "
                "se deben solo al cambio.")
    if st.button("Calcular escenarios", key="btn_escenarios"):
        st.session_state["escenarios"] = escenarios(perfil, supuestos, min(n_sims, 5_000))
    esc = st.session_state.get("escenarios")
    if esc is not None:
        a, b = st.columns(2)
        for colm, metrica, fmt, titulo in [(a, "P(más que el mínimo)", ".0%", "Probabilidad de financiar más que el mínimo"),
                                           (b, "Mesada media total (SMMLV)", ".2f", "Mesada media (incluye casos sin pensión, SMMLV)")]:
            d = esc[metrica]
            fig = go.Figure(go.Bar(y=d.index, x=d.values, orientation="h", width=0.55,
                                   marker=dict(color=[LINEA if i == 0 else AZUL for i in range(len(d))], line=dict(width=0)),
                                   text=[pct(v) if fmt == ".0%" else dec(v) for v in d.values], textposition="outside", cliponaxis=False,
                                   textfont=dict(color=INK2), hovertemplate="%{y}: <b>%{x:" + fmt + "}</b><extra></extra>"))
            estilo(fig, titulo, 330)
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(tickformat=fmt, rangemode="tozero")
            colm.plotly_chart(fig, use_container_width=True, config=GRAFICO)
        st.dataframe(esc.style.format({"P(pensión)": pct, "P(más que el mínimo)": pct,
                                       "Mesada media total (SMMLV)": dec, "Mesada P90 (SMMLV)": dec}), use_container_width=True)
        st.caption("Si vas a terminar en la garantía de pensión mínima, un ahorro voluntario pequeño puede no cambiar tu mesada: solo "
                   "reduce lo que paga el Estado. Lo que más mueve el resultado suele ser la edad de retiro.")

# --------------------------------------------------------------------------- 4. Sensibilidad
with tab4:
    st.markdown("¿Qué supuestos mueven tu resultado? Cada supuesto se lleva a un valor bajo y uno alto, con los demás en su valor base.")
    metricas = {"afp_p_pension": "Probabilidad de pensionarte", "afp_p_capital_suficiente": "Probabilidad de financiar más que el mínimo",
                "afp_mesada_media_total": "Mesada media total (SMMLV)"}
    metrica = st.radio("Indicador", list(metricas), format_func=metricas.get, horizontal=True, key="metrica_tornado")
    if st.button("Calcular sensibilidad", key="btn_tornado"):
        st.session_state["tornado"] = sensibilidad(perfil, supuestos, min(n_sims, 3_000))
    t = st.session_state.get("tornado")
    if t is not None:
        d = t[t.metrica == metrica].sort_values("rango")
        base = d.base.iloc[0]
        fmt = ".2f" if metrica == "afp_mesada_media_total" else ".0%"
        fig = go.Figure()
        for lado, color, nombre in [("bajo", BAJO, "Valor bajo del supuesto"), ("alto", ALTO, "Valor alto del supuesto")]:
            fig.add_trace(go.Bar(y=d.supuesto, x=d[lado] - base, base=base, orientation="h", name=nombre, width=0.32,
                                 marker=dict(color=color, line=dict(color=SURFACE, width=2)), customdata=d[lado],
                                 hovertemplate="%{y}<br>" + nombre + ": <b>%{customdata:" + fmt + "}</b><extra></extra>"))
        fig.add_vline(x=base, line=dict(color=INK, width=1))
        estilo(fig, f"{metricas[metrica]}: base {pct(base) if fmt == '.0%' else dec(base)}", 400, barmode="group", bargap=0.35)
        fig.update_xaxes(tickformat=fmt)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True, config=GRAFICO)
        st.dataframe(d.sort_values("rango", ascending=False).set_index("supuesto")[["base", "bajo", "alto"]]
                     .style.format(pct if fmt == ".0%" else dec), use_container_width=True)

# --------------------------------------------------------------------------- 5. Metodología
with tab5:
    num = lambda x: f"{x:,}".replace(",", ".")
    st.markdown(f"""
**Qué simula.** Para tu perfil se simulan {num(n_sims)} vidas laborales hasta la edad de retiro. Cada una combina:

1. **Salario:** modelo Tobit estimado con 583.000 cotizantes de la GEIH 2022–2025, con un componente permanente y choques persistentes, condicionado en tu salario actual.
2. **Meses cotizados:** cadena de Markov calibrada con la GEIH y datos administrativos (rotación, antigüedad en el empleo, afiliados), condicionada en tus semanas.
3. **Rentabilidad:** bootstrap de las rentabilidades reales de Protección (2016–2026), con incertidumbre sobre la rentabilidad promedio y la trayectoria de multifondos por defecto.
4. **Reglas de la Ley 100:**
   - **AFP:** capital suficiente, garantía de pensión mínima o devolución de saldos.
   - **Colpensiones:** tasa de reemplazo del art. 34, o indemnización sustitutiva.

**Supuestos base:**
- Tasa técnica real del {pct(P['supuestos']['tasa_tecnica_real'])}.
- Crecimiento real del SMMLV del {pct(P['supuestos']['crecimiento_real_smmlv'])}.
- La AFP verifica el capital suficiente con un crecimiento de beneficios del {pct(G_REG, 2)} (Res. MinHacienda 1045 de 2026).
- 13 mesadas al año y tablas de mortalidad RV08.

**Validación:**
- Reproduce una liquidación real de Colpensiones confirmada por un tribunal.
- Coincide con referencias de capital necesario y cobertura.
- Predice salarios y tasas de cotización de 2025 con modelos estimados solo hasta 2024.

**Limitaciones:**
- No incluye bono pensional, traslados entre regímenes, invalidez ni sobrevivientes (salvo el cónyuge opcional).
- Supone las reglas actuales: la reforma pensional (Ley 2381 de 2024) aún no está modelada.
- La comparación con Colpensiones aplica sus reglas a la misma persona, aunque en la realidad cada afiliado está en un solo régimen.
- En el modelo, la propensión a cotizar no depende del salario.
- Las rentabilidades de 10 años subestiman crisis como la de 2021–2022.

*Ejercicio académico; no constituye asesoría financiera ni pensional. Para decisiones reales, usa la doble asesoría de tu AFP y de Colpensiones.*
""")
