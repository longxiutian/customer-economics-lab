# Instructor feedback collection

The learner ends the session with **end lab** or **end simulation**, then answers
**“Any feedback to Professor Tian?”** or skips. A collection notice explains the
identifier retained with that response. The usage/learning debrief follows this
exchange; completing the executive report alone never starts it.

| Route | Delivery | Instructor's identifier |
| --- | --- | --- |
| Own coding agent | Standard-library HTTPS helper | Stable feedback-install ID and random workspace ID; students may sign the reply |
| UNC API in a coding agent | Same helper, separate from model requests | Stable feedback-install ID and random workspace ID; students may sign the reply |
| BlueChip + Longleaf | Authenticated broker job-completion hook | BlueChip-supplied UNC login, with the workspace and close cycle |

The existing HTTPS broker stores encrypted feedback and identifiers in private
D1 tables. Collection and instructor export remain available without an active
GPU allocation. Feedback-install credentials grant only append access under that
pseudonym; they cannot read records, invoke a model or use a subscription. Local
identifiers are not verified student identities. BlueChip attribution comes from
its configured platform identity header, rather than model-generated names.

Local originals and a durable delivery outbox stay under the learner's `usage/`
folder. One attempt is bounded to five seconds. If service is unavailable, the
personal debrief continues and the upload remains pending. Preparing the debrief,
reopening the lab, or explicitly running `cohort_lab.instructor_feedback` allows
another bounded attempt. Replays return the original receipt. A new end cycle
adds a separate record and preserves earlier responses. A skip stores a decline
without a feedback body. Pre-notice historical closures are not uploaded.

Feedback, signatures and platform identities are excluded from Jev, Sol,
Nemotron and personal-review evidence. Hosted collection checks the prior
awaiting-feedback state, close cycle, owner and hash against the actual incoming
message. The completed queue payload is redacted once the encrypted record is
stored. Student-facing receipts contain delivery metadata, not the reply/login.

The operator endpoint is protected by the existing instructor administration
credential. Export outside the public checkout, using a secure environment
reference rather than putting a credential in a command:

```text
python scripts/export_instructor_feedback.py --output PRIVATE_NEW_FILE.json
```

The helper prints the destination and row count, never feedback or identifiers.
The private export includes route, identifier source, workspace, close cycle,
response/decline, time and release. It is not published to GitHub or Canvas.
The service records export time and count. No retention/deletion automation or
automatic email to the instructor is configured.
