# Project-scoped GitHub delivery policy

Date: 2026-11-01
Status: implemented in the Workflow v3 control plane
Executing agent: DeepSeek

## Reason

Workflow v3 previously used `dev-control-plane` as the default remote for every
new job. That is correct for this control plane but wrong for registered Qortal
and Qortium projects whose delivery remote is `origin` and whose GitHub
repository is different. A project's remote must be resolved from that project's
validated configuration, not from a global name or a copied default.

## Registry schema

The registered-projects table gains four delivery columns:

| Column | Meaning |
| --- | --- |
| `Git remote` | Remote name that must exist in the verified checkout. |
| `GitHub repository` | `owner/name`; the remote URL must normalise to it. |
| `Development branch pattern` | Must stay inside `agent/*`. |
| `Automatic push` | Explicit `yes`/`no` owner grant for automatic delivery. |

The control plane registers itself separately with its real
`dev-control-plane` remote. Application projects use their own `origin` remote.
Missing, ambiguous, non-GitHub or URL-mismatched configuration refuses the start;
there is no fallback remote.

## Runtime behavior

- `dev start` resolves exactly one registry row by repository path or `--project`
  and validates the remote before creating a job.
- The Telegram Dev Monitor resolves the same policy during preview and passes
  `--project` and `--registry` to the same CLI. It never passes
  `--authorize-push` or a remote override.
- Automatic push is granted only for a valid policy, a URL-matched remote, and a
  non-protected branch matching `agent/*`. A different branch remains `PENDING`
  or fails if push was explicitly forced.
- The contract snapshot stores the resolved policy. Resume and status evaluate
  that snapshot rather than reading a new default.
- Existing jobs keep their recorded contract state; legacy jobs without a
  contract are untouched.
- Pre-existing owner dirty paths remain `allowed_dirty_paths` and
  `forbidden_paths`; owner work is never staged or cleaned.

## Mandatory checks

Task-start skill/freshness/documentation evidence, capability harvest,
documentation updates, the scoped commit, authorized push and verified remote SHA
remain mandatory. The new `delivery_policy` and `branch_policy` checks verify the
recorded project policy against the actual checkout and current branch.

## Regression coverage

- `tools/test_project_delivery_policy.py`: multiple project remotes, unregistered
  repository, missing/ambiguous/mismatched/non-GitHub remotes, invalid branch
  pattern, `agent/*` matching, disabled automatic push, unauthorized branch and
  failed push.
- `tools/test_dev_cli.py`: CLI uses the project remote, refuses a missing policy
  and a conflicting `--remote`, withholds automatic push outside `agent/*`, and
  fails the contract on a failed push.
- `tools/test_dev_monitor_control.py`: monitor start passes the project ID and
  registry path, performs no weakening override, and hides a project with an
  invalid policy from start eligibility.

## Boundaries

This policy does not authorize `main`/`master`/`trunk`, merges, tags, releases,
deployment, QDN writes, wallet transactions or server changes. It is a Git
delivery check, not an OS sandbox.
