# Legacy consolidation implementation report — 2026-11-01

- Executing agent: `DeepSeek`
- Report writer: `DeepSeek` (same as executor)
- Dispatcher/orchestration: Workflow v3 unattended development job
  `20261101T080057Z-consolidate-legacy-workflows-and-87a13678`
- Status: **COMPLETE for the authorized consolidation scope.** Remaining gaps
  are listed below and do not hide unverified work.
- Branch: `agent/control-plane/workflow-v3-20261031`
- Canonical remote: `dev-control-plane`
  (`git@github.com:iffinland/dev-control-plane.git`)

## 1. Objective

Consolidate the two legacy repositories into the canonical Workflow v3 control
plane, preserve provenance, migrate valuable missing knowledge, make task-start
and delivery discipline executable, fix the monitor service PATH in isolation,
push the development branch and verify its remote SHA without modifying either
legacy repository or any running service.

## 2. Sources (read-only)

| Source | Ref | Commit | State |
| --- | --- | --- | --- |
| `github.com/iffinland/ai-development-orchestration` | `agent/orchestration/bootstrap` | `c52e04841adfde062e579463a39bf0463609c8d5` | Clean; unchanged |
| `github.com/iffinland/qortal-dev-workspace` | `main` | `b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2` | Clean; unchanged |

The detailed file-by-file comparison, classifications and conflict resolutions
are in
[`2026-11-01-legacy-consolidation.md`](2026-11-01-legacy-consolidation.md).

## 3. Changes

### 3.1 Monitor service PATH fix (isolated commit)

Commit `3fd50ae` (`fix(monitor): add explicit user PATH to service unit`) changes
exactly one file:

```text
deploy/systemd/user/qortium-dev-monitor.service
+Environment="PATH=/home/iffi/.opencode/bin:/home/iffi/.local/bin:/usr/local/bin:/usr/bin:/bin"
```

No service was restarted or reconfigured.

### 3.2 Qortal knowledge migration

- `platforms/qortal/guides/` now contains the Qortal-specific session routing,
  task classification, native app workflow, QDN/bridge contract,
  architecture/data-integrity rules, publication/discovery/scaling, runtime
  diagnostics, live validation, audit/refactor, release/provenance, Git hygiene,
  final handoff, governance, workflow-v2 and template material, migrated
  read-only from `qortal-dev-workspace` at `b8fd2f6`.
- `platforms/qortal/guides/README.md` records provenance, reuse rules and gaps.
- `platforms/qortal/README.md` and `platforms/README.md` link the migration and
  keep current Qortal source/runtime authoritative.
- New reusable Qortal skills:
  - `skills/qortal/qortal-host-bridge-contract/`
  - `skills/qortal/qortal-qdn-authority-integrity/`
  - `skills/qortal/qortal-publication-discovery-scaling/`
  - `skills/qortal/qortal-live-validation-release/`
  - `skills/qortal/qortal-runtime-diagnostics/`
- Canonical templates added:
  `templates/PROJECT-CONTEXT.md`, `AUDIT-ISSUE.md`,
  `IMPLEMENTATION-ISSUE.md`, `OWNER-HANDOFF.md`.

### 3.3 Executable Workflow v3 completion contract

- `tools/devjob/contract.py` — contract loader/evaluator.
- `tools/devjob/runner.py` — stores the contract with the job, evaluates it after
  acceptance commands, records results in `job.json`, `dev status` and
  `report.md`, and maps `FAILED`/`PENDING` into job state.
- `tools/dev.py` — `dev start --contract-file`.
- `tools/test_completion_contract.py` — 12 regression tests.
- `examples/workflow-v3/contract.json` and updated
  `examples/workflow-v3/TASK.md`.
- `docs/operations/DEV-WORKFLOW-V3.md`, `WORKFLOW.md`, `templates/TASK.md` and
  `templates/STATUS.json` now define the required evidence fields.
- New `skills/shared/workflow-v3-completion-contract/SKILL.md`.
- CI and `validate_control_plane.py` require the contract, test and example.

Checked evidence: skill discovery, freshness, documentation loading, capability
harvest, documentation updates, development branch/protected-branch
authorization, clean tree with declared owner exceptions, scoped commit/paths,
unauthorized merge rejection, secret-bearing paths and secret-like diff content,
authorized push and remote SHA. Push, protected-branch, merge, deploy, QDN,
wallet and destructive actions remain separate authorization flags; the contract
never grants them.

### 3.4 Owner changes preserved

The following pre-existing working-tree changes were **not** overwritten and
were **not** committed by this task:

- `skills/README.md` (owner rows/descriptions)
- `skills/qortium/home2-qdn-publishing/SKILL.md`
- `skills/qortium/qdn-resource-discovery/SKILL.md`
- `skills/shared/browser-thumbnail-generation/` (untracked)

The migration's own `skills/README.md` index rows were staged selectively so the
owner's dirty rows did not enter the migration commit.

## 4. Validation

All commands were run in `/home/iffi/dev-workspace/control-plane` on the working
tree.

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tools -p 'test_*.py' -q` | **362 tests OK** |
| `python3 tools/validate_control_plane.py` | **PASS** — 95 active Markdown files, 413 relative links, 75 required files |
| `python3 tools/validate_skills.py` | **PASS** — 23 active skills indexed exactly once |
| `python3 tools/validate_security.py --self-test` | **PASS** |
| `python3 tools/validate_security.py .` | **PASS** — 220 files scanned |
| `python3 tools/validate_agent_permissions.py --check` | **PASS** — 337 rules, 97 checks |
| `tools/install_opencode_profiles.sh --check` | **PASS** — policy check; nothing installed |
| `python3 tools/test_completion_contract.py` | **12 tests OK** |
| `python3 tools/opencode_guard.py check` | **PASS** — one heavyweight execution (this job), Qortium read-only |
| `git diff --cached --check` | **PASS** for the migration commit |
| Staged tree extraction validation (`git archive` of the indexed tree) | **PASS** — control-plane, skills, security and contract tests |

The earlier `git diff --check` on the whole working tree reports one trailing
whitespace in the pre-existing owner change
`skills/qortium/qdn-resource-discovery/SKILL.md`. It was deliberately not staged
and not silently rewritten.

## 5. Git and delivery

Commits prepared and pushed by this task:

```text
3fd50ae  fix(monitor): add explicit user PATH to service unit
4551105  feat(control-plane): consolidate legacy workflows and enforce completion contract
```

Push command:

```bash
git push dev-control-plane HEAD:agent/control-plane/workflow-v3-20261031
```

Observed result at the time this report was authored: the branch was created on
`dev-control-plane` and the remote SHA matched local `HEAD`:

```text
local  = 455110527567eecc7a59629540e6f28d7b60a90b
remote = 455110527567eecc7a59629540e6f28d7b60a90b
```

This report commit follows `4551105`; the final pushed SHA is the one verified in
the job handoff and by `git ls-remote` against `dev-control-plane`. The legacy
`origin` remote still points at `ai-development-orchestration` and was not used
for delivery.

## 6. Safety and boundaries

- No legacy repository was modified, moved, reset, cleaned or deleted.
- No running service, Qortium node, configuration, data directory or wallet was
  modified, restarted or signalled.
- No protected-branch merge, deploy, release, QDN write, wallet transaction or
  destructive operation was performed.
- No secret was printed or committed; the security validator and Git hooks
  scanned the staged content.
- No `origin` push was performed.

## 7. Remaining gaps

1. Shadow Archives project context and its 24 project-specific reports remain in
   the legacy repository; `PROJECT-REGISTRY.md` still marks the context as
   pending import.
2. QWB project context/evidence remains deferred; no local application checkout
   was verified.
3. Migrated Qortal guides are `verified-reference`, not current runtime truth.
   Their reference revisions date from 2026-09-11 and must be revalidated per
   task.
4. No new live Qortal/Qortium runtime matrix was executed; this was a
   documentation/control-plane change.
5. Two broken links in the legacy project-specific tree were not repaired because
   those files were intentionally not migrated.
6. Owner dirty skill changes remain uncommitted for owner review.
7. The completion contract is a policy layer, not an OS sandbox; wrappers,
   interpreters and SSH can exceed command patterns. Authorization, Git hooks,
   branch protection and review remain authoritative.
8. The shared completion-contract skill remains `candidate` until a real job
   completes through it with an authorized push and verified remote SHA.
