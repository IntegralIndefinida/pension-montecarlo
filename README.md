# Simulador estocástico de pensiones (Monte Carlo), Colombia

> 🚧 En construcción. Pasos 1 y 2 de 10: marco normativo y datos.

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
- [ ] Rentabilidades
- [ ] Perfil salarial
- [ ] Densidad de cotización
- [ ] Acumulación, desacumulación y regímenes
- [ ] Motor de simulación y sensibilidad
- [ ] Validación y CI
- [ ] App Streamlit

*Este proyecto es un ejercicio académico y no constituye asesoría financiera ni pensional.*
