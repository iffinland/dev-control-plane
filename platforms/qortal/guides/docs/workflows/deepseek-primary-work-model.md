# DeepSeek Primary Work Model

## Universal coordination (2026-09-13)

Read `/home/iffi/VsCodec-Projects/AI-Orchestration/AGENTS.md` first.
It owns shared roles (including Codex Local orchestration), agent branches,
GitHub handoff and reference freshness. This workspace retains platform-specific
execution and evidence rules. Older role summaries below are platform overlays;
they do not override that shared coordination contract.

> Naming: the workflow is named after the primary local implementation agent
> model used in this environment. The roles are model-agnostic; any equivalent
> local coding agent may fill the DeepSeek slot.

## Purpose

Define how work is split between ChatGPT (architecture/task planning/review),
DeepSeek (primary local investigation and implementation) and Codex (independent
audit, high-risk review, repeated-failure escalation and release-critical
verification).

## Roles

### ChatGPT

Cross-project architect, task planner, GitHub-backed reviewer, documentation and
handoff reviewer. Web access to local uncommitted files is not assumed; it MUST
use GitHub or structured evidence supplied by a local agent and MUST NOT claim
to have inspected files it cannot access.

### DeepSeek

Default cost-efficient local implementation agent for routine development.
Investigates, implements, validates locally, self-audits and hands off. Works on
one bounded objective at a time. Does not perform external writes.

### Codex

Independent local auditor and high-risk implementer. Used for architecture and
data-integrity review, repeated failures, contradictory evidence, and final
release-critical verification. Operates, like DeepSeek, behind the same
authority boundary.

## Risk levels

### LEVEL 1 — DeepSeek implementation

Routine, bounded, well-understood change with clear acceptance evidence and no
new authority or data-integrity semantics.

Flow: DeepSeek implements → validates locally → self-audit → owner/live host
validation when applicable.

### LEVEL 2 — DeepSeek implementation plus mandatory review

Change touches shared architecture, QDN schema/identifier design, engagement
semantics, caching/authority interaction, or cross-cutting performance. Or a
Level 1 task failed once.

Flow: DeepSeek implements → DeepSeek produces a review artifact per
[`../../templates/DEEPSEEK-REVIEW.md`](../../templates/DEEPSEEK-REVIEW.md) →
ChatGPT review → owner validation.

### LEVEL 3 — Codex implementation or Codex independent audit

High-risk data-integrity/authority change, repeated failures, unexplained
runtime/node behavior, contradictory test evidence, or a release-candidate
independent audit.

Flow: Codex reviews or implements independently → evidence-based verdict →
owner authorization for any external action.

## Escalation triggers

Escalate to ChatGPT or Codex when:

- authority or platform contracts remain unverified;
- identity, name ownership, moderation trust, migration authority or other
  critical data-integrity boundaries materially change;
- the same task fails twice;
- one focused correction after failed owner/host validation does not resolve the
  issue;
- the diff becomes substantially broader than planned;
- tests remain contradictory or runtime behavior cannot be explained;
- an independent high-confidence review is required before release.

## Pilot measurements

Record for each substantial task: task class, risk level, agent, whether a
second iteration was needed, whether escalation occurred, and the validation
layers actually completed. This workspace has no historical pilot data yet —
do not invent any. Record real measurements in the report for the task.

## Workflow summary

```
ChatGPT scopes and reviews
-> DeepSeek investigates, implements and self-audits locally
-> owner/runtime validation in a real Qortal host
-> GitHub
-> Codex escalation when required
```

## Related files

- [`workflow-v2.md`](workflow-v2.md)
- [`report-storage-policy.md`](report-storage-policy.md)
- [`../../agents/roles/CHATGPT.md`](../../agents/roles/CHATGPT.md)
- [`../../agents/roles/DEEPSEEK.md`](../../agents/roles/DEEPSEEK.md)
- [`../../agents/roles/CODEX.md`](../../agents/roles/CODEX.md)
