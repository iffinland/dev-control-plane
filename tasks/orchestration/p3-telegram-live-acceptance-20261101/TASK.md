# workspace/p3-telegram-live-acceptance: isolated P3 live harness

Contract: `/home/iffi/dev-workspace/control-plane/AGENTS.md`

Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T140335Z-p3-telegram-live-acceptance-test-c2538145`.

Project ID / exact repo / base SHA / agent branch:
`control-plane/control-plane` / `/home/iffi/dev-workspace/control-plane` /
`1660f03f61eab7dbf4acbf889f34de735fc7d404` /
`agent/control-plane/workflow-v3-20261031`.

Outcome and measurable exit criterion:
Implement a safe, reusable P3 live Telegram acceptance harness for Queue
instruction and Cancel job. It must use an isolated temporary Git repository, a
generated temporary project registry, temporary monitor/Workflow state and a
deterministic fake worker; never start OpenCode or spend model budget; never edit
the owner Telegram config or production registry; force the synthetic job to
`CANCELLED`; fail closed while the production monitor is running; and provide
cleanup, regression tests, operator instructions and precise evidence capture.
All required acceptance commands, the broader validator set and the permission
check must pass. The live Telegram run is not executed by the agent.

In scope / out of scope / invariants:
In scope: `tools/devmonitor/acceptance.py`,
`tools/p3_live_acceptance.py`, `tools/test_p3_live_acceptance.py`, the small
`_build_components` injection point, operations documentation, validator
required-file list and task evidence. Out of scope: live Telegram actions, live
monitor restart/configuration, production registry changes, production projects,
Qortium node/service/data/logs, VPS changes, deployment, merge, QDN, wallet or
push beyond the authorized development branch.

Applicable skills (path / maturity / freshness result):
No matching reusable Qortal/Qortium platform skill exists for this control-plane
test harness. Reused current monitor/Workflow v3 source and the P3/P4 tests and
runbooks. `skills/shared/capability-harvest` was read for the final decision test.
The owner-dirty `skills/README.md` is forbidden, so no new skill index entry was
attempted; harvest result is project-specific/control-plane.

Authorized external actions (exact repo, branch, operation; otherwise none):
Commit task-owned files and push to `dev-control-plane` branch
`agent/control-plane/workflow-v3-20261031` under the job's validated delivery
policy. No live Telegram action, service restart, merge, deploy, QDN, wallet or
server action.

Required surfaces and real runtime acceptance steps:
Automated: full `unittest` discovery, control-plane/skills/security validators and
agent-permission check. Owner-only: stop the production monitor manually, run
`prepare` then `run --confirm-live-telegram`, perform Queue instruction and Cancel
job in the private owner chat, fill `telegram-evidence.json`, run `verify`, then
`cleanup` and restart the production monitor manually. This was not executed by
the agent.

Acceptance evidence required:
Exact diff and commit SHA, full test output, validator outputs, permission check,
guard check, preserved owner dirty paths and the job evidence file. Live
Telegram message/update IDs and callback labels are captured by the harness
journal when the owner performs the run.

Canonical report path / handoff branch:
`tasks/orchestration/p3-telegram-live-acceptance-20261101/IMPLEMENTATION.md`;
`agent/control-plane/workflow-v3-20261031`.

Owner-only steps:
The real bot interaction, production monitor stop/start and the Qortium/no-change
attestation remain owner actions. The agent did not send Telegram messages, run
the harness live, restart services, create transactions, force-push or merge.
