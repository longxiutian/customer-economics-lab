# Studio North: source-data simulation and model separation

Studio North is a fictional monthly creative-work membership for independent professionals. Some members primarily want ready-to-use templates to save time; others want guided learning to build skills. Standard membership costs $50 per month and premium membership costs $75. Members can upgrade and buy paid workshops or other add-ons. Search campaigns and partner relationships acquire customers. Membership renews monthly until cancellation or payment failure; there is no reactivation in this dataset.

The decision is whether successive acquisition cohorts are moving the company toward better acquisition efficiency, durable contribution and faster recovery of acquisition spending. More revenue alone does not answer that question. We need to distinguish acquisition volume, acquisition mix, retention, expansion and contribution costs, comparing cohorts at common ages.

## Observation design

- There are exactly 24 first-paid monthly acquisition cohorts, January 2024 through December 2025.
- The observation cutoff is January 1, 2026, exclusive. The January 2024 cohort has 24 observed monthly membership opportunities, including its acquisition month; December 2025 has only its acquisition month.
- A customer pays in the acquisition month, age zero. At every subsequent scheduled month, a still-active customer makes a renewal decision. Cancellation or failure ends the subscription permanently.
- For customers active at the cutoff, the January 2026 pending period is an operational scheduling record. It is **not** an observed renewal or a future zero. SQL excludes it from observed retention.
- CRM also contains randomized eligible prospects who never buy. They stay in experiment denominators but never enter an acquisition cohort.

## Persistent heterogeneous churn

The behavioral foundation follows the shifted Beta-Geometric approach: an individual has a persistent underlying propensity to leave, while different individuals have different propensities. The lab deliberately extends the simple single-Beta population into a **mixture of two Beta distributions**.

At acquisition, draw one latent component and then one propensity:

\[
z_i \sim \operatorname{Bernoulli}(w_{c,s,k}),\qquad
\theta_i\mid z_i=0\sim\operatorname{Beta}(0.7,12),\qquad
\theta_i\mid z_i=1\sim\operatorname{Beta}(2,5).
\]

Here, `c` is acquisition cohort index 0–23, `s` is the pre-acquisition stated need, and `k` is acquisition channel. The component with larger average churn propensity has weight

\[
w_{c,s,k}=\operatorname{clip}\!\left(b_s+d_k-0.06c/23+0.02\sin(0.6c),\;0.05,\;0.85\right).
\]

| Assumption | Value |
| --- | --- |
| `b_save_time` | 0.40 |
| `b_build_skill` | 0.24 |
| `d_search` | +0.04 |
| `d_partner` | −0.04 |
| `d_organic` | 0.00 |
| Durable component mean churn propensity | 0.7 / 12.7 ≈ 0.055 |
| Fragile component mean churn propensity | 2 / 7 ≈ 0.286 |

These latent components are simulation devices, **not** observable customer segments or the two stated needs. Every observed need/channel group contains continuous residual heterogeneity. Each customer draws `theta` only once; the generator never redraws it at renewal. A falling cohort churn rate can therefore arise because higher-propensity customers have left, without any individual's underlying propensity improving.

In ordinary months, renewal conditional on still being active is Bernoulli with probability `1 − theta`. A temporary service disruption in March and April 2025 multiplies churn odds by 1.35:

\[
q_{i,t}=\frac{m_t\theta_i}{1-\theta_i+m_t\theta_i},\qquad
R_{i,t}\mid R_{i,t-1}=1\sim\operatorname{Bernoulli}(1-q_{i,t}),
\]

where `m_t = 1.35` in those two calendar months and 1 otherwise. The same original `theta` remains in force after the disruption. This distinguishes a common calendar shock from acquisition-cohort age and makes a stationary single-Beta specification an approximation.

## Revenue, costs and acquisition

Customer survival and revenue retention are different processes. Retained members can upgrade from standard to premium; add-on quantities depend on tenure and stated need. Initial discounts reduce transaction revenue, and refunds are separate ledger events linked to original payments. Costs remain recorded when a payment is partially refunded. Positive membership revenue is required for every paid member-month in this business.

Acquisition budgets are determined separately from realized customer counts. Planned CAC trends downward, while realized counts vary. The proportion acquired through partners and the share seeking skill development also change over time. Both mix shifts and changes within observed groups can contribute to aggregate improvements; the analyst must not attribute all movement to one mechanism.

The two acquisition experiments randomize eligible prospects into balanced treatment and control arms. The tests have their own control groups, pre-acquisition attributes and fixed follow-up windows. Treatment effects on acquisition and short-window revenue do not identify the causal effect of a hypothetical retention intervention.

## Separation from inference

The eight observed CSV exports do **not** contain `theta`, the latent mixture component, future renewals, or latent lifetime value. The data manifest records simulation assumptions for provenance, but the inference model must use only observed SQL-derived cohort cells and its declared predictors. It must not read simulation parameters to initialize, calibrate or select the fitted result.

The mixture population, changing composition and calendar disruption are intentionally richer than a single-Beta survival model. A Bayesian neural retention model would also be an approximation to these individual-level mechanisms. The simulation is not changed until a chosen model produces a desired error. A good fit is allowed; exact recovery is neither assumed nor the release criterion. The important checks are accounting integrity, absence of future/latent leakage, temporal holdout performance, uncertainty and a reproducible path from source records to decisions.

## Reproducibility and tests

`cohort_lab.data.generate_data` uses one standard-library `random.Random` generator with frozen seed `20261116`. Currency is generated in integer cents. The public release includes the frozen CSVs and SHA-256 manifest, so normal student use does not regenerate data. Changing the generator is a dataset revision, not a silent preprocessing step.

Automated tests check one latent draw per acquired customer; theoretical mixture mean and variance against independent simulation; declining aggregate hazard by survivor selection; the calendar shock's odds calculation; exactly 24 acquisition cohorts; consecutive monthly periods and absorbing churn; pending versus observed periods; exclusion of latent truth from observed columns; and byte-for-byte regeneration of all frozen exports and metadata. Independent hand-ledger tests verify refunds, contribution, CAC, payback and experiment denominators.

## Methodological sources

- Lee, Fader and Hardie, *How to Project Patient Persistency* (2007), and the related [Fader–Hardie retention-model resources](https://www.brucehardie.com/notes/016/): persistent individual dropout propensity and survivor selection. The published single-Beta example is not a parameter recommendation for Studio North.
- Juan Orduz, [Revenue Retention Modeling with NumPyro](https://juanitorduz.github.io/revenue_retention_numpyro/): separating active-customer retention from revenue dynamics and performing Bayesian prediction. The report's model appendix specifies the actual inference model and its adaptations; these data are not generated from that fitted model.

All eight source exports are original synthetic records. No private assignment, real customer record or licensed case dataset is redistributed.
