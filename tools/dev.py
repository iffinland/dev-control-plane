#!/usr/bin/env python3
"""Workflow v3 development CLI.

Commands:
    dev start    create and start a detached development job
    dev status   show one job or list jobs
    dev report   render the durable job report
    dev logs     read or follow a job log
    dev resume   continue an existing job without discarding work
    dev accept   record owner acceptance for manual criteria

Jobs run in their own session, so they survive SSH disconnects without tmux.
The existing execution guard still enforces resource preflight, one heavyweight
OpenCode execution, the eight-hour wall-clock maximum and safe process-group
cancellation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from devjob import __version__, runner  # noqa: E402
from devjob.store import (  # noqa: E402
    JobLocked,
    StoreError,
    job_dir,
    latest_job,
    list_jobs,
    load_job,
    state_root,
    worker_is_alive,
)


def _apply_state_dir(args: argparse.Namespace) -> None:
    value = getattr(args, "state_dir", None)
    if value:
        os.environ["DEV_CONTROL_PLANE_STATE"] = str(Path(value).expanduser())


def _resolve_job(args: argparse.Namespace) -> dict:
    identifier = getattr(args, "job_id", None)
    if identifier:
        return load_job(identifier)
    job = latest_job()
    if job is None:
        raise runner.JobError("no development jobs exist yet; run `dev start` first")
    if getattr(args, "reconcile", True):
        if runner.reconcile_job(job):
            job = load_job(job["id"])
    return job


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        if args.prompt_file == "-":
            return sys.stdin.read()
        try:
            return Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise runner.JobError(f"could not read prompt file: {exc}") from exc
    return args.prompt or ""


def _print_job_started(job: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(job, indent=2, sort_keys=True))
        return
    print(f"Job started: {job['id']}")
    print(f"State:       {job['state']}")
    print(f"Repo:        {job['repo']}")
    print(f"Timeout:     {runner._format_seconds(job['timeout_seconds'])}")
    print(f"Log:         {job['log_path']}")
    print(f"Worker log:  {job['worker_log_path']}")
    print(f"Report:      {job['report_path']}")
    print("")
    print(f"Check with:  dev status {job['id']}")
    print(f"Follow with: dev logs --follow {job['id']}")


def command_start(args: argparse.Namespace) -> int:
    _apply_state_dir(args)
    prompt = _read_prompt(args).strip()
    if not prompt and not args.dry_run:
        raise runner.JobError("a prompt is required: use --prompt or --prompt-file")
    criteria = runner.build_criteria(
        commands=args.criterion,
        manual=args.manual_criterion,
        files=args.acceptance_file,
    )
    timeout = runner.parse_duration(args.timeout)
    repo = Path(args.repo).expanduser().resolve()
    snapshot = runner.git_snapshot(repo)
    branch = args.branch or snapshot.get("branch") or None
    if args.dry_run:
        payload = runner.preflight(proc_root=args.proc_root, workspace=args.workspace)
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "title": args.title,
                    "repo": str(repo),
                    "branch": branch,
                    "timeout_seconds": timeout,
                    "agent": args.agent,
                    "model": args.model,
                    "criteria": criteria,
                    "notifications_enabled": not args.no_notify,
                    "preflight": payload,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if payload.get("status") != "REFUSE" else 20
    job = runner.create_job(
        title=args.title,
        prompt=prompt,
        repo=repo,
        branch=branch,
        criteria=criteria,
        timeout_seconds=timeout,
        agent=args.agent,
        model=args.model,
        workspace=args.workspace,
        proc_root=args.proc_root,
        notifications_enabled=not args.no_notify,
    )
    _print_job_started(job, args.json)
    return 0 if job.get("state") == "RUNNING" else 20


def command_status(args: argparse.Namespace) -> int:
    _apply_state_dir(args)
    if args.all:
        jobs = list_jobs()
        for job in jobs:
            runner.reconcile_job(job)
        jobs = list_jobs()
        if args.json:
            print(json.dumps([runner.status_payload(job) for job in jobs], indent=2, sort_keys=True))
            return 0
        if not jobs:
            print("No development jobs.")
            return 0
        print(f"{'STATE':8} {'JOB':48} {'TOTAL':>10} {'ATTEMPT':>10}  TITLE")
        for job in jobs:
            payload = runner.status_payload(job)
            total = runner._format_seconds(payload.get("elapsed_seconds"))
            attempt = runner._format_seconds(payload.get("attempt_elapsed_seconds"))
            print(
                f"{payload['state']:8} {payload['id']:48} "
                f"{total:>10} {attempt:>10}  {payload['title']}"
            )
        return 0
    job = _resolve_job(args)
    if runner.reconcile_job(job):
        job = load_job(job["id"])
    if args.json:
        print(json.dumps(runner.status_payload(job), indent=2, sort_keys=True))
    else:
        print(runner.render_status(job))
    return 0


def command_report(args: argparse.Namespace) -> int:
    _apply_state_dir(args)
    job = _resolve_job(args)
    if runner.reconcile_job(job):
        job = load_job(job["id"])
    path = runner.write_report(job)
    if args.json:
        print(json.dumps({"job": runner.status_payload(job), "report_path": str(path)}, indent=2, sort_keys=True))
    else:
        print(runner.render_report(job).rstrip())
        print("")
        print(f"Report written: {path}")
    return 0


def _tail(path: Path, lines: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            content = handle.readlines()
    except FileNotFoundError:
        return f"dev: log does not exist yet: {path}\n"
    except OSError as exc:
        return f"dev: could not read log {path}: {exc}\n"
    return "".join(content[-max(1, lines) :])


def command_logs(args: argparse.Namespace) -> int:
    _apply_state_dir(args)
    job = _resolve_job(args)
    path = Path(job["worker_log_path"] if args.worker else job["log_path"])
    sys.stdout.write(_tail(path, args.lines))
    sys.stdout.flush()
    if not args.follow:
        return 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(0, os.SEEK_END)
            while True:
                chunk = handle.read()
                if chunk:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                else:
                    time.sleep(0.5)
    except FileNotFoundError:
        print(f"dev: log does not exist yet: {path}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def command_resume(args: argparse.Namespace) -> int:
    _apply_state_dir(args)
    job = _resolve_job(args)
    if job.get("state") == "RUNNING" and worker_is_alive(job):
        raise runner.JobError(
            f"job {job['id']} is RUNNING (worker pid {job.get('worker_pid')}); "
            "inspect it with `dev status` instead of starting a duplicate"
        )
    job = runner.resume_job(
        job["id"],
        timeout_seconds=runner.parse_duration(args.timeout) if args.timeout else None,
        prompt=args.prompt,
        new_session=args.new_session,
        force=args.force,
    )
    if args.json:
        print(json.dumps(job, indent=2, sort_keys=True))
    else:
        print(f"Job resumed: {job['id']}")
        print(f"Attempt:     {len(job.get('attempts') or []) + 1}")
        print(f"Session:     {job.get('session_id') or '(new session)'}")
        print(f"Log:         {job['log_path']}")
    return 0


def command_accept(args: argparse.Namespace) -> int:
    _apply_state_dir(args)
    job = _resolve_job(args)
    job = runner.accept_job(
        job["id"],
        criterion_ids=args.criterion,
        all_manual=args.all_manual,
        note=args.note,
    )
    if args.json:
        print(json.dumps(runner.status_payload(job), indent=2, sort_keys=True))
    else:
        print(runner.render_status(job))
    return 0 if job.get("state") == "SUCCESS" else 1


def command_worker(args: argparse.Namespace) -> int:
    _apply_state_dir(args)
    return runner.run_worker(args.job_id)


def add_state_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state-dir",
        default=None,
        help="job state directory (default: $DEV_CONTROL_PLANE_STATE or XDG state)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev",
        description="Workflow v3 autonomous development jobs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"dev {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start a detached development job")
    add_state_argument(start)
    start.add_argument("--title", required=True, help="short job title")
    start.add_argument("--repo", default=".", help="repository/worktree to develop in")
    start.add_argument("--branch", default=None, help="expected branch label (recorded only)")
    prompt = start.add_mutually_exclusive_group()
    prompt.add_argument("--prompt", default="", help="authorized task prompt")
    prompt.add_argument("--prompt-file", default=None, help="read the prompt from a file ('-' for stdin)")
    start.add_argument(
        "--criterion",
        action="append",
        default=[],
        help="verifiable acceptance command; repeatable. Use LABEL::COMMAND to name it",
    )
    start.add_argument(
        "--manual-criterion",
        action="append",
        default=[],
        help="owner-verified acceptance criterion; repeatable",
    )
    start.add_argument(
        "--acceptance-file",
        action="append",
        default=[],
        help="JSON array of acceptance criteria; repeatable",
    )
    start.add_argument("--timeout", default="8h", help="wall-clock timeout (maximum 8h; default 8h)")
    start.add_argument("--agent", default=os.environ.get("DEV_AGENT", runner.DEFAULT_AGENT))
    start.add_argument("--model", default=os.environ.get("DEV_MODEL", runner.DEFAULT_MODEL))
    start.add_argument("--workspace", default=str(runner.DEFAULT_WORKSPACE))
    start.add_argument("--proc-root", default="/proc", help=argparse.SUPPRESS)
    start.add_argument("--no-notify", action="store_true", help="do not send Telegram notifications")
    start.add_argument("--dry-run", action="store_true", help="validate and print the plan only")
    start.add_argument("--json", action="store_true")
    start.set_defaults(func=command_start)

    status = subparsers.add_parser("status", help="show job status")
    add_state_argument(status)
    status.add_argument("job_id", nargs="?", default=None)
    status.add_argument("--all", action="store_true", help="list all jobs")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    report = subparsers.add_parser("report", help="render the durable job report")
    add_state_argument(report)
    report.add_argument("job_id", nargs="?", default=None)
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=command_report)

    logs = subparsers.add_parser("logs", help="read or follow a job log")
    add_state_argument(logs)
    logs.add_argument("job_id", nargs="?", default=None)
    logs.add_argument("-n", "--lines", type=int, default=100)
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("--worker", action="store_true", help="read the worker log instead of the run log")
    logs.set_defaults(func=command_logs)

    resume = subparsers.add_parser("resume", help="continue an existing job")
    add_state_argument(resume)
    resume.add_argument("job_id", nargs="?", default=None)
    resume.add_argument("--timeout", default=None, help="new wall-clock timeout (maximum 8h)")
    resume.add_argument("--prompt", default=None, help="replacement resume instruction")
    resume.add_argument("--new-session", action="store_true", help="start a new OpenCode session")
    resume.add_argument("--force", action="store_true", help="allow resuming a SUCCESS job")
    resume.add_argument("--json", action="store_true")
    resume.set_defaults(func=command_resume)

    accept = subparsers.add_parser("accept", help="record manual owner acceptance")
    add_state_argument(accept)
    accept.add_argument("job_id", nargs="?", default=None)
    accept.add_argument("--criterion", action="append", default=[])
    accept.add_argument("--all-manual", action="store_true")
    accept.add_argument("--note", default=None)
    accept.add_argument("--json", action="store_true")
    accept.set_defaults(func=command_accept)

    worker = subparsers.add_parser("_worker", help="internal detached worker (do not call directly)")
    add_state_argument(worker)
    worker.add_argument("--job-id", required=True)
    worker.set_defaults(func=command_worker)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (runner.JobError, StoreError, JobLocked) as exc:
        print(f"dev: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
