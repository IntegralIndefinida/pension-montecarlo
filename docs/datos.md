# Datos

Todo se descarga y procesa con un solo comando:

```bash
python -m pension_mc.data                 # todo (descargas incrementales)
python -m pension_mc.data --solo ipc      # un paso
python -m pension_mc.data --force         # repetir descargas
```

Los archivos crudos quedan en `data/raw/` y los procesados en `data/processed/` (Parquet). Ninguno de los dos se versiona.

## Fuentes

| Insumo | Fuente | Acceso | Cobertura |
|---|---|---|---|
| Valor de unidad de los fondos de pensiones obligatorias | Superintendencia Financiera | API de datos.gov.co, dataset [`uawh-cjvi`](https://www.datos.gov.co/Hacienda-y-Cr-dito-P-blico/Fondo-de-Pensiones-Obligatorias-y-Cesant-as-C-P-L-/uawh-cjvi) | Diario, 1-ene-2016 en adelante; 4 AFP |
| IPC, serie de empalme (base dic. 2018 = 100) | DANE | Anexo `anex-IPC-Indices-<mes><año>.xlsx`, ubicado automáticamente en la [página del IPC](https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc) | Mensual, 2003 en adelante |
| Salario mínimo | Decretos anuales | Serie de `dane_data.referencias.SMLV`, contrastada con `config/parametros.yaml` | Anual, 1992–2026 |
| Tablas de mortalidad RV08 | Superfinanciera, Resolución 1555 de 2010 | PDF publicado por [Fasecolda](https://www.fasecolda.com/wp-content/uploads/res-1555-2010.pdf), leído con `pdftotext` | Edades 15–110, por sexo |
| GEIH | DANE | Librería [`dane-data`](https://github.com/IntegralIndefinida/DANE-data) (los microdatos deben estar descargados) | 2022–2025 por defecto (marco 2018) |

**Dependencia del sistema:** `pdftotext` (paquete `poppler` en Arch, `poppler-utils` en Debian/Ubuntu).

## Archivos procesados

| Archivo | Una fila por | Columnas |
|---|---|---|
| `valor_unidad_diario.parquet` | fecha × AFP × fondo | `fecha`, `afp`, `fondo`, `valor_unidad` |
| `rentabilidad_mensual.parquet` | mes × AFP × fondo | `fecha` (fin de mes), `afp`, `fondo`, `valor_unidad`, `r_nominal`, `r_real` |
| `ipc_mensual.parquet` | mes | `fecha`, `ipc`, `inflacion_mensual`, `inflacion_anual` |
| `smmlv_anual.parquet` | año | `anio`, `smmlv`, `inflacion_dic_anterior`, `var_nominal`, `var_real` |
| `mortalidad_rv08.parquet` | sexo × edad | `sexo`, `edad`, `lx`, `dx`, `qx`, `ex` |
| `geih_pensiones.parquet` | persona-mes (15–70 años) | variables armonizadas de `dane-data` + `estado_pension`, `cotiza`, `independiente`, `antiguedad_empleo` |

## Decisiones de procesamiento

1. **Rentabilidades.** Se toma el valor de unidad del último día de cada mes. La serie es diaria e incluye fines de semana, así que **se descarta el mes en curso** si no tiene dato del último día. La rentabilidad real es `(1 + r_nominal) / (1 + inflación mensual) − 1`. Los fondos de cesantías se excluyen. El fondo "alternativo" solo existe en Skandia.
2. **IPC.** Se usa la serie de empalme, y la inflación anual es la variación a 12 meses.
3. **SMMLV.** Su crecimiento real descuenta la inflación de diciembre del año anterior, que es la referencia del aumento. El pipeline falla si la serie de `dane-data` no coincide con `config/parametros.yaml`.
4. **RV08.** Se valida que `l(x+1) = l(x) − d(x)`, que `q(x) = d(x)/l(x)` y que la tabla cierre en `q(110) = 1`. Si algo falla, el pipeline se detiene.
5. **GEIH.**
   - `cotiza` = 1 si la persona está ocupada y cotiza (P6920 = 1); 0 en cualquier otro caso, *incluidos desocupados e inactivos*. Su promedio por edad es la probabilidad mensual de aportar.
   - `estado_pension` distingue Cotiza / No cotiza / Pensionado (entre ocupados) y No ocupado.
   - `independiente` marca a cuentapropistas y patrones, que cotizan sobre el 40 % del ingreso.
   - `antiguedad_empleo` (P6426) son los meses continuos en el empleo actual de los ocupados. Para un cotizante es una cota inferior de cuánto lleva cotizando sin interrupción.
   - Las etiquetas de posición ocupacional (P6430) del cuestionario de 2022 en adelante (7 = jornalero, 8 = otro) vienen corregidas desde `dane-data` (commit `cf5fcd1`).

## Limitaciones

- **Historia corta de rentabilidades:** los datos abiertos empiezan en 2016 (10,7 años), aunque el esquema multifondos existe desde ~2011. Para más historia habría que extraerla del tablero Power BI de la Superfinanciera.
- **La GEIH es transversal:** no sigue a las mismas personas en el tiempo, así que la persistencia en la cotización no se observa directamente (ver el paso 5 del plan).
- **Ingreso laboral de la GEIH (`INGLABO`):** es el ingreso declarado, no el IBC; para cotizantes dependientes es una buena aproximación.
