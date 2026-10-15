# Table 5. GLI head-of-government historical-panel performance

Separate GLI panel; origins 1956–2020, aligned targets 1957–2021. The final aligned 2021 target represents the December 31, 2020 source observation. Correct change predictions use the highest-probability class. Brier range is 0–2; log-loss floor is 10^-12. All models share the same cases. This historical panel is not joined to DPI, and score levels from different samples do not constitute a controlled model comparison.

| Model | Cases | Observed changes | Correct change predictions | Brier score | Clipped log loss | Accuracy (%) |
| --- | --- | --- | --- | --- | --- | --- |
| Persistence | 1677 | 167 | 0 | 0.1992 | 2.7516 | 90.0 |
| Markov | 1677 | 167 | 0 | 0.1833 | 0.3795 | 90.0 |
| Duration | 1677 | 167 | 0 | 0.1845 | 0.3810 | 90.0 |
| Duration + geographic network | 1677 | 167 | 0 | 0.1862 | 0.3846 | 89.9 |

Source: Frozen GLI head-of-government predictions and metrics; chronological expanding evaluation.

CSV values retain full numerical precision; Markdown values are rounded for display.
