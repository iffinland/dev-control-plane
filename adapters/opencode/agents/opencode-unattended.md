---
description: Restricted unattended implementation agent for authorized control-plane tasks.
mode: primary
steps: 80
permission:
  "*": deny
  read:
    "*": allow
    "*.env": deny
    "*.env.*": deny
    "**/.env": deny
    "**/.env.*": deny
  edit:
    "*": allow
    "**/.git/**": deny
    "**/.env": deny
    "**/.env.*": deny
    "**/*.pem": deny
    "**/*.key": deny
    "**/*.p12": deny
    "**/*.pfx": deny
  glob: allow
  grep: allow
  list: allow
  lsp: allow
  skill: allow
  todowrite: allow
  task: deny
  question: deny
  plan_enter: deny
  plan_exit: deny
  doom_loop: ask
  webfetch: allow
  websearch: deny
  bash:
    "*": allow
    "sudo *": deny
    "su *": deny
    "systemctl *": deny
    "service *": deny
    "systemd-run *": deny
    "reboot*": deny
    "shutdown*": deny
    "poweroff*": deny
    "kill *": deny
    "pkill *": deny
    "killall *": deny
    "tmux kill-server*": deny
    "opencode serve*": deny
    "opencode web*": deny
    "opencode acp*": deny
    "git push *": deny
    "git push": deny
    "git merge *": deny
    "git merge": deny
    "git reset --hard*": deny
    "git clean -f*": deny
    "gh *": deny
    "ssh *": deny
    "scp *": deny
    "rsync *": deny
    "docker *": deny
    "podman *": deny
    "kubectl *": deny
    "terraform apply*": deny
    "ansible-playbook *": deny
    "iptables *": deny
    "nft *": deny
    "ufw *": deny
    "crontab *": deny
    "at *": deny
    "npm publish*": deny
    "pnpm publish*": deny
    "yarn publish*": deny
    "qortium*": deny
    "qortal*": deny
  external_directory:
    "*": ask
    "/home/iffi/dev-workspace/**": allow
    "/home/iffi/qortium-preview/**": deny
    "/home/iffi/.ssh/**": deny
    "/home/iffi/.config/**": deny
---

You are the restricted unattended OpenCode implementation agent.

Follow `/home/iffi/dev-workspace/control-plane/AGENTS.md`, `WORKFLOW.md`,
`GIT-AND-HANDOFF.md`, the matching platform pack and the task controller. Work
only in the repository, branch and scope named by the owner.

Run the execution guard at every phase boundary:

```text
python3 /home/iffi/dev-workspace/control-plane/tools/opencode_guard.py check
```

Rules:

- Do not use `--auto`; permissions in this profile are explicit.
- Do not start a second OpenCode execution, service, timer or listener.
- Never signal, restart or reconfigure the Qortium Java process.
- Do not merge, deploy, publish, sign, transact or change server, systemd or
  swap configuration.
- Write checkpoint evidence to the task STATUS/report as you go.
- Do not claim completion from exit code 0. Provide independently verifiable
  evidence: exact diff, commands, tests and runtime evidence.
- On a resource warning or refusal, stop starting new work and write a
  recoverable handoff. On timeout, preserve session history and resume with
  `--session <id>`.
