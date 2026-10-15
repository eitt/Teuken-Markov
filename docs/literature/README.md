# Literature and novelty review

The [review](LITERATURE_REVIEW.md) assesses the analysis saved at commit `d9815d9f672265236376a30ecc342b661d50b0e6` against a targeted set of primary studies available by 12 October 2026. It concludes that the methods have clear precedents and that the strongest present contribution is an incremental empirical benchmark and measurement-sensitivity audit. It does not establish worldwide priority or causal influence.

- [Manuscript text](MANUSCRIPT_RELATED_WORK.md): English related work, calibrated contribution, result paragraph and suggested title. Citation numbers match the full review and inventory.
- [Literature matrix](literature_matrix.csv): 26 studies with outcomes, designs, overlap, limits and reading status.
- [Closest studies](closest_studies.csv): ten direct comparisons.
- [Verified bibliography](references.bib): BibTeX keys and primary links; working-paper and chapter DOI status are explicit.
- [Source metadata](sources.json) and [result evidence](result_evidence.json): machine-readable records.
- [Provenance](provenance.json): frozen analysis commit and hashes of the saved results used in the review.

The review is a bounded scoping exercise, not an exhaustive systematic review. Some works were verified only through primary abstracts or previews; their inventory entries state those limits. Original publication years are separated from platform posting dates.

From the repository root, reproduce the documents and PDF using:

```bash
python -m pip install -r requirements-publication.txt
python docs/literature/build_review.py
```

The script reads saved results and writes English Markdown, CSV, JSON, BibTeX and `outputs/literature/Teuken_Literature_and_Novelty_Review.pdf`. It never refits a model or recodes governments. The compiled PDF is excluded from Git; editable sources and the generator are tracked.
