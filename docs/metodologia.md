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

## 2. Salarios

Módulo `pension_mc.wages`. Estimación y validación en [`notebooks/03_salarios.ipynb`](../notebooks/03_salarios.ipynb).

### Datos

Cotizantes de 18 a 65 años con ingreso laboral positivo, GEIH 2022–2025 (583.208 personas-mes), con el ingreso deflactado a pesos de septiembre de 2026. Los tipos $k$ son las combinaciones de educación (primaria o menos, secundaria, media, superior) × sexo.

### Modelo

Para el log del salario **latente** de la persona $i$ a la edad $a$:

$$
\ln w^*_{ia} = f_k(a) + g\,t + \alpha_i + z_{ia}, \qquad
z_{ia} = \rho_k z_{i,a-1} + \varepsilon_{ia}, \quad z_{i,17} = 0
$$

$$
\alpha_i \sim N(0, \sigma_{\alpha,k}^2), \qquad \varepsilon_{ia} \sim N(0, \sigma_{\varepsilon,k}^2)
$$

- $f_k(a)$: perfil cuadrático en la edad para cada tipo, con el nivel del último año estimado (2025).
- $g$: crecimiento real de la productividad (supuesto, 1 % anual).
- El salario observado es $w = \max(w^*, \text{SMMLV})$, y el IBC es `clip(w, 1, 25) × SMMLV` (40 % del ingreso para independientes).

### Estimación

**Paso 1: Tobit heterocedástico.** Se considera que gana el mínimo quien declara hasta el mínimo + el auxilio de transporte + 2 % del mínimo: en la GEIH hay amontonamiento en 1,00 y en 1,12–1,16 SMMLV, y el auxilio no hace parte del IBC. Son el 41 % de los cotizantes, así que se estima por máxima verosimilitud:

$$
y^* = X\beta + e^{Z\gamma} u, \quad u \sim N(0, 1); \qquad
\ell_i = \begin{cases} \ln \Phi\!\left(\frac{c_i - X_i\beta}{s_i}\right) & \text{si } y_i \le c_i \\ -\ln s_i + \ln \phi\!\left(\frac{y_i - X_i\beta}{s_i}\right) & \text{si no} \end{cases}
$$

ponderando con el factor de expansión. $X$ tiene $[1, e, e^2]$ por tipo ($e = (a-40)/10$) y efectos de año; $Z$ tiene $[1, e, e^2]$ por tipo. Se usan gradientes analíticos y L-BFGS-B. Sin la censura con auxilio (umbral de 1,05 SMMLV), los errores de validación son casi el doble.

**Paso 2: persistencia.** Con $z$ en cero a los 17 años, la varianza de $\alpha + z$ crece con la edad:

$$
\sigma_k(a)^2 = \sigma_{\alpha,k}^2 + \sigma_{\varepsilon,k}^2 \frac{1 - \rho_k^{2(a-17)}}{1 - \rho_k^2}
$$

$(\sigma_\alpha, \sigma_\varepsilon, \rho)$ se ajustan por tipo a la $\sigma_k(a)$ del Tobit entre los 20 y los 64 años (mínimos cuadrados en logaritmos; Deaton y Paxson, 1994). Resultados: $\rho$ entre 0,95 y 0,995 (choques casi permanentes); en educación superior, $\sigma_\varepsilon$ es 2 a 3 veces mayor.

### Simulación

Frecuencia anual: el salario de un año rige sus 12 meses.

- **Sin salario actual:** $\alpha \sim N(0, \sigma_\alpha^2)$ y $z_a \sim N(0, v_z(a))$.
- **Con salario actual $w_0$:** el desvío $u = \ln w_0 - f_k(a)$ se reparte entre $\alpha$ y $z$ según sus varianzas: $\alpha \mid u \sim N\!\left(u\,\sigma_\alpha^2 / v_u,\; \sigma_\alpha^2 v_z / v_u\right)$ y $z = u - \alpha$. Si $w_0$ es el mínimo, $u$ se sortea de la normal truncada por debajo del umbral.

### Validación

Para cada tipo y edad (25, 40, 55) se simula una sección transversal y se compara con la GEIH 2025: el error medio es de 1,8 % en la mediana y de 6,6 % en el P90, y la proporción en el mínimo queda sobreestimada en ~3 puntos.

### Limitaciones

- El perfil es de corte transversal: mezcla efectos de edad y de cohorte.
- **La división entre $\alpha$ y $z$ está débilmente identificada** por tipo. Imponer una $\rho$ común empeora mucho el ajuste de la varianza (hasta 0,46 en log), así que se mantienen los ajustes por tipo. La división solo afecta la simulación condicionada en el salario actual.
- Después de los 50–55 años la dispersión estimada baja en algunos grupos (salida selectiva). El AR(1) no puede reproducir una varianza decreciente y la sobreestima un poco cerca del retiro.
- El error de medición del ingreso declarado queda dentro del componente permanente, y no se corrige la selección (solo se observa a quienes cotizan).

## 3. Densidad de cotización

Módulo `pension_mc.contributions`. Estimación, calibración y validación en [`notebooks/04_cotizacion.ipynb`](../notebooks/04_cotizacion.ipynb).

### Tasas por edad

$\pi_k(a)$ es la proporción de la **población** del tipo $k$ (educación × sexo) que cotiza a la edad $a$, en la GEIH 2023–2025 ponderada. Los desocupados e inactivos cuentan como "no cotiza". Se suaviza con un logit binomial y un spline cúbico natural de 7 grados de libertad por tipo.

### Cadena de Markov con propensión individual

Para la persona $i$ del tipo $k$:

$$
\pi_i(a) = \text{logística}\big(c_k(a) + \beta\,\eta_i(a)\big), \qquad E_\eta[\pi_i(a)] = \pi_k(a)
$$

- $\eta_i(a) \sim N(0,1)$ sigue un AR(1) con persistencia anual $\rho_\eta$ **hasta los 30 años** y queda fijo después: la situación laboral se forma en la juventud y se consolida con la edad. La edad de consolidación se estima (ver abajo).
- $c_k(a)$ se obtiene por cuadratura de Gauss-Hermite.

Cada mes:

$$
s_t = \mu(a)\,(1 - \pi_{i,t}), \qquad f_t = \frac{\pi_{i,t+1} - \pi_{i,t}(1 - s_t)}{1 - \pi_{i,t}}, \qquad \mu(a) = \mu_0\, e^{-\kappa (a-40)/10}
$$

$s$ es la probabilidad de dejar de cotizar y $f$ la de empezar. $f$ hace que la probabilidad marginal de cada persona siga su $\pi_i(a)$; si la tasa cae más rápido de lo que permite $s$, se usa $s = 1 - \pi_{t+1}/\pi_t$.

### Calibración

La GEIH no sigue a las personas, así que $(\mu_0, \kappa, \beta, \rho_\eta)$ se calibran por simulación con números aleatorios comunes, con cuatro momentos:

| Momento | Dato | Modelo | Fuente |
|---|---|---|---|
| Cotizantes del mes / activos (últimos 6 meses) | 0,82 | 0,82 | MinTrabajo (`sk9s-yxmi`); en las AFP las columnas parecen invertidas, y así el total coincide con los cotizantes de la GEIH |
| Cotizantes de 25–44 años con ≥ 36 meses en el empleo actual | 0,46 | 0,46 | GEIH (P6426), cota inferior |
| Ídem, 45–64 años | 0,73 | 0,74 | GEIH (P6426), cota inferior |
| Alguna vez cotizó (afiliados / población de 18 a 70 años) | 0,77 | 0,77 | MinTrabajo y GEIH, cota superior |

Resultado: $\mu_0 = 0{,}30$, $\kappa = 0{,}58$, $\beta = 6{,}2$, $\rho_\eta = 0{,}70$; error máximo de 0,2 puntos.

**Edad de consolidación.** Se recalibra el modelo con edades de 25 a 40 años. Los mejores ajustes están entre 28 y 32 años (error cuadrático medio de 0,002 a los 30); desde los 35 el ajuste empeora (0,012) y a los 40 es malo (0,032). Se usa 30. Los parámetros no están bien identificados por separado (otras combinaciones dan errores similares), pero los resultados sí lo están.

### Lo que se aprendió en la validación

1. **Con solo rotación + "alguna vez cotizó"** ($\beta = 1{,}4$, η permanente), los periodos de cotización simulados eran mucho más cortos que la antigüedad observada en el empleo (31 % vs. 46–73 % con 3 años o más).
2. **Con rotación constante,** los periodos de los mayores quedaban por debajo de su antigüedad. Por eso se agregó $\kappa$.
3. **Con la cadena estacionaria simple** ($f = \mu\pi$), una rotación baja hacía que la cadena siguiera con rezago la caída de la tasa antes del retiro. La entrada $f_t$ que sigue la trayectoria eliminó ese rezago.
4. **Con η permanente,** las semanas de un joven decidían su destino. A los 25 años, tener 0 o 100 semanas era tener 1 % o 93 % de probabilidad de pensionarse, porque quien no cotizó entre los 18 y los 25 quedaba marcado para siempre. Este problema apareció al probar el motor (paso 7). Con η móvil en la juventud la probabilidad queda entre 41 % y 53 %, y el modelo reproduce además "alguna vez cotizó", que con η permanente no lograba (61 %). Con η móvil a *todas* las edades no es posible reproducir los periodos largos de los 45–64 años.

### Sensibilidad

Con la composición educativa de los jóvenes, la proporción que alcanza las semanas de la garantía de pensión mínima es:

| Variante | Proporción |
|---|---|
| Base (consolidación a los 30) | 39,8 % |
| Consolidación entre los 25 y los 35 | 39,1–40,3 % |
| Rotación 0,79–0,86, duración +5 puntos, alguna vez 0,70 | 38,4–40,3 % |
| Consolidación a los 40 (mal ajuste) | 37,2 % |
| η permanente | 34–37 % |

### Condicionamiento en la historia

`condicionar(edad, sexo, educ, semanas)` muestrea $(\eta, \text{estado actual})$ por rechazo: simula historias desde los 15 años y conserva las que acumulan las semanas reportadas (±25). El η que devuelve es el del momento actual.

### Limitaciones

- Entre los 25 y los 34 años, el modelo genera más rotación de la que sugiere la antigüedad observada. Puede subestimar algo la cotización de los jóvenes.
- Las tasas son de corte transversal: no hay tendencia de formalización.
- $\eta$ no está correlacionado con el salario del paso 4.
- No se distingue entre asalariados e independientes.

## 4. Acumulación, mesada y reglas de pensión

Módulos `pension_mc.accumulation`, `pension_mc.decumulation` y `pension_mc.regimes`. Ejemplos en [`notebooks/05_pension.ipynb`](../notebooks/05_pension.ipynb).

### Acumulación (AFP)

En pesos reales, con el aporte al final del mes:

$$
S_t = S_{t-1}(1 + r_t) + c_t\,(0{,}115 \cdot \text{IBC}_t + v_t)
$$

$r_t$ es la rentabilidad real del portafolio de multifondos (paso 3), $c_t$ el indicador de cotización (paso 5), el IBC sale del salario (paso 4) y $v_t$ es un aporte voluntario opcional.

### De saldo a mesada

Capital necesario por cada peso de mesada, con 13 mesadas al año como 12 pagos anticipados de 13/12:

$$
F(x) = \frac{13}{12}\sum_{m \ge 0} \left(\frac{1+g}{1+i}\right)^{m/12} {}_{m/12}p_x
$$

- Tablas RV08 con supervivencia interpolada linealmente entre edades enteras.
- $i$: tasa técnica real (4 %, supuesto).
- $g$: crecimiento real de la mesada: 0 para pensiones indexadas al IPC y el crecimiento del SMMLV para la pensión mínima.
- Con cónyuge beneficiario (100 %): ${}_tp = {}_tp_x + {}_tp_y - {}_tp_x\,{}_tp_y$.

Verificación: con $i = 0$, $F \cdot 12/13/12$ coincide con la esperanza de vida de la RV08.

### Reglas en las AFP

| Situación al llegar a la edad de pensión | Resultado |
|---|---|
| $S \ge \text{SMMLV} \cdot F(x; g = g_{\text{SMMLV}})$ | Capital suficiente: mesada $= S / F(x; 0)$ |
| Si no, con la edad y las semanas de la garantía de pensión mínima | Mesada = 1 SMMLV; el Estado paga $\text{SMMLV} \cdot F - S$ |
| En otro caso | Devolución de saldos |

**Sobre el art. 64.** El texto exige capital para una pensión mayor al 110 % del SMMLV **de 1993 reajustado por IPC**, umbral muy inferior al SMMLV actual. Como ninguna pensión puede ser menor que el mínimo (art. 35), la AFP verifica con el Saldo de Pensión Mínima si el saldo financia 1 SMMLV vitalicio (Res. MinHacienda 3099 de 2015, modificada por la 3023 de 2017). Esa es la regla que se implementa.

### Reglas en Colpensiones

Con la edad y las semanas:
- **Mesada:** $\text{mesada} = \min(r + 1{,}5 \lfloor (\text{sem} - \text{sem}_{\min})/50 \rfloor,\; r + 15,\; 80)\% \cdot \text{IBL}$, con $r = \text{clip}(65{,}5 - 0{,}5\,s,\; 55,\; 65)$ y $s = \text{IBL}/\text{SMMLV}$. Piso de 1 SMMLV y tope de 25 SMMLV.
- **IBL:** promedio real del IBC de los últimos 120 meses cotizados, o de toda la vida si es mayor y hay ≥ 1.250 semanas.

Sin las semanas: indemnización sustitutiva = IBC semanal promedio × semanas × 13 %.

### Requisitos de semanas por año

| | Hombres | Mujeres |
|---|---|---|
| Garantía de pensión mínima (AFP) | 1.150 | 1.150 hasta 2025; 1.135 en 2026 y −15 por año hasta 1.000 (C-054 de 2024) |
| Colpensiones | 1.300 | 1.300 hasta 2025; 1.250 en 2026 y −25 por año hasta 1.000 en 2036 (C-197 de 2023) |

### Simplificaciones

- **Sin beneficiarios por defecto** (opcional con `conyuge`). Para un hombre con cónyuge 3 años menor el capital necesario sube ~29 %, así que la mesada sin beneficiarios es una cota superior.
- **Renta vitalicia** valorada a la tasa técnica: no se simula el retiro programado año a año.
- **Sin bono pensional ni traslados** entre regímenes.
- **Perfiles con historia:** el saldo actual lo informa la persona (o se aproxima con las semanas), y el IBL de Colpensiones usa solo el periodo simulado.

## 5. Motor de simulación

Módulo `pension_mc.simulate`. Análisis en [`notebooks/06_motor.ipynb`](../notebooks/06_motor.ipynb).

```python
from pension_mc.simulate import Perfil, Supuestos, simular, tornado

perfil = Perfil(edad=30, sexo="Mujer", educacion="Superior", salario=3_500_000,
                semanas=250, cotiza_hoy=True)
r = simular(perfil, Supuestos(), n_sims=10_000)
r.resumen()          # probabilidades, mesadas, semanas, saldo, costo de la garantía, Colpensiones
r.afp, r.colpensiones  # una fila por simulación
```

### Flujo de una simulación

1. **Salarios** (paso 4): trayectoria anual condicionada en el salario actual, con piso de 1 SMMLV. El IBC es el salario, o el 40 % del ingreso para independientes, con tope de 25 SMMLV.
2. **Cotización** (paso 5): condicionada en las semanas ya cotizadas y en si cotiza hoy. Admite lagunas forzadas y congelar la tasa desde una edad (para quien sigue trabajando después de los 55).
3. **Rentabilidad** (paso 3): bootstrap estacionario, t multivariada o escenario determinista; trayectoria de multifondos por defecto o un fondo fijo; ajuste de la media e incertidumbre de la media opcionales.
4. **Saldo y reglas** (paso 6): aplica a la misma población las reglas de las AFP y de Colpensiones.

### Perfil y supuestos

| `Perfil` | Descripción |
|---|---|
| `edad`, `sexo`, `educacion` | Definen el tipo (perfil salarial y de cotización) |
| `salario`, `semanas`, `cotiza_hoy`, `saldo` | Historia actual; sin `saldo` se aproxima con las semanas |
| `independiente` | Cotiza sobre el 40 % del ingreso |
| `edad_retiro`, `fondo`, `aporte_voluntario_pct` | Decisiones del afiliado |
| `laguna`, `conyuge_diferencia_edad` | Experimentos y beneficiario |

| `Supuestos` | Base |
|---|---|
| `metodo_rentabilidad`, `ajuste_rentabilidad`, `incertidumbre_media` | bootstrap, 0, no |
| `tasa_tecnica`, `crecimiento_smmlv`, `crecimiento_salarios` | 4 %, 1 %, 1 % |
| `cotizacion` | calibración base (consolidación a los 30); alternativas en `CALIBRACIONES_COTIZACION` |
| `seed` | 2026 |

### Números aleatorios

Cada componente recibe una semilla derivada de `Supuestos.seed` con `numpy.random.SeedSequence`:
- **Misma semilla:** dos escenarios comparten los números aleatorios, así que sus diferencias se deben al supuesto y no al ruido.
- **Semillas distintas:** las corridas son independientes. Con 10.000 simulaciones, el error de una probabilidad es ~0,5 puntos, igual al binomial teórico.

Una primera versión usaba `seed + k` por componente, y las semillas consecutivas compartían flujos.

### Análisis

- `comparar(escenarios)`: tabla de resúmenes.
- `tornado(perfil, variaciones)`: sensibilidad uno a uno sobre campos de `Supuestos` o del `Perfil`.

### Limitaciones del motor

- La mesada media no descuenta los años de pensión que se pierden al retirarse más tarde.
- La comparación AFP vs. Colpensiones aplica ambas reglas a la misma persona.
- Sin bono pensional ni beneficiarios por defecto.
- El escenario de la reforma pensional (Ley 2381 de 2024) aún no está implementado.
