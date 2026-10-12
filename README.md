# Transiciones ideológicas del Ejecutivo en las Américas

Proyecto reproducible en Python para analizar cambios anuales entre izquierda, centro y derecha y explorar escenarios de evolución conjunta de los países. Combina instituciones políticas, indicadores económicos, precios internacionales y una red geográfica. Su objetivo es comparar probabilidades de transición y evaluar si la información de los vecinos mejora el desempeño frente a referencias simples.

La evaluación es retrospectiva y utiliza series públicas revisadas. Las simulaciones son trayectorias condicionadas a supuestos. El proyecto no identifica efectos causales, no ofrece predicciones ciertas y no constituye un sistema de pronóstico operativo con las versiones de datos disponibles en cada fecha histórica.

## Inicio rápido

Requiere **Python 3.10 o superior** con las dependencias compatibles de `requirements.txt`. Ejecute los comandos desde esta carpeta, donde se encuentran `run.py` y `requirements.txt`.

```bash
python -m pip install -r requirements.txt
python run.py --download --run --simulate
```

La ejecución entregada se probó con **Python 3.12**. Para instalar sus versiones exactas de dependencias, utilice `requirements-lock.txt`; ese archivo requiere **Python 3.11 o superior**. Con Python 3.10 use `requirements.txt`, que permite resolver versiones compatibles en lugar de imponer ese entorno fijado.

```bash
python -m pip install -r requirements-lock.txt
```

Para repetir el análisis con los archivos ya descargados y sin acceso a Internet:

```bash
python run.py --offline --run --simulate
```

Para descargar de nuevo las fuentes y reconstruir el análisis:

```bash
python run.py --download --refresh --run --simulate
```

También puede separar las etapas:

```bash
python run.py --download
python run.py --offline --run
python run.py --offline --simulate
```

`--download` obtiene las fuentes públicas y utiliza la caché cuando existe. `--refresh` solicita una nueva descarga y requiere `--download`; una versión nueva puede cambiar los resultados. `--offline` requiere una caché completa y no puede combinarse con `--download` o `--refresh`. `--run` prepara el panel y ejecuta la evaluación temporal. `--simulate` también prepara y evalúa los modelos antes de producir escenarios; no exige una ejecución previa con `--run`. Para las opciones concretas de la versión instalada:

```bash
python run.py --help
```

Las opciones de sensibilidad y simulación incluyen:

| Opción | Efecto | Valor predeterminado |
|---|---|---|
| `--land-only` | Excluye aristas marítimas | Red terrestre y marítima |
| `--competitive-only` | Restringe los orígenes y los estados iniciales simulados a `EIEC >= 6` | Sin ese filtro |
| `--start-year` | Primer año de origen de evaluación | `2000` |
| `--runs` | Trayectorias Monte Carlo por escenario | `500` |
| `--horizon` | Pasos anuales posteriores al estado inicial | `6` |
| `--seed` | Semilla de las simulaciones | `2026` |

Por ejemplo:

```bash
python run.py --offline --run --land-only
python run.py --offline --run --competitive-only
python run.py --offline --simulate --runs 1000 --horizon 8 --seed 2026
```

Conserve los archivos originales y su registro de hashes si necesita reproducir exactamente una ejecución. Reproducir el código con una descarga más reciente no equivale a reproducir la misma versión de los datos.

## Cobertura y significado de la variable política

La fuente principal es **Database of Political Institutions, DPI 2023**, publicada en 2026 y con observaciones de 1975 a 2023. DPI registra la situación institucional principalmente al **1 de enero** de cada año. La orientación económica del partido del jefe del Ejecutivo se clasifica como derecha, centro o izquierda. Esta variable no mide toda la ideología personal del dirigente ni permite equiparar automáticamente izquierda/derecha con democracia/autocracia.

El universo seleccionado comprende **31 países soberanos de las Américas**: Argentina, Bahamas, Barbados, Belice, Bolivia, Brasil, Canadá, Chile, Colombia, Costa Rica, Cuba, Ecuador, El Salvador, Estados Unidos, Granada, Guatemala, Guyana, Haití, Honduras, Jamaica, México, Nicaragua, Panamá, Paraguay, Perú, República Dominicana, Santa Lucía, Surinam, Trinidad y Tobago, Uruguay y Venezuela.

No cubre los 35 países soberanos del continente: **Antigua y Barbuda, Dominica, San Cristóbal y Nieves, y San Vicente y las Granadinas** no están representados en la fuente DPI utilizada. La presencia de un país en el universo tampoco garantiza observaciones válidas en todos los años. La muestra de transiciones depende de que existan estados políticos consecutivos utilizables. Los códigos desconocidos o no aplicables no se reinterpretan como centro.

Antes de preparar las características se excluyen registros políticos de países que no pertenecían al sistema COW en el **1 de enero** de ese año, según las fechas de `States2024`. Es un criterio operativo de elegibilidad para esta fuente de red, **no una fecha exacta de soberanía ni una redefinición de independencia**. La ejecución registra cuántas filas excluye.

El **Global Leader Ideology Dataset, GLI**, de Herre, proporciona una referencia adicional de 1945 a 2020 para contrastar clasificaciones. Su unidad y sus reglas difieren de DPI: clasifica al líder, mientras DPI utiliza la orientación del partido ejecutivo. GLI no amplía por sí solo la serie principal hasta años posteriores ni elimina las discrepancias de medición.

## Fuentes y trazabilidad

| Fuente | Función en el proyecto | Alcance y cautela |
|---|---|---|
| DPI 2023 | Estados ideológicos consecutivos del Ejecutivo | 1975–2023; observaciones principalmente al 1 de enero |
| World Development Indicators, Banco Mundial | Crecimiento del PIB, inflación, apertura comercial, peso de las importaciones de combustibles y turismo | Series anuales revisadas; cobertura desigual entre países e indicadores |
| Correlates of War, Direct Contiguity v3.2 | Aristas terrestres y marítimas | Grafo de `t-1` hasta el final de la fuente en 2016; después conserva esa última topología |
| Banco Mundial, Pink Sheet | Precios mensuales históricos de petróleo e índice de alimentos; el libro también contiene trigo | La especificación principal utiliza petróleo y alimentos, no trigo como predictor separado |
| GLI, Herre | Referencia opcional para medición ideológica | 1945–2020; no reemplaza automáticamente DPI |

Los archivos de origen se conservan en `data/raw/`. El registro de descargas incluye la procedencia y los hashes de los archivos utilizados. Consulte [SOURCES.md](SOURCES.md) para los enlaces, las referencias y las diferencias de medición.

La red representa **proximidad geográfica**, no contactos diplomáticos observados ni flujos comerciales bilaterales. La apertura comercial de WDI es una característica de cada país; no constituye una arista comercial. Para un año de origen `t`, el grafo utiliza `min(t-1, 2016)`: COW registra relaciones presentes durante alguna parte del año, por lo que se retrasa la topología un año para que sea anterior al origen político del 1 de enero. Desde el origen de 2017 se conserva la estructura de 2016. Esa continuidad es un supuesto ante el final de la fuente, no una medición de la topología de 2023 o del futuro.

## Orden temporal del análisis

Para cada país y año de origen `t`, el desenlace es la clase política al **1 de enero de `t+1`**, condicionada a la clase al **1 de enero de `t`**. Los indicadores económicos corresponden al año **`t-1`** y la exposición a vecinos utiliza sus estados al **1 de enero de `t`**, sobre la topología de `min(t-1, 2016)`.

Por ejemplo, para evaluar la transición del 1 de enero de 2010 al 1 de enero de 2011 se utilizan la orientación política inicial de 2010, los estados iniciales de los vecinos en 2010 y la información económica de 2009. Una elección celebrada durante 2010 puede reflejarse en el estado de 2011.

Los rezagos evitan utilizar deliberadamente indicadores del año posterior en los predictores. Sin embargo, las series macroeconómicas actuales contienen revisiones y pueden haber sido publicadas después de la fecha de origen. **El proyecto no reconstruye las publicaciones disponibles en tiempo real en 2010 ni en ningún otro año.** Esta distinción limita la interpretación de su desempeño como pronóstico histórico realizable.

La evaluación recorre los años de origen **2000–2022**, con entrenamiento expansivo: en cada paso sólo entran transiciones de años de origen anteriores, desde el inicio de la muestra utilizable en 1975. Las etiquetas de entrenamiento deben haber ocurrido antes o en la fecha de origen evaluada. La última transición observable termina el **1 de enero de 2023**. No se realiza una partición aleatoria que mezcle el futuro con el pasado.

## Modelos y evaluación

El proyecto compara referencias simples con modelos de regresión logística con penalización **L2**, implementados con `scikit-learn`. Todos deben producir probabilidades para las mismas clases y evaluarse sobre observaciones comparables.

| Modelo | Información principal |
|---|---|
| Persistencia | Mantener la clase política inicial |
| Markov | Probabilidades históricas de transición entre clases |
| Doméstico | Estado inicial e indicadores del país |
| Red | Información doméstica y composición ideológica de los vecinos |
| Choques | Información doméstica y variables internacionales rezagadas |
| Ambos | Información doméstica, vecinos y choques |

La referencia Markov utiliza suavizado de Laplace, sumando uno a cada celda de la matriz de transiciones calculada sólo con el entrenamiento. Los modelos logísticos incluyen el país y el estado inicial como variables categóricas; la especificación doméstica añade **duración del estado ideológico observado**, `state_duration`, y competitividad electoral a los indicadores económicos. Esa duración cuenta años consecutivos con la misma clasificación: no es la permanencia personal del líder (`yrsoffc`). Se reinicia tras un cambio o una interrupción de la serie, y está limitada por el comienzo de las observaciones. Un cambio de líder que conserve la clase ideológica puede prolongar la misma racha.

Por incorporar duración, el estado efectivo de los modelos ampliados contiene memoria. Puede interpretarse como una extensión de Markov con estado ampliado o duración, cercana al planteamiento de modelos semi-Markov; no es una cadena de primer orden definida únicamente por izquierda/centro/derecha. La especificación de choques utiliza crecimiento mundial, cambios de precios de petróleo y alimentos, COVID-19 rezagado e interacciones con exposición comercial, importaciones de combustibles y turismo.

La comparación utiliza **Brier multiclase**, **log loss** y **calibración**. Las dos primeras métricas valoran las probabilidades, no sólo la clase más probable; valores menores indican mejor desempeño. El Brier se calcula como la media de la suma, sobre las tres clases, de los errores cuadrados de probabilidad; su escala es de 0 a 2. La calibración permite revisar si una probabilidad anunciada guarda relación con la frecuencia observada del evento.

La persistencia asigna probabilidad uno al estado inicial y cero a los demás. Su log loss sería infinito cuando existe alternancia. Para comparar numéricamente, la salida `log_loss_clipped` trunca la probabilidad del resultado observado por debajo de `1e-12` y registra el número de resultados con probabilidad cero. Esa convención debe acompañar cualquier cifra publicada. La imputación de covariables numéricas y su estandarización se ajustan dentro de cada entrenamiento; no rellenan ni reclasifican las etiquetas políticas.

Se examina además el subconjunto en el que realmente cambió la clase política. Este grupo se identifica **después de obtener las predicciones**, para diagnosticar cómo funcionan los modelos en transiciones menos frecuentes. El cambio futuro observado no puede utilizarse para decidir qué modelo aplicar ni como predictor. Un buen resultado general puede estar dominado por la persistencia y debe contrastarse con este diagnóstico.

Los resultados deben leerse junto con la cobertura, la frecuencia de cada clase y el número de cambios. La comparación entre modelos no establece que las diferencias sean estadísticamente significativas ni que el mejor modelo observado se mantenga como el mejor en otros periodos. El archivo de coeficientes procede del ajuste final con **todo el panel**, separado de los ajustes usados para evaluar cada año. Sus coeficientes describen ese modelo regularizado y no son efectos causales.

## COVID-19, Ucrania y precios internacionales

La información sobre un acontecimiento no se utiliza antes de su inicio. En particular, el indicador rezagado de COVID-19 se activa en los años de origen 2021 y 2022. No se asigna conocimiento de la pandemia a una predicción situada al 1 de enero de 2020. Cuando ese indicador aparece por primera vez en la evaluación, el entrenamiento previo aún no contiene casos con el indicador activo: no puede haber aprendido su asociación hasta que esas observaciones entren posteriormente en el entrenamiento.

La invasión a gran escala de Ucrania comenzó en febrero de 2022, mientras la última etiqueta DPI termina el 1 de enero de 2023. Con los rezagos del proyecto y años de origen que terminan en 2022, un indicador rezagado de la invasión sería cero en todo el panel observable. Por ello **Ucrania se excluye de las variables estimadas**. No existe un coeficiente aprendido de la invasión sobre las transiciones políticas. Una perturbación de precios asociada a Ucrania aparece únicamente como supuesto de escenario y no como efecto estimado de la guerra sobre los gobiernos americanos.

Los movimientos históricos del petróleo y alimentos permiten representar presiones internacionales observadas. Sus cambios también responden a oferta, demanda y otros acontecimientos. El libro de origen contiene asimismo trigo, que no entra como predictor separado en la especificación principal. Una asociación con una transición política no identifica cuál de esas causas actuó. Los escenarios relacionados con guerras o crisis futuras son supuestos explícitos sobre esas presiones; no estimaciones causales de los acontecimientos.

## Qué significa la simulación

Cada país es un nodo con un estado político. Las simulaciones comienzan en el último estado DPI observado, **enero de 2023**; no inicializan los gobiernos actuales de 2026. Sólo entran países con estado válido en esa fecha y elegibles según los filtros de la ejecución. En cada paso anual todos los países se actualizan **simultáneamente**, utilizando los estados del paso anterior. Se calculan probabilidades condicionadas al estado previo, al entorno y a las variables del escenario; después se muestrea un nuevo estado.

El modelo de simulación es el ajuste final `network_shocks`, entrenado con todo el panel observable. La topología de 2016 y las covariables nacionales se mantienen fijas. La duración ideológica aumenta si se mantiene la clase y vuelve a uno si cambia; la composición de vecinos se recalcula a partir de los estados simulados. El crecimiento mundial permanece en su valor base, salvo durante la perturbación de recesión. Los cambios de precios se fijan en cero y COVID-19 en cero, excepto los cambios de precios expresamente impuestos por el escenario.

| Escenario del código | Supuesto durante los dos primeros pasos | A partir del tercer paso |
|---|---|---|
| `condiciones_constantes` | Crecimiento mundial en su valor base; variación de petróleo y alimentos igual a cero | Mantiene la misma referencia |
| `recesion_hipotetica` | Crecimiento mundial anual de **−2 %**; variación de precios igual a cero | Crecimiento mundial vuelve al valor base |
| `energia_alimentos_hipotetico` | Variación anual de petróleo **+50 %** y de alimentos **+20 %**; crecimiento mundial en su valor base | Variación de ambos precios vuelve a cero |

Son tasas y condiciones impuestas, no perturbaciones estimadas de una guerra específica. El crecimiento doméstico tampoco cambia automáticamente cuando se modifica el crecimiento mundial. Con el horizonte predeterminado de seis pasos, los años posteriores al estado inicial son 2024–2029.

Puede describirse como un **autómata probabilístico en una red**. No es el Juego de la Vida literal: no usa sus reglas deterministas de nacimiento y supervivencia. Tampoco representa las decisiones de cada votante ni un mecanismo demostrado de imitación entre gobiernos.

La actualización es anual y agregada. **No se activa únicamente en años electorales**, porque no se conoce aquí el calendario futuro completo ni todos los mecanismos de sustitución del Ejecutivo. Un cambio simulado entre dos años no equivale necesariamente a una elección prevista. Los resultados dependen de los supuestos, del modelo y del muestreo. Las bandas de percentiles 5–95 muestran dispersión Monte Carlo condicionada a los parámetros ajustados; no incorporan incertidumbre de parámetros, de medición ni del calendario político.

No interprete una trayectoria particular como el futuro más probable ni una frecuencia de simulación como una certeza electoral. El modelo anual debe revisarse antes de utilizarlo para preguntas sobre elecciones concretas, golpes de Estado, cambios de coalición o continuidad presidencial.

## Archivos del proyecto y salidas

| Archivo | Responsabilidad |
|---|---|
| `run.py` | Punto de entrada |
| `src/americas_markov/cli.py` | Opciones, etapas y guardado de salidas |
| `src/americas_markov/data.py` | Descargas, caché, hashes y lectura de DPI/WDI/Pink Sheet |
| `src/americas_markov/network.py` | Contigüidad COW y fechas de pertenencia estatal |
| `src/americas_markov/features.py` | Rezagos, duración ideológica y características vecinales |
| `src/americas_markov/models.py` | Referencias, regresiones y evaluación expansiva |
| `src/americas_markov/simulation.py` | Tres escenarios y actualización simultánea |
| `src/americas_markov/reporting.py` | Gráficos y resumen de ejecución |
| `tests/test_core.py` | Verificaciones del núcleo |

La ejecución principal escribe en **`outputs/main/`**. `--land-only` utiliza `outputs/land_only/`; `--competitive-only` añade `_competitive` al nombre de la carpeta. Ejecuciones repetidas con las mismas opciones de red y competitividad actualizan esos archivos; conserve una copia si necesita comparar semillas u horizontes anteriores.

| Salida | Contenido |
|---|---|
| `caracteristicas.csv` | Estados, covariables y referencias temporales |
| `panel_transiciones.csv` | Transiciones consecutivas elegibles |
| `cobertura_covariables.csv` | Proporción faltante de cada predictor en el panel |
| `transiciones_conteos.csv` | Conteos descriptivos de pares de clases |
| `transiciones_probabilidades_descriptivas.csv` | Frecuencias condicionales de todo el panel; no predicciones fuera de muestra |
| `predicciones_fuera_muestra.csv` | Probabilidades, objetivos y límites de entrenamiento de cada origen |
| `metricas.csv` y `metricas_por_ano.csv` | Desempeño por subconjunto y por año |
| `calibracion.csv` | Probabilidades y frecuencias agrupadas por clase y rango |
| `coeficientes_descriptivos.csv` | Coeficientes del ajuste final completo |
| `pesos_red_2016.csv` y `aristas_red_2016.csv` | Última topología COW utilizada en simulaciones |
| `escenario_<nombre>.csv.gz` | Trayectorias, incluido el estado inicial observado; sólo con `--simulate` |
| `escenarios_resumen.csv` | Medias y percentiles por clase y año simulado |
| `RESULTADOS.txt` y `run_info.json` | Resumen, opciones, convenciones y versiones de ejecución |

Los gráficos `comparacion_modelos`, `calibracion`, `desempeno_por_ano` y, cuando se simula, `escenarios` se guardan en **PNG y SVG**. Las tablas de entrada procesadas y los estados ideológicos desconocidos se guardan en `data/processed/`. Los originales y sus registros de descarga permanecen en `data/raw/`.

## Interpretación y contribución posible

La relación entre vecinos puede reflejar difusión, condiciones nacionales similares o choques compartidos. La penalización L2 y la evaluación temporal no resuelven esa distinción causal. También importan la falta de datos, las discrepancias de clasificación, las diferencias institucionales y la elección de topología.

La combinación de países, estados políticos, vecindad y procesos de Markov tiene antecedentes. Gleditsch y Ward (2006) estudian transiciones entre democracia y autocracia con contexto geográfico. Antràs y Padró i Miquel (2025) formalizan influencia extranjera y olas ideológicas. Herre (2023) documenta la medición de ideologías ejecutivas. Estos trabajos delimitan la pregunta y evitan atribuir novedad a herramientas ya establecidas.

Una contribución potencial es **comparar de forma reproducible la capacidad predictiva de estados previos, condiciones domésticas, exposición geográfica y presiones internacionales para transiciones ejecutivas en las Américas**. Su valor depende de los resultados, de controles adicionales y de una revisión bibliográfica más amplia. Este repositorio no afirma prioridad mundial ni novedad suficiente para una publicación por el mero hecho de combinar esas herramientas.


## Resultado de la ejecución entregada

La muestra contiene 1.207 transiciones observables, con 108 cambios. La evaluación expansiva de 2000–2022 comprende 604 observaciones y 60 cambios. El menor Brier multiclase corresponde a Markov simple (0,182862); el modelo combinado obtiene 0,184616. La exactitud cercana al 90 % está dominada por permanencia: ninguno de los seis modelos acierta la clase de los 60 cambios al seleccionar la probabilidad máxima.

La ordenación del riesgo de alternancia ofrece un diagnóstico distinto: AUC-ROC 0,612745 y precisión promedio 0,156091 para el modelo combinado, frente a prevalencia 0,099338. Esto no implica calibración superior, significación estadística ni anticipación fiable de elecciones. Las métricas completas, sin selección de umbral sobre el test, figuran en `metricas.csv`.

Los datos necesarios están incluidos para ejecutar offline. No se redistribuyen los archivos ZIP originales ni el PDF del código COW; el descargador puede obtenerlos. Los lectores locales no hacen descargas implícitas y verifican los hashes de sus entradas.

El cuaderno `Americas_Markov_Colab.ipynb` permite cargar este proyecto en Colab o ejecutar desde su carpeta en Jupyter. Las celdas se entregan sin salidas de ejecución; los resultados adjuntos proceden de ejecutar el mismo programa mediante `run.py`.

## Ampliación histórica y drivers

[RESEARCH_EXTENSION.md](RESEARCH_EXTENSION.md) documenta una evaluación DPI desde 1985, un panel GLI histórico separado y bloques de exposición a petróleo y ENSO. Los nuevos resultados se guardan en `outputs/extensions/` y `outputs/history/`.

```bash
python run_extensions.py --download --run
# Con las fuentes incluidas, sin red:
python run_extensions.py --offline --run
```

La ampliación evalúa 1.007 casos DPI y 1.677 casos históricos GLI HOG. Los nuevos drivers no superan el Brier global de Markov simple en esta ejecución. GLI y DPI discrepan en el 22,57 % de las observaciones conjuntamente clasificadas y alineadas por fecha; las fuentes se conservan separadas. ENSO mide variabilidad climática, no cambio climático antropogénico.
