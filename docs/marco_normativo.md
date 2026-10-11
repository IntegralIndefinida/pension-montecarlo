# Marco normativo del simulador

**Fecha de corte de la revisión:** 9 de octubre de 2026.

Este documento resume las reglas del Sistema General de Pensiones de Colombia que implementa el simulador. Todos los valores numéricos están en [`config/parametros.yaml`](../config/parametros.yaml), cada uno con su fuente y un **estado de verificación**:

- ✅ **Verificado:** confirmado en una fuente oficial o en varias fuentes coincidentes.
- ⚠️ **Por verificar:** encontrado en fuentes secundarias (prensa, AFP, consultoras); falta contrastarlo con la norma o con la entidad.
- ❓ **Pendiente:** no se encontró el dato o depende de decisiones aún abiertas.

> **Regla de oro:** antes de publicar resultados, todo parámetro marcado ⚠️ o ❓ debe pasar a ✅, o quedar documentado como supuesto en el README.

---

## 1. Contexto: ¿qué régimen modelar?

| Periodo | Reglas aplicables |
|---|---|
| Hasta el 31 de marzo de 2027 | Ley 100 de 1993 y sus modificaciones: **RAIS** (AFP) y **RPM** (Colpensiones) en competencia |
| Desde el 1 de abril de 2027 | **Ley 2381 de 2024** (sistema de pilares), según la Sentencia C-264 de 2026 |

**Estado de la reforma (Ley 2381 de 2024):**
1. Junio de 2025: la Corte Constitucional suspendió su entrada en vigencia por un vicio de trámite y devolvió la ley a la Cámara.
2. 25 de agosto de 2026, **Sentencia C-264 de 2026**: la Corte declaró exequible la mayor parte de la ley por el trámite y devolvió nueve artículos a la Cámara (entre ellos, según la prensa, el **régimen de transición**). La fecha de entrada en vigencia reportada es el **1 de abril de 2027**.
3. **Sigue pendiente** el estudio de las demandas de fondo (contenido) de la ley.

**Decisión de diseño:** como cualquier afiliado joven se pensionará bajo la reforma, el simulador tendrá dos escenarios:
- **Escenario A, ley actual (RAIS/RPM):** reglas estables y bien documentadas. Será el **MVP**.
- **Escenario B, reforma (pilares):** se implementa después, con los parámetros marcados como provisionales hasta que se resuelva el trámite en la Cámara.

⚠️ Verificar el texto de la Sentencia C-264 de 2026 en la relatoría de la Corte Constitucional y el resultado del nuevo trámite en la Cámara.

---

## 2. Cotización (común a ambos regímenes de la Ley 100)

| Concepto | Valor | Estado |
|---|---|---|
| Tasa de cotización total | 16 % del IBC | ✅ |
| Reparto empleador / trabajador (dependientes) | 12 % / 4 % | ⚠️ |
| IBC mínimo | 1 SMMLV | ✅ |
| IBC máximo | 25 SMMLV | ⚠️ |
| IBC de independientes | 40 % del ingreso mensual | ⚠️ |
| SMMLV 2025 | $1.423.500 | ✅ |
| SMMLV 2026 | $1.750.905 (Decreto 1469 de 2025, ratificado por el Decreto 0159 de 2026 tras la suspensión provisional del Consejo de Estado) | ⚠️ |

**Reparto del 16 % en el RAIS** (Superfinanciera, conceptos 2017-0044321 y 2021-0126207):

| Destino | % del IBC | Estado |
|---|---|---|
| Cuenta de ahorro individual | 11,5 % | ✅ |
| Fondo de Garantía de Pensión Mínima (FGPM) | 1,5 % | ✅ |
| Comisión de administración + seguro previsional (invalidez y sobrevivencia) | 3,0 % (tope legal, art. 20 Ley 100) | ✅ |

**Fondo de Solidaridad Pensional (FSP):** aporte *adicional* al 16 % para IBC ≥ 4 SMMLV: 1 %, más un punto adicional escalonado de 0,2 % a 1 % para IBC entre 16 y más de 20 SMMLV (art. 27 Ley 100, modificado por la Ley 797 de 2003). ⚠️

**Implicación para el modelo:** solo el **11,5 %** del IBC entra a la cuenta individual. El FSP no afecta el saldo, pero sí el costo para el afiliado (relevante si se calcula una "rentabilidad" de los aportes).

---

## 3. Régimen de Ahorro Individual con Solidaridad (RAIS, AFP como Protección)

### 3.1 Acumulación
```
saldo[t+1] = saldo[t] · (1 + r_fondo[t]) + 11,5 % · IBC[t] · cotiza[t] + aporte_voluntario[t]
```
- `r_fondo[t]` es la rentabilidad del fondo en el que está el afiliado (ver sección 5).
- Los aportes voluntarios al fondo obligatorio suman al saldo (opcional en el simulador).
- Los **bonos pensionales** (afiliados que vienen del ISS/Colpensiones) quedan **fuera del alcance**.

### 3.2 Requisitos de pensión de vejez

| Vía | Requisito | Norma | Estado |
|---|---|---|---|
| **Capital suficiente** | Saldo que financie una pensión ≥ **110 % del SMMLV** a cualquier edad | Art. 64 Ley 100 | ✅ |
| **Garantía de Pensión Mínima (GPM)** | Hombres: 62 años y 1.150 semanas. Mujeres: 57 años y semanas decrecientes (ver abajo). Si el saldo no alcanza, el Estado completa hasta 1 SMMLV | Art. 65 Ley 100 | ✅ (edades) |
| **Devolución de saldos** | Si a la edad de pensión no cumple ninguna de las anteriores | Art. 66 Ley 100 | ✅ |

**Semanas de las mujeres para la GPM (Sentencia C-054 de 2024):** la Corte declaró inexequible el requisito de 1.150 semanas para las mujeres, con efectos diferidos hasta el 31 de diciembre de 2025. Sin ley del Congreso, el requisito baja **15 semanas por año desde 2026** hasta llegar a **1.000**.

| Año | 2026 | 2027 | 2028 | 2029 | 2030 | 2031 | 2032 | 2033 | 2034 | 2035+ |
|---|---|---|---|---|---|---|---|---|---|---|
| Semanas | 1.135 | 1.120 | 1.105 | 1.090 | 1.075 | 1.060 | 1.045 | 1.030 | 1.015 | 1.000 |

⚠️ La tabla es una **derivación** de la regla de la sentencia (1.150 − 15 por año). Falta confirmarla con la Superfinanciera o con una AFP, y verificar que el Congreso no haya expedido otra regla.

### 3.3 Desacumulación (de saldo a mesada)
- **Modalidades:** retiro programado, renta vitalicia y retiro programado con renta vitalicia diferida.
- **Mesada simplificada (renta vitalicia):**
  ```
  mesada = saldo_al_retiro / (13 · ä_x)
  ```
  donde `ä_x` es el valor presente actuarial de una anualidad mensual vitalicia a la edad `x` (13 mesadas al año). Se calcula con la tabla de mortalidad y una tasa técnica real.
- **Tabla de mortalidad:** **RV08** (rentistas válidos, por sexo, experiencia 2005–2008), adoptada por la **Resolución 1555 de 2010** de la Superfinanciera y obligatoria desde el 1 de octubre de 2010. ⚠️ Verificar si fue reemplazada por una tabla más reciente.
- **Tasa técnica:** ❓ supuesto de partida del **4 % real anual**, con análisis de sensibilidad. Buscar la tasa que usan la Superfinanciera y las aseguradoras para renta vitalicia.
- **Simplificaciones declaradas:** no se modela la pensión de sobrevivientes (beneficiarios), la invalidez ni el auxilio funerario. El factor sin beneficiarios **sobreestima** la mesada; se documentará el sesgo.

---

## 4. Régimen de Prima Media (RPM, Colpensiones)

Se implementa como **referencia de comparación** (beneficio definido, sin cuenta individual).

| Concepto | Valor | Norma | Estado |
|---|---|---|---|
| Edad | Hombres 62, mujeres 57 | Art. 33 Ley 100 (Ley 797 de 2003) | ✅ |
| Semanas, hombres | 1.300 | Ídem | ✅ |
| Semanas, mujeres | 1.250 en 2026, bajando 25 por año hasta 1.000 en 2036 | Sentencia C-197 de 2023 | ⚠️ |
| IBL | Promedio de los salarios de los últimos 10 años, actualizados por IPC (o de toda la vida laboral si es más favorable y tiene ≥ 1.250 semanas) | Art. 21 Ley 100 | ⚠️ |
| Tasa de reemplazo | `r = 65,50 − 0,50 · s`, con `s = IBL / SMMLV`; +1,5 puntos por cada 50 semanas adicionales al mínimo; máximo entre 80 % y 70,5 % | Art. 34 Ley 100 (Ley 797 de 2003) | ⚠️ |
| Pensión mínima / máxima | 1 SMMLV / 25 SMMLV | | ⚠️ |

**Semanas de las mujeres en el RPM** (según la tabla publicada por Porvenir y la prensa):

| Año | 2026 | 2027 | 2028 | 2029 | 2030 | 2031 | 2032 | 2033 | 2034 | 2035 | 2036+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Semanas | 1.250 | 1.225 | 1.200 | 1.175 | 1.150 | 1.125 | 1.100 | 1.075 | 1.050 | 1.025 | 1.000 |

⚠️ Un artículo de Portafolio menciona 1.275 para 2026. Confirmar con Colpensiones.

---

## 5. Multifondos (RAIS)

| Fondo | Perfil |
|---|---|
| Mayor riesgo | Mayor proporción de renta variable; para afiliados jóvenes |
| Moderado | Balanceado |
| Conservador | Renta fija; para afiliados cercanos al retiro |
| Retiro programado | Para pensionados en esa modalidad |

- **Asignación por defecto:** el Decreto 959 de 2018 (que modifica el Decreto 2555 de 2010) asigna a quienes no eligen fondo entre **mayor riesgo y moderado según sexo y edad**, con **convergencia gradual** hacia el moderado y luego hacia el conservador al acercarse a la edad de pensión.
- ❓ **Pendiente:** las tablas de porcentajes por edad están como imagen en la norma compilada. Leerlas directamente en el art. 2.6.11.1.6 y siguientes del Decreto 2555 de 2010 (Función Pública / SUIN-Juriscol).
- **Fuente de datos de rentabilidad:** valor de unidad de los fondos de pensiones obligatorias, publicado por la Superfinanciera (se trabaja en el paso 2 del plan). El esquema multifondos opera desde ~2011, lo que limita la historia disponible.

---

## 6. Reforma pensional (Ley 2381 de 2024): escenario B

| Pilar | Descripción | Estado |
|---|---|---|
| **Solidario** | Renta básica solidaria para adultos mayores en pobreza o vulnerabilidad | ⚠️ |
| **Semicontributivo** | Beneficio para quienes cotizaron pero no alcanzan las semanas | ⚠️ |
| **Contributivo, componente de prima media** | Colpensiones recibe las cotizaciones sobre el IBC **hasta 2,3 SMMLV** | ✅ (umbral, cartilla MinSalud) |
| **Contributivo, componente complementario de ahorro individual** | AFP sobre la porción del IBC **entre 2,3 y 25 SMMLV** | ✅ (umbral) |
| **Ahorro voluntario** | Voluntario | ⚠️ |

- **Régimen de transición:** en el texto aprobado aplica a quienes tengan **900 semanas (hombres) o 750 semanas (mujeres)** a la fecha de entrada en vigencia, que siguen con las reglas anteriores. ❓ Fue uno de los artículos devueltos a la Cámara por la Sentencia C-264 de 2026, así que los umbrales pueden cambiar.
- ❓ **Pendiente:** fórmula de liquidación de la mesada del componente de prima media, reparto de la cotización entre componentes, Fondo de Ahorro del Pilar Contributivo y requisitos del pilar semicontributivo. Leer el texto oficial de la ley (Función Pública / Secretaría del Senado) una vez se cierre el trámite.

**Implicación para el modelo:** para el escenario B, el IBC de cada mes se parte en dos: la porción hasta 2,3 SMMLV va a un componente de beneficio definido (similar al RPM) y el excedente a la cuenta individual. Por esa estructura, la reforma afecta sobre todo a quienes ganan más de 2,3 SMMLV.

---

## 7. Supuestos económicos (no normativos)

Van en `config/parametros.yaml`, bajo `supuestos`, y se someten a análisis de sensibilidad:

| Supuesto | Valor inicial | Fundamento |
|---|---|---|
| Inflación de largo plazo | 3 % anual | Meta del Banco de la República |
| Crecimiento real del SMMLV | 1 % anual | ❓ Calibrar con la serie histórica |
| Crecimiento real de productividad (salarios) | 1 % anual | ❓ Calibrar con la GEIH |
| Tasa técnica para anualidades | 4 % real anual | ❓ |
| Semanas por mes | 4,2857 (30 / 7) | Convención de Colpensiones (⚠️) |

---

## 8. Alcance: qué queda fuera

1. Bonos pensionales y traslados entre regímenes.
2. Pensión de invalidez y de sobrevivientes.
3. Regímenes especiales (Fuerzas Militares, magisterio, etc.) y pensiones de alto riesgo.
4. BEPS (Beneficios Económicos Periódicos).
5. Impuestos y descuentos de salud sobre la mesada.

Todas estas exclusiones se declaran en la pestaña de metodología de la app.

---

## 9. Checklist de verificación (pasar de ⚠️/❓ a ✅)

- [ ] Sentencia C-264 de 2026: texto, artículos devueltos y resultado del trámite en la Cámara.
- [ ] Texto oficial de la Ley 2381 de 2024: fórmula del componente de prima media y reparto de la cotización.
- [ ] Decreto 2555 de 2010, art. 2.6.11.1.6 y siguientes: tablas de asignación por defecto de multifondos.
- [ ] Resolución 1555 de 2010: descargar la tabla RV08 y confirmar que sigue vigente.
- [ ] Semanas de las mujeres (RAIS 2026: 1.135; RPM 2026: 1.250): confirmar con la Superfinanciera / Colpensiones.
- [ ] SMMLV 2026: confirmar la vigencia del Decreto 0159 de 2026.
- [ ] Art. 34 Ley 100: texto exacto de la tasa de reemplazo del RPM.
- [ ] Art. 27 Ley 100: escala exacta del FSP.
- [ ] Tasa técnica para renta vitalicia.

---

## Fuentes consultadas

- Asofondos, [Corte Constitucional suspende entrada en vigencia de la reforma pensional](https://asofondos.org.co/comunicados/corte-constitucional-suspende-entrada-vigencia-reforma-pensional/)
- Vanguardia, [Reforma pensional: esto es lo que cambiaría desde abril de 2027](https://www.vanguardia.com/colombia/2026/08/26/reforma-pensional-esto-es-lo-que-cambiaria-para-usted-desde-abril-de-2027/)
- Semana, [Reforma pensional: sobrevivió al procedimiento, pero la batalla jurídica continúa](https://www.semana.com/economia/empresas/articulo/reforma-pensional-sobrevivio-al-procedimiento-pero-la-batalla-juridica-continua/202600/)
- Softland, [Reforma pensional en Colombia 2026](https://softland.com/co/reforma-pensional-en-colombia-2026/)
- MinSalud, [ABC reforma pensional Ley 2381 de 2024](https://minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/VP/DOA/abece-reforma-pensional-ley-2381-de-2024.pdf)
- Superfinanciera, [Concepto 2021-0126207 (reparto de la cotización)](https://normativa.colpensiones.gov.co/compilacion/docs/concepto_superfinanciera_0126207_2021.htm)
- Superfinanciera, [Resolución 1555 de 2010 (tablas RV08)](https://normativa.colpensiones.gov.co/compilacion/docs/resolucion_superfinanciera_1555_2010.htm)
- Colpensiones (normativa), [Decreto 959 de 2018 (multifondos)](https://normativa.colpensiones.gov.co/compilacion/docs/decreto_0959_2018.htm)
- Corte Constitucional, [Sentencia C-054 de 2024](https://ambitojuridico.com/sites/default/files/2024-05/Sent-C-054-24.pdf)
- La Nota Económica / Porvenir, [Cambio de semanas para mujeres desde 2026](https://lanotaeconomica.com.co/movidas-empresarial/porvenir-explica-como-cambiaran-los-requisitos-de-semanas-para-pension-de-vejez-de-mujeres-a-partir-de-2026/)
- El Heraldo, [Entra en vigor reducción de semanas para mujeres desde 2026](https://www.elheraldo.co/colombia/2026/01/02/entra-en-vigor-reduccion-de-semanas-para-la-pension-de-mujeres-desde-2026-asi-funcionara/)
- Siempre al Día, [Salario mínimo 2026](https://siemprealdia.co/colombia/derecho-laboral/salario-minimo-2026/)
