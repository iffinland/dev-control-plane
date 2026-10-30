# Implementation: Qortal development knowledge integration

Executing agent: DeepSeek (runtime-declared `deepseek/deepseek-flash`, executed
via the OpenCode CLI harness). Report writer: DeepSeek.
Base: `main` @ `8c69e05f9e1d7f9bf7520b597f0fa7e58879df29`.

## Result

Integrated the two supplied Qortal development sources without adopting them as
platform truth. The material is classified, provenance-labelled and routed
through a new candidate skill plus condensed reference notes. Existing
Qortal/Qortium boundaries, data contracts, security rules and owner-controlled
publishing are unchanged.

## Files created

- `skills/qortal/legacy-dapp-audit-repair/SKILL.md` — reusable inventory →
  compatibility → reproduction → prioritized repair → regression → release
  readiness procedure.
- `platforms/qortal/references/README.md` — provenance, hashes, routing and
  reuse rules.
- `platforms/qortal/references/q-app-host-compatibility.md` — condensed host,
  bridge, QDN, security and release checks with unverified/conflicting claims
  called out.
- `platforms/qortal/references/legacy-app-audit-checklist.md` — operational
  checklist and evidence fields.
- `platforms/qortal/references/source-adoption-analysis.md` — adopted, rejected,
  Qortal/Qortium and unverified classification.
- `tasks/orchestration/qortal-development-knowledge-integration-20261031/`
  — `TASK.md`, `STATUS.json`, `IMPLEMENTATION.md`.

## Files modified

- `AGENTS.md` — routes legacy Qortal dApp work to the new skill; states the
  condensed reference is candidate and not platform truth.
- `WORKFLOW.md` — adds an authorized unattended/overnight-session delta without
  duplicating or weakening existing safety, validation and handoff rules.
- `platforms/qortal/README.md` — records the condensed reference and its
  candidate status; keeps full import deferred.
- `platforms/README.md` — updates pack status without changing the import
  boundary.
- `skills/README.md` — indexes the new skill exactly once.
- `ENVIRONMENT.md` — registers the central source-reference path.
- `README.md` — adds the Qortal legacy audit reference to the main document
  list.

## Adopted

- Qortal host/QDN audit checks as **questions to verify**, including serving and
  routing, `NAVIGATE_TO_PATH`, theme/frame, search semantics, data availability,
  publish/fee/timeout, money verification, encryption, storage isolation,
  sanitization, media and release verification.
- Legacy audit methodology and release matrix.
- Preserve data contracts; additive changes; no automatic publish/pay; verify
  before retry.
- Generalized overnight practices: bounded outcome, no routine blocking,
  recorded follow-ups, serial money/data baseline, disjoint parallel work,
  one shared-runtime driver, budget stop condition and morning summary.

## Rejected

- Third-party guide as platform authority or as verified contracts.
- Q-Shop+/qplus-app product scope, paths, branches, design decisions, exact
  tooling, usage threshold and PR wording.
- Copying the guide's templates/code into the control plane.
- Any universal app framework.
- Transferring Qortal bridge/QDN rules to Qortium.
- Adding a background agent, scheduler or automatic task execution.

## Qortal vs Qortium

The new skill and references are Qortal-only. Qortium receives no Qortal
contract; only the platform-independent audit/overnight *practices* are recorded
as candidates for separate Qortium validation. Qortium skills and the Qortium
pack were not modified.

## Unverified and compatibility risks

- Version pins (Core 6.1.9, Hub 3.0.3, GO 3.0) were not revalidated against
  current source/runtime.
- Exact CSP, dialog lifetime, timeout tables, service caps, fees, host `develop`
  actions, `pollOptions`, private-encryption enforcement and several release
  behaviors remain version-sensitive.
- `exactmatchnames` guidance conflicts with the existing verified
  `qortal-qdn-content-crud` observation; the existing skill wins and the
  conflict is recorded.
- `PUBLISH_MULTIPLE` result shape is documented as both reject and resolve; the
  existing skill's observation is retained.
- The new skill is `candidate` until a real legacy app audit is completed.

## Validation

- `python3 tools/validate_control_plane.py` — passed.
- `python3 tools/validate_skills.py` — passed (16 skills indexed exactly once).
- `python3 tools/validate_security.py .` — passed.
- `python3 tools/test_git_hooks.py` — passed.
- GitHub Actions result and PR link: see the central report.

No application, platform, server, QDN or transaction action was performed.
