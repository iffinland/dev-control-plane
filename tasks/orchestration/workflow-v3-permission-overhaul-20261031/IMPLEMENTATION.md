# Implementation — control-plane/workflow-v3-permission-overhaul

Executing agent (actual executor of the work): DeepSeek
(`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261031T202338Z-workflow-v3-permission-model-ove-1225f2d4`.

Report/handoff writer (if different from the executing agent): same agent.

Exact application repository / branch / SHA:
`/home/iffi/dev-workspace/control-plane`,
`agent/control-plane/workflow-v3-20261031`, implementation commit
`efa9ae452cda93bdcbebbe19cc8922c6e73fee05`.

Verdict and measurable acceptance achieved:
The permission and outcome-classification overhaul is implemented and locally
validated. Full tests, control-plane validation and permission validation pass;
the effective merged profile was checked with `opencode debug agent`. Owner
review/merge and a restart of any long-running OpenCode session remain pending.

Investigation result:
The two latest Qortium Dev Monitor jobs were inspected from their structured
OpenCode session exports. Both rejected operations were `external_directory`
denials for the Workflow v3 state root
`/home/iffi/.local/state/dev-control-plane`:
`cat ~/.local/state/dev-control-plane/jobs/<id>/job.json ...`,
`cd ~/.local/state/dev-control-plane/monitor && python3 ...` and
`cp -a ~/.local/state/dev-control-plane /tmp/opencode/...`. A `/**` pattern does
not match the directory root itself. The old broad Qortium path substring
denials also rejected commands that merely mentioned those paths.

Changes:
- Added exact and recursive approved `external_directory` roots for the
  workspace, Workflow v3 state, OpenCode installation, `/tmp/opencode` and the
  tool-output cache; kept credential directories and the auth file denied.
- Denied Qortium wallet/seed/mnemonic/keystore material to file tools and common
  shell reads; kept node lifecycle, mutation, move/copy and redirection denied.
- Made job state readable but not editable by the agent.
- Replaced overbroad Qortium substring bash denials with targeted mutation
  denials so diagnostics and commands that only mention the paths work.
- Added ordered structured-event recovery: later successful tool activity
  recovers a permission denial; a later same-operation success recovers a failed
  command; unrelated successes, unresolved denials, missing dependencies, step
  exhaustion, incomplete work, `BLOCKED:` markers and failed required criteria
  remain authoritative.
- Updated the installer, operations documentation, adapter README and Workflow
  v3 contract text.
- Added regression tests for recovered/unresolved permission denials, recovered
  same-operation command failures, unrelated successes, exact directory roots,
  workflow state access and credential/wallet boundaries.

Skills used (path / maturity / freshness result):
No platform skill applied; control-plane contract and current Workflow v3 source
read directly.

Evidence by layer:
- `python3 -m unittest discover -s tools -p 'test_*.py' -q`: 253 tests, OK.
- `python3 tools/validate_control_plane.py`: PASS (54 Markdown files, 209 links,
  50 required files).
- `python3 tools/validate_agent_permissions.py`: PASS (337 rules, 97 checks).
- `python3 tools/validate_skills.py`: PASS (17 skills indexed once).
- `python3 tools/validate_security.py .`: PASS (157 files scanned).
- `python3 tools/opencode_guard.py check`: PASS.
- `tools/install_opencode_profiles.sh --check`: PASS, nothing installed.
- `tools/install_opencode_profiles.sh`: installed the updated profile with a
  timestamped backup.
- `opencode debug agent opencode-development`: merged effective rules loaded;
  workflow state and approved tooling allowed, credential paths and Qortium
  wallet reads denied, Qortium mutation denied.
- Scoped `git diff --check`: clean.

Required checks not executed and why:
No new real model session was started under the new profile. The running job
session kept its previous in-memory profile; restarting OpenCode during the job
would terminate it. Effective merged rules were verified through
`opencode debug agent`. No Qortium restart, monitor change or Telegram call was
made.

Preserved owner work:
Pre-existing dirty `skills/README.md`,
`skills/qortium/home2-qdn-publishing/SKILL.md`,
`skills/qortium/qdn-resource-discovery/SKILL.md` and untracked
`skills/shared/browser-thumbnail-generation/` remain untouched and unstaged.

Remaining findings / next actor / resume condition:
next actor = owner. Review and merge. Restart any long-running OpenCode session
to load the installed development profile. Resume from implementation commit
`efa9ae4`.

Canonical report path / SHA-256 / authorized remote evidence:
`/home/iffi/dev-workspace/docs/workspace/implementation/2026-10-31-workflow-v3-permission-overhaul.md`,
SHA-256 `719952a110f35381969d5c60f23a1a2449a054587ce36074b4838d314eeb80fc`;
local only, no remote publication authorized.

Commit and push state / verified remote SHA:
implementation commit `efa9ae452cda93bdcbebbe19cc8922c6e73fee05` plus handoff
commits on this branch; no push authorized; no remote SHA.
