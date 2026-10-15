# Executive ideological transitions in the Americas

The project interface, documentation, notebook and generated outputs use English. See [ENGLISH_MIGRATION.md](ENGLISH_MIGRATION.md) for canonical filenames and compatibility with archived runs.

A reproducible Python project for analyzing annual changes among Left, Center and Right and exploring scenarios for countries' joint evolution. It combines political institutions, economic indicators, international prices and a geographic network. The aim is to compare transition probabilities and assess whether neighboring countries' information improves performance relative to simple baselines.

The evaluation is retrospective and uses revised public series. Simulations produce trajectories conditional on specified assumptions. The project does not identify causal effects, provide certain predictions or constitute an operational forecasting system based on the data versions available at each historical date.

## Quick start

Requires **Python 3.10 or later** with compatible dependencies from `requirements.txt`. Run the commands from this directory, which contains `run.py` and `requirements.txt`.

```bash
python -m pip install -r requirements.txt
python run.py --download --run --simulate
```

The supplied run was tested with **Python 3.12**. To install its exact dependency versions, use `requirements-lock.txt`; that file requires **Python 3.11 or later**. With Python 3.10, use `requirements.txt` to resolve compatible versions rather than impose the locked environment.

```bash
python -m pip install -r requirements-lock.txt
```

To repeat the analysis using downloaded files without Internet access:

```bash
python run.py --offline --run --simulate
```

To download the sources again and rebuild the analysis:

```bash
python run.py --download --refresh --run --simulate
```

You can also run the stages separately:

```bash
python run.py --download
python run.py --offline --run
python run.py --offline --simulate
```

`--download` retrieves public sources and uses the cache when available. `--refresh` requests a new download and requires `--download`; a new source version may change the results. `--offline` requires a complete cache and cannot be combined with `--download` or `--refresh`. `--run` prepares the panel and performs the temporal evaluation. `--simulate` also prepares and evaluates the models before producing scenarios; it does not require a prior `--run`. For the options supported by the installed version:

```bash
python run.py --help
```

Sensitivity and simulation options include:

| Option | Effect | Default |
|---|---|---|
| `--land-only` | Excludes maritime edges | Land and maritime network |
| `--competitive-only` | Restricts evaluation origins and simulated initial states to `EIEC >= 6` | No competitiveness filter |
| `--start-year` | First evaluation origin year | `2000` |
| `--runs` | Monte Carlo trajectories per scenario | `500` |
| `--horizon` | Annual steps after the initial state | `6` |
| `--seed` | Simulation seed | `2026` |

For example:

```bash
python run.py --offline --run --land-only
python run.py --offline --run --competitive-only
python run.py --offline --simulate --runs 1000 --horizon 8 --seed 2026
```

Retain the original files and their hash records to reproduce a run exactly. Rerunning the code with a more recent download does not reproduce the same data version.

## Coverage and meaning of the political variable

The main source is the **Database of Political Institutions, DPI 2023**, published in 2026 with observations from 1975 to 2023. DPI records institutional conditions primarily on **January 1** of each year. The economic orientation of the chief executive's party is classified as Right, Center or Left. This variable does not capture the leader's entire personal ideology or make Left/Right equivalent to democracy/autocracy.

The selected universe comprises **31 sovereign countries in the Americas**: Argentina, Bahamas, Barbados, Belize, Bolivia, Brazil, Canada, Chile, Colombia, Costa Rica, Cuba, Ecuador, El Salvador, United States, Grenada, Guatemala, Guyana, Haiti, Honduras, Jamaica, Mexico, Nicaragua, Panama, Paraguay, Peru, Dominican Republic, Saint Lucia, Suriname, Trinidad and Tobago, Uruguay and Venezuela.

It does not cover all 35 sovereign countries in the Americas: **Antigua and Barbuda, Dominica, Saint Kitts and Nevis, and Saint Vincent and the Grenadines** are absent from the DPI source used here. A country's inclusion in the universe also does not guarantee valid observations in every year. The transition sample requires consecutive usable political states. Unknown or not-applicable codes are not reinterpreted as Center.

Before feature preparation, political records are excluded for countries outside the COW state system on **January 1** of the relevant year, using the dates in `States2024`. This is an operational eligibility rule for the network source, **not an exact date of sovereignty or a redefinition of independence**. The run records the number of excluded rows.

Herre's **Global Leader Ideology Dataset, GLI**, provides an additional reference for 1945–2020 to compare classifications. Its unit and coding rules differ from DPI: it classifies the leader, whereas DPI uses the executive party's orientation. GLI alone neither extends the main series to later years nor resolves measurement disagreement.

## Sources and provenance

| Source | Role in the project | Scope and caveat |
|---|---|---|
| DPI 2023 | Consecutive executive ideological states | 1975–2023; observations primarily on January 1 |
| World Development Indicators, World Bank | GDP growth, inflation, trade openness, fuel-import share and tourism | Revised annual series; uneven coverage across countries and indicators |
| Correlates of War, Direct Contiguity v3.2 | Land and maritime edges | Graph from `t-1` through the source endpoint in 2016; the final topology is then carried forward |
| World Bank, Pink Sheet | Historical monthly oil prices and food index; the workbook also contains wheat | The main specification uses oil and food, with no separate wheat predictor |
| GLI, Herre | Optional reference for ideological measurement | 1945–2020; does not automatically replace DPI |

Source files are retained in `data/raw/`. The download record includes the provenance and hashes of the files used. See [SOURCES.md](SOURCES.md) for links, references and measurement differences.

The network represents **geographic proximity**, rather than observed diplomatic contacts or bilateral trade flows. WDI trade openness is a country feature; it does not define a trade edge. For an origin year `t`, the graph uses `min(t-1, 2016)`: COW records relationships present during any part of a year, so topology is lagged by one year to precede the January 1 political origin. From the 2017 origin onward, the 2016 structure is retained. This continuation is an assumption required by the source endpoint, not a measurement of topology in 2023 or the future.

## Temporal alignment

For each country and origin year `t`, the outcome is the political class on **January 1 of `t+1`**, conditional on the class on **January 1 of `t`**. Economic indicators refer to **`t-1`**, while neighborhood exposure uses neighbors' states on **January 1 of `t`**, with the topology of `min(t-1, 2016)`.

For example, evaluating the transition from January 1, 2010 to January 1, 2011 uses the initial political orientation in 2010, neighbors' initial states in 2010 and economic information from 2009. An election held during 2010 may be reflected in the 2011 state.

The lags prevent deliberate use of following-year indicators as predictors. However, current macroeconomic series contain revisions and may have been published after the origin date. **The project does not reconstruct the releases available in real time in 2010 or any other year.** This distinction limits interpretation of its performance as a historically feasible forecast.

Evaluation covers origin years **2000–2022**, using expanding training windows: each step includes only transitions with earlier origins, from the start of the usable sample in 1975. Training outcomes must have occurred on or before the evaluated origin date. The final observable transition ends on **January 1, 2023**. No random split mixes future and past observations.

## Models and evaluation

The project compares simple baselines with **L2**-penalized logistic regression models implemented in `scikit-learn`. Every model must produce probabilities for the same classes and be evaluated on comparable observations.

| Model | Main information |
|---|---|
| Persistence | Retains the initial political class |
| Markov | Historical transition probabilities between classes |
| Domestic | Initial state and domestic indicators |
| Network | Domestic information and neighbors' ideological composition |
| Shocks | Domestic information and lagged international variables |
| Both | Domestic information, neighbors and shocks |

The Markov baseline uses Laplace smoothing, adding one to every cell of the transition matrix computed from training data alone. Logistic models include country and initial state as categorical variables; the domestic specification adds **observed ideological state duration**, `state_duration`, and electoral competitiveness to the economic indicators. Duration counts consecutive years with the same classification; it is not the leader's personal tenure (`yrsoffc`). It resets after a change or a gap in the series and is limited by the start of observations. A new leader who retains the ideological class can extend the same run.

Because the expanded models incorporate duration, their effective state contains memory. They can be interpreted as duration-augmented or expanded-state Markov models, related to a semi-Markov formulation; they are not first-order chains defined solely by Left/Center/Right. The shock specification uses global growth, oil and food price changes, lagged COVID-19 and interactions with trade exposure, fuel imports and tourism.

The comparison uses **multiclass Brier score**, **log loss** and **calibration**. The first two metrics assess probabilities, beyond the most likely class; lower values indicate better performance. Brier is the mean sum of squared probability errors across the three classes, with a range of 0 to 2. Calibration examines whether a stated probability corresponds to the event's observed frequency.

Persistence assigns probability one to the initial state and zero to the others. Its log loss would be infinite when the state changes. For numerical comparison, `log_loss_clipped` floors the observed outcome's probability at `1e-12` and records the number of zero-probability outcomes. Any published value must state this convention. Numerical covariate imputation and standardization are fitted within each training window; they neither fill nor reclassify political labels.

The subset in which the political class actually changed is examined separately. This group is identified **after predictions are obtained**, to diagnose model performance on less frequent transitions. The observed future change cannot determine which model to apply or serve as a predictor. Strong overall performance may be dominated by persistence and should be assessed alongside this diagnostic.

Read results together with coverage, class frequencies and the number of changes. Model comparisons do not establish that differences are statistically significant or that the best observed model will remain best in other periods. The coefficient file comes from the final fit using **the entire panel**, separately from the fits used to evaluate each year. Its coefficients describe that regularized model and are not causal effects.

## COVID-19, Ukraine and international prices

Information about an event is not used before its onset. In particular, the lagged COVID-19 indicator activates at the 2021 and 2022 origins. A prediction dated January 1, 2020 is not assigned knowledge of the pandemic. When the indicator first appears in evaluation, earlier training data contain no active cases: its association cannot have been learned until those observations subsequently enter training.

The full-scale invasion of Ukraine began in February 2022, while the last DPI target is January 1, 2023. With the project's lags and origin years ending in 2022, a lagged invasion indicator would be zero throughout the observable panel. **Ukraine is therefore excluded from estimated features.** No coefficient for the invasion's relationship with political transitions has been learned. A price disturbance associated with Ukraine appears only as a scenario assumption, rather than an estimated war effect on governments in the Americas.

Historical oil and food movements represent observed international pressures. Their changes also respond to supply, demand and other events. The source workbook contains wheat, which is not a separate predictor in the main specification. An association with a political transition does not identify which of those causes operated. Scenarios associated with wars or future crises impose explicit assumptions about these pressures; they do not estimate the events' causal effects.

## Interpreting the simulation

Each country is a node with a political state. Simulations begin at the last observed DPI state, **January 2023**; they do not initialize governments in office in 2026. Only countries with a valid state on that date and eligible under the run's filters are included. At each annual step, all countries update **simultaneously**, using the previous step's states. Probabilities are calculated conditional on the previous state, environment and scenario variables; a new state is then sampled.

The simulation model is the final `network_shocks` fit, trained on the full observable panel. The 2016 topology and domestic covariates remain fixed. Ideological duration increases when the class persists and resets to one when it changes; neighborhood composition is recalculated from simulated states. Global growth stays at baseline except during the recession disturbance. Price changes and COVID-19 are set to zero, except for price changes explicitly imposed by a scenario.

| Scenario ID | Assumption during the first two steps | From the third step onward |
|---|---|---|
| `constant_conditions` | Global growth at baseline; zero oil and food price changes | Maintains the same baseline |
| `hypothetical_recession` | Annual global growth of **−2%**; zero price changes | Global growth returns to baseline |
| `hypothetical_energy_food` | Annual oil price change of **+50%** and food price change of **+20%**; global growth at baseline | Both price changes return to zero |

These rates and conditions are imposed, rather than estimated disturbances from a particular war. Domestic growth also does not change automatically when global growth changes. With the default six-step horizon, years after the initial state are 2024–2029.

The simulation can be described as a **probabilistic automaton on a network**. It is not a literal Game of Life: it does not use that model's deterministic birth and survival rules. Nor does it represent individual voters' decisions or an established mechanism of imitation between governments.

Updates are annual and aggregate. **They are not restricted to election years**, because the full future calendar and all mechanisms of executive replacement are not known here. A simulated change between two years does not necessarily represent a predicted election. Results depend on assumptions, the model and sampling. The 5–95 percentile bands show Monte Carlo dispersion conditional on fitted parameters; they exclude uncertainty about parameters, measurement and the political calendar.

Do not interpret a particular trajectory as the most likely future or a simulation frequency as electoral certainty. The annual model requires further assessment before use for questions about specific elections, coups, coalition changes or presidential continuity.

## Project files and outputs

| File | Responsibility |
|---|---|
| `run.py` | Entry point |
| `src/americas_markov/cli.py` | Options, stages and output saving |
| `src/americas_markov/data.py` | Downloads, cache, hashes and DPI/WDI/Pink Sheet reading |
| `src/americas_markov/network.py` | COW contiguity and state-membership dates |
| `src/americas_markov/features.py` | Lags, ideological duration and neighborhood features |
| `src/americas_markov/models.py` | Baselines, regressions and expanding-window evaluation |
| `src/americas_markov/simulation.py` | Three scenarios and synchronous updates |
| `src/americas_markov/reporting.py` | Charts and run summary |
| `tests/test_core.py` | Core checks |

The main run writes to **`outputs/main/`**. `--land-only` uses `outputs/land_only/`; `--competitive-only` appends `_competitive` to the folder name. Repeated runs with the same network and competitiveness options update those files; retain a copy to compare earlier seeds or horizons.

| Output | Content |
|---|---|
| `features.csv` | States, covariates and time references |
| `transition_panel.csv` | Eligible consecutive transitions |
| `feature_coverage.csv` | Missing share of each predictor in the panel |
| `transition_counts.csv` | Descriptive counts of class pairs |
| `descriptive_transition_probabilities.csv` | Conditional frequencies from the entire panel; not out-of-sample predictions |
| `predictions.csv` | Probabilities, targets and training boundaries for each origin |
| `metrics.csv` and `metrics_by_year.csv` | Performance by subset and year |
| `calibration.csv` | Probabilities and frequencies grouped by class and range |
| `descriptive_coefficients.csv` | Coefficients from the full final fit |
| `network_weights_2016.csv` and `network_edges_2016.csv` | Final COW topology used in simulations |
| `scenario_<name>.csv.gz` | Trajectories, including the observed initial state; only with `--simulate` |
| `scenario_summary.csv` | Means and percentiles by class and simulated year |
| `RESULTS.txt` and `run_info.json` | Summary, options, conventions and run versions |

Charts named `model_comparison`, `calibration`, `performance_by_year` and, when simulated, `scenarios` are saved as **PNG and SVG**. Processed input tables and unknown ideological states are saved in `data/processed/`. Original files and their download records remain in `data/raw/`.

## Interpretation and potential contribution

Relationships between neighbors may reflect diffusion, similar domestic conditions or shared shocks. L2 penalization and temporal evaluation do not resolve this causal distinction. Missing data, classification disagreements, institutional differences and topology choices also matter.

Combining countries, political states, neighborhoods and Markov processes has precedents. Gleditsch and Ward (2006) study transitions between democracy and autocracy with geographic context. Antràs and Padró i Miquel (2025) formalize foreign influence and ideological waves. Herre (2023) documents the measurement of executive ideologies. These studies define the question and prevent established tools from being presented as novel.

A potential contribution is **a reproducible comparison of the predictive value of previous states, domestic conditions, geographic exposure and international pressures for executive transitions in the Americas**. Its value depends on the results, additional controls and a broader literature review. This repository does not claim global priority or publication-worthy novelty simply from combining those tools.

## Results from the supplied run

The sample contains 1,207 observable transitions, including 108 changes. Expanding-window evaluation for 2000–2022 comprises 604 observations and 60 changes. The lowest multiclass Brier score belongs to the simple Markov model (0.182862); the combined model scores 0.184616. Accuracy near 90% is dominated by persistence: none of the six models correctly selects the class in the 60 changed cases when choosing the highest-probability outcome.

Change-risk ranking provides a different diagnostic: ROC AUC of 0.612745 and average precision of 0.156091 for the combined model, against a prevalence of 0.099338. This does not imply superior calibration, statistical significance or reliable election forecasting. Complete metrics, without selecting a threshold on the test set, appear in `metrics.csv`.

The data required for offline execution are included. Original ZIP archives and the COW codebook PDF are not redistributed; the downloader can retrieve them. Local readers do not download implicitly and verify their input hashes.

The `Americas_Markov_Colab.ipynb` notebook lets you load this project in Colab or run it from its directory in Jupyter. Cells are supplied without execution outputs; attached results were produced by running the same program through `run.py`.

## Historical and driver extension

[RESEARCH_EXTENSION.md](RESEARCH_EXTENSION.md) documents DPI evaluation starting in 1985, a separate historical GLI panel, and oil and ENSO exposure blocks. New results are saved in `outputs/extensions/` and `outputs/history/`.

```bash
python run_extensions.py --download --run
# With the included sources, without network access:
python run_extensions.py --offline --run
```

## Maps, figures and tables in English

The publication package adds six main figures, three supplements and six presentation tables, all in English. It includes geopolitical maps, historical coverage, source disagreement, held-out performance and conditional scenarios. See [PUBLICATION_GUIDE.md](PUBLICATION_GUIDE.md) and the [figure gallery](outputs/publication/README.md).

```bash
python -m pip install -r requirements-publication.txt
python run_publication.py
```

The command reads frozen outputs and verified local cartography without model fitting or downloads. It also re-renders the original diagnostics in English. Vector SVG/PDF masters, 300/600 dpi PNGs, plotted data and a captioned figure-and-table PDF are produced in `outputs/publication/`.

The extension evaluates 1,007 DPI cases and 1,677 historical GLI HOG cases. The new drivers do not outperform the simple Markov model's overall Brier score in this run. GLI and DPI disagree in 22.57% of jointly classified observations aligned by date; the sources remain separate. ENSO measures climate variability, not anthropogenic climate change.

## Literature review and novelty

The [literature review](docs/literature/LITERATURE_REVIEW.md), with a cutoff of October 12, 2026, compares the analysis with 26 selected studies and ten close precedents. It includes an [evidence matrix](docs/literature/literature_matrix.csv), [BibTeX bibliography](docs/literature/references.bib) and [English manuscript text](docs/literature/MANUSCRIPT_RELATED_WORK.md). Sources, tables and access limitations are documented in [the guide](docs/literature/README.md).

The methods have clear precedents. The defensible contribution is a reproducible retrospective benchmark and a measurement-sensitivity audit of executive ideological transitions. The review establishes neither global priority nor a reliable ability to anticipate changes. To reproduce the documents and PDF without refitting models:

```bash
python docs/literature/build_review.py
```
