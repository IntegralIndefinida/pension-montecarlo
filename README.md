# Simulador estocástico de pensiones (Monte Carlo), Colombia

> 🚧 En construcción. Pasos 1 a 6 de 10: marco normativo, datos, rentabilidades, salarios, densidad de cotización y reglas de pensión.

¿Cuál es la **distribución** de la pensión futura de un afiliado al sistema pensional colombiano, considerando la incertidumbre en las rentabilidades, los salarios y la densidad de cotización?

## Uso

```bash
pip install -e ".[dev]"
python -m pension_mc.data      # descarga y procesa los insumos (requiere pdftotext y microdatos GEIH vía dane-data)
pytest
```

## Estado

- [x] Marco normativo: [`docs/marco_normativo.md`](docs/marco_normativo.md) y parámetros en [`config/parametros.yaml`](config/parametros.yaml)
- [x] Datos: `python -m pension_mc.data` ([`docs/datos.md`](docs/datos.md)) y análisis exploratorio en [`notebooks/01_eda.ipynb`](notebooks/01_eda.ipynb)
- [x] Rentabilidades: `pension_mc.returns` ([`docs/metodologia.md`](docs/metodologia.md#1-rentabilidades)) y validación en [`notebooks/02_rentabilidades.ipynb`](notebooks/02_rentabilidades.ipynb)
- [x] Perfil salarial: `pension_mc.wages` ([`docs/metodologia.md`](docs/metodologia.md#2-salarios)) y validación en [`notebooks/03_salarios.ipynb`](notebooks/03_salarios.ipynb)
- [x] Densidad de cotización: `pension_mc.contributions` ([`docs/metodologia.md`](docs/metodologia.md#3-densidad-de-cotización)) y calibración en [`notebooks/04_cotizacion.ipynb`](notebooks/04_cotizacion.ipynb)
- [x] Acumulación, desacumulación y regímenes (AFP y Colpensiones): `pension_mc.accumulation`, `decumulation` y `regimes` ([`docs/metodologia.md`](docs/metodologia.md#4-acumulación-mesada-y-reglas-de-pensión)) y ejemplos en [`notebooks/05_pension.ipynb`](notebooks/05_pension.ipynb)
- [ ] Motor de simulación y sensibilidad
- [ ] Validación y CI
- [ ] App Streamlit

*Este proyecto es un ejercicio académico y no constituye asesoría financiera ni pensional.*
