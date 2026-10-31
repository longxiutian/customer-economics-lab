# Channel acquisition holdouts and customer value

Experiments have one role in this edition: estimate the cost of additional acquisitions through Search and Partner. Describe the design and acquisition results upfront, then connect iCAC to contribution LTV in the report finale. Do not reintroduce experimental revenue, retention, journey interventions, program-pooled iCAC, or lifetime treatment-effect decompositions.

## Frozen acquisition-only source

`data/channel_holdouts.csv` is an original synthetic, arm-level pilot export. Four disjoint tests cover channel × baseline need. Each assigns 500 never-paid eligible prospects to treatment and 500 to its own control, July 1–August 1, 2025 (31 days, end exclusive). Count first paid acquisitions through every route. Nonbuyers remain in assignment totals. The source supplies no person identifiers, subsequent revenue, or retention outcomes.

The pilot is a separate research sample and budget, outside the operational cohort panel. Do not append pilot acquisitions to cohort counts, allocate pilot spending to operational customers, or join assignment to the LTV model. The operational panel contains 5,703 customers after removal of the legacy experimental prospects and their linked records. Its retained raw rows are byte-identical to the preceding release.

For reproducibility the pilot totals are frozen inputs, not results drawn from the fitted LTV model:

| Test | Channel | Need | Assigned T/C | Buyers T/C | Treatment media / other cost |
|---|---|---|---|---|---|
| CH-01 | search | save_time | 500/500 | 90/40 | $10,000 / $1,000 |
| CH-02 | search | build_skill | 500/500 | 84/35 | $10,000 / $1,000 |
| CH-03 | partner | save_time | 500/500 | 80/40 | $10,000 / $1,000 |
| CH-04 | partner | build_skill | 500/500 | 100/35 | $10,000 / $1,000 |

Control focal spending is zero. These are supplied teaching observations; random assignment is a design attribute of the synthetic source, not a claim that a real campaign ran. The generation of historical membership records and private future evaluation labels remains outside the public analysis workflow. The manifest records the dataset migration and pilot design; every downstream result starts from the released CSVs.

## Acquisition calculations

Canonical saved DuckDB SQL produces `channel_cac.csv`. Let k = N_T/N_C, expected background buyers = k B_C, additional buyers = B_T − k B_C, and additional acquisition spending = S_T − k S_C. Here S includes focal media plus other incremental acquisition costs. Credited CAC = S_T/B_T is a transparent attribution-style benchmark; iCAC = additional spending / additional buyers for positive lift. Background means without the focal campaign, not free of all marketing. There is no program-pooled or company-wide incremental CAC.

Each test estimates its own channel/audience response at its recorded dose. It is not a randomized comparison between channels or an entire marginal cost curve. The approximate 95% lift interval uses unpooled Bernoulli standard errors over all assigned prospects; invert only its positive part with costs fixed. If it crosses zero, no finite upper iCAC bound is reported. The main report lists the results descriptively; uncertainty detail belongs in the appendix.

## Join to LTV only at the end

`channel_value_decision.csv` joins saved `channel_cac.csv` to saved `cohort_valuation_by_segment.csv` on July 2025, channel and baseline need. Six receipts are observed in that value benchmark. LTV is discounted contribution over twelve receipts, before acquisition cost, with forecast share shown. No experimental input enters retention or revenue estimation.

Planning value per additional customer = contribution LTV before CAC − iCAC. Total planning net value = additional buyers × assumed contribution value − additional acquisition spending. Assume additional pilot customers have the matching operational cohort's value, and that the campaign does not alter the value of customers who would acquire anyway. This is an assumption-based projection, not an experimentally identified lifetime return. Do not subtract iCAC from net LTV, which already deducts CAC. iCAC is also the break-even contribution-value threshold for this projection.

Retain observed blended CAC for the matching historical cohort accounts. Retain the lab's undiscounted cash-payback convention; course discounted payback is a different convention. Neither an LTV estimate nor one channel test establishes an optimal budget allocation.

## Course connection and citation

Larsen (2019), “You Don't Know Your Customer Acquisition Cost,” motivates the background-inflow correction and the distinction between average and marginal acquisition cost. MBA 743 Topic 3, slides 6–10, covers that discussion; Topic 4 connects customer contribution, acquisition cost and payback. Use explicit author-year citations in the report and the references list. The article and course slides are not redistributed; see [sources](sources.md).
