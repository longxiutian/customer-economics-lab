# Three ways to run Studio North

The learning task, eight datasets, guided checkpoints, analysis skill and two final
artifacts stay the same. What changes is where the agent and computation run and
whose account supplies model access.

## 1. Your own coding agent

Paste the repository's student prompt into Codex, Claude Code, or VS Code with an enabled AI
agent/harness. The agent retrieves the specified release, or resolves main once to an exact
commit and records it; it preserves an existing lab when resuming. No manual Git or ZIP
download is needed. The agent reads the skills and executes
the locked analytical code in its local or cloud workspace. Model access comes
from the account or credentials configured for that harness. VS Code is an editor;
its selected agent and provider determine model access.

The workspace holds the CSVs, DuckDB SQL, fitted model outputs, figures, TeX/PDF,
your saved judgments and personal-debrief evidence. You can ask the agent to
investigate alternative code or models after the baseline, preserving the baseline.

## 2. UNC-funded model service through MCP — TBD

The proposed experience uses a student coding client, potentially Codex on a Free
account, connected to an authenticated university model service through MCP.
University-funded calls would use a central quota and return usage receipts.
The local/cloud workspace still needs a working execution environment for the
analysis and report. UNC funding, authentication, quotas, supported clients and
the end-to-end student workflow remain to be agreed and tested with UNC IT.

MCP exposes tools and information. It does not by itself replace or pay for the
client's own conversational inference. A model served through an MCP tool and the
client's native model are separate usage streams. Free Codex is subject to product
access and limits; its adequacy for this complete lab must be tested. This is a
scenario for investigation, not a released student instruction or promised benefit.

## 3. BlueChip with Longleaf-hosted Nemotron

The student signs in through BlueChip and uses one lab entry point. A broker binds
the authenticated login to a private run. CPU workers perform DuckDB aggregation,
statistical fitting and report generation; Longleaf/Nemotron interprets returned
evidence. Four independent GPU replicas can sit behind a fair inference router.
Student workspaces remain outside GPU memory and do not reset when a later request
is sent to another replica. This increases inference capacity; CPU fits and PDF
builds also need sufficient capacity.

The one-GPU rehearsal was verified. Four-replica classroom provisioning and a real
student end-to-end check remain separate deployment work. The prior fixed rehearsal
window is expired; neither this document nor a pasted prompt starts a new service.

## The same personal debrief for each route

The [personal-debrief contract](personal-debrief.md) belongs to the GitHub skills.
It tracks actual questions, saved reasoning, output evidence and available usage
from the opening. Every route ends with the management report plus personal
recommendations for Studio North analysis and better AI practice. Measured counters,
estimated recorded text and unavailable usage remain separate.

## Primary references

- [OpenAI MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli):
  MCP supplies tools/information and has client-specific configuration and access.
- [OpenAI pricing/access](https://learn.chatgpt.com/docs/pricing): Free access exists
  with plan-specific availability and limits; the course does not promise adequacy.
- [VS Code model access](https://code.visualstudio.com/docs/agent-customization/language-models):
  selected harnesses, account access and provider keys determine what runs.
- [Claude Code usage](https://code.claude.com/docs/en/costs) and
  [VS Code telemetry](https://code.visualstudio.com/docs/configure/telemetry):
  usage export mechanisms vary by interface and account.
- The pinned Studio North source and [serving contract](serving-architecture.md)
  are the evidence for the local analysis and proposed four-replica design.
