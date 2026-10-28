# Instructional sources

The lab's synthetic records and generator are original. These references explain the teaching ideas; their datasets, graphics, articles, and videos are not included as redistributable lab data.

- **Gil Bouhnick — Cohort analysis and retention rate.** [Mobilespoon article](https://www.mobilespoon.net/2019/07/cohort-analysis-retention-rate.html). Inspiration for comparing customers, orders, revenue, cumulative value, and acquisition recovery across joining cohorts. The lab computes its own contribution from explicit revenue and variable-cost records; a transaction commission is not silently treated as a complete margin.
- **Juan Orduz — Cohort Revenue Retention Analysis with Flax and NumPyro.** [Walkthrough](https://juanitorduz.github.io/revenue_retention_numpyro/). Inspiration for cohort-period retention/revenue forecasting, evaluation, and uncertainty. This lab uses a simpler documented survival/revenue model, then adds explicit contribution costs, acquisition cost, discounting, and a common valuation horizon. It is not a verbatim reproduction of the original neural-network implementation.
- **Dan McCarthy — Estimating cohort-level CLV from transaction data.** [Video tutorial](https://www.youtube.com/watch?v=UJ6Rfmk5Vrw). Background on transforming transaction histories into age-aligned cohort data and customer-value estimates. This lab uses the term **LTV**; the source video's original title retains CLV.

Supporting software is listed in `pyproject.toml` and `uv.lock`. Archify is bundled separately under its own license; see its vendor directory. The references above do not imply that their authors endorse this lab or its synthetic conclusions.
