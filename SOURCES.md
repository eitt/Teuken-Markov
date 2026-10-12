# Fuentes, versiones y referencias

Esta lista identifica las fuentes públicas del proyecto. La versión que determina una ejecución es el archivo guardado y su hash, no sólo la fecha visible en el portal. Las series descargadas actualmente pueden revisar observaciones históricas; no son una colección de publicaciones disponibles en cada fecha del pasado.

## Datos políticos principales

**Cruz, Cesi, Philip Keefer, Carlos Scartascini y Alberto Simpser (2026). _The Database of Political Institutions (DPI): 2023_. IDB Open Data.**

- DOI del conjunto de datos: <https://doi.org/10.60966/8tx1xs4i>.
- Portal y código de variables: <https://data.iadb.org/dataset/the-database-of-political-institutions-dpi-2023>.
- Cobertura nominal: 1975–2023; la edición fue publicada en 2026. La mayoría de las variables describe el 1 de enero; algunas variables electorales resumen acontecimientos del año.
- La variable `execrlc` representa la orientación económica del partido del jefe del Ejecutivo. Debe interpretarse según el código de variables de esta edición. Los valores desconocidos o no aplicables no equivalen a una clase ideológica intermedia.
- Licencia indicada por el proveedor: CC BY 4.0. Cite esta edición y sus cuatro autores al reutilizarla.

La selección de las Américas incluye 31 países. Antigua y Barbuda, Dominica, San Cristóbal y Nieves, y San Vicente y las Granadinas no aparecen en la fuente utilizada. Los años sin clasificación válida se distinguen de una permanencia política observada. El predictor `state_duration` cuenta años consecutivos de la misma clasificación observada, no los años en el cargo de un líder (`yrsoffc`).

## Referencia adicional de ideología

**Herre, Bastian (2023). “Identifying Ideologues: A Global Dataset on Political Leaders, 1945–2020”. _British Journal of Political Science_, 53(2), 740–748.**

- Artículo: <https://doi.org/10.1017/S0007123422000217>.
- Repositorio del autor: <https://github.com/bastianherre/global-leader-ideologies>.
- Documentación y fuentes del autor: <https://www.bastianherre.com/data>.
- GLI clasifica la ideología económica del líder como izquierda, centro, derecha o sin ideología, e identifica casos sin información o no aplicables. No debe confundirse esta medida con la orientación del partido en DPI.

GLI permite contrastar medición dentro de su cobertura, 1945–2020. Su corte anual al 31 de diciembre también difiere del corte principal de DPI al 1 de enero. No se supone que ambas clasificaciones sean intercambiables, y no se presenta una sustitución de datos entre fuentes como una extensión homogénea de la serie.

## Indicadores económicos nacionales

**Banco Mundial. _World Development Indicators_ (WDI).**

- Catálogo: <https://databank.worldbank.org/source/world-development-indicators>.
- API pública y documentación: <https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation>.
- Términos de uso: <https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets>.

| Variable del código | Indicador WDI | Unidad |
|---|---|---|
| `gdp_growth` | `NY.GDP.MKTP.KD.ZG` | Cambio porcentual anual del PIB real |
| `inflation` | `FP.CPI.TOTL.ZG` | Cambio porcentual anual de precios al consumidor |
| `trade_open` | `NE.TRD.GNFS.ZS` | Exportaciones más importaciones como porcentaje del PIB |
| `fuel_import_share` | `TM.VAL.FUEL.ZS.UN` | Importaciones de combustibles como porcentaje de importaciones de mercancías |
| `tourism_exports_share` | `ST.INT.RCPT.XP.ZS` | Ingresos del turismo internacional como porcentaje de exportaciones totales |
| `population` | `SP.POP.TOTL` | Personas; variable auxiliar |

La serie de crecimiento del PIB para el agregado `WLD` proporciona `world_growth`. La cobertura puede variar considerablemente y la ausencia de un valor no significa un valor cero. Las transformaciones concretas deben leerse junto con el código y las salidas de preparación de datos.

La apertura comercial es una medida nacional. No observa la dirección ni el peso de intercambios entre pares de países y no construye una red de comercio bilateral. Los datos WDI revisados permiten una evaluación retrospectiva con rezagos, pero no reconstruyen las cifras publicadas en la fecha de origen histórica.

## Red geográfica

**Correlates of War Project. _Direct Contiguity Data, 1816–2016_. Versión 3.2.**

- Portal, archivos y código de variables: <https://correlatesofwar.org/data-sets/direct-contiguity/>.
- La fuente distingue contigüidad terrestre y cuatro clases marítimas, con umbrales de 12, 24, 150 y 400 millas. La versión cubre 1816–2016.
- Para un año de origen `t`, el proyecto utiliza la topología anual de `min(t-1, 2016)`. El rezago evita usar relaciones iniciadas durante el propio año de origen. Desde el origen de 2017 conserva la topología de 2016, una decisión de modelización ante el final de la fuente. El archivo no observa contactos políticos o comerciales.
- La tabla de pertenencia estatal **States2024** permite enlazar identificadores y comprobar fechas de elegibilidad: <https://correlatesofwar.org/data-sets/state-system-membership/>. Los registros políticos sin pertenencia COW al 1 de enero se excluyen antes de preparar las características. Esa pertenencia es un criterio operativo de la fuente, no una fecha exacta de soberanía. Su versión y su hash se conservan en el registro de descargas.

El proveedor solicita indicar la versión y citar también su artículo de referencia:

**Stinnett, Douglas M., Jaroslav Tir, Philip Schafer, Paul F. Diehl y Charles Gochman (2002). “The Correlates of War Project Direct Contiguity Data, Version 3”. _Conflict Management and Peace Science_, 19(2).**

Consulte el portal para sus reglas de contigüidad y territorios. Los registros COW incluyen relaciones presentes durante alguna parte del año: la implementación combina un grafo de `t-1` con elegibilidad estatal fechada al 1 de enero de `t`. La entrada al sistema COW no es sinónimo de independencia. La relación geográfica no demuestra influencia entre gobiernos.

## Precios internacionales

**Banco Mundial. _Commodity Price Data (The Pink Sheet)_, serie mensual histórica.**

- Portal de datos y descargas mensuales y anuales: <https://www.worldbank.org/en/research/commodity-markets>.
- La especificación principal utiliza el promedio de petróleo crudo, en dólares nominales por barril, y el índice de alimentos, con base 2010 = 100. El archivo contiene asimismo trigo; no es un predictor separado de esta especificación.
- El código calcula medias aritméticas por año calendario sólo con doce meses válidos por serie. El cambio anual es `100 * (media_anual / media_anual_previa - 1)`. Los años parciales se excluyen.
- La fuente se actualiza regularmente. Conserve el archivo descargado para reproducir una ejecución y no sustituya inadvertidamente precios históricos por las previsiones del _Commodity Markets Outlook_.

Los precios internacionales permiten construir medidas de presiones económicas. No son indicadores exclusivos de COVID-19, de la invasión de Ucrania o de ninguna guerra. Los escenarios que modifican estas variables expresan supuestos; no prueban efectos causales de esos acontecimientos.

## Antecedentes que delimitan la contribución

**Gleditsch, Kristian Skrede, y Michael D. Ward (2006). “Diffusion and the International Context of Democratization”. _International Organization_, 60(4), 911–933.**

- DOI: <https://doi.org/10.1017/S0020818306060309>.
- Registro institucional: <https://repository.essex.ac.uk/10118/>.
- Modelo de transiciones país-año entre democracia y autocracia como proceso de Markov, con contexto geográfico. Es antecedente de la combinación de estados políticos, vecindad y probabilidades de transición; su desenlace no es izquierda/centro/derecha.

**Antràs, Pol, y Gerard Padró i Miquel (2025). “Exporting Ideology: The Right and Left of Foreign Influence”. _Quarterly Journal of Political Science_, 20(1), 33–70.**

- DOI: <https://doi.org/10.1561/100.00023119>.
- Texto publicado en el sitio del autor: <https://antras.scholars.harvard.edu/sites/g/files/omnuum5876/files/2025-02/100.00023119.pdf>.
- Modelo formal de influencia extranjera motivada por redistribución y movilidad internacional de capital. Desarrolla implicaciones sobre olas ideológicas y elecciones escalonadas, con discusión explícita de Latinoamérica. No es una estimación del efecto causal de vecinos en el panel de este proyecto.

**Blanco, Luisa, y Robin Grier (2013). “Explaining the Rise of the Left in Latin America”. _Latin American Research Review_, 48(1), 68–90.**

- DOI: <https://doi.org/10.1353/lar.2013.0011>.
- Analiza ideología del Ejecutivo en 100 elecciones de 18 países latinoamericanos, 1975–2007. Ofrece antecedentes sobre condiciones económicas y políticas nacionales que deben distinguirse de difusión internacional. La verificación utilizada aquí alcanza el resumen y los metadatos editoriales.

La existencia de estos antecedentes impide presentar el proyecto como la primera utilización de Markov, redes o contagio ideológico en ciencia política. La posible contribución empírica específica requiere una revisión bibliográfica adicional y resultados de evaluación que la sustenten.

## Fuentes adicionales de la extensión histórica y drivers

La ejecución separada de [RESEARCH_EXTENSION.md](RESEARCH_EXTENSION.md) conserva GLI y DPI como mediciones distintas. El panel histórico GLI usa HOG como opción primaria, con cortes al 31 de diciembre y rótulos alineados al enero siguiente; no añade datos políticos posteriores a 2020 ni imputa competitividad electoral.

Las nuevas exposiciones WDI son `TX.VAL.FUEL.ZS.UN` (combustibles / exportaciones de mercancías) y `NV.AGR.TOTL.ZS` (agricultura, silvicultura y pesca / PIB). Fuente: <https://data.worldbank.org/indicator/TX.VAL.FUEL.ZS.UN> y <https://data.worldbank.org/indicator/NV.AGR.TOTL.ZS>. Las participaciones de importaciones y exportaciones se utilizan por separado, con rezago adicional, y no se restan como medida neta.

NOAA ONI: <https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt>; documentación: <https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/>. Se congela una serie homogénea, sin sustituir RONI por tramos. ENSO mide variabilidad climática y no constituye atribución de cambio climático. La agregación de once ventanas DJF–OND excluye NDJ porque contiene enero del siguiente año; sigue siendo una evaluación retrospectiva con revisiones.

Las respuestas API completas, los datos ONI y sus manifiestos se conservan en `data/raw/`. Los resultados y las métricas por periodo están en `outputs/extensions/`; las discrepancias entre fuentes en `outputs/history/`.
