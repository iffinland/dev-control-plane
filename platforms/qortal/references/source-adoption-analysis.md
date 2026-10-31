# Source adoption analysis: Qortal development knowledge

Date: 2026-10-31. Status: decision record for this integration.
Sources: `PROMPT-night-1.md` and `QORTAL_Q_APP_MASTER_GUIDE_FOR_LLMS.md`, as
recorded in [`README.md`](README.md). Both were read in full.

This analysis classifies the supplied material. It does not make the material
platform authority. Current Qortal/Qortium source and observed runtime remain
authoritative.

## 1. Qortal-specific technical requirements

Adopted as **audit checks** (not as verified contracts) because they describe
the Qortal Q-App host/QDN boundary and match the shape of existing Qortal
skills:

- `qortalRequest` host detection; outside-host rejecting stub.
- QDN `APP` vs `WEBSITE` serving, relative asset base, injected `_qdn*`
  globals, router basename and deep-link behavior.
- `NAVIGATE_TO_PATH` → immediate `NAVIGATION_SUCCESS`; no `history.back()`.
- Theme boot order, live `THEME_CHANGED`/`LANGUAGE_CHANGED`, frame-height and
  mobile/keyboard layout.
- Search semantics: explicit `service`, `mode=ALL` for lists, explicit `limit`,
  contains-by-default matching, exact re-check in code, encoding by the app.
- Data-not-on-node status/retry behavior; search row as authority; body
  validation and normalization.
- Identifier rules, JSON versioning, UTF-8-safe base64, tombstone semantics,
  block-time deadlines.
- Publish fee/name prerequisites, no automatic publish, unconfirmed-transaction
  batching, timeout-is-unknown, decline-is-quiet, verify-before-retry.
- Money validation and on-chain payment verification; public-node degradation.
- `*_PRIVATE` encryption, public metadata, shared-origin storage isolation,
  HTML sanitization, link/media handling.
- Release artifact, zip-layout, metadata file-list and served-build checks.

Detailed operational form:
[`q-app-host-compatibility.md`](q-app-host-compatibility.md).
Reusable procedure:
[`legacy-dapp-audit-repair` skill](../../../skills/qortal/legacy-dapp-audit-repair/SKILL.md).

## 2. Potentially reusable Qortium practices

These are **practices**, not Qortal contracts. They may inform Qortium work only
after checking Qortium Home/Core source and runtime:

- audit phases and evidence fields;
- explicit write/money gates, no automatic retry, timeout as unknown;
- distinguishing search/list metadata from byte availability;
- additive data versioning and tombstone-compatible readers;
- compatibility matrices and old↔new fixture tests;
- release artifact versus served-bytes verification;
- accessibility, keyboard, responsive and theme checklists;
- overnight-session integration discipline.

Not transferable to Qortium without separate evidence:

- `qortalRequest`, `q-apps.js`, Qortal host messages and CSP;
- Qortal service names, identifiers, fees, name/account semantics;
- Qortal encryption/service rules and Core REST paths;
- Qortal `APP`/`WEBSITE` routing assumptions.

The Qortium pack and its skills remain unchanged. See
[`platforms/qortium/README.md`](../../qortium/README.md).

## 3. Platform-independent development workflows

Adopted:

- inventory before judging; reproduce before fixing; evidence over opinion;
- compatibility matrix with explicit `unknown`;
- severity-based prioritization (data/money/security first);
- pin money/data behavior with tests before changing it;
- smallest coherent change; one logical change per commit;
- layered validation and a single final release gate;
- release-readiness evidence and served-artifact verification;
- capability harvest after the task;
- overnight/unattended discipline when the owner explicitly authorizes it.

Overnight additions were integrated into
[`WORKFLOW.md`](../../../WORKFLOW.md) as a compact authorized-session delta,
not as a second workflow. Existing safety, identity, validation-cadence and
handoff rules still apply.

## 4. Project-specific guidance not adopted

From `PROMPT-night-1.md`, the following remain Q-Shop+/qplus-app project
evidence and are **not** global rules:

- Q-Shop+ product scope, feature list, visual direction, Q-Share+/Q-Mail+/
  Q-Mintership+ reuse targets and specific component names;
- the exact worktree path, branch, package manager commands, ESLint 9 config,
  `scripts/build-zip.sh`, test counts and release title;
- the 85% usage threshold, specific round structure, screenshot matrix and
  PR wording;
- "Simon is asleep" instructions, specific open questions and product decisions
  (version `1.0.0`, Q-Shop+ share links, blocked-names list);
- any instruction to publish, pay, deploy or open a PR that is specific to that
  project rather than authorized by the current task.

The **practice** of a bounded overnight session, disjoint parallel work,
integration one change at a time, a budget stop condition and a morning summary
was adopted in generalized form.

## 5. Unverified or version-sensitive claims

Left as questions, not rules:

- all version pins (Core 6.1.9, Hub 3.0.3, GO 3.0, Electron/WebView versions);
- exact CSP header, sandbox flags, dialog lifetime and late-Accept behavior;
- timeout tables, cold-read duration and retry counts;
- service size caps, fees, unconfirmed limit and chat retention/rate limits;
- `pollOptions` single-string behavior and action parameters on newer hosts;
- Hub `develop` `<webview>` model and unreleased action parameters;
- DOMPurify minimum version;
- `qapp-core` `publicSalt`/identity compatibility;
- private-encryption enforcement for `FILE`/`IMAGE`/`DOCUMENT`;
- `exactmatchnames` exact filtering (conflicts with an existing verified skill);
- `PUBLISH_MULTIPLE` result shape (existing skill observed reject and resolve);
- Dev Mode proxy behavior and in-app Back history effect.

Full list:
[`q-app-host-compatibility.md` §9](q-app-host-compatibility.md#9-claims-requiring-confirmation-before-reuse).

## 6. Adopted and rejected recommendations summary

| Recommendation | Decision | Reason |
| --- | --- | --- |
| Use the guide as a self-contained build manual | Rejected as authority | Third-party, version-pinned, partly unverified. Used as audit input only. |
| Apply the guide's Golden Rules as verified contracts | Rejected | They are hypotheses to check; several are version-sensitive. |
| Build a legacy audit/repair procedure | Adopted | Reusable, evidence-based, matches owner priority. |
| Preserve data contracts and additive changes | Adopted | Required for backward compatibility. |
| No auto-publish/pay; verify after timeout | Adopted | Protects money and data; already aligned with governance. |
| Inventory and prioritized repair queue | Adopted | Prevents rewrite-first debt. |
| Full release-test matrix and served-build check | Adopted | Strong release-readiness gate. |
| Copy the guide's templates/code into the control plane | Rejected | Unnecessary duplication; platform source is the reference. |
| Import Q-Shop+ product/design decisions | Rejected | Project-specific. |
| Create a universal app framework | Rejected | Governance explicitly avoids giant abstractions. |
| Treat guide claims as Qortium truths | Rejected | Separate platform authority. |
| Add overnight autonomy as a new background service | Rejected | No background agent/scheduler is authorized; only an explicitly authorized session delta. |
| Add overnight prompt practices | Adopted in generalized form | Useful for bounded unattended work without duplicating safety rules. |

## 7. Qortal versus Qortium applicability

| Area | Qortal | Qortium |
| --- | --- | --- |
| Host bridge | `qortalRequest` / q-apps.js audit rules | Qortium Home `qdnRequest`; separate |
| Serving | `APP`/`WEBSITE`, `_qdnBase` | Separate Home/QDN runtime |
| Search/publish | Qortal QDN service and fee rules | Home 2 source-token flow; separate skills |
| Audit methodology | Applicable | Applicable only as a practice, with Qortium evidence |
| Overnight discipline | Applicable | Applicable |
| Data compatibility | Preserve Qortal contracts | Preserve Qortium contracts separately |
| Release verification | Artifact/served-bytes principle applies | Principle applies; mechanics separate |

## 8. Conflict check

The new guidance was checked against:

- [`AGENTS.md`](../../../AGENTS.md): no new authority, no background service, no
  relaxed write/publish rules; identity and report rules unchanged.
- [`WORKFLOW.md`](../../../WORKFLOW.md): reuse-first, bounded fix vs checkpoint,
  capability harvest and handoff remain intact; the new section only adds an
  explicitly authorized unattended-session delta.
- [`GIT-AND-HANDOFF.md`](../../../GIT-AND-HANDOFF.md): branch, task, identity and
  push-permission rules unchanged.
- Qortal platform pack: the full-documentation deferral is clarified; the new
  material is labelled candidate and is not a full import.
- Qortium platform pack and skills: no Qortal contract was added to Qortium
  guidance; Qortium skills were not modified.
- Existing verified Qortal skills: where the guide conflicts, the verified skill
  wins and the conflict is recorded.

No unresolved governance conflict was found.
