# Simulador estocástico de pensiones (Monte Carlo), Colombia

> 🚧 En construcción. Pasos 1 a 5 de 10: marco normativo, datos, rentabilidades, salarios y densidad de cotización.

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
- [ ] Acumulación, desacumulación y regímenes
- [ ] Motor de simulación y sensibilidad
- [ ] Validación y CI
- [ ] App Streamlit

*Este proyecto es un ejercicio académico y no constituye asesoría financiera ni pensional.*
