# Segmentation, acquisition cost and the relevant value

This revision connects Studio North to MBA 743's existing teaching without changing its released data or fitted models. The two acquisition holdouts are retained: their purpose is to estimate acquisitions and contribution caused by the tested campaign among all assigned prospects, including nonbuyers.

## Segmentation objective

Seek within-cell homogeneity and across-cell heterogeneity in the outcome relevant to the decision. For a fixed population and outcome horizon, total population variance equals customer-weighted within-cell variance plus variance between cell means. Reducing one increases the other. Compare candidate partitions with the same number of cells; adding cells can mechanically improve in-sample separation.

The four candidate partitions use the same 4,278 mature, nonexperimental paid customers, two cells each, and six-receipt contribution including zeros after exit. Stated need has the largest between-cell share, 8.31% (8.09% after cohort centering). The other 91.69% remains within need cells. This is descriptive separation in outcome levels, not evidence about treatment-response heterogeneity or validated future prediction. Recognizability, adequate cell size and actionability still matter. The four channel-by-need acquisition cells and post-acquisition journey diagnostics serve different purposes and are not ranked as comparable candidates here.

MBA 743 Topic 1, *Customer Journeys*, slides 30–39 distinguishes intrinsic heterogeneity from the firm's segmentation. Slides 37–39 compare equal-complexity partitions of the same people. The slide uses average absolute deviations; this report uses population variance to obtain an additive decomposition. In the slide's $20/$30/$70/$80 example, grouping (20,80)/(30,70) gives within/between variance 650/0; grouping (20,30)/(70,80) gives 25/625. That example does not imply demographic segmentation is always superior.

## Three acquisition-cost quantities

| Quantity | Numerator and denominator | Supported use |
|---|---|---|
| Observed blended CAC | Matching recorded media plus other acquisition spending / all acquired cohort customers | Cohort accounts alongside those customers' contribution LTV |
| Attribution-style test CAC | Treatment media spending / all treated-arm buyers | Transparent campaign-credit benchmark, not a newly estimated last-click metric |
| Test media iCAC | Incremental media spending / incremental buyers | The randomized population, campaign dose and follow-up actually tested |

Let k = N_T/N_C. Expected background buyers at treatment scale are k B_C, incremental buyers are ΔB = B_T − k B_C, and incremental media cost is ΔS = S_T − k S_C. For positive lift, iCAC = ΔS/ΔB. When control cost is nonzero, both sides of the attribution-to-incrementality bridge must change.

| Test | Assigned T/C | Buyers T/C | Media | Credited CAC | Incremental buyers | Media iCAC |
|---|---:|---:|---:|---:|---:|---:|
| Search / save time, May 2025, 31 days | 250/250 | 73/25 | $650 | $8.90 | 48 | $13.54 |
| Partner / build skill, September 2025, 30 days | 250/250 | 61/29 | $900 | $14.75 | 32 | $28.13 |

The first contrast is $0 versus $2.60 media per assigned prospect; the second is $0 versus $3.60. Control media and other acquisition-cost entries for these campaigns are zero. Background acquisitions mean purchases expected without this focal campaign, with other marketing and brand conditions unchanged; the source's organic label does not identify a globally marketing-free population. Random assignment is evaluated among everyone assigned, not only clickers or buyers.

The sum of separately standardized effects gives 80 incremental buyers for $1,550: $19.375 media iCAC for **these two campaigns as run**. Its weights depend on the chosen doses and arm sizes. It is not a whole-company estimate, a universal channel correction, a channel ranking, or the marginal CAC of the next advertising dollar. No global holdout identifies incremental CAC for all 24 cohorts. Coordinated portfolio holdouts would need to address overlap, substitution and interactions; a marginal cost curve additionally needs evidence across spending levels.

The approximate 95% normal buyer-lift interval is inverted with recorded spending fixed. The media-iCAC intervals are $10.02–$20.89 and $18.52–$58.45; the independent-test program interval is $14.95–$27.52. If a lift interval crosses zero, its positive region gives no finite upper iCAC bound. These are not simultaneous intervals or uncertainty about future spend. A bounded iCAC does not establish profit.

## Which CAC belongs with LTV?

For cohort accounting, use average discounted contribution **before acquisition cost**, less matching observed blended CAC. This allocates exactly the recorded total cost once. Replacing CAC with spend/incremental buyers while charging every acquired customer would overallocate that cost. The lab's net twelve-receipt LTV already subtracts blended CAC: do not subtract iCAC again or divide that net value by iCAC and call it a causal acquisition return.

For the intervention, let V_H be contribution before acquisition cost for each assigned prospect over the same H from assignment and under one stated discount convention. The decision is ΔV_H − ΔS_H, with all additional acquisition costs included. For positive ΔB:

`ΔV_H − ΔS_H = ΔB × (ΔV_H/ΔB − iCAC)`.

Thus the consistent per-incremental-acquisition comparison is incremental contribution per incremental acquisition versus iCAC. In the existing undiscounted 30/31-day ledgers, the point decompositions are $23.47 versus $13.54 for Search and $25.47 versus $28.125 for Partner. Incremental contribution divided by incremental media is 1.73 and 0.91. Net effects are $476.70 and −$84.95, with existing 95% intervals $8.74–$944.66 and −$582.67–$412.77. The contribution-per-incremental-buyer ratios are point decompositions only; ratio uncertainty would require the joint value/lift distribution. Existing net-contribution intervals remain the inferential statements.

Reading ΔV_H/ΔB as the LTV of induced buyers requires extra assumptions, including monotone acquisition response and no effect on spending or retention among people who would buy anyway. Buying and value must be counted to the same H under the same regime. Average treated-buyer LTV mixes induced and would-buy-anyway buyers. Multiplying it by lift, or comparing test iCAC to a six-receipt segment mean, is not a causal or horizon-matched valuation.

Control protection is documented only through each prespecified 30/31-day window. Later transactions do not establish a long-run counterfactual. The short-run effect is not a lower bound on lifetime value: purchase timing can be pulled forward and controls can catch up, while retention can add value. A longer protected experiment could estimate discounted contribution for all assigned prospects. A model extrapolation requires additional explicit, testable assumptions. The existing cohort model's twelve receipts start at acquisition, not assignment, and do not supply that causal effect.

MBA 743 Topic 3, *Acquisition Metrics*, slides 6–10 introduces Larsen and cost curves; slides 23–25 emphasizes all-assigned comparisons; slides 32–34 shows why buyer lift and revenue returns need contribution economics. Topic 4, *Lifetime Value Metrics*, slides 3 and 31 separates value before and after CAC. Slides 30 and 35 use **discounted contribution payback**. The lab's existing **undiscounted cash payback** is explicitly labeled and retained.

## Sources

- Kim Larsen (May 14, 2019), [You Don't Know Your Customer Acquisition Cost](https://blog.usejournal.com/you-dont-know-your-customer-acquisition-cost-f7bf820f9d4a), Noteworthy / The Journal Blog. The assigned course PDF was checked; it is not redistributed. See the [source record](../assets/articles/larsen-2019-customer-acquisition-cost/README.md).
- Longxiu Tian (2026), *MBA 743: Managing Customer Data*, Mod II, Kenan-Flagler Business School: Topics 1, 3 and 4, slides and pre-lecture notes. Course materials remain in their course distribution.

Implementation and frozen-artifact checks are documented separately in [version 6 changes](v6-changes.md).
