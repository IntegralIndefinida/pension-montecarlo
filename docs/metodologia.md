# Metodología

Ecuaciones y supuestos de cada componente del simulador. Los parámetros están en [`config/parametros.yaml`](../config/parametros.yaml) y las reglas legales en [`marco_normativo.md`](marco_normativo.md).

## 1. Rentabilidades

Módulo `pension_mc.returns`. Validación en [`notebooks/02_rentabilidades.ipynb`](../notebooks/02_rentabilidades.ipynb).

### Datos

Rentabilidades reales mensuales $r_{t,j}$ de los fondos $j \in$ {mayor riesgo, moderado, conservador, retiro programado} de Protección, de febrero de 2016 a septiembre de 2026 ($T = 128$ meses). Se trabaja con log-rentabilidades $x_{t,j} = \ln(1 + r_{t,j})$.

Todos los generadores simulan **los cuatro fondos a la vez** (el mismo mes histórico o la misma realización), lo que conserva su correlación (0,64–0,95).

### Generador 1: bootstrap estacionario (caso base)

Politis y Romano (1994). Para cada trayectoria $s$:

$$
i_{s,0} \sim U\{1..T\}, \qquad
i_{s,t} = \begin{cases} U\{1..T\} & \text{con probabilidad } p = 1/b \\ (i_{s,t-1} + 1) \bmod T & \text{con probabilidad } 1 - p \end{cases}
$$

y $x^{sim}_{s,t,j} = x_{i_{s,t},j}$. Los bloques tienen largo geométrico de media $b$, y el remuestreo es circular.

**Largo de bloque.** Se usa el $b$ óptimo de Politis y White (2004) con la corrección de Patton, Politis y White (2009), promediado entre fondos:

$$
\hat b = \left(\frac{\hat G^2}{\hat g(0)^2}\right)^{1/3} T^{1/3}, \quad
\hat G = \sum_{|k| \le M} \lambda(k/M)\,|k|\,\hat\gamma(k), \quad
\hat g(0) = \sum_{|k| \le M} \lambda(k/M)\,\hat\gamma(k)
$$

donde $\lambda$ es el núcleo de tapa plana y $M$ se elige con la regla de autocorrelaciones no significativas. Con los datos actuales $\hat b \approx 1{,}4$ meses: la autocorrelación es débil. Los resultados a 10 y 50 años casi no cambian con $b$ entre 1,4 y 24 meses.

### Generador 2: t multivariada

Log-rentabilidades i.i.d.:

$$
x_t = \mu + \frac{L z_t}{\sqrt{w_t/\nu}}, \quad z_t \sim N(0, I),\; w_t \sim \chi^2_\nu,\; L L' = \tfrac{\nu-2}{\nu} S
$$

con $\mu$ y $S$ la media y la covarianza muestrales, de modo que la covarianza simulada sea $S$. Los grados de libertad $\nu$ se estiman por máxima verosimilitud perfilada en una grilla; con los datos actuales $\hat\nu = 4$. No reproduce la autocorrelación, pero da colas más gruesas que la muestra: es una alternativa prudente.

### Generador 3: escenarios deterministas

Rentabilidad real anual constante igual a los percentiles 10 / 50 / 90 de la rentabilidad anualizada $\exp(12\,\bar x_s) - 1$ de las trayectorias del bootstrap. Dependen del horizonte con el que se calculan.

### Ajuste de la media

`media_objetivo` recentra las log-rentabilidades de un fondo para que su media corresponda a una rentabilidad real anual $m$, sin cambiar la volatilidad ni la correlación:

$$
\tilde x_{t,j} = x_{t,j} - \bar x_j + \ln(1 + m_j)/12
$$

### Incertidumbre de la media

El error estándar de la media anual es de 1,8 a 2,7 puntos según el fondo, mayor que la diferencia entre fondos. Con `incertidumbre_media=True`, cada trayectoria recibe un desplazamiento permanente de su media:

$$
\delta_s \sim N\!\left(0,\; S / T\right), \qquad x^{sim}_{s,t} \leftarrow x^{sim}_{s,t} + \delta_s
$$

que corresponde a la distribución muestral del promedio, con la correlación entre fondos. A 50 años, la incertidumbre de la media domina sobre la volatilidad mensual. Por ejemplo, el rango P5–P95 de la rentabilidad anualizada del moderado pasa de ~2–5 % a ~0–8 %. Es una cota superior, porque ignora toda información distinta de estos 10 años. Se usa en el análisis de sensibilidad, no en el caso base.

### Multifondos por edad

`pesos_por_defecto(edad, sexo, n_meses)` devuelve la proporción del saldo en cada fondo según la edad cumplida en cada mes:

1. **Mayor riesgo → moderado** (art. 2.6.11.1.5, Decreto 959 de 2018): 100 % en mayor riesgo hasta los 41 años (mujeres) o 46 (hombres); baja 20 puntos por año hasta 0 % a los 46 / 51.
2. **Convergencia al conservador** (art. 2.6.11.1.6 + 2 años desde 2014): 20 % a los 52 / 57, sube 20 puntos por año hasta 100 % a los 56 / 61. Lo que no está en el conservador va al moderado.

La rentabilidad del portafolio es $\sum_j w_{t,j}\, r_{s,t,j}$, rebalanceado cada mes. También se puede fijar un solo fondo (`pesos_fijos`).

### Limitaciones

- Solo 10,7 años de historia, con dos episodios extremos: el COVID (marzo de 2020) y el choque de inflación y tasas (2021–2022).
- Las rentabilidades son las del valor de unidad, es decir, netas de los costos que se descuentan del fondo. La comisión de administración se cobra sobre el aporte (sección 2 del marco normativo), así que no afecta este cálculo.
- No se modelan cambios futuros en el régimen de inversión de los fondos.
