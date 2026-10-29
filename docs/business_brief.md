# Studio North: customer economics and capital allocation

Studio North sells a monthly creative-work membership to independent professionals. Its template library helps members finish recurring work faster; guided learning helps members develop new skills. Standard and premium plans generate recurring subscription revenue, while workshops and other add-ons generate additional purchases. Customers can renew or leave each month. The business and all source records are fictional.

Management is reviewing the next acquisition budget and the pace of expansion. The central decision is:

> Are we moving in the right direction as a company? Are successive customer cohorts becoming more valuable relative to what we spend to acquire them?

Customers state their primary need as **saving time** or **building skills** before acquisition. Search campaigns reach people actively seeking help; partner campaigns reach members through professional communities and workshops. The data also contain organic purchases made by experimental control participants. These are observed acquisition labels, not proof that a channel caused a member's long-run value.

The two needs suggest different reasons to renew. A professional facing an immediate deadline may value a fast finished output; someone developing a capability may value a sequence of lessons and future projects. These are plausible business explanations to assess against the data, not assumptions that all members of a group behave alike. The baseline stated need and original acquisition channel remain fixed attributes for analysis even when later experience changes.

One broad experience map introduces discovery, evaluation, subscription, first value, regular use and renewal, with potential benefits and friction points. It is an orientation to the service, not a measured satisfaction curve or a separate journey for each segment. The analytical question remains whether later joining cohorts improve within comparable groups as well as through a changing customer mix.

The operating team provides eight separate exports from CRM, billing, renewals, product/support, surveys, marketing spending, attribution, and campaign experiments. Their shared keys allow ordinary record linkage, but their row units and clocks differ. DuckDB SQL turns these records into saved, reconciled analytical views. Those views support the management assessment and remain available for independent review.

## Comparison rules

- Joining cohorts run from **January 2024 through December 2025**. The observation cutoff is **January 1, 2026, 00:00 UTC**, exclusive. Later cohort ages have not happened yet; they are not zero outcomes.
- A customer joins a cohort on their first successful positive payment. A later refund reduces value but does not erase the acquisition. CRM creation and experiment assignment are separate events.
- `age_month = 0` is the first-paid calendar month. The core dataset has one individual subscription per person and no reactivation. Renewal records establish contractual retention; product usage and paying activity are different measurements.
- Revenue reflects payments, discounts, and separately dated refunds. Contribution deducts explicit nonmarketing variable costs. Compare values per original acquired customer, not only among survivors.
- Acquisition spending includes the documented media and other acquisition costs. Campaigns are monthly and explicitly target a primary-need group. Do not silently redistribute their costs across other segment definitions.
- Compare LTV using a **12-month horizon** and a **1% monthly discount rate**, with each month's contribution treated as received at month end (`t = age_month + 1`). Distinguish value before CAC from net value after CAC.
- Cash payback uses cumulative **undiscounted** contribution against acquisition cost. A cohort that pays back in its first-paid month has a payback period of one month. Payback and discounted LTV answer different questions.
- Fixed operating expenses are outside the dataset. The conclusion concerns customer economics and company growth, rather than a complete accounting-profit forecast.

## Decisions for the management team

1. Determine whether newer cohorts create more contribution value relative to acquisition spending and recover that spending fast enough to support growth.
2. Distinguish a shift toward stronger customer/channel groups from improvement within those groups. Use simple, interpretable segments and preserve residual differences among their members.
3. Decide where to continue, constrain, or test acquisition spending. Separate randomized campaign evidence from descriptive channel economics and forecasts for immature cohorts.
4. Assign monitoring responsibilities and conditions for revisiting the recommendation. Growing revenue alone does not establish improving unit economics or sustainable company cash generation.

The executive report labels conclusions as **observed**, **forecast**, or **assumed**. Its opening recommendation is backed by the cohort and acquisition evidence; model details, parameters, data classifications, and reproducibility receipts follow in technical appendices. A mixed or uncertain conclusion is appropriate when the evidence supports it. Fixed costs and the causal long-run value of advertising remain outside what these exports establish.
