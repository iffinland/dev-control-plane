# Legacy repository consolidation inventory — 2026-11-01

Status: read-only inventory and consolidation record. Executing agent:
`DeepSeek` (Workflow v3 unattended development job). Report writer: `DeepSeek`.
This record is English-only and preserves source provenance.

## 1. Scope and sources

The task compared two legacy repositories with the current local canonical
control plane and migrated valuable missing knowledge. Both legacy repositories
were inspected read-only. Neither was modified, moved, reset, cleaned or deleted.

```text
Canonical control plane:
  path:    /home/iffi/dev-workspace/control-plane
  branch:  agent/control-plane/workflow-v3-20261031
  base:    3fd50ae687872c194068b700329aa5375c43c0e3 (before this consolidation)
  remote:  dev-control-plane = git@github.com:iffinland/dev-control-plane.git

Legacy source 1:
  repository: https://github.com/iffinland/ai-development-orchestration
  path:       /home/iffi/dev-workspace/projects/ai-development-orchestration
  branch:     agent/orchestration/bootstrap
  commit:     c52e04841adfde062e579463a39bf0463609c8d5
  committed:  2026-09-13T17:12:35+03:00
  state:      clean; not modified

Legacy source 2:
  repository: https://github.com/iffinland/qortal-dev-workspace
  path:       /home/iffi/dev-workspace/projects/qortal-dev-workspace
  branch:     main
  commit:     b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2
  committed:  2026-09-13T17:13:13+03:00
  state:      clean; not modified
```

The current control plane was itself derived from
`ai-development-orchestration`, which is why many files are identical or have
evolved in place. `qortal-dev-workspace` is the Qortal-specific successor and
contains the largest body of unique technical knowledge.

## 2. Method

1. Enumerated every non-`.git` file in both legacy repositories and in the
   control plane.
2. Compared same-path files byte-for-byte and read every divergent or
   legacy-only file.
3. Read the current control-plane contract, workflow, handoff rules, registry,
   environment registry, platform packs, skills index, templates, validators,
   Git hooks and Workflow v3 implementation.
4. Classified material as **unique**, **duplicated**, **obsolete** or
   **conflicting**.
5. Migrated only reusable or active routing knowledge. Project-specific
   historical evidence was left in the legacy repository.
6. Preserved unrelated dirty owner changes in the control-plane working tree.

No legacy repository file was written. The only reads against running Qortium
were read-only status checks; no service, node, configuration, data or wallet
was modified.

## 3. `ai-development-orchestration` inventory

### 3.1 Identical files (already present)

These files are byte-identical in the legacy repository and the current control
plane, so no migration was needed:

- `CLAUDE.md`
- `reports/2026-09-13-*` (all nine historical report/evidence files)
- `research/2026-09-13-reusable-development-patterns.md`
- `roles/CHATGPT.md`
- `roles/CODEX.md`
- `skills/_template/SKILL.md`
- `templates/HANDOFF.md`

### 3.2 Divergent files (already evolved in the control plane)

| File | Legacy state | Current state | Classification |
| --- | --- | --- | --- |
| `AGENTS.md` | Phase 2 orchestration contract | Added platform packs, report storage, report template, identity/profile precision | **Superseded** by current control plane |
| `WORKFLOW.md` | Workflow v2-era execution | Added validation cadence, unattended/Workflow v3, controller identity rules | **Superseded** |
| `GIT-AND-HANDOFF.md` | Earlier handoff-state model | Added central report storage, CLI/profile identity clarification, REPORT template | **Superseded** |
| `PROJECT-REGISTRY.md` | Original workstation paths | Verified VPS paths, deferred entries, registration rule | **Superseded**; old paths are historical |
| `ENVIRONMENT.md` | Dated tunnel/node/reference inventory | VPS path registry and current freshness gate | **Superseded**; old endpoints are historical evidence |
| `README.md` | Donor bootstrap description | Canonical control-plane description and structure | **Superseded** |
| `roles/DEEPSEEK.md` | No central report-storage line | Reports stored centrally | **Superseded** |
| `skills/README.md` | Smaller library | Expanded index and quality gate | **Superseded** |
| `templates/TASK.md`, `templates/STATUS.json` | Earlier fields | Current fields plus Workflow v3 evidence | **Superseded** |
| Shared/qortal/qortium skills | Earlier revisions | Current revisions and additional skills | **Superseded** |

### 3.3 Unique legacy-only material

None that requires migration. The repository's own reports already record the
Phase 1/Phase 2 bootstrap and are preserved in the control plane's `reports/`
directory. Its unique value is historical provenance, not missing active
knowledge.

### 3.4 Obsolete or conflicting material

- Old `/home/iffi/VsCodec-Projects/...` routing: obsolete; current registry uses
  the verified `/home/iffi/dev-workspace/...` paths.
- Dated Qortal/Qortium tunnel endpoints and reference SHAs: historical evidence;
  not current routing.
- The repository remote is still configured as `origin` in the control plane.
  It is **not** the canonical push target; `dev-control-plane` is.

## 4. `qortal-dev-workspace` inventory

### 4.1 Unique and migrated

| Source | Classification | Destination / treatment |
| --- | --- | --- |
| `agents/00-SESSION-START.md` | Unique Qortal routing | Migrated to `platforms/qortal/guides/agents/` |
| `agents/01-TASK-CLASSIFICATION.md` | Unique Qortal task classes | Migrated |
| `agents/README.md` | Unique guide catalog and legacy migration record | Migrated |
| `agents/qortal-native-app-workflow.md` | Unique Qortal app-design workflow | Migrated |
| `agents/qortal-architecture-and-data-integrity.md` | Unique authority/data-integrity rules | Migrated; harvested into `qortal-qdn-authority-integrity` skill |
| `agents/qortal-qdn-and-bridge.md` | Unique bridge/host/QDN contract | Migrated; harvested into `qortal-host-bridge-contract` skill |
| `agents/qdn-publication-discovery-and-scaling.md` | Unique publication/discovery/scaling rules | Migrated; harvested into `qortal-publication-discovery-scaling` skill |
| `agents/runtime-diagnostics-and-performance.md` | Unique runtime diagnosis rules | Migrated; harvested into `qortal-runtime-diagnostics` skill |
| `agents/live-qdn-validation.md` | Unique live-validation layers | Migrated; harvested into `qortal-live-validation-release` skill |
| `agents/issue-driven-audit-and-refactor.md` | Unique audit-to-issue procedure | Migrated |
| `agents/app-release-and-provenance.md` | Unique release/provenance gates | Migrated; harvested into `qortal-live-validation-release` skill |
| `agents/git-generated-files-and-hygiene.md` | Unique owner-preservation/diff hygiene | Migrated |
| `agents/final-report-and-owner-handoff.md` | Unique report vocabulary and handoff fields | Migrated |
| `agents/roles/CHATGPT.md`, `DEEPSEEK.md`, `CODEX.md` | Qortal role overlays | Migrated as platform overlays; control-plane `roles/` remains the active role authority |
| `docs/architecture/qortal-dapp-development-standard.md` | Unique durable Qortal standard | Migrated; linked from the platform pack |
| `docs/governance/source-of-truth-and-lifecycle.md` | Unique authority tiers and lifecycle | Migrated |
| `docs/workflows/workflow-v2.md` | Superseded execution contract with unique domain detail | Migrated as platform reference; control-plane `WORKFLOW.md` wins on routing |
| `docs/workflows/deepseek-primary-work-model.md` | Superseded role/escalation model | Migrated as platform reference; control-plane roles and workflow win |
| `docs/workflows/report-storage-policy.md` | Superseded report root/categories | Migrated as historical platform detail; control-plane `docs/REPORT-STORAGE-POLICY.md` wins |
| `templates/TASK-CONTROLLER.md`, `PROJECT-CONTEXT.md`, `AUDIT-ISSUE.md`, `IMPLEMENTATION-ISSUE.md`, `OWNER-HANDOFF.md`, `DEEPSEEK-TASK.md`, `DEEPSEEK-REVIEW.md` | Unique task/report shapes | Migrated under `platforms/qortal/guides/templates/`; the first four were also promoted to canonical `templates/` |
| `tools/validate-workspace.sh` | Structural Qortal workspace checker | **Superseded** by control-plane `validate_control_plane.py`, `validate_skills.py`, `validate_security.py` and the Git hooks |

### 4.2 Duplicated material

- The Qortal role overlays duplicate the control-plane role model at a platform
  level. They are retained as migrated platform references, not as a second
  authority.
- `docs/workflows/report-storage-policy.md` duplicates the central report-storage
  policy with an older root and different category names. The central policy
  wins.
- `docs/workflows/workflow-v2.md` and `deepseek-primary-work-model.md` duplicate
  the control-plane workflow/role model. The current `WORKFLOW.md`,
  `GIT-AND-HANDOFF.md` and `roles/` win.
- The mirrored `templates/` copies duplicate canonical templates. They are kept
  only to preserve original relative links in the migrated guides; the active
  templates are under `templates/`.

### 4.3 Unique but intentionally not migrated

| Material | Reason |
| --- | --- |
| `docs/shadow-archives-webportal/**` (24 reports and one smoke harness) | Project-specific historical evidence. It belongs to the Shadow Archives project and central project report history, not to global platform guidance. It remains in the legacy repository; provenance is recorded here. |
| `projects/shadow-archives-webportal.md` | Project-specific context with dated owner decisions and report links. Importing it without its report tree would create dangling links; it remains deferred to a project-context import. |
| `docs/ai-orchestration/audits/2026-09-13-universal-orchestration-audit.md` | Historical audit of the earlier orchestration cutover; already superseded by control-plane migration records. |
| `tools/validate-workspace.sh` | Replaced by stronger current validators and Git hooks; retaining it would create a second validation standard. |

### 4.4 Obsolete or conflicting material

- `.git`-era workstation paths (`/home/iffi/VsCodec-Projects/...`) are obsolete.
- Qortal node/tunnel details dated 2026-09-11/2026-09-13 are historical; current
  `ENVIRONMENT.md` requires per-task verification.
- Workflow v2 and the DeepSeek primary work model are superseded by Workflow v3.
- The old report root inside `qortal-dev-workspace` conflicts with the central
  `/home/iffi/dev-workspace/docs/<project>/<category>/` policy; the central
  policy wins.
- Two links in the legacy tree were already broken before migration
  (`2026-09-12-real-qortal-host-validation-report.md` and
  `projects/shadow-archives-webportal.md` pointed at
  `2026-09-11-owner-runtime-visual-correction-report.md`, while the file is
  `...-followup-report.md`). Those files were not migrated, so the broken links
  were not carried into the control plane.

## 5. Conflict resolution record

| Conflict | Resolution |
| --- | --- |
| Qortal workspace `AGENTS.md` says read the old `AI-Orchestration/AGENTS.md` first | Control-plane `AGENTS.md` is canonical; migrated guides are platform detail. |
| Qortal workflow v2 vs control-plane Workflow v3 | Workflow v3 governs execution; v2 is retained only for domain detail. |
| Qortal report root vs central report policy | Central `docs/REPORT-STORAGE-POLICY.md` wins. |
| Qortal role overlays vs control-plane roles | Control-plane `roles/` wins; overlays are platform references. |
| Legacy environment endpoints vs current registry | Current `ENVIRONMENT.md` wins; legacy endpoint values are historical. |
| `origin` remote vs canonical remote | Push to `dev-control-plane`; `origin` still points at the legacy donor repository and must not be used for canonical delivery. |
| Owner dirty skill changes vs migration commits | Owner changes are preserved; the migration commits only its own files and index rows. |

## 6. Executable Workflow v3 completion contract

The task-start and handoff rules are now machine-checked, not prompt advice:

- `tools/devjob/contract.py` evaluates a JSON contract for skill discovery,
  freshness, documentation loading, capability harvest, documentation updates,
  branch/protected-branch state, clean tree, scoped commit/paths, unauthorized
  merges, secret-bearing paths, secret-like diff content, and the authorized
  push/remote SHA.
- `dev start --contract-file` stores the contract with the job; `dev status` and
  `report.md` display the check results.
- Contract `FAILED` => job `FAILED`; contract `PENDING` => job `BLOCKED`.
  Contract failure never overrides a failed acceptance criterion.
- Push, protected-branch, merge, deploy, QDN, wallet and destructive actions
  remain separate explicit authorization fields. The contract verifies
  authorization; it does not grant it.
- `tools/test_completion_contract.py` covers the positive path and the negative
  cases.
- Canonical task/status templates and the Workflow v3 runbook carry the evidence
  fields.

## 7. Remaining gaps

1. **Shadow Archives project context and report tree** were not imported. The
   canonical project context is still "Pending Phase 2 import" in
   `PROJECT-REGISTRY.md`.
2. **QWB project context/evidence** remains deferred; the application checkout
   is absent from this workspace.
3. **Migrated Qortal guides are `verified-reference`, not re-validated runtime
   truth.** Their reference revisions date from 2026-09-11; each dependent task
   must rerun the freshness gate. They were not promoted to
   `verified-runtime`.
4. **No new live Qortal/Qortium runtime matrix** was executed for this
   consolidation. It is a documentation/control-plane change.
5. **The two pre-existing broken links in the legacy project-specific tree**
   were not repaired because those files were intentionally not migrated. They
   remain a legacy-repository data-quality issue.
6. **Owner dirty skill changes** in the working tree
   (`skills/README.md`, two Qortium skill updates and the untracked
   `skills/shared/browser-thumbnail-generation/`) were preserved but not
   committed by this task. They remain owner review items.
7. **The contract is policy, not an OS sandbox.** Shell wrappers, interpreters,
   SSH sessions and copied binaries can exceed visible command patterns. Owner
   authorization, Git hooks, branch protection and review remain authoritative.
8. **One real Workflow v3 job has not yet completed through the new contract.**
   The skill is therefore `candidate` until that runtime evidence exists.
