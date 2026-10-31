# OpenCode adapter

Status: instruction-level adapter only. It does not copy governance, configure
automatic execution, or create a second policy.

## Discovery

OpenCode loads the canonical root instruction file through the owner's global
OpenCode `instructions` setting:

```text
/home/iffi/dev-workspace/control-plane/AGENTS.md
```

The local global configuration is:

```text
~/.config/opencode/opencode.jsonc
```

The entry is an absolute path so OpenCode can load the control plane when the
working directory is a registered project outside the control-plane directory.

## Inheritance and precedence

When working in a registered project:

1. explicit owner task authorization and constraints;
2. control-plane `AGENTS.md`, `WORKFLOW.md` and `GIT-AND-HANDOFF.md`;
3. the matching platform pack under `platforms/`;
4. the project's own `AGENTS.md`, which may add project-specific constraints but
   must not weaken the control plane or claim broader authority;
5. matching skills after their freshness check;
6. historical reports and task artifacts.

Do not overwrite an existing project-level `AGENTS.md`. Add only project-specific
deltas and let the root contract supply shared rules.

## Session persistence

Terminal session persistence with tmux is documented in the
[OpenCode tmux session runbook](../../docs/operations/OPENCODE-TMUX-SESSIONS.md).
tmux keeps an OpenCode terminal alive across SSH/Termius disconnects and allows
reattachment. It does not authorize autonomous execution: no service, scheduler,
polling loop or `opencode serve` listener is configured.

## Unattended execution

Bounded unattended execution is documented in the
[unattended runbook](../../docs/operations/UNATTENDED-OPENCODE.md). It uses:

- a separate restricted agent profile at
  [`agents/opencode-unattended.md`](agents/opencode-unattended.md), installed as
  `~/.config/opencode/agents/opencode-unattended.md`;
- the no-daemon guard at
  [`tools/opencode_guard.py`](../../tools/opencode_guard.py), which enforces a
  one-execution lock, resource preflight, an eight-hour maximum and safe process-
  group cancellation;
- the existing tmux terminal persistence and control-plane authorization rules.

The separate Workflow v3 development profile is
[`agents/opencode-development.md`](agents/opencode-development.md). It is used by
the `dev` CLI for owner-authorized development jobs. It allows project-local
dependency installation, builds/tests, Git commit/push/PR, SSH, QDN
publish/update, Qortal API calls, authorized development-wallet operations, live
application tests and read-only VPS/Qortium diagnostics. It still denies
Qortium/node mutation or signalling, VPS system-configuration changes, system
administration, global package installation, force-push, branch merge, release,
package publication and listener creation.

The development profile's command patterns are policy, not an OS sandbox. The
verified 1.19.5 semantics, the remaining wrapper/script/SSH bypasses and the
read-only diagnostic policy are documented in
[OpenCode permission semantics](../../docs/operations/OPENCODE-PERMISSIONS.md).
See also the [Workflow v3 runbook](../../docs/operations/DEV-WORKFLOW-V3.md).

Install either profile by copying the repository file to
`~/.config/opencode/agents/<name>.md` (or symlinking it). The control-plane
installer is `tools/install_opencode_profiles.sh`; it validates the development
profile first and supports `--check`, `--dry-run` and `--target`. It is never run
automatically by a job.

Verified v1.19.5 behaviour that the runbook relies on:

- `opencode run` is the non-interactive surface and waits for session idle;
- without `--auto`, `opencode run` auto-rejects `ask` permissions;
- exit code `0` means idle, not accepted work;
- session history persists in SQLite and can be resumed with `--session`;
- there is no native monetary budget cap or whole-run timeout.

The owner must not use `--auto` for unattended work. Permission patterns are not
a security sandbox; the control-plane contract and owner review remain
authoritative.

## Boundaries

- OpenCode is an execution client, not a governance source.
- No automatic commit, push, publish, deploy or QDN write is configured.
- No background agent, polling loop, scheduler or auto-dispatch is configured.
- Credentials and API keys remain in the owner's external configuration and
  must never be copied into this repository.
- Reports follow
  [`docs/REPORT-STORAGE-POLICY.md`](../../docs/REPORT-STORAGE-POLICY.md); the
  policy applies to every project session because OpenCode loads the canonical
  `AGENTS.md`.
- The global config is loaded at OpenCode startup. Restart OpenCode after the
  adapter or root contract changes.
