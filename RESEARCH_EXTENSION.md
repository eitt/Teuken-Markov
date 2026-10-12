# Ampliación histórica y drivers observados

La extensión permite evaluar más años y contrastar exposición a petróleo y variabilidad ENSO. Los análisis se ejecutan por separado y conservan los resultados originales en `outputs/main/`. No se empalman las etiquetas de GLI con DPI ni se asigna una dirección izquierda/derecha a los choques.

## Ejecutar

Desde la raíz del proyecto, con las dependencias de `requirements.txt`:

```bash
python run_extensions.py --download --run
```

Con los datos incluidos, sin acceso a Internet:

```bash
python run_extensions.py --offline --run
python -m unittest discover -s tests -v
```

Las opciones `--start-year 1985`, `--history-start-year 1956` y `--history-role hog` son predeterminadas. `--history-role leader` ejecuta una sensibilidad con el líder político de GLI; no rellena HOG faltante mediante otra función ejecutiva. La actualización de datos requiere `--download --refresh` y puede cambiar resultados. La CLI original `run.py` y sus seis modelos mantienen su comportamiento.

## Qué se amplía

| Análisis | Fuente / fechas | Evaluación de esta ejecución |
|---|---|---|
| DPI principal | Enero de 1975–2023 | Orígenes 1985–2022; 1.007 pares y 93 cambios |
| DPI anterior a 2000 | Mismas etiquetas, sin añadir años a la fuente | 403 pares adicionales y 33 cambios |
| DPI desde 2000 | Ventana original, entrenamiento desde 1975 | 604 pares y 60 cambios |
| GLI HOG histórico | Fuente diciembre de 1945–2020 | Orígenes alineados 1956–2020; 1.677 pares y 167 cambios |

La fuente DPI ya proporcionaba 49 años: `--start-year` determina dónde comienza la evaluación, no dónde comienza todo el entrenamiento. En 1985 el entrenamiento contiene 200 pares y sólo 15 cambios; los modelos con drivers adicionales deben interpretarse como exploratorios.

GLI observa el 31 de diciembre y DPI principalmente el 1 de enero. Se conserva el año de fuente y se etiqueta el corte GLI de diciembre de Y con enero de Y+1: los rótulos alineados 1946–2021 **no añaden observaciones posteriores a diciembre de 2020**. Son fechas adyacentes, no una identidad garantizada: una investidura del 1 de enero, como en Brasil, puede modificar al Ejecutivo entre esos cortes.

GLI HOG tiene 29 series nacionales y 27 países con alguna ideología clasificable; Bahamas y Belice carecen de HOG clasificable. No cubre Antigua y Barbuda, Dominica, Granada, San Cristóbal y Nieves, Santa Lucía y San Vicente y las Granadinas. EIEC, elecciones y años exactos de mandato no están disponibles en GLI y permanecen faltantes. Las duraciones históricas cuentan rachas de cortes anuales idénticos, no fechas exactas de investidura.

Entre 1975 y 2021, GLI HOG y DPI tienen 1.019 observaciones conjuntamente clasificadas y 230 desacuerdos (**22,57 %**). No se declara una fuente como verdad ni se modifican manualmente las clases para alcanzar consenso. GLI utiliza DPI entre sus materiales: esta comparación evalúa sensibilidad de medición y no constituye validación completamente independiente.

## Drivers y orden temporal

Para el origen político enero de t y desenlace enero de t+1:

| Variable | Fuente y medición | Año utilizado |
|---|---|---|
| Precio del petróleo | Pink Sheet: cambio porcentual de la media anual | t−1 |
| Exposición importadora | WDI `TM.VAL.FUEL.ZS.UN`: combustibles / importaciones de mercancías | t−2 |
| Exposición exportadora | WDI `TX.VAL.FUEL.ZS.UN`: combustibles / exportaciones de mercancías | t−2 |
| ENSO | NOAA ONI: media de 11 ventanas trimestrales DJF–OND | t−1 |
| Exposición agrícola | WDI `NV.AGR.TOTL.ZS`: agricultura, silvicultura y pesca / PIB | t−2 |

Las interacciones multiplican el índice o cambio porcentual por la participación nacional dividida entre 100. Se mantienen efectos principales e interacciones en los bloques petrolero y ENSO. Los porcentajes importador y exportador tienen denominadores distintos: **no se restan ni se denominan exposición neta petrolera**. Combustibles incluye productos distintos del petróleo. La exposición agrícola es un proxy económico general y no representa una teleconexión física de ENSO estimada para cada país.

El núcleo reducido utiliza crecimiento, inflación, duración de la clase, competitividad, país y estado inicial. Se comparan persistencia, Markov y cuatro especificaciones L2: núcleo, núcleo+petróleo, núcleo+ENSO y núcleo+ambos. El panel GLI temprano compara persistencia, Markov, duración y duración+red, sin imputar macroeconomía previa a 1960 dentro de esos predictores.

ONI mide **variabilidad climática**, no calentamiento antropogénico. No se cambian productos ONI/RONI por tramos. NDJ de Y contiene enero de Y+1 y se excluye para no incluir meses posteriores al año asignado. La media de DJF–OND es una agregación de 11 ventanas solapadas definida aquí, no 11 meses independientes ni un índice anual oficial de NOAA. La fuente conserva 1950–2025 completos; el año terminal 2026 incompleto se excluye.

Los rezagos ordenan fechas de los eventos, pero los indicadores económicos y climáticos contienen revisiones. Algunas publicaciones de diciembre llegan después de enero: no se reconstruyen los datos que estaban efectivamente disponibles en cada fecha histórica. Esta limitación se conserva en todos los resultados.

## Resultados de la extensión

Brier multiclase global: menor es mejor; comparaciones sobre los mismos 1.007 casos DPI.

| Modelo | Brier 1985–2022 |
|---|---:|
| Persistencia | 0,184707 |
| Markov | **0,171169** |
| Núcleo reducido | 0,172592 |
| Núcleo + petróleo | 0,173445 |
| Núcleo + ENSO | 0,173585 |
| Núcleo + petróleo + ENSO | 0,174484 |

Los nuevos drivers **no mejoran el Brier global** de esta ejecución frente a Markov. En 2000–2022, el modelo ENSO mejora ligeramente el núcleo reducido (0,183909 frente a 0,184250), pero continúa por encima de Markov (0,182862). No se atribuye significación estadística a diferencias sin un contraste apropiado. Los modelos reducidos aislados aciertan por argmax 2 de los 93 cambios de toda la ventana; el combinado acierta 2/93. En la ventana 2000–2022 ninguno acierta los 60 cambios. La exactitud global cercana al 91 % sigue dominada por permanencia.

En GLI HOG, Markov obtiene Brier 0,183308, duración 0,184468 y duración+red 0,186231. Ninguno acierta mediante argmax los 167 cambios evaluados. Las métricas de distintas fuentes no son directamente comparables como si tuvieran las mismas etiquetas, países y años.

`conditional_oil_scenarios.csv` contiene contrastes de un paso desde el corte observado de enero de 2023: cambio petrolero hipotético 0 %, −50 % y +50 %, con exposiciones nacionales y otros predictores fijos. Son probabilidades condicionadas al modelo ajustado; no predicciones categóricas de ganadores ni efectos causales de una crisis. No incluyen incertidumbre de parámetros. Los estados desconocidos no entran en la simulación.

## Otros drivers y límites del diseño

La implementación original ya incluye crecimiento mundial, alimentos y pandemia, con limitaciones por el reducido número de años de choque. Una dummy global de guerra o crisis no sustituye las diferencias de exposición nacional. Un choque observado durante el intervalo de pronóstico no debe introducirse retrospectivamente como información conocida antes de que ocurriera.

La guerra de Ucrania comienza en 2022. Con el esquema predictivo actual de rezago t−1 y DPI hasta enero de 2023, no hay un desenlace enero de 2024 para evaluar un origen enero de 2023 informado por los choques de 2022. Se podrían estudiar asociaciones explicativas contemporáneas con un diseño distinto, pero no presentarlas como predicciones desde enero de 2022.

Para extender después de 2023 se necesitan nuevas etiquetas políticas verificadas. Para analizar cambio climático, se necesitan temperatura/precipitación nacionales, extremos o impactos locales y una definición separada de tendencias y episodios. El archivo libre de Berkeley Earth examinado no proporcionó cobertura nacional hasta 2023; no se completó artificialmente. ENSO×agricultura queda como bloque exploratorio.

Los efectos fijos completos de año absorberían cualquier choque global común. Las interacciones con exposición nacional conservan variación entre países, pero no identifican por sí solas causalidad. Los choques pueden afectar al incumbente sin determinar qué orientación ideológica lo sustituye. Países autoritarios, elecciones competitivas y diferencias de medición requieren sensibilidades separadas.

## Archivos y reproducibilidad

- `outputs/extensions/dpi_drivers/`: métricas generales y por periodo, predicciones, cobertura y escenarios petroleros.
- `outputs/extensions/gli_hog/`: evaluación histórica separada; `gli_leader/` si se elige esa sensibilidad.
- `outputs/history/`: paneles GLI, ausencia/cobertura, comparaciones y desacuerdos por país.
- `data/raw/driver_exposures_manifest.json` y `climate_manifest.json`: fuentes, fecha, unidades y SHA256.

La copia DPI subida inicialmente a GitHub normalizó CRLF a LF. El loader acepta esa conversión **sólo si reconstruir CRLF reproduce exactamente el SHA256 original registrado**; cualquier celda o espacio modificado sigue causando error. `.gitattributes` protege las próximas descargas frente a nuevas conversiones de Git. No se desactiva la validación de contenido.

## Referencias y fuentes

- Herre, B. (2023). Identifying Ideologues: A Global Dataset on Political Leaders, 1945–2020. *British Journal of Political Science*, 53(2), 740–748. <https://doi.org/10.1017/S0007123422000217>. Datos y reglas: <https://github.com/bastianherre/global-leader-ideologies>.
- Campello, D., y Zucco, C. (2016). Presidential Success and the World Economy. *Journal of Politics*, 78(2), 589–602. <https://doi.org/10.1086/684749>.
- Cole, S., Healy, A., y Werker, E. (2012). Do voters demand responsive governments? Evidence from Indian disaster relief. *Journal of Development Economics*, 97(2), 167–181. <https://doi.org/10.1016/j.jdeveco.2011.05.005>.
- Cooperman, A. (2022). (Un)Natural Disasters: Electoral Cycles in Disaster Relief. *Comparative Political Studies*. <https://doi.org/10.1177/00104140211047410>.
- WDI: <https://data.worldbank.org/indicator/TX.VAL.FUEL.ZS.UN>, <https://data.worldbank.org/indicator/NV.AGR.TOTL.ZS>.
- NOAA: <https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt> y <https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/>.
