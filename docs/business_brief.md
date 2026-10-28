# The company question

You are reviewing a fictional consumer subscription service. Management wants to know:

> Are we moving in the right direction as a company? Are successive customer cohorts becoming more valuable relative to what we spend to acquire them?

The service offers standard and premium monthly plans and optional add-on purchases. Customers describe their primary need as **saving time** or **building skills**. Search and partner campaigns acquire customers. The data also contain organic purchases made by experimental control participants.

You receive eight separate exports from CRM, billing, renewals, product/support, surveys, marketing spending, attribution, and campaign experiments. They contain original synthetic records with documented shared keys. Your task is to build and inspect the evidence through DuckDB SQL, rather than begin with a supplied cohort dashboard.

## Comparison rules

- Joining cohorts run from **January 2024 through December 2025**. The observation cutoff is **January 1, 2026, 00:00 UTC**, exclusive. Later cohort ages have not happened yet; they are not zero outcomes.
- A customer joins a cohort on their first successful positive payment. A later refund reduces value but does not erase the acquisition. CRM creation and experiment assignment are separate events.
- `age_month = 0` is the first-paid calendar month. The core dataset has one individual subscription per person and no reactivation. Renewal records establish contractual retention; product usage and paying activity are different measurements.
- Revenue reflects payments, discounts, and separately dated refunds. Contribution deducts explicit nonmarketing variable costs. Compare values per original acquired customer, not only among survivors.
- Acquisition spending includes the documented media and other acquisition costs. Campaigns are monthly and explicitly target a primary-need group. Do not silently redistribute their costs across other segment definitions.
- Compare LTV using a **12-month horizon** and a **1% monthly discount rate**, with each month's contribution treated as received at month end (`t = age_month + 1`). Distinguish value before CAC from net value after CAC.
- Cash payback uses cumulative **undiscounted** contribution against acquisition cost. A cohort that pays back in its first-paid month has a payback period of one month. Payback and discounted LTV answer different questions.
- Fixed operating expenses are outside the dataset. The conclusion concerns customer economics and company growth, rather than a complete accounting-profit forecast.

## Your judgments

1. Which simple baseline segmentation helps explain variation in customer behavior and value? State a reason first, then check it on older, comparable cohorts.
2. What do the observed cohort curves, acquisition costs, and company layers suggest about the firm's direction? Distinguish a changing customer/channel mix from improvement within groups.
3. Does experimental evidence or the forecast for young cohorts change your verdict? Recommend an action and state what future evidence would cause you to reconsider.

The final report should label conclusions as **observed**, **forecast**, or **assumed**. A mixed verdict or “too early to tell” is acceptable when it follows from the evidence. Keep the experiment's eligible prospects and controls intact; a descriptive cohort trend does not establish the cause of that trend.
