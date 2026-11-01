# DeepSeek Task Delta

Use the canonical compact
[`TASK-CONTROLLER.md`](TASK-CONTROLLER.md) with
[`Workflow v2`](../docs/workflows/workflow-v2.md). Do not copy the full shared
governance contract into the prompt.

Add only these DeepSeek-specific instructions when they apply:

- start a fresh conversation for the bounded objective, normally one issue;
- begin from the observed symptom/outcome and expected behavior, not a presumed
  root cause;
- trace the real production path to the first confirmed mismatch;
- use applicable read-only node/QDN evidence;
- verify platform behavior against current Qortal source, not memory;
- run the project's declared verify/build commands;
- leave required real-host or owner validation pending until actually confirmed;
- allow one focused correction after a failed owner/host check, then escalate
  unexplained repetition or a high-risk boundary to ChatGPT/Codex;
- do not commit, push, publish, deploy, release, close issues, or perform live
  writes without exact owner authorization;
- do not require or fabricate SSH evidence.

The task controller MUST state the repository, project context, one objective,
exit criterion, scope, verified starting evidence, task-specific constraints,
required validation, external-action authority, and canonical report path.
