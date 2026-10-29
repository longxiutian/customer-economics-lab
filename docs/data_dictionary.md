# Source data and accounting definitions

These are original synthetic records for **Studio North**, a monthly creative-work
membership for independent professionals. Members use reusable templates to save
time or guided learning to build skills. Standard/premium plans renew monthly;
paid workshops and other add-ons appear as separate purchases.
There are 24 first-paid joining cohorts, January 2024 through December 2025.
The exclusive observation cutoff is **2026-01-01 00:00:00 UTC**. All money is USD.
The observed exports are frozen and hash-verified. Data generation is maintained separately by the instructor; the student workflow does not require a generation seed or future outcomes. No real customer or course records are included.

`data/data_dictionary.json` contains the exact columns, types, nullability and
primary keys. `data/data_manifest.json` records file hashes, row counts, source
cutoffs, definitions and experiment designs. The loader refuses changed exports.

## Eight source exports

| File | Row meaning | Key and joins |
|---|---|---|
| `people.csv` | One person, including prospects who never buy | `person_id` joins every person-level source. Baseline attributes precede acquisition or assignment. |
| `subscription_periods.csv` | One scheduled monthly subscription cycle | `period_id`; one `subscription_id` per person. A paid outcome establishes retained membership. |
| `transactions.csv` | One payment or refund event | `transaction_id`; joins `period_id` and `person_id`. Refunds reference an earlier payment. |
| `product_events.csv` | One observed interaction | `event_id`, `person_id`. Usage is distinct from membership. |
| `feedback.csv` | One completed linked survey | `response_id`, `person_id`. Nonresponse is missing evidence. |
| `campaign_spend.csv` | One campaign per spending date | `(campaign_id, spend_date)`. Sum independently before joining outcomes. |
| `acquisition_attribution.csv` | One acquired person and credit for the first payment | `person_id`, `first_paid_transaction_id`, optionally `credited_campaign_id`. |
| `experiment_assignments.csv` | One eligible prospect in one randomized test | `(experiment_id, person_id)`. Includes nonbuyers and each test's own controls. |

The joins are deliberately ordinary, documented joins. This lab does not require
identity inference or a matching algorithm.

## Universal Customer View and the connection map

**Universal Customer View (UCV)** classifies fields, not files. The four categories
are **Identifiers, Engagement, Relationship, Perception**. The companion
[field taxonomy](ucv-tables.md) gives one four-column table per source dataset,
with every actual field appearing exactly once. It explains ambiguous operational
metadata and leaves genuinely absent categories empty. An aggregate spending
field does not become an individual customer action merely because it supports
the Engagement category.

Stage 1 regenerates `diagrams/ucv-tables.json` and `.md` from the actual source
headers, checks complete field coverage, and binds them to raw-file hashes.
`diagrams/source-tables.html` is the native Archify ERD: all columns and SQL
types, PK/FK roles, relationship cardinality, and focused views of membership,
customer experience, and acquisition. Its derived `campaign_metadata` view is
explicitly labelled; it is not a ninth raw dataset. The original spending key
is `(campaign_id, spend_date)`, while the derived view has one row per campaign.
Refund `related_transaction_id` points to the original payment in the same ledger.

The separate `diagrams/source-systems.html` overview traces raw sources through
saved DuckDB SQL views to observed cohort economics, model forecasts, randomized
test effects and the company decision. Native SVG/PNG exports accompany both
diagrams; `diagram_manifest.json` hashes all report inputs. The diagrams do not
imply a database server needs to be provisioned.

`source-systems-report.png` is a compact print edition of a separate native
Archify workflow: the same source groups, SQL transformation, evidence types and
decision, with the reader's wide background lanes omitted. Its native nodes and
edges remain intact, with fixed 12px titles and 9px context before a 2x raster
export. The detailed HTML/ERD retains all field and cardinality information.
The `source-tables-report` edition retains every field, key and relationship in
narrower cards for a readable A3 report foldout. It omits only the SQL-type column;
types remain available in the full ERD and exact data dictionary.

## People, segments and subscription status

`primary_need` is a baseline intended use: `save_time` or `build_skill`.
`age_band` is `18_34` or `35_plus`; `region` is `east` or `west`.
These alternative segmentation schemes each have two groups. A segment is not a
joining cohort. `household_type` is a descriptive `solo`/`shared` attribute; the
subscription and analytical unit remain the individual person.

The plan tier is `standard` or `premium`. Retained customers may upgrade and buy
add-ons. A cycle's `renewal_outcome` is `paid`, `cancelled`, `failed` or `pending`.
There is no reactivation in this first dataset. A future pending cycle is a
scheduling record, not an observation of future retention. Paid membership is
monotone until exit, but usage and spending vary.

## Dates, cohorts and missing future observations

The first positive successful payment defines acquisition. A later refund does
not erase that acquisition; it reduces realized revenue. CRM registration is not
acquisition. `cohort_month` is the first-paid calendar month; `cohort_index` starts
at zero for January 2024. `age_month` starts at **0** in the acquisition month.

SQL creates a complete person-month history only through the last fully observed
calendar month. Months after known exit are observed zeros. Months after the
data cutoff do not exist in the output and must not be filled with zeros. The
youngest cohort has one observed month.

In valuation, the monthly receipt for `age_month=0` is discounted at `t=1`.
Cash payback is undiscounted. `first_observed_payback_age` uses the zero-based
age index; `cash_payback_month` adds one to express the number of monthly receipt
periods. A blank observed payback means it has not been observed, not never.

## Transaction amounts

Generation uses integer cents; exported money and SQL sums use decimals.
Each payment is one order and contains one `charge_type`: `subscription` or
`add_on`. Subscription quantity is one; add-ons record their actual quantity and
unit price. On a payment, `gross_amount = quantity × unit_price`.

Refunds are separate dated rows, share the original `order_id`, and identify the
original `related_transaction_id`. They do not repeat the original gross amount,
discount or service cost. Count distinct paid orders, not ledger rows.

| Measure | Definition |
|---|---|
| `gross_payment_revenue` | Successful payment amounts **after discounts, before refunds**. The name describes the positive payment model target. |
| `net_revenue` | `gross_amount - discount_amount - refund_amount`, summed over financial events. |
| `variable_cost` | Incurred service/payment costs; count once, including when a later refund occurs. |
| `contribution` | Net revenue minus variable cost, before marketing and fixed costs. |
| `retained` | Paid scheduled subscription cycle in that month. |
| `paying` | At least one successful payment event in the month. |
| `orders` | Number of distinct payment order IDs, including add-on orders. |

In this particular dataset every paid membership cycle is billed successfully,
so retained and paying counts coincide. Their definitions remain distinct.
Recorded `core_action` activity need not occur every paid month. Revenue
retention differs from customer retention because tiers, add-on quantities,
discounts and refunds vary. Neither revenue nor contribution is company net profit.

## Acquisition spending and attribution

The channels are `search` and `partner`. Some randomized control buyers have
`organic` credit. Ordinary campaigns and experimental campaigns have separate
IDs. Every paid campaign explicitly targets one `primary_need`, so source/need
cost aggregation is supported. Spend cannot be allocated to age or region merely
in proportion to resulting conversions or revenue.

Recorded acquisition cost includes `media_spend` and campaign-specific
`other_acquisition_spend` (creative/vendor costs). Transaction discounts reduce
revenue; they are not counted again as acquisition spending. Campaign dates and
the credited acquisition month align by construction. Extending the window
across months would require an explicit cost-allocation rule.

Source/need CAC is recorded targeted spending divided by credited first-paid
customers. Organic segment CAC is **undefined**, not zero. Company-wide CAC is
all tracked acquisition spending divided by all acquired customers, including
experimental buyers and controls. It is not fully loaded company CAC, and it is
not incremental CAC. All tracked campaign expenses enter company totals once.

## Randomized experiments

`EXP-01` tests a search campaign for `save_time` prospects in May 2025.
`EXP-02` tests a partner campaign for `build_skill` prospects in September 2025.
Each assigns 250 preexisting, never-paid eligible prospects to treatment and 250
to its own control. Assignment is balanced and seeded. Profile attributes exist
before assignment. No prospect participates in both tests.

The prespecified outcome window is the assignment calendar month, ending
exclusively at the first day of the next month. The treatment spends the focal
campaign budget; control spends zero on that focal campaign. All assigned
prospects stay in the denominator, including nonbuyers. A control buyer with
organic credit still contributes to control outcomes. The two tests have
different eligible populations and cannot be treated as a randomized head-to-head
channel comparison.

SQL compares per-assigned-person outcomes and scales the control totals to the
treatment group size. It reports incremental customers, net revenue and
contribution, then subtracts incremental media spending. Incremental CAC is blank
if the estimated additional customer count is nonpositive. Purchase-rate intervals
are approximate 95% unpooled normal intervals, not certainty about profitability.

## Derived tables

`customer_month` and `cohort_age_summary` retain observed zeros and omit the
future. `cohort_totals` supplies normalized cohort curves. `company_month`
contains calendar-time joining-cohort layers; `company_totals` reconciles their
sum. `cohort_cash_economics` contains cumulative observed contribution and cash
recovery. `cohort_six_month_comparison` fixes customer age at five (six observed
receipt periods). `segmentation_comparison` evaluates residual variation in
six-month contribution among people with six complete observed months.

All figures and model inputs come from these saved SQL outputs. Forecasted LTV
uses a separate 12-month valuation horizon and 1% monthly discount. Forecasts,
cohort trends and segment differences do not establish marketing incrementality;
the randomized comparisons answer specific intervention questions.
