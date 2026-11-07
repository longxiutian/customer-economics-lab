# Architecture and debrief review

Opus consultation 1: `a9b716baa2c5416882334f6920ab8ccf`, claude-opus-5-5,
high, normal terminal response; 1,585 input / 6,437 output tokens, including
2,505 thinking tokens. One attempt, no cache. Architecture response saved here.

Accepted: separate CPU capacity from GPU serving; label partial chat coverage;
namespace evidence to a frozen student snapshot; reject foreign citations and
fabricated quotes; hold uncertain dispatch/delivery without replay; keep operator
debrief usage separate; freeze before review and version any later correction.

Qualified: the broker accepts only requests with the private BlueChip integration
key before reading the platform-supplied identity header. It need not be publicly
unreachable, but the secret must stay in the server tool configuration. Local
worker/router IPC is operator-owned; it is not a public student authentication API.

Deferred to classroom activation, not presented as implemented: four real GPU
replicas, concurrent CPU capacity, the supported native BlueChip turn/usage export,
and the final delivery-channel integration. No new GPU allocation or notifications.
The short UI inspection found a native conversation-context token breakdown,
which measures current context occupancy, not cumulative provider usage. It did
not establish a supported automatic telemetry export for the lab broker.

The personal example uses only instructor rehearsal records. The Opus debrief
correctly recognized the acceptance-test judgments and did not attribute them to
a real student. Codex checked the narrative against all ten snapshot items.
The example's recommended SQL and channel-holdout design are proposed next steps,
not claims that those additional analyses were executed.

Student debrief call: claude-opus-5-5 high, normal end_turn, 3,799 input / 2,799
output tokens including 913 thinking tokens (6,598 total), one attempt, no cache.
These costs are outside the rehearsal student's 127,200 Nemotron tokens.

No changes were made to the frozen rehearsal release, active agent prompt, or
public broker. The new modules need a new release hash and a verified serving window.

Final Codex correction: the original Opus response said any new model fit needed
an external harness. That was too broad: checkpoint 14 already runs the prescribed
fresh fit in the hosted lab. The rendered example now distinguishes that supported
fit from trying alternative statistical models or modifying fitting code. Its
recommendation also cites evidence 8 (the fresh-fit receipt). The provider response
remains unchanged; `finish_debrief.py` applies the explicit, reproducible correction.
