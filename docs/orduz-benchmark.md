# The Orduz-derived neural retention comparison

This repository implements a genuine Bayesian neural network as a **separate retention benchmark**. It does not relabel a linear regression as Juan Orduz's model. The executive LTV forecast uses the report's stated hierarchical survival and revenue models; the neural comparison provides an additional empirical check on the retention component.

## What comes from the source

Juan Orduz's [Cohort Revenue Retention Analysis with Flax and NumPyro](https://juanitorduz.github.io/revenue_retention_numpyro/) combines a small Bayesian retention network with a revenue model. Its network has four sigmoid hidden units and a sigmoid output, with Laplace priors on weights and biases. This repository implements that mathematical architecture directly in NumPyro/JAX, so Flax is unnecessary. It is an explicit adaptation rather than a verbatim reproduction of his notebook.

## What this business requires us to change

Studio North has absorbing monthly contractual churn. Once someone leaves, the person cannot reappear as a retained member. Repeated cumulative survivor counts therefore cannot be treated as independent replications with the original acquired-customer denominator. The adapted likelihood uses each month's observed risk set:

\[
d_{g,t}\sim\operatorname{Binomial}(n_{g,t-1},q_{g,t}),\qquad
q_{g,t}=\sigma\!\left(\sigma(x_{g,t}W+b)v+a\right),
\]

where `d` is the number leaving, `n` is the number still active, `g` identifies entry cohort × stated need × channel, and `sigma` is the sigmoid function. All 73 weights and biases have independent Laplace(0,1) priors. This model describes a group's hazard; it does not recover the true hidden propensity of an individual customer.

There are 16 fixed input features:

| Features | Transformation |
| --- | --- |
| Customer age | `age_month / 23` |
| Acquisition cohort | `(cohort_index − 11.5) / 11.5` |
| Pre-acquisition need | `build_skill` indicator; `save_time` reference |
| Acquisition channel | `partner` and `organic` indicators; `search` reference |
| Calendar month | February–December indicators; January reference |

Fixed transformations require no scaling statistics from the holdout period. The network does not use latent simulation propensities, mixture labels, future outcomes or data-generation parameters. The true calendar shock is not supplied as an input.

## Inference and fair comparison

The network is fitted once to observations through September 2025 using NumPyro SVI, an AutoNormal guide, ClippedAdam at learning rate 0.01, 10,000 optimization steps and 400 approximate posterior draws. The reproducible seed is the run seed plus 300. Execution uses CPU and float64.

October–December predictions start from each eligible group's September membership count and multiply successive predicted renewal probabilities. They never reset to the actual October or November survivor counts. New cohorts acquired during the holdout period are excluded because they have no September origin. The three-month window matches the main retention backtest.

`tables/orduz_benchmark.csv` contains held-out actual counts, mean expected survivor forecasts and 5th–95th parameter-uncertainty bands. `benchmark_summary.json` records architecture, transformations, priors, settings, train/holdout hashes, MAE, WAPE, numerical diagnostics, implementation hash and package versions. Lower MAE indicates more accurate count forecasts for this specific window; the comparison is reported even when the neural model performs worse.

## Limits and verification

These bands exclude future customer-level renewal noise, so they are not full posterior predictive intervals. Stable finite SVI losses do not establish exact posterior convergence, and mean-field variational inference can understate uncertainty. Neural weights are not interpretable causal effects. A single three-month backtest does not validate all future regimes or prove that a retention intervention will work.

Tests verify the nonlinear hidden-layer calculation against an independent formula, the fixed feature design, conditional risk sets, recursive forecasts, rejection of invalid panels and minimum optimization budgets, and unchanged forecasts when held-out outcomes are altered. The release's fresh-process reproducibility check additionally compares the saved benchmark artifacts.
