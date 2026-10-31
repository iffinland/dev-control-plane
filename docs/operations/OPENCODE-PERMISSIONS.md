# OpenCode permission semantics and development policy

Status: active reference, verified against OpenCode 1.19.5 on 2026-10-31.
Scope: the Workflow v3 `opencode-development` profile and the limits of its
command-pattern controls.
Related: [Workflow v3 runbook](DEV-WORKFLOW-V3.md),
[unattended runbook](UNATTENDED-OPENCODE.md),
[OpenCode adapter](../../adapters/opencode/README.md),
[control-plane contract](../../AGENTS.md).

## Why this document exists

The development profile is deliberately more permissive than the restricted
unattended profile: normal development needs Git, SSH, builds, tests, package
installation, Qortal/QDN tooling and live application checks. It also needs
read-only diagnostics of the VPS and the running Qortium node.

Those permissions are **policy rules**, not an operating-system sandbox. This
document records what OpenCode actually enforces, what the profile intends, and
which actions remain outside pattern enforcement. Never describe these rules as
OS-level isolation.

## Verified OpenCode 1.19.5 behaviour

Evidence:

- local client: `/home/iffi/.opencode/bin/opencode --version` -> `1.19.5`;
- upstream tag `v1.19.5`, commit
  `810c0eba1a7348036f8bdf61e6632d0c36c6876c`;
- permission engine:
  `packages/opencode/src/permission/index.ts` and
  `packages/opencode/src/util/wildcard.ts`;
- shell tool: `packages/opencode/src/tool/shell.ts` and
  `packages/opencode/src/permission/arity.ts`;
- public semantics: <https://opencode.ai/docs/permissions/>.

The tested agent definition is visible without starting a model session:

```bash
opencode debug agent opencode-development
```

Key facts that the profile relies on:

1. A rule resolves to `allow`, `ask` or `deny`.
2. Rules are evaluated by pattern match and the **last matching rule wins**.
   Agent rules are merged with global configuration and take precedence.
3. Patterns use simple wildcards: `*` matches any characters, `?` matches one
   character, and a pattern ending in `" *"` also matches with no arguments.
4. Without `--auto`, a non-interactive `opencode run` auto-rejects `ask`
   requests. The development profile therefore uses explicit `allow`/`deny`
   rules rather than relying on prompts.
5. Bash rules match the source text of each command parsed by tree-sitter, not
   the whole shell line. Chained commands are evaluated separately. Redirections
   are included in a command's source text.
6. `external_directory` is a separate check for paths outside the OpenCode
   working directory. Path permissions for `read` and `edit` are also separate
   from `bash`.
7. An exit code of `0` means the session went idle, not that the requested work
   was accepted.

## Development policy

The canonical profile is
[`adapters/opencode/agents/opencode-development.md`](../../adapters/opencode/agents/opencode-development.md).
It allows:

- `git commit`, feature-branch `git push`, and `gh pr create`/`gh pr view`;
- `ssh` for development and read-only remote diagnostics (see the limitation
  below);
- project-local dependency installation, builds, tests, linters, scripts and
  live application checks;
- QDN publish/update tooling and Qortal API calls when the job authorizes them;
- development-wallet transactions only when the job explicitly authorizes them;
- read-only VPS/Qortium diagnostics: `ps`, `top`, `free`, `df`, `uptime`,
  `journalctl`, `systemctl status/show/cat/list-*`, `service ... status`,
  `dpkg -l`, `apt list`, `sysctl -a`, `ip ... show`, `dmesg`, and read-only
  reads of Qortium logs/configuration through the `read` tool.

It denies or constrains:

- `sudo`, `su`, privilege-escalation paths, system package managers, global
  package installs, `systemd-run`, reboot/shutdown/poweroff, `crontab`/`at`;
- mutating service-manager operations (`systemctl start/stop/restart/...`,
  `service ... start/stop/restart`), process-name signals, and
  `tmux kill-server`;
- `opencode serve/web/acp/upgrade`, network listeners and package-registry
  publication (`npm/pnpm/yarn publish`);
- force-push, `git reset --hard`, `git clean -f`, branch merge, PR merge,
  release and repository deletion;
- containers/orchestration, `iptables`/`nft`/`ufw`, `nsenter`, `chroot`,
  hostname/timezone/locale changes, network-interface changes, mounts, swap and
  kernel-module changes, and `journalctl` maintenance options;
- starting or writing the Qortium node: `qortium*`, `java ... qortium`, the JAR,
  `/home/iffi/qortium-preview/**` and `/home/iffi/qortium-data/**` for shell
  writes and edits. The same paths are allowed for diagnostics and the `read`
  tool;
- `.env`/key files for the `read` and `edit` tools, with `.env.example` allowed.
  Bash has best-effort denials for `.env` and direct key reads, but see the
  limitations below.

### Read-only Qortium examples

```bash
ps -o pid,ppid,user,etimes,rss,args -p <pid>
systemctl status qortium
systemctl --no-pager status qortium
journalctl -u qortium -n 100 --no-pager
service qortium status
```

Use the `read` tool for node configuration and logs. Do not use `tail >`,
`tee`, `cat >`, `rm`, `mv`, `cp`, `chmod`, `chown`, `truncate` or `dd` against
the node paths. Shell redirection against `/home/iffi/qortium-preview/**` and
`/home/iffi/qortium-data/**` is denied, but the pattern rules are not a complete
write barrier.

## Limits of command-pattern control

The profile is useful for preventing ordinary accidents and making policy
visible. It is not isolation. These limitations are intentional and must be
stated in any report that cites the profile as a safety control.

| Limitation | Example | What actually happens |
| --- | --- | --- |
| Shell wrappers hide the inner command | `bash -c 'sudo ...'`, `sh -c 'systemctl restart qortium'` | The visible command starts with `bash`/`sh`; the inner text is a string argument. |
| Interpreters and scripts | `python3 script.py`, `node -e "...open('/home/iffi/qortium-preview/x','w')..."` | The command line does not contain the sensitive verb or path. |
| `env`/`command` wrappers | `env sudo ...`, `command sudo ...` | The deny patterns match command names, not every wrapper form. |
| Command substitution and pipes | `echo "$(sudo ...)"`, `cat file \| sh` | The outer command is evaluated; a generated or piped script is not. |
| Remote SSH execution | `ssh host 'sudo systemctl restart qortium'` | SSH is allowed; the remote shell and remote policy are outside these local rules. |
| Path-qualified binaries | `/usr/bin/sudo ...` | Absolute-path variants are denied where listed, but aliases, copied binaries and wrappers remain. |
| Bash is not `read`/`edit` | `cat .env`, `python -c "open('.env').read()"` | `.env` denials on the `read` tool do not automatically apply to shell reads. Narrow shell denials are best-effort. |
| External-directory checks are partial for bash | `ls /etc`, `grep ... /etc/...` | In 1.19.5 the shell tool scans paths only for a fixed set of file commands; the V2 core marks command-argument path detection as advisory. |
| QDN/dev-wallet semantics | `qortal` transaction or publish command | The pattern allows the CLI call; it cannot distinguish mainnet from testnet, dev wallet from main wallet, or a safe metadata update from a real transaction. |
| Protected-branch semantics | `git push origin main` | The profile cannot know which remote branch is protected. Git hooks, branch protection and owner review remain authoritative. |
| Service identity | `systemctl --user stop qortium` | Only listed read-only verbs are re-allowed; a wrapper can still call a mutating verb. |

### What is enforced

- OpenCode's own `read`/`edit`/`external_directory` checks for its tools are
  real enforcement *inside those tools*: editing
  `/home/iffi/qortium-preview/**` is denied, and reads outside the workspace
  require an explicit `external_directory` allow.
- The execution guard enforces one heavyweight OpenCode run at a time, reads
  Qortium only to report PID/RSS, and terminates only the process group it
  created.
- Git hooks, branch protection and owner review remain the controls for
  branches, pushes and merges.

### What is not enforced

- No OS-level isolation, container, seccomp, mount namespace, read-only bind
  mount or mandatory access control is configured by this repository.
- No host-level protection prevents a shell script, interpreter, SSH session or
  copied binary from changing files the user account can write.
- No monetary, wallet-network or QDN target validation exists in the profile.
- No continuous mutation monitor of the Qortium node is provided. The guard's
  Qortium read is observational only.

Do not add a broader claim to a task report, commit message or notification.

## Validation

Run the policy checker after any profile change:

```bash
python3 tools/validate_agent_permissions.py --check
python3 tools/validate_agent_permissions.py --matrix
python3 tools/validate_agent_permissions.py --limitations
python3 tools/test_agent_permissions.py
python3 tools/test_opencode_guard.py
python3 tools/test_install_profiles.py
```

The checker implements OpenCode's last-match wildcard model and a conservative
top-level shell splitter. It is a regression check for the intended policy, not
a substitute for `opencode debug agent` or a live test.

After installing profiles, verify the merged definition that OpenCode will
actually load:

```bash
opencode debug agent opencode-development
```

If global `opencode.jsonc` rules change, re-run that command: agent rules are
merged with global rules, and the effective order matters.

## Refresh gate

Re-inspect the OpenCode source and this document when the local client changes
version, when `opencode debug agent` shows a different rule order, or when the
permission docs change. Permission semantics are version-dependent; an upgrade
can invalidate the profile's assumptions.
