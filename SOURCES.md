# Sources, versions, and references

This list identifies the project's public data sources. The saved file and its hash determine the version used in a run; the date displayed on the source portal is not sufficient. Series downloaded today may contain revisions to historical observations; they do not constitute a collection of releases available at each historical date.

## Primary political data

**Cruz, Cesi, Philip Keefer, Carlos Scartascini, and Alberto Simpser (2026). _The Database of Political Institutions (DPI): 2023_. IDB Open Data.**

- Dataset DOI: <https://doi.org/10.60966/8tx1xs4i>.
- Portal and codebook: <https://data.iadb.org/dataset/the-database-of-political-institutions-dpi-2023>.
- Nominal coverage: 1975–2023; this edition was published in 2026. Most variables describe conditions on January 1; some electoral variables summarize events during the year.
- The variable `execrlc` represents the economic orientation of the chief executive's party. It must be interpreted according to this edition's codebook. Unknown or inapplicable values do not represent an intermediate ideological class.
- Provider-stated license: CC BY 4.0. Cite this edition and all four authors when reusing it.

The Americas selection includes 31 countries. Antigua and Barbuda, Dominica, Saint Kitts and Nevis, and Saint Vincent and the Grenadines do not appear in the source used. Years without a valid classification are distinguished from observed political persistence. The predictor `state_duration` counts consecutive years with the same observed classification, rather than a leader's years in office (`yrsoffc`).

## Additional ideology reference

**Herre, Bastian (2023). “Identifying Ideologues: A Global Dataset on Political Leaders, 1945–2020”. _British Journal of Political Science_, 53(2), 740–748.**

- Article: <https://doi.org/10.1017/S0007123422000217>.
- Author's repository: <https://github.com/bastianherre/global-leader-ideologies>.
- Author's documentation and sources: <https://www.bastianherre.com/data>.
- GLI classifies leaders' economic ideology as left, center, right, or no ideology, and identifies cases with no information or that are inapplicable. This measure should not be confused with party orientation in DPI.

GLI supports a comparison of measurements within its 1945–2020 coverage. Its annual December 31 reference date also differs from DPI's primary January 1 reference date. The two classifications are not assumed to be interchangeable, and substituting data between sources is not presented as a homogeneous extension of the series.

## National economic indicators

**World Bank. _World Development Indicators_ (WDI).**

- Catalog: <https://databank.worldbank.org/source/world-development-indicators>.
- Public API and documentation: <https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation>.
- Terms of use: <https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets>.

| Code variable | WDI indicator | Unit |
|---|---|---|
| `gdp_growth` | `NY.GDP.MKTP.KD.ZG` | Annual percentage change in real GDP |
| `inflation` | `FP.CPI.TOTL.ZG` | Annual percentage change in consumer prices |
| `trade_open` | `NE.TRD.GNFS.ZS` | Exports plus imports as a percentage of GDP |
| `fuel_import_share` | `TM.VAL.FUEL.ZS.UN` | Fuel imports as a percentage of merchandise imports |
| `tourism_exports_share` | `ST.INT.RCPT.XP.ZS` | International tourism receipts as a percentage of total exports |
| `population` | `SP.POP.TOTL` | Persons; auxiliary variable |

The GDP growth series for the `WLD` aggregate supplies `world_growth`. Coverage can vary considerably, and a missing value does not mean zero. Specific transformations should be read alongside the code and data preparation outputs.

Trade openness is a national measure. It does not observe the direction or weight of exchanges between country pairs and does not construct a bilateral trade network. Revised WDI data support a retrospective evaluation with lags, but they do not reconstruct the figures published at each historical forecast origin.

## Geographic network

**Correlates of War Project. _Direct Contiguity Data, 1816–2016_. Version 3.2.**

- Portal, files, and codebook: <https://correlatesofwar.org/data-sets/direct-contiguity/>.
- The source distinguishes land contiguity and four maritime classes, with thresholds of 12, 24, 150, and 400 miles. This version covers 1816–2016.
- For an origin year `t`, the project uses the annual topology for `min(t-1, 2016)`. This lag avoids using relationships that began during the origin year itself. From the 2017 origin onward, it retains the 2016 topology, a modeling decision made because the source ends in that year. The file does not observe political or commercial contacts.
- The **States2024** state membership table supports identifier matching and eligibility date checks: <https://correlatesofwar.org/data-sets/state-system-membership/>. Political records without COW membership on January 1 are excluded before feature preparation. This membership is an operational criterion of the source, rather than an exact date of sovereignty. Its version and hash are retained in the download log.

The provider requests that users state the version and also cite its reference article:

**Stinnett, Douglas M., Jaroslav Tir, Philip Schafer, Paul F. Diehl, and Charles Gochman (2002). “The Correlates of War Project Direct Contiguity Data, Version 3”. _Conflict Management and Peace Science_, 19(2).**

Consult the portal for its contiguity and territory rules. COW records include relationships present during some part of the year: the implementation combines a graph for `t-1` with state eligibility dated January 1 of `t`. Entry into the COW system is not synonymous with independence. A geographic relationship does not establish influence between governments.

## International prices

**World Bank. _Commodity Price Data (The Pink Sheet)_, historical monthly series.**

- Data portal and monthly and annual downloads: <https://www.worldbank.org/en/research/commodity-markets>.
- The main specification uses the crude oil average, in nominal dollars per barrel, and the food index, with a base of 2010 = 100. The file also contains wheat; it is not a separate predictor in this specification.
- The code calculates calendar-year arithmetic means only when each series has twelve valid months. Annual change is `100 * (annual_mean / previous_annual_mean - 1)`. Partial years are excluded.
- The source is updated regularly. Retain the downloaded file to reproduce a run, and avoid inadvertently replacing historical prices with forecasts from the _Commodity Markets Outlook_.

International prices support the construction of measures of economic pressure. They are not indicators specific to COVID-19, the invasion of Ukraine, or any war. Scenarios that change these variables express assumptions; they do not establish causal effects of those events.

## Prior research that defines the contribution's scope

**Gleditsch, Kristian Skrede, and Michael D. Ward (2006). “Diffusion and the International Context of Democratization”. _International Organization_, 60(4), 911–933.**

- DOI: <https://doi.org/10.1017/S0020818306060309>.
- Institutional record: <https://repository.essex.ac.uk/10118/>.
- A model of country-year transitions between democracy and autocracy as a Markov process, with geographic context. It provides a precedent for combining political states, neighborhood context, and transition probabilities; its outcome is not left/center/right.

**Antràs, Pol, and Gerard Padró i Miquel (2025). “Exporting Ideology: The Right and Left of Foreign Influence”. _Quarterly Journal of Political Science_, 20(1), 33–70.**

- DOI: <https://doi.org/10.1561/100.00023119>.
- Published text on the author's website: <https://antras.scholars.harvard.edu/sites/g/files/omnuum5876/files/2025-02/100.00023119.pdf>.
- A formal model of foreign influence motivated by redistribution and international capital mobility. It develops implications for ideological waves and staggered elections, with an explicit discussion of Latin America. It does not estimate a causal effect of neighbors in this project's panel.

**Blanco, Luisa, and Robin Grier (2013). “Explaining the Rise of the Left in Latin America”. _Latin American Research Review_, 48(1), 68–90.**

- DOI: <https://doi.org/10.1353/lar.2013.0011>.
- Analyzes executive ideology in 100 elections across 18 Latin American countries, 1975–2007. It provides evidence on national economic and political conditions, which should be distinguished from international diffusion. Verification here is limited to the abstract and publisher metadata.

These precedents rule out presenting the project as the first use of Markov models, networks, or ideological contagion in political science. Any specific empirical contribution requires further literature review and supporting evaluation results.

## Additional sources for the historical extension and drivers

The separate run described in [RESEARCH_EXTENSION.md](RESEARCH_EXTENSION.md) retains GLI and DPI as distinct measurements. The historical GLI panel uses HOG as its primary option, with December 31 reference dates and labels aligned to the following January; it does not add political data after 2020 or impute electoral competitiveness.

The new WDI exposures are `TX.VAL.FUEL.ZS.UN` (fuels / merchandise exports) and `NV.AGR.TOTL.ZS` (agriculture, forestry, and fishing / GDP). Sources: <https://data.worldbank.org/indicator/TX.VAL.FUEL.ZS.UN> and <https://data.worldbank.org/indicator/NV.AGR.TOTL.ZS>. Import and export shares are used separately, with an additional lag, and are not subtracted to form a net measure.

NOAA ONI: <https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt>; documentation: <https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/>. A homogeneous series is frozen, without substituting RONI for individual segments. ENSO measures climate variability and does not constitute climate change attribution. Aggregation across eleven DJF–OND windows excludes NDJ because it includes January of the following year; this remains a retrospective evaluation using revised data.

Complete API responses, ONI data, and their manifests are retained in `data/raw/`. Results and metrics by period are in `outputs/extensions/`; source disagreements are in `outputs/history/`.
