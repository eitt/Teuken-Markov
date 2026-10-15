# Historical extension and observed drivers

The extension evaluates additional years and examines exposure to oil prices and ENSO variability. The analyses run separately and preserve the original results in `outputs/main/`. GLI and DPI labels are not spliced together, and shocks are not assigned a left/right direction.

## Running the extension

From the project root, with the dependencies in `requirements.txt` installed:

```bash
python run_extensions.py --download --run
```

Using the included data, without Internet access:

```bash
python run_extensions.py --offline --run
python -m unittest discover -s tests -v
```

The default options are `--start-year 1985`, `--history-start-year 1956`, and `--history-role hog`. `--history-role leader` runs a sensitivity analysis using GLI's political leader measure; it does not fill missing HOG observations using another executive role. Updating the data requires `--download --refresh` and may change the results. The original `run.py` CLI and its six models retain their existing behavior.

## Scope of the extension

| Analysis | Source / dates | Evaluation in this run |
|---|---|---|
| Main DPI analysis | January 1975–2023 | Origins 1985–2022; 1,007 pairs and 93 changes |
| DPI before 2000 | Same labels, with no additional source years | 403 additional pairs and 33 changes |
| DPI from 2000 onward | Original window, with training from 1975 | 604 pairs and 60 changes |
| Historical GLI HOG | December 1945–2020 source data | Aligned origins 1956–2020; 1,677 pairs and 167 changes |

The DPI source already provided 49 years: `--start-year` determines when evaluation begins, rather than the beginning of the full training period. In 1985, the training data contain 200 pairs and only 15 changes; models with additional drivers should be interpreted as exploratory.

GLI observes December 31, while DPI primarily observes January 1. The source year is retained, and the GLI observation from December of Y is labeled January of Y+1: the aligned 1946–2021 labels **do not add observations after December 2020**. These are adjacent dates, with no guarantee of an identical executive: a January 1 inauguration, as in Brazil, can change the executive between the two reference dates.

GLI HOG contains 29 national series and 27 countries with at least one classifiable ideology; the Bahamas and Belize have no classifiable HOG. It does not cover Antigua and Barbuda, Dominica, Grenada, Saint Kitts and Nevis, Saint Lucia, or Saint Vincent and the Grenadines. EIEC, elections, and exact years in office are unavailable in GLI and remain missing. Historical durations count runs of identical annual observations rather than exact inauguration dates.

Between 1975 and 2021, GLI HOG and DPI have 1,019 jointly classified observations and 230 disagreements (**22.57%**). Neither source is designated as the truth, and classes are not manually changed to produce agreement. GLI uses DPI among its source materials: this comparison assesses measurement sensitivity and does not constitute fully independent validation.

## Drivers and temporal ordering

For a political origin in January of t and an outcome in January of t+1:

| Variable | Source and measurement | Year used |
|---|---|---|
| Oil price | Pink Sheet: percentage change in the annual mean | t−1 |
| Import exposure | WDI `TM.VAL.FUEL.ZS.UN`: fuels / merchandise imports | t−2 |
| Export exposure | WDI `TX.VAL.FUEL.ZS.UN`: fuels / merchandise exports | t−2 |
| ENSO | NOAA ONI: mean of 11 three-month DJF–OND windows | t−1 |
| Agricultural exposure | WDI `NV.AGR.TOTL.ZS`: agriculture, forestry, and fishing / GDP | t−2 |

The interactions multiply the index or percentage change by the national share divided by 100. Main effects and interactions are retained in the oil and ENSO blocks. Import and export percentages have different denominators: **they are not subtracted or described as net oil exposure**. Fuels include products other than oil. Agricultural exposure is a broad economic proxy and does not represent a physical ENSO teleconnection estimated for each country.

The lean core uses growth, inflation, class duration, competitiveness, country, and initial state. Persistence, Markov, and four L2 specifications are compared: core, core+oil, core+ENSO, and core+both. The early GLI panel compares persistence, Markov, duration, and duration+network, without imputing pre-1960 macroeconomic data into those predictors.

ONI measures **climate variability**, rather than anthropogenic warming. ONI/RONI products are not switched across segments. NDJ of Y includes January of Y+1 and is excluded to avoid including months after the assigned year. The DJF–OND mean is an aggregation of 11 overlapping windows defined here, rather than 11 independent months or an official NOAA annual index. The source retains complete years from 1950–2025; the incomplete terminal year, 2026, is excluded.

Lags establish the temporal order of events, but economic and climate indicators contain revisions. Some December releases arrive after January: the data actually available at each historical date are not reconstructed. This limitation applies to all results.

## Extension results

Overall multiclass Brier score: lower is better; comparisons use the same 1,007 DPI cases.

| Model | Brier 1985–2022 |
|---|---:|
| Persistence | 0.184707 |
| Markov | **0.171169** |
| Lean core | 0.172592 |
| Core + oil | 0.173445 |
| Core + ENSO | 0.173585 |
| Core + oil + ENSO | 0.174484 |

The new drivers **do not improve the overall Brier score** relative to Markov in this run. In 2000–2022, the ENSO model slightly improves on the lean core (0.183909 versus 0.184250), but remains above Markov (0.182862). Differences are not assigned statistical significance without an appropriate test. The individual lean models correctly predict 2 of the 93 changes across the full window using argmax; the combined model correctly predicts 2/93. In the 2000–2022 window, none correctly predicts any of the 60 changes. Overall accuracy near 91% remains dominated by persistence.

In GLI HOG, Markov obtains a Brier score of 0.183308, duration 0.184468, and duration+network 0.186231. None correctly predicts any of the 167 evaluated changes using argmax. Metrics from different sources are not directly comparable as though they shared the same labels, countries, and years.

`conditional_oil_scenarios.csv` contains one-step contrasts from the observed January 2023 snapshot: hypothetical oil price changes of 0%, −50%, and +50%, holding national exposures and other predictors fixed. These are probabilities conditional on the fitted model, rather than categorical predictions of winners or causal effects of a crisis. They do not include parameter uncertainty. Unknown states do not enter the simulation.

## Other drivers and design limitations

The original implementation already includes world growth, food, and the pandemic, with limitations arising from the small number of shock years. A global war or crisis dummy does not substitute for differences in national exposure. A shock observed during the forecast interval should not be introduced retrospectively as information known before it occurred.

The war in Ukraine begins in 2022. Under the current predictive design, with a t−1 lag and DPI through January 2023, there is no January 2024 outcome to evaluate a January 2023 origin informed by the 2022 shocks. Contemporaneous explanatory associations could be studied with a different design, but should not be presented as predictions made from January 2022.

Extending beyond 2023 requires new, verified political labels. Analyzing climate change requires national temperature/precipitation data, extremes or local impacts, and separate definitions of trends and episodes. The freely available Berkeley Earth file examined did not provide national coverage through 2023; its coverage was not artificially extended. ENSO×agriculture remains an exploratory block.

A full set of year fixed effects would absorb any common global shock. Interactions with national exposure retain variation across countries, but do not identify causality on their own. Shocks can affect the incumbent without determining the ideological orientation of its replacement. Authoritarian countries, competitive elections, and measurement differences require separate sensitivity analyses.

## Files and reproducibility

- `outputs/extensions/dpi_drivers/`: overall metrics and metrics by period, predictions, coverage, and oil scenarios.
- `outputs/extensions/gli_hog/`: separate historical evaluation; `gli_leader/` if that sensitivity analysis is selected.
- `outputs/history/`: GLI panels, missingness/coverage, comparisons, and disagreements by country.
- `data/raw/driver_exposures_manifest.json` and `climate_manifest.json`: sources, date, units, and SHA256.

The DPI copy initially uploaded to GitHub normalized CRLF to LF. The loader accepts that conversion **only if reconstructing CRLF exactly reproduces the recorded original SHA256**; any changed cell or space still causes an error. `.gitattributes` protects subsequent downloads from further Git conversions. Content validation remains enabled.

## References and sources

- Herre, B. (2023). Identifying Ideologues: A Global Dataset on Political Leaders, 1945–2020. *British Journal of Political Science*, 53(2), 740–748. <https://doi.org/10.1017/S0007123422000217>. Data and rules: <https://github.com/bastianherre/global-leader-ideologies>.
- Campello, D., and Zucco, C. (2016). Presidential Success and the World Economy. *Journal of Politics*, 78(2), 589–602. <https://doi.org/10.1086/684749>.
- Cole, S., Healy, A., and Werker, E. (2012). Do voters demand responsive governments? Evidence from Indian disaster relief. *Journal of Development Economics*, 97(2), 167–181. <https://doi.org/10.1016/j.jdeveco.2011.05.005>.
- Cooperman, A. (2022). (Un)Natural Disasters: Electoral Cycles in Disaster Relief. *Comparative Political Studies*. <https://doi.org/10.1177/00104140211047410>.
- WDI: <https://data.worldbank.org/indicator/TX.VAL.FUEL.ZS.UN>, <https://data.worldbank.org/indicator/NV.AGR.TOTL.ZS>.
- NOAA: <https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt> and <https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/>.
