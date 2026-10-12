# English maps, figures and tables

The publication outputs distinguish observed political history, measurement disagreement, held-out performance and conditional scenarios. They do not depict current governments or identify causal international diffusion. All figure text, captions and presentation tables are in English. Historical source codes remain unchanged in the model inputs.

## Reproduce the figure book

```bash
python -m pip install -r requirements-publication.txt
python run_publication.py
```

This command reads the saved analyses and verified cartography without downloading data or fitting models. If full intermediate extension tables have not yet been generated, run `python run_extensions.py --offline --run` first. The original simulation summaries are already provided; to regenerate them use `python run.py --offline --simulate`.

Files are written to `outputs/publication/`. Each figure has a vector SVG and PDF master, a 300 dpi PNG, a 600 dpi PNG, and a CSV containing the plotted evidence. `publication_manifest.json` provides the title, caption, source and final dimensions. Six presentation tables are available as CSV and Markdown, with accompanying complete English exports where useful. The compiled `Americas_Figures_and_Tables_English.pdf` includes the figures, captions and tables. High-resolution PNGs and the compiled delivery PDF are generated locally rather than versioned.

Use `--review-only` to omit 600 dpi PNGs, `--no-book` to omit the compiled PDF, or `--no-legacy` to leave the original diagnostic figures untouched. By default, saved legacy diagnostics are also re-rendered in English, without model fitting. Compatible historical output filenames are retained.

## Figure plan

| Output | Evidence and purpose |
|---|---|
| Figure 1 | Geopolitical map of DPI executive-party orientation on 1 January 2023; unknown classifications and absent countries remain visible. |
| Figure 2 | DPI and GLI HOG historical composition with source coverage. Separate panels preserve different measures and observation dates. |
| Figure 3 | Country-level frequency of observed ideological change in the expanded DPI evaluation, with eligible-pair denominators. |
| Figure 4 | Country-level DPI–GLI disagreement in the adjacent-date comparison; joint coverage accompanies each rate. |
| Figure 5 | Expanded DPI probability scores and the number of correctly classified changes. The same evaluation cases are used across models. |
| Figure 6 | Conditional simulations from the original analysis. Bands show Monte Carlo variation under fixed fitted parameters. |
| Supplement 1 | The frozen 2016 COW geographical network, distinguishing land and water proximity. |
| Supplement 2 | Held-out calibration and precision–recall for ideological-change risk. Sparse probability bins retain their sample counts. |
| Supplement 3 | One-step oil counterfactuals under fixed January 2023 covariates. Missing country exposure data are identified. |

The six main figures support the central empirical story; the three supplements document modelling assumptions and diagnostics. Tables provide exact counts, memberships, model metrics and driver definitions. They replace plots where exact lookup is the purpose.

## Interpretation and production

- **Dates:** DPI ends on 1 January 2023. GLI records refer to 31 December of their source year, ending in 2020; their alignment to the following January is a comparison proxy. Historical composition uses the original GLI source year.
- **Coverage:** the mapping universe is 35 sovereign American countries. Territories provide geographic context and do not inherit a parent state's political classification. Missing data are neither Center nor zero change.
- **Measurement:** DPI records executive-party economic orientation. GLI classifies a leader and distinguishes HOG from the alternative leader rule. GLI uses DPI among its underlying sources, so source agreement is not independent validation. Canada is shown as Right in January 2023 because that is the supplied DPI classification; it is not a manual recoding of the Liberal Party.
- **Evaluation:** expanded DPI origins are 1985–2022. The total of 1,007 held-out cases includes 93 observed changes. Comparisons use identical cases within each source. Absolute DPI and GLI scores are not directly ranked because their outcomes and evaluation samples differ.
- **Scenarios:** the original simulations contain 500 paths per scenario, 30 classified initial countries and states dated 2023–2029. Their 5th–95th percentile bands omit parameter uncertainty. A hypothetical price perturbation does not identify an effect of the Ukraine war. Oil and ENSO predictor blocks are exploratory; ENSO is not anthropogenic climate change.
- **Layout:** masters are 160 mm wide at their declared final heights. Figure text is at least 7 pt. The PDF book embeds vector masters at their exact size, without rescaling or trimming the figure canvas. Maps use a verified Natural Earth 50m subset and include a Caribbean inset. SVG/PDF masters support print; PNG exports support dissemination.

`data/cartography/` records the cartographic provenance, public-domain terms and exact geometry hashes. The compressed Americas subset is loaded strictly offline. Every model comparison and scenario remains tied to its saved analysis outputs; no new uncertainty intervals or causal estimates are manufactured for presentation.
