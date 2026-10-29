# Universal Customer View by source dataset

**Identifiers:** Keys and profile descriptors identify or link people, groups and records; not every identifier is unique.
**Engagement:** Observed customer interactions and their measurement context. Firm marketing activity and attribution metadata are retained as explicitly marked contextual evidence; they do not establish individual exposure, action or a causal effect.
**Relationship:** Contractual and commercial arrangements, customer status, and explicitly marked operational context for relationship economics.
**Perception:** Customer-reported views or intentions, distinguished from behavior and analyst inference.

Each field appears once in the best-fitting category. Empty categories are evidence gaps, not zeros. A dagger (†) marks contextual or operational placement. Such a field supports interpretation without itself establishing a customer action or attitude; its rationale follows the table. The dagger is not part of the field name.

## people.csv

**CRM** — One person, including eligible prospects who never purchase.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `person_id`<br>`age_band`<br>`household_type`<br>`region` | — | `record_created_at`†<br>`attributes_recorded_at`† | `primary_need` |

- `age_band`: Profile descriptor; it identifies a demographic group, not a unique person.
- `household_type`: Profile descriptor; the subscription unit remains one individual.
- `region`: Geographic profile descriptor, not an observed preference.
- `record_created_at`: CRM relationship provenance; registration does not establish a paid customer.
- `attributes_recorded_at`: Profile provenance: verifies attributes were available before acquisition or assignment.
- `primary_need`: A stated intention recorded before acquisition, not a need inferred from future behavior.

## subscription_periods.csv

**Renewal system** — One scheduled monthly cycle; a paid outcome establishes retained membership for that cycle.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `period_id`<br>`subscription_id`<br>`person_id` | — | `period_start`<br>`period_end`<br>`renewal_due_at`<br>`renewal_outcome`<br>`cancellation_effective_at`<br>`plan_tier` | — |

- `renewal_outcome`: Contractual status establishes retention; a logged product action does not.
- `renewal_due_at`: A scheduled deadline may be known before the outcome is observed.
- `cancellation_effective_at`: Contractual exit timing; a blank is not proof of indefinite survival.

## transactions.csv

**Finance** — One payment or refund event; each payment is one order and refunds reuse its order ID.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `transaction_id`<br>`person_id`<br>`period_id`<br>`related_transaction_id`<br>`order_id` | `occurred_at`<br>`transaction_type`<br>`charge_type`<br>`quantity`<br>`gross_amount`<br>`discount_amount`<br>`refund_amount` | `unit_price`†<br>`variable_cost`† | — |

- `unit_price`: The item's commercial price term is Relationship context; billed quantity and realized amounts record transaction Engagement.
- `variable_cost`: Firm-side accounting context for relationship economics; unlike billed amounts, it does not record a customer payment or reported perception.
- `related_transaction_id`: A refund links to the original payment; it does not identify another customer.
- `refund_amount`: Observed financial reversal; a reason for dissatisfaction is not recorded here.

## product_events.csv

**Product and support** — One observed product/support interaction; no event does not mean no subscription.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `event_id`<br>`person_id` | `occurred_at`<br>`event_type`<br>`platform` | — | — |

- `platform`: Context of an observed interaction, not an acquisition channel or a motive.

## feedback.csv

**Customer research** — One completed linked survey response; nonresponse is missing, not a zero rating.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `response_id`<br>`person_id` | `submitted_at`<br>`journey_stage`† | — | `ease_rating`<br>`value_rating`<br>`main_difficulty` |

- `submitted_at`: Survey-response activity and timing, not the attitude itself.
- `journey_stage`: Context of the response, not a measured universal customer path.
- `main_difficulty`: Customer-reported difficulty; a hypothesis about causes, not causal evidence.

## campaign_spend.csv

**Marketing spending** — One campaign per spending date; aggregate before joining to customer outcomes.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `campaign_id`<br>`target_need`† | `spend_date`†<br>`channel`†<br>`media_spend`†<br>`other_acquisition_spend`† | — | — |

- `target_need`: Identifies the campaign's target group; unlike a person's primary_need, it is not an individually stated intention. Channel describes the firm's marketing activity, so it is Engagement context instead.
- `spend_date`: Timing of firm marketing activity, not a customer touchpoint timestamp.
- `channel`: Context of firm marketing activity; it does not prove an individual's exposure.
- `media_spend`: Firm-side campaign spending is retained as Engagement context, not individual engagement or evidence of exposure.
- `other_acquisition_spend`: Firm-side creative/vendor costs are Engagement context, not observed customer activity; aggregate once before joining customers.

## acquisition_attribution.csv

**Marketing attribution** — One acquired person and the recorded credit for the first successful payment.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `person_id`<br>`first_paid_transaction_id`<br>`credited_campaign_id` | `source_type`†<br>`credited_at`†<br>`attribution_rule`† | — | — |

- `source_type`: Recorded acquisition-path credit; an attribution label does not establish incrementality.
- `credited_at`: When credit was recorded, not necessarily the acquisition or exposure time.
- `attribution_rule`: Measurement metadata for engagement credit, not a customer action itself.

## experiment_assignments.csv

**Experiment platform** — One eligible person per randomized experiment, including all nonbuyers.

| Identifiers | Engagement | Relationship | Perception |
| --- | --- | --- | --- |
| `experiment_id`<br>`person_id`<br>`tested_campaign_id` | — | `assigned_at`†<br>`arm`†<br>`followup_end_at`† | — |

- `assigned_at`: Experimental relationship/design metadata; assignment is not observed exposure or purchase.
- `arm`: Randomized intervention assignment; control nonbuyers must remain in the denominator.
- `followup_end_at`: Prespecified measurement window, not a subscription end date.
