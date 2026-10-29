# From renewal records to retention and contribution value

## Business mechanism before forecasts

Studio North is a contractual monthly membership. Acquisition establishes period zero. Each later paid period requires a successful renewal. Cancellation is absorbing in this dataset; a future scheduled renewal is still unobserved. This differs from a noncontractual shopping business where an inactive customer can return.

Within a cohort, customer need and acquisition channel, members have different persistent propensities to churn. The main inference model represents those differences with one Beta distribution. More fragile members tend to leave earlier, so the remaining group can have a lower average churn rate even though each member's underlying propensity stays constant. These are model-based distribution estimates, not individually observed propensities or evidence of a causal loyalty intervention.

## Retention specification

For acquisition cohort k, need g and channel m, let mu be mean individual churn propensity and phi be concentration. Define alpha = mu × phi and beta = (1 − mu) × phi. The individual propensity variance is mu × (1 − mu)/(phi + 1).

The probability of surviving t renewals is B(alpha, beta + t)/B(alpha, beta). Conditional churn at renewal t ≥ 1 is alpha/(alpha + beta + t − 1). The number of renewals is Binomial(previous survivors, 1 − conditional churn). This conditional likelihood uses each at-risk renewal decision once. It does not independently resample the original cohort's cumulative survivors every month.

Mean propensity uses a logit regression with need, channel, a centered acquisition-month trend and a shared cohort random effect. Concentration uses a log regression with need and channel. Cohort effects are partially pooled through a half-Normal scale. December 2025 has no observed renewal decisions: its retention estimates borrow information from other cohorts and its covariates. Future ages and pending records contribute no failure events.

The retention cohort trend is `(cohort_index − 11.5)/11.5`, with January 2024 indexed zero. The revenue trend retains `(cohort_index − 11.5)/12`; its log-age feature is `log(1 + age_month)`. Search and saving time are the reference categories. These exact transforms accompany coefficient interpretation.

| Parameter block | Prior | Meaning |
|---|---|---|
| Mean intercept | Normal(−2.5, 1) | Baseline log-odds of individual monthly churn |
| Mean covariate coefficients | Normal(0, 0.5) | Need, channel and cohort-trend differences |
| Log-concentration intercept | Normal(log(4), 1) | Baseline dispersion at a given mean |
| Log-concentration covariates | Normal(0, 0.5) | Need/channel differences in dispersion |
| Cohort effect scale | HalfNormal(0.25) | Variation around the shared trend |
| Standardized cohort effects | Normal(0, 1) | 24 cohort deviations, multiplied by the scale |

The retention covariates are a fixed whitelist. Latent simulator variables, future outcomes, usage after acquisition and survey responses do not enter the fitted model.

### Prior provenance and information from the data

The `Normal(log(4), 1)` prior for the log-concentration intercept was selected during the Opus-assisted model-design review **before the first inference fit**. It was not estimated from, moment-matched to, or calibrated against hidden generator parameters. Its standard deviation of 1 on the log scale allows a broad range of baseline concentrations; concentration is not fixed at 4.

The release's `parameter_summary.csv` records posterior means, standard deviations, intervals and diagnostics. Compare these with the stated priors to assess how much the observed renewal records inform the parameters; this is not evidence that the model recovers an unobserved true distribution.

## Revenue and contribution

Gross payment revenue follows a Gamma distribution. Its shape equals retained members × a positive dispersion parameter; its rate makes expected revenue equal retained members × expected gross revenue per retained member. Log expected member revenue uses log(1 + age), cohort trend, need and channel. Revenue is modeled in hundreds of dollars for numerical scaling; reported outputs are dollars.

Revenue coefficients have Normal priors with standard deviation 0.8 (intercept center −0.5, log-age center 0.1, remaining centers zero). The per-member Gamma shape has LogNormal(log(4), 0.8) prior. Recorded product prices, plan changes and add-ons generate the source revenue; the inference model does not know those latent purchasing rules.

Net revenue deducts recorded discounts and refunds. Contribution also deducts recorded nonmarketing variable costs. Forecast conversion of gross to net and contribution uses observed channel × need × age ratios, with the same group's observed renewal periods as fallback. These ratios are fixed assumptions, not estimated future cost distributions.

## Estimation and decision quantities

The main model uses NumPyro NUTS, four sequential CPU chains, float64, target acceptance 0.95, and a declared seed. The default command budget gives each chain 1,000 warmup iterations and 1,000 retained draws. Four hundred evenly spaced draws from the full sample carry parameter uncertainty into valuations. The full sample supplies parameter summaries and diagnostics.

Release requires no divergences, maximum reported R-hat ≤ 1.01 and minimum effective sample size ≥ 400. These checks address numerical sampling, not whether the business model is true. Residual dispersion and held-out errors remain visible even when unfavorable. Seeds are never changed to manufacture a better result.

Keep actual contribution for observed ages, then forecast from the last actual survivor count. Compare every cohort over twelve monthly receipts. Discount contribution at 1% monthly with the acquisition-month receipt at t = 1. Subtract tracked CAC once for net contribution value. Cash payback uses **undiscounted** contribution and one-based receipt months. A later reversal below cost is flagged separately. Twelve-month value is a specified decision horizon, not an infinite-lifetime promise.

Company CAC includes the whole acquisition spending ledger, including zero-conversion and unallocated spending. Unsupported organic-cell CAC is missing, not free. Randomized campaign evidence has its own eligible population and horizon; buyer-only LTV comparisons cannot identify causal advertising lifetime value.

## Observed-data boundary

This analysis begins with a frozen synthetic observed-data release. Its generation workflow and future evaluation outcomes are instructor-held outside this repository. Model fitting uses only the declared observed SQL outputs; it never reads simulator settings or future labels. The model is an approximation whose assumptions must be checked against observed history and chronological backtests.

The [Orduz benchmark](orduz-benchmark.md) provides a different flexible retention model on the same chronological holdout. It never supplies the executive LTV numbers. Validation compares both models with a transparent carry-forward baseline. Forecast bands in the management report describe parameter uncertainty conditional on the model and fixed economics; they omit renewal process noise, future cost uncertainty and regime change.

Full coefficients, priors, means, standard deviations, 5th–95th percentiles, R-hat and effective sample size are saved to `parameter_summary.csv`. Derived mean/variance of churn propensity by cell are saved separately. The report explains the mechanism before forecasts and places technical detail in its appendices.

## Source scope

The persistent-propensity survival mechanism is grounded in [Fader and Hardie (2007)](https://www.brucehardie.com/papers/021/); the implications of survivor selection for customer-base value are developed in [Fader and Hardie (2010)](https://www.brucehardie.com/papers/022/). The observed covariate structure, cohort random effects and Bayesian priors are explicit lab design choices. [McCarthy, Fader and Hardie (2017)](https://journals.sagepub.com/doi/10.1509/jm.15.0519) motivates linking acquisition, retention and spending to business value, but the lab does not implement that paper's complete enterprise-valuation system.

The Gamma revenue component adapts [Orduz's NumPyro walkthrough](../assets/articles/orduz-2024-cohort-revenue-retention/orduz-source-notebook.pdf), with an estimated per-member dispersion parameter and explicit conversion to contribution. The separate neural comparison uses his four-unit sigmoid architecture and Laplace weight priors, adapted to conditional contractual churn. These different roles are stated separately so the reader can distinguish source methods from this implementation's choices.
