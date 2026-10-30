# DeepSeek adapter

Status: client-boundary and role note only. DeepSeek is a local implementation
client, not a governance source.

## Canonical inputs

DeepSeek reads the same files as every other client:

- `/home/iffi/dev-workspace/control-plane/AGENTS.md`
- `/home/iffi/dev-workspace/control-plane/WORKFLOW.md`
- `/home/iffi/dev-workspace/control-plane/GIT-AND-HANDOFF.md`
- the matching platform pack and project-level deltas
- matching skills after their freshness check

## Boundaries

- Do not create a DeepSeek-specific knowledge base or copy skills.
- Do not put API keys, tokens, passwords or wallet data in this repository, task
  artifacts, reports or prompts that are persisted to Git.
- Resolve credentials from the owner's external environment or secret store at
  run time.
- Do not start, schedule or poll tasks automatically.
- Do not commit, push, publish, deploy, sign or mutate external state without
  exact task-scoped authorization.
- Record the actual executing agent in reports and handoffs. The client or
  orchestrator is not automatically the executor.

## Operational note

The Phase 1 control plane provides instructions and validation only. It does not
verify that a DeepSeek client is installed, configured or reachable on this VPS.
That must be established separately before any future dispatch step.
