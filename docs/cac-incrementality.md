# Channel acquisition holdouts and customer value

Experiments have one role in this edition: estimate the cost of additional acquisitions through Search and Partner. Describe the design and acquisition results upfront, then connect iCAC to contribution LTV in the report finale. Do not reintroduce experimental revenue, retention, journey interventions, program-pooled iCAC, or lifetime treatment-effect decompositions.

## Frozen acquisition-only source

`data/channel_holdouts.csv` is an original synthetic, arm-level acquisition export. Six monthly enrollment waves, July–December 2025, each contain four channel × baseline-need tests. Every test assigns 500 never-paid prospects to treatment and 500 to its own control. All 24,000 prospects are disjoint across the 24 tests. Every window lasts exactly 31 days, with an exclusive end. Count first paid acquisitions through every route, retaining nonbuyers in assignment totals. There are no person identifiers, subsequent revenue or retention outcomes.

The tests use separate research samples and budgets outside the 5,703-customer operational panel. Do not append their acquisitions to operating cohort counts, allocate their spending to operational customers, or join assignment to the LTV model. Dataset 5.1 preserves the seven operational CSVs and the complete original July export byte for byte; it appends 40 arm rows for August–December. The data manifest records prior hashes, preserved prefix length and unchanged files. The operational model inputs remain identical, permitting verified fit reuse without rewriting the original fit receipts.

All 48 arm totals are frozen inputs, not results drawn from the fitted LTV model. The original July wave remains:

| Test | Channel | Need | Assigned T/C | Buyers T/C | Treatment media / other cost |
|---|---|---|---|---|---|
| CH-01 | search | save_time | 500/500 | 90/40 | $10,000 / $1,000 |
| CH-02 | search | build_skill | 500/500 | 84/35 | $10,000 / $1,000 |
| CH-03 | partner | save_time | 500/500 | 80/40 | $10,000 / $1,000 |
| CH-04 | partner | build_skill | 500/500 | 100/35 | $10,000 / $1,000 |

Every wave uses $10,000 media plus $1,000 other incremental cost per treatment arm; control focal spending is zero. Spending is $44,000 per enrollment wave and $264,000 over six waves. These are supplied synthetic teaching observations; random assignment is a design attribute, not a claim that a real campaign ran. The public analysis reproduces all results from frozen exports without a private generator or future evaluation labels.

## Continuous testing and the two clocks

Enroll fresh, disjoint prospects on the first of each month. Preserve each assignment for the full window; analyze at its scheduled end, not when a favorable result appears. July closes August 1; August closes September 1; September closes October 2; October closes November 1; November closes December 2; December closes January 1, 2026. The last result is available at the report cutoff. Calendar-month labels refer to enrollment, not premature results at the next month's first day.

`channel_cac.csv` preserves every completed test. `channel_cac_current.csv` selects each channel/need cell's latest completion date, irrespective of lift direction or significance. Validation rejects incomplete windows, a duration other than 31 days and ambiguous same-cell completion dates. An unfavorable current result must not be replaced with an older favorable result. Nonpositive lift has undefined iCAC and warrants holding expansion, not fabricating a finite price. Do not pool waves or channels, assume July's cost persists, or introduce repeated peeking/optional stopping.

At each monthly spending review, update acquisition cost from completed windows and contribution value as operating cohorts mature. The cost clock is 31 days; the value clock requires six observed monthly receipts for a common benchmark. Preserve the latest eligible value cohort rather than pretending the December acquisition tests have six observed receipts. Retain holdouts when spending, campaign or eligibility changes; document the changed operating conditions. Monthly repetition is this case's chosen design, not a cadence prescribed by Larsen.

Fund the research program explicitly. Operational company tables exclude both research spending and subsequent research-customer contribution. Their surplus is not complete company cash flow. Show the recurring research budget in company economics and management action, with its full reconciliation in the appendix; do not subtract it alone and label the result total company profit.

## Acquisition calculations

Canonical saved DuckDB SQL produces `channel_cac.csv`. Let k = N_T/N_C, expected background buyers = k B_C, additional buyers = B_T − k B_C, and additional acquisition spending = S_T − k S_C. Here S includes focal media plus other incremental acquisition costs. Credited CAC = S_T/B_T is a transparent attribution-style benchmark; iCAC = additional spending / additional buyers for positive lift. Background means without the focal campaign, not free of all marketing. There is no program-pooled or company-wide incremental CAC.

Each test estimates its own channel/audience response at its recorded dose. It is not a randomized comparison between channels or an entire marginal cost curve. The approximate 95% lift interval uses unpooled Bernoulli standard errors over all assigned prospects; invert only its positive part with costs fixed. If it crosses zero, no finite upper iCAC bound is reported. These are per-test intervals, not simultaneous coverage across 24 tests. Show the cost history and latest descriptive results upfront; preserve every wave's counts, credited CAC, iCAC and intervals in the appendix. The trend does not identify why acquisition cost changed.

## Join to LTV only at the end

`channel_value_decision.csv` joins saved `channel_cac_current.csv` to saved `cohort_valuation_by_segment.csv` by channel and baseline need, using the latest common cohort with at least six observed receipts in every tested cell. At this cutoff, current tests enrolled in December and the value benchmark is July 2025. Keep both dates explicit. LTV is discounted contribution over twelve receipts, before acquisition cost, with forecast share shown. No experimental input enters retention or revenue estimation. The report compares July and current acquisition costs at the same current value benchmarks to isolate the consequence of updating iCAC; that is not a reconstruction of the information available for a July decision.

Planning value per additional customer = contribution LTV before CAC − iCAC. Total planning net value = additional buyers × assumed contribution value − additional acquisition spending. Assume additional pilot customers have the matching operational cohort's value, and that the campaign does not alter the value of customers who would acquire anyway. This is an assumption-based projection, not an experimentally identified lifetime return. Do not subtract iCAC from net LTV, which already deducts CAC. iCAC is also the break-even contribution-value threshold for this projection.

Call the accounting measure **historical average CAC**: recorded operating acquisition spending divided by all first-paid customers in that cohort. It is not an incremental estimate. Retain the lab's undiscounted cash-payback convention; course discounted payback is different. Restore historical CAC once to the saved cash path, then compare cumulative contribution with current iCAC. Neither LTV nor the monthly series establishes an optimal budget curve.

## Course connection and citation

Larsen (2019), “You Don't Know Your Customer Acquisition Cost,” motivates the background-inflow correction and the distinction between average and marginal acquisition cost. MBA 743 Topic 3, slides 6–10, covers that discussion; Topic 4 connects customer contribution, acquisition cost and payback. Use explicit author-year citations in the report and the references list. The article and course slides are not redistributed; see [sources](sources.md).
