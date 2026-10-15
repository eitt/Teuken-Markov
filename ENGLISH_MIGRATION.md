# English project interface

Code comments, docstrings, command-line help, error messages, the notebook, documentation and generated presentation outputs use English. Scientific formulas, model specifications, observations and numerical results are preserved. Original source bytes, party names, authors' names and bibliographic titles retain their source spelling.

## Canonical outputs

The main and land-only analyses now write the following files:

| Artifact | English filename |
| --- | --- |
| Feature panel | `features.csv` |
| Consecutive transition pairs | `transition_panel.csv` |
| Covariate coverage | `feature_coverage.csv` |
| Observed transition counts | `transition_counts.csv` |
| Full-panel descriptive transition probabilities | `descriptive_transition_probabilities.csv` |
| Chronological predictions | `predictions.csv` |
| Aggregate model scores | `metrics.csv` |
| Scores by prediction origin | `metrics_by_year.csv` |
| Final-fit descriptive coefficients | `descriptive_coefficients.csv` |
| Geographic weights and edges | `network_weights_2016.csv`, `network_edges_2016.csv` |
| Calibration data and figure | `calibration.csv`, `calibration.png`, `calibration.svg` |
| Comparison and annual performance figures | `model_comparison.*`, `performance_by_year.*` |
| Scenario summaries and figures | `scenario_summary.csv`, `scenarios.*` |
| Compressed scenario paths | `scenario_<scenario_id>.csv.gz` |
| Run summary and metadata | `RESULTS.txt`, `run_info.json` |

Processed annual prices and unclassified political observations are stored as `data/processed/annual_prices.csv` and `data/processed/unknown_ideologies.csv`. Extension and history outputs already used English names and retain their established schemas.

## Scenario identifiers and compatibility

| Canonical identifier | Display label | Archived identifier accepted by readers |
| --- | --- | --- |
| `constant_conditions` | Constant conditions | `condiciones_constantes` |
| `hypothetical_recession` | Hypothetical recession | `recesion_hipotetica` |
| `hypothetical_energy_food` | Hypothetical energy and food shock | `energia_alimentos_hipotetico` |

`simulate()` accepts the archived identifiers and returns the canonical English identifier. Publication readers prefer an English file when both names exist, and fall back to an archived filename when needed. Normalization changes only scenario identifiers in memory; it never rewrites an archived input file. New analysis outputs use English names.

Existing scripts that open output paths directly should use the filenames above. In custom Python readers, `americas_markov.artifacts.read_artifact_csv` provides filename fallback and scenario normalization. Command-line flags and their numerical defaults remain unchanged.

## Reproduction

From the project directory:

```bash
python -m pip install -r requirements-publication.txt
python run.py --offline --run --simulate
python run_extensions.py --offline --run
python run_publication.py
python docs/literature/build_review.py
```

The first two analysis commands refit their respective models. Publication and literature commands consume the saved results. Source refreshes remain explicit and may change the scientific results; translating the interface did not refresh or recode any data.

Validation records in `outputs/ENGLISH_VALIDATION.txt` document the numerical comparison and checks completed for this migration. Checksum inventories describe the current files, while download manifests retain the original source hashes.
