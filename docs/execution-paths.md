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

## 2. UNC-funded model service through MCP

The [UNC API route](api-route.md) keeps the student in their current coding-agent
chat. An optional local MCP sends compact checkpoint evidence to UNC
gpt-6.1-sol; the native agent runs the local analysis and presents the teaching.
Paste [the UNC API prompt](unc-api-startup-prompt.txt). The bridge prepares its
secure connection, checks lab relevance with Jev and assigns model access in the
background. Students do not request or paste an API key. Each subscription has
a 400,000-token monthly input/output allowance; confirmed ledger headroom controls
background rollover to another approved subscription. The bridge reserves budget
before dispatch and records actual receipts. All statistical computation and
report generation still run in the coding agent's local/cloud workspace.

MCP exposes tools and information. It does not by itself replace or pay for the
client's own conversational inference. A model served through an MCP tool and the
client's native model are separate usage streams. Free Codex is subject to product
access and limits. The [full guided rehearsal](../api_bridge/acceptance/full-guided.json)
completed nineteen checkpoints, fresh CPU fits, the 45-page executive report and
a reviewed personal debrief. Its 26 Sol calls used 62,757 UNC tokens; native
harness usage is a separate stream. The instructor also successfully tested the
same-chat route. These are measured examples, rather than a fixed budget for every
student's questions.

## 3. BlueChip with Longleaf-hosted Nemotron

The student signs in through BlueChip and uses one lab entry point. A broker binds
the authenticated login to a private run. CPU workers perform DuckDB aggregation,
statistical fitting and report generation; Longleaf/Nemotron interprets returned
evidence. Four independent GPU replicas can sit behind a fair inference router.
Student workspaces remain outside GPU memory and do not reset when a later request
is sent to another replica. This increases inference capacity; CPU fits and PDF
builds also need sufficient capacity.

Use this route during the instructor's announced service window. Its class-release
and capacity checks are managed separately from the local UNC API route. A pasted
prompt does not start a GPU allocation. Keep your saved workspace and use the
returned progress link while computation or interpretation is queued.

## The same personal debrief for each route

The [personal-debrief contract](personal-debrief.md) belongs to the GitHub skills.
It tracks actual questions, saved reasoning, output evidence and available usage
from the opening. Download the executive report at checkpoint 18 and continue
asking questions. When finished, say **end lab** or **end simulation**, then
answer **“Any feedback to Professor Tian?”** or say **skip feedback**. The personal
usage/learning debrief follows that response. Measured counters, estimated
recorded text and unavailable usage remain separate.

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
