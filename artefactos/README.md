# Artefactos del modelo

Lo que el motor de simulación necesita en ejecución. Se versionan para que las pruebas, la integración continua y la app funcionen sin descargar la GEIH.

| Archivo | Contenido | Se regenera con |
|---|---|---|
| `modelo_salarial.json` | Tobit heterocedástico y persistencia (σα, σε, ρ) por tipo | `pension_mc.wages.estimar()` |
| `modelo_cotizacion.json` | Tasas por edad y tipo, y calibración (μ₀, κ, β, ρ_η) | `pension_mc.contributions.estimar()` |
| `rentabilidad_mensual.parquet` | Rentabilidades reales mensuales de los fondos de pensiones obligatorias | `python -m pension_mc.data --solo ipc rentabilidades` |
| `mortalidad_rv08.parquet` | Tablas de mortalidad de rentistas RV08 | `python -m pension_mc.data --solo mortalidad` |

Las estimaciones necesitan los microdatos de la GEIH (vía `dane-data`) y el pipeline de `docs/datos.md`.
