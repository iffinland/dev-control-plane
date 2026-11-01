# Task

## Target

- Repository:
- Branch:
- Outcome:
- Exit criterion:

## Task-start contract

Every new Workflow v3 job receives a mandatory completion contract
automatically. The harness initializes a job-specific evidence file under the
runtime state directory with observed metadata and `UNRECORDED` fields; fill
those fields truthfully before finishing. Initialization is not completion. An
explicit `--contract-file` may add constraints but cannot disable a mandatory
check.

- Skills discovered (paths, platform, maturity, freshness result):
- Relevant documentation read (control-plane and project paths):
- Baseline (branch, HEAD, owner changes):
- Tooling and environment verification:

## Scope and authorization

- In scope:
- Out of scope:
- Authorized external actions (each separately, otherwise none):
- Project delivery policy (registry remote / GitHub repository / branch pattern):
- Development-branch push authorized / remote:
- Protected-branch, merge, deploy, QDN, wallet, destructive actions authorized:
- Forbidden actions:

## Implementation

- First confirmed mismatch or approved design boundary:
- Smallest coherent change:
- Files/areas allowed to change:

## Validation

- Commands run and results:
- Runtime/host/QDN evidence:
- Missing or owner-only validation:

## Completion contract

- Capability harvest result:
- Documentation updates:
- Scoped commit(s):
- Authorized push and verified remote SHA (or the exact pending authorization):

Do not claim completion from OpenCode exit code 0, a build alone or a publish
response alone. The job record's acceptance criteria and completion contract are
authoritative. Preserve the working tree and session on timeout, step exhaustion
or cancellation so `dev resume` can continue.
