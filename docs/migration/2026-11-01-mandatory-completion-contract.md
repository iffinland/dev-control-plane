# Mandatory Workflow v3 completion contract — 2026-11-01

- Executing agent: `DeepSeek`
- Report writer: `DeepSeek` (same as executor)
- Job: `20261101T082730Z-enforce-workflow-v3-completion-c-e66d7249`
- Base: `4e5826c8bf4c52c9be33e0177e04ae1ea564f964`
- Branch: `agent/control-plane/workflow-v3-20261031`
- Canonical remote: `dev-control-plane`
  (`git@github.com:iffinland/dev-control-plane.git`)
- Status: implementation and local validation complete. The exact delivery
  commit and pushed SHA are recorded in the job handoff.

## 1. Objective

Make the executable completion contract mandatory for every **new** Workflow v3
job, including `dev start` and Telegram Dev Monitor starts, without breaking
legacy jobs or resume. An explicit `--contract-file` may add constraints but may
never disable mandatory checks. A test suite or OpenCode exit `0` alone must not
produce `SUCCESS`.

## 2. Baseline and migration evidence inspected

The implementation read the current contract/evaluator, job worker, CLI, monitor
facade and status renderer, the existing contract and CLI/monitor tests, and the
migration records:

- `tools/devjob/contract.py`, `tools/devjob/runner.py`, `tools/dev.py`;
- `tools/devmonitor/jobs.py`, `tools/devmonitor/render.py`;
- `tools/test_completion_contract.py`, `tools/test_dev_cli.py` and the monitor
  test suite;
- `docs/migration/2026-11-01-legacy-consolidation.md` and
  `docs/migration/2026-11-01-legacy-consolidation-implementation.md`;
- `WORKFLOW.md`, `AGENTS.md`, `docs/operations/DEV-WORKFLOW-V3.md`,
  `docs/operations/QORTIUM-DEV-MONITOR.md`, the skills catalogue and the
  completion-contract skill.

The earlier migration deliberately made the contract opt-in with
`--contract-file`. This change replaces that for new jobs while leaving already
recorded jobs untouched.

## 3. Behaviour implemented

### 3.1 Mandatory default contract

`runner.create_job` now always prepares a contract. With no explicit file it
builds the default from the job's real branch, starting `HEAD`,
`dev-control-plane` remote and `TASK.md` evidence. The default enables every
mandatory check:

```text
skill_discovery, freshness, documentation_loading, capability_harvest,
documentation_updates, clean_tree, commit, no_merge_commits, push
```

The job record stores `completion_contract_spec`,
`completion_contract_source` (`default`/`file`) and
`completion_contract_required`. Status and reports expose the mandatory flag,
source and every failed/pending check.

### 3.2 Explicit override policy

`contract.load_contract` and `contract.prepare_contract` enforce owner policy:

- a mandatory `require` check cannot be set to `false`;
- an explicit contract cannot remove all evidence files;
- evidence, allowed/forbidden paths, remote and explicit authorization may be
  customized;
- mandatory checks are added back if an explicit file omits them;
- CLI authorization flags may grant an action explicitly; they never revoke a
  grant written by the owner in the contract file.

New CLI options: `--evidence-file`, `--scope`, `--remote`,
`--authorize-push`, `--authorize-protected-branch`, `--authorize-merge`.
`--contract-file` is now an optional override, not the only way to get a
contract.

### 3.3 Truthful state and legacy compatibility

- A new job with a missing or skipped mandatory contract cannot be `SUCCESS`.
- A genuine acceptance/validation failure is classified before pending
  authorization, so it remains `FAILED` rather than being hidden as `BLOCKED`.
- Unauthorized required push and unauthorized protected-branch work are
  `PENDING` and therefore `BLOCKED`; an already-created unauthorized merge
  remains a failure.
- `dev accept` now reuses the stored contract result, so manual acceptance
  cannot turn a failed/pending contract into success.
- Legacy jobs have no `completion_contract_required` flag and no recorded
  contract. They keep legacy status and resume behaviour; resume does not
  retroactively add or weaken a contract.

### 3.4 Owner dirty files

The default contract records every pre-existing dirty/untracked path from the
job's starting snapshot in both `allowed_dirty_paths` and `forbidden_paths`.
Those files are preserved, are not demanded to be cleaned, and cannot be
silently absorbed into the job commit. Scoped path checking still applies to the
job's own commits.

### 3.5 CLI and Telegram monitor

The CLI prepares the default before both `--dry-run` and real start. The monitor
continues to use the fixed-shape `dev start` invocation and deliberately passes
no `--contract-file` or weakening authorization flag, so monitor-started jobs
receive the same mandatory contract. Monitor job status now renders the contract
state and failed/pending checks.

### 3.6 Migrated Qortal documentation paths

Active instructions in migrated Qortal guides were corrected from the obsolete
laptop paths under `/home/iffi/VsCodec-Projects/...` to the canonical
control plane and central report tree. The original paths remain only as
explicit historical provenance notes. No legacy repository was modified.

### 3.7 Documentation and skills

Updated `AGENTS.md`, `WORKFLOW.md`, the Workflow v3 and monitor operating docs,
the task/status examples, the skills catalogue entry and the reusable
`workflow-v3-completion-contract` skill.

## 4. Validation evidence

Commands were run in `/home/iffi/dev-workspace/control-plane` on this working
tree.

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tools -p 'test_*.py' -q` | **375 tests OK** |
| `python3 tools/test_completion_contract.py` | **18 tests OK** |
| `python3 tools/test_dev_cli.py` | **42 tests OK** |
| `python3 tools/test_dev_monitor_jobs.py` | **15 tests OK** |
| `python3 tools/test_dev_monitor_control.py` | **15 tests OK** |
| `python3 tools/validate_control_plane.py` | **PASS** — 97 active Markdown files, 419 links, 78 required files |
| `python3 tools/validate_skills.py` | **PASS** — 23 active skills indexed once |
| `python3 tools/validate_security.py .` | **PASS** — 222 files scanned |
| `python3 tools/validate_security.py --self-test` | **PASS** |
| `python3 tools/validate_agent_permissions.py --check` | **PASS** — 337 rules, 97 checks |
| `tools/install_opencode_profiles.sh --check` | **PASS** policy check only |

The CLI fixture now provides a real temporary Git repository, a bare
`dev-control-plane` remote, durable `TASK.md` evidence and fake delivery commits.
That lets the tests prove mandatory enforcement rather than mocking it away.
The monitor facade test runs the real `dev start --dry-run` and asserts the
default contract is present.

## 5. Preserved owner changes

The following pre-existing owner changes were **not** staged, rewritten or
discarded by this task:

- `skills/README.md` (owner rows/descriptions);
- `skills/qortium/home2-qdn-publishing/SKILL.md`;
- `skills/qortium/qdn-resource-discovery/SKILL.md`;
- `skills/shared/browser-thumbnail-generation/` (untracked).

Only the completion-contract catalogue row was staged from `skills/README.md`.

## 6. Safety and boundaries

- No legacy repository was modified.
- No Qortium node/service/configuration/data/wallet was modified, restarted or
  signalled.
- No protected-branch merge, force-push, deploy, release, QDN write or wallet
  transaction was performed.
- Contract checks remain policy, not an OS sandbox; authorization and review
  still govern wrappers, interpreters, SSH and remote commands.

## 7. Remaining issues

1. A Telegram-monitor start still has no separate push-authorization control, so
   a monitor job that reaches delivery completeness without that authorization
   is truthfully `BLOCKED` pending an owner decision. The owner can authorize via
   the CLI/contract file; adding a monitor authorization control is a separate
   UI/config decision.
2. Legacy jobs intentionally keep legacy behaviour. They are not retroactively
   given the mandatory contract.
3. The contract skill remains `candidate` until a real job completes through the
   mandatory default with an authorized push and verified remote SHA.
