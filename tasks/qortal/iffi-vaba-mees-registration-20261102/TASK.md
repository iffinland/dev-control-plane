# qortal/iffi-vaba-mees-registration-20261102: register Qortal CMS and diagnose cover-image error

Contract: /home/iffi/dev-workspace/control-plane/AGENTS.md
Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through Workflow v3 job
`20261102T083541Z-register-qortal-cms-and-investig-44833fa6`.
Project ID / exact repo / base SHA / agent branch:
`qortal/iffi-vaba-mees` / `iffinland/iffi-vaba-mees-QORTAL` at
`64f55bf7b6f4a1a093f19413d3a985e61a9fad37` / no application branch created;
control-plane handoff is on `agent/control-plane/workflow-v3-20261031`.
Platform session router / canonical project context:
Qortal platform pack (`platforms/qortal/README.md`); project context is the
checkout itself (no project `AGENTS.md`). Central report root:
`/home/iffi/dev-workspace/docs/iffi-vaba-mees-QORTAL/`.

Outcome and measurable exit criterion:
Register the existing Qortal website repository in Workflow v3 with a valid
`origin` / `iffinland/iffi-vaba-mees-QORTAL` / `agent/*` / automatic-push policy
and a verified acceptance profile; establish read-only Qortal API connectivity;
determine whether the live `WEBSITE/iffi vaba mees` resource corresponds to the
repository; trace `Cover image could not be processed.` to source and name
regression tests. Exit when registry, policy, profile, tests and validators pass
and scoped registration/documentation changes are committed and pushed.

In scope / out of scope / invariants:
In scope: read-only repository inspection, safe clone, registry and acceptance
profile, monitor visibility check, read-only Qortal API/QDN metadata, source
trace and documentation. Out of scope: CMS application changes, QDN writes,
wallet transactions, Qortium node changes, deploy, merge and main-branch push.
Invariant: preserve pre-existing owner dirty paths in the control plane and
never overwrite an existing project checkout.

Applicable skills (path / platform / maturity / freshness result):
- `skills/qortal/legacy-dapp-audit-repair` (Qortal, candidate): used for the
  read-only audit structure; its freshness gate was satisfied only for
  source/metadata layers, not real host reproduction.
- `skills/qortal/qortal-host-bridge-contract` (Qortal, verified-reference):
  used for bridge/CSP/QDN boundary checks; current live gateway headers were
  checked (`img-src 'self' data: blob:`).
- `skills/shared/browser-thumbnail-generation` (shared, candidate): used for the
  image decode/bounds failure analysis; not reused as runtime-proven.
- `skills/shared/workflow-v3-completion-contract` (shared, candidate): used for
  task-start evidence, scoped commit, authorization and remote-SHA checks.
Freshness result: repository source inspected at `64f55bf`; live Qortal API
metadata and gateway headers observed 2026-11-02. No skill was promoted.

Documentation read (control-plane / platform pack / project):
`AGENTS.md`, `WORKFLOW.md`, `GIT-AND-HANDOFF.md`, `PROJECT-REGISTRY.md`,
`ENVIRONMENT.md`, `docs/operations/DEV-WORKFLOW-V3.md`, `platforms/qortal/README.md`,
`skills/README.md` and the loaded skills above; project `README.md`,
`PROJECT_ROADMAP.md`, `agents/README.md`, `package.json`, `vite.config.js`,
services, hooks and the blog publish modal.

Reference freshness evidence / environment IDs:
Application `main` `64f55bf7b6f4a1a093f19413d3a985e61a9fad37`; isolated build
from that commit; Qortal node status/height observed read-only on 2026-11-02.

Proven reference implementation to reuse (or exact missing investigation delta):
The project itself is the only source for the failing `loadImageFile` path. No
current verified fix exists; the missing delta is a reproducible failing image
fixture and a real Host reproduction.

Required surfaces and real runtime acceptance steps:
Registry policy resolution, monitor registry/profile resolution, `npm run lint`,
`npm run build`, control-plane unit tests and validators. Owner-only: identify
the intended live source and reproduce the image failure in the real Host with
the failing file; no QDN publication until separately authorized.

Authorized external actions (exact repo, branch, operation; otherwise none):
Commit and push only scoped registration/documentation changes to
`iffinland/dev-control-plane` on
`agent/control-plane/workflow-v3-20261031`. No application commit/push, no main
push, no merge/deploy, no QDN write, no wallet transaction, no Qortium change.

Unattended execution authorization (only when explicitly granted):
- Agent profile / guard command / maximum wall-clock:
  `opencode-development`; `opencode_guard.py`; job timeout 7,200 s.
- Resource limits / stop condition:
  Guard preflight; stop at acceptance or timeout.
- Checkpoint cadence and recovery:
  Guard check at phase boundaries; preserve working tree/session for resume.

Forbidden actions (unattended):
CMS application edits, QDN publishing, wallet or mainnet transactions, Qortium
node/service/data/log/JAR changes, VPS system changes, port exposure, firewall or
tunnel changes, credential/private-key access, destructive cleanup, name-based
signalling.

Acceptance evidence required (OpenCode exit code 0 alone is not success):
Exact registry/profile diff, policy resolution, monitor parser result, live QDN
metadata and gateway/bundle comparison, source trace, control-plane test and
validator output, commit SHA and matching remote SHA.

Canonical report path / handoff branch:
`/home/iffi/dev-workspace/docs/iffi-vaba-mees-QORTAL/audit/2026-11-02-registration-and-cover-image-diagnosis.md`;
control-plane handoff on `agent/control-plane/workflow-v3-20261031`.

Owner-only steps or reason owner validation is not applicable:
Owner must decide which source should publish `WEBSITE/iffi vaba mees`: the
live bundle is a different Qortal CMS application, not this repository's
`main` build. Owner must also supply a failing cover file/user agent before the
image error can be reproduced and fixed.

Capability-harvest expectation (likely reusable capability or project-specific):
Project-specific live-resource mismatch and image decode diagnosis; no new
global skill. The existing browser-thumbnail and host-bridge skills cover the
reusable parts and were not upgraded without real runtime evidence.

Documentation updates expected (or explicit none):
`PROJECT-REGISTRY.md`, `acceptance-profiles.json`, this compact handoff and the
central audit report. No platform-pack change.

Scoped commit expectation (exact paths):
`PROJECT-REGISTRY.md`, `acceptance-profiles.json`,
`tasks/qortal/iffi-vaba-mees-registration-20261102/TASK.md`,
`tasks/qortal/iffi-vaba-mees-registration-20261102/STATUS.json`.

Remote SHA verification expectation:
Push the scoped commit to `dev-control-plane` on the authorized branch and
verify `git ls-remote` equals local `HEAD`.
