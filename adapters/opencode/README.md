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
