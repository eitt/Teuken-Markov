# Table 4. DPI driver-extension performance under chronological evaluation

Periods are defined by prediction origin, not target year. Each row counts the same cases separately for one model; rows and overlapping periods must not be summed. Correct change predictions require the highest-probability class to equal the observed new state. Multiclass Brier scores sum squared error across three classes (range 0–2); lower scores and losses are better. Log loss uses a 10^-12 probability floor. Overall accuracy is dominated by persistence.

| Evaluation period | Model | Cases | Observed changes | Correct change predictions | Brier score | Clipped log loss | Accuracy (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| All origins (1985–2022) | Persistence | 1007 | 93 | 0 | 0.1847 | 2.5518 | 90.8 |
| All origins (1985–2022) | Markov | 1007 | 93 | 0 | 0.1712 | 0.3618 | 90.8 |
| All origins (1985–2022) | Reduced controls | 1007 | 93 | 2 | 0.1726 | 0.3706 | 90.9 |
| All origins (1985–2022) | Reduced controls + oil | 1007 | 93 | 2 | 0.1734 | 0.3751 | 90.9 |
| All origins (1985–2022) | Reduced controls + ENSO | 1007 | 93 | 2 | 0.1736 | 0.3724 | 90.9 |
| All origins (1985–2022) | Reduced controls + oil + ENSO | 1007 | 93 | 2 | 0.1745 | 0.3770 | 90.8 |
| Origins before 2000 (1985–1999) | Persistence | 403 | 33 | 0 | 0.1638 | 2.2626 | 91.8 |
| Origins before 2000 (1985–1999) | Markov | 403 | 33 | 0 | 0.1536 | 0.3301 | 91.8 |
| Origins before 2000 (1985–1999) | Reduced controls | 403 | 33 | 2 | 0.1551 | 0.3594 | 92.1 |
| Origins before 2000 (1985–1999) | Reduced controls + oil | 403 | 33 | 2 | 0.1559 | 0.3604 | 92.1 |
| Origins before 2000 (1985–1999) | Reduced controls + ENSO | 403 | 33 | 2 | 0.1581 | 0.3632 | 92.1 |
| Origins before 2000 (1985–1999) | Reduced controls + oil + ENSO | 403 | 33 | 2 | 0.1589 | 0.3645 | 91.8 |
| Origins from 2000 (2000–2022) | Persistence | 604 | 60 | 0 | 0.1987 | 2.7448 | 90.1 |
| Origins from 2000 (2000–2022) | Markov | 604 | 60 | 0 | 0.1829 | 0.3830 | 90.1 |
| Origins from 2000 (2000–2022) | Reduced controls | 604 | 60 | 0 | 0.1842 | 0.3780 | 90.1 |
| Origins from 2000 (2000–2022) | Reduced controls + oil | 604 | 60 | 0 | 0.1851 | 0.3849 | 90.1 |
| Origins from 2000 (2000–2022) | Reduced controls + ENSO | 604 | 60 | 0 | 0.1839 | 0.3785 | 90.1 |
| Origins from 2000 (2000–2022) | Reduced controls + oil + ENSO | 604 | 60 | 0 | 0.1849 | 0.3854 | 90.1 |

Source: Frozen DPI driver-extension predictions and period metrics; expanding training windows use only previous outcomes.

CSV values retain full numerical precision; Markdown values are rounded for display.
