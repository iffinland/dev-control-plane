"""Inline keyboard definitions.

Callback data is always short and opaque. Paths, job IDs, prompts and user IDs
never appear in callback data; the router resolves a server-side reference after
re-authorizing the caller.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

MAX_CALLBACK_BYTES = 64
RUNNING_JOB_STATES = frozenset({"RUNNING"})
RESUMABLE_JOB_STATES = frozenset(
    {"SUCCESS", "FAILED", "BLOCKED", "TIMEOUT", "CANCELLED"}
)


def job_action_flags(job: Mapping[str, object]) -> tuple[bool, bool]:
    """Resolve the supported job actions from the durable job state.

    Raw ``dev start``/``dev resume`` records do not include the computed
    ``worker_alive`` field, so action availability must not depend on it. A
    RUNNING job always exposes cancellation; Workflow v3 re-verifies the exact
    guard identity before signalling and reconciles a disappeared worker without
    sending a signal. Only terminal states expose Resume, so a live attempt
    cannot be duplicated. Callers still gate every action on control mode.
    """

    state = str(job.get("state") or "").upper()
    return (state in RESUMABLE_JOB_STATES, state in RUNNING_JOB_STATES)


def button(text: str, callback_data: str) -> dict:
    if len(callback_data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise ValueError("callback data exceeds Telegram's 64-byte limit")
    return {"text": text[:60], "callback_data": callback_data}


def keyboard(rows: Iterable[Sequence[dict]]) -> dict:
    return {"inline_keyboard": [list(row) for row in rows if row]}


def main_menu(*, control: bool = False) -> dict:
    rows = [
        [button("Jobs", "jl:0"), button("Projects", "p")],
        [button("Documents", "d"), button("Help", "h")],
    ]
    if control:
        rows.insert(0, [button("Start job", "w:new")])
    return keyboard(rows)


def back_to_main() -> dict:
    return keyboard([[button("Main menu", "m")]])


def jobs_menu(
    job_refs: Sequence[tuple[str, str]],
    *,
    page: int,
    total_pages: int,
) -> dict:
    rows: list[list[dict]] = []
    for ref, label in job_refs:
        rows.append([button(label, f"j:{ref}")])
    navigation: list[dict] = []
    if page > 0:
        navigation.append(button("Previous", f"jl:{page - 1}"))
    if page + 1 < total_pages:
        navigation.append(button("Next", f"jl:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([button("Main menu", "m")])
    return keyboard(rows)


def job_menu(
    ref: str,
    *,
    control: bool = False,
    resumable: bool = False,
    cancellable: bool = False,
) -> dict:
    rows = [
        [button("Refresh", f"j:{ref}:r"), button("Report", f"j:{ref}:p")],
        [
            button("Preview run log", f"j:{ref}:lr"),
            button("Preview worker log", f"j:{ref}:lw"),
        ],
        [button("Download report", f"j:{ref}:dr")],
    ]
    if control:
        actions: list[dict] = []
        if resumable:
            actions.append(button("Resume", f"j:{ref}:s"))
        if cancellable:
            actions.append(button("Cancel job", f"j:{ref}:c"))
        if actions:
            rows.append(actions)
        rows.append([button("Queue instruction", f"j:{ref}:q")])
    rows.append([button("Jobs", "jl:0"), button("Main menu", "m")])
    return keyboard(rows)


def log_menu(ref: str, kind: str) -> dict:
    return keyboard(
        [
            [button("Refresh preview", f"j:{ref}:{'lr' if kind == 'run' else 'lw'}")],
            [
                button(
                    "Download log",
                    f"j:{ref}:{'dlr' if kind == 'run' else 'dlw'}",
                )
            ],
            [button("Back to job", f"j:{ref}"), button("Main menu", "m")],
        ]
    )


def report_menu(ref: str) -> dict:
    return keyboard(
        [
            [button("Download report", f"j:{ref}:dr")],
            [button("Back to job", f"j:{ref}"), button("Main menu", "m")],
        ]
    )


def projects_menu(*, control: bool = False) -> dict:
    rows = []
    if control:
        rows.append([button("Start job", "w:new")])
    rows.append([button("Documents", "d"), button("Main menu", "m")])
    return keyboard(rows)


def document_roots_menu(root_browses: Sequence[tuple[str, str]]) -> dict:
    rows = [[button(label, f"b:{browse_id}")] for browse_id, label in root_browses]
    rows.append([button("Main menu", "m")])
    return keyboard(rows)


def document_listing_menu(
    browse_id: str,
    entries: Sequence[tuple[int, str, bool]],
    *,
    page: int,
    total_pages: int,
) -> dict:
    rows: list[list[dict]] = []
    for index, label, is_dir in entries:
        prefix = "[dir] " if is_dir else ""
        action = "o" if is_dir else "v"
        rows.append([button(f"{prefix}{label}", f"b:{browse_id}:{action}:{index}")])
    navigation: list[dict] = []
    if page > 0:
        navigation.append(button("Previous", f"b:{browse_id}:p"))
    if page + 1 < total_pages:
        navigation.append(button("Next", f"b:{browse_id}:n"))
    if navigation:
        rows.append(navigation)
    rows.append([button("Up", f"b:{browse_id}:u"), button("Roots", "d")])
    rows.append([button("Main menu", "m")])
    return keyboard(rows)


def document_preview_menu(browse_id: str, index: int, *, can_download: bool) -> dict:
    rows: list[list[dict]] = []
    if can_download:
        rows.append([button("Download redacted copy", f"b:{browse_id}:d:{index}")])
    rows.append([button("Back", f"b:{browse_id}"), button("Main menu", "m")])
    return keyboard(rows)


def confirmation_menu(nonce: str) -> dict:
    return keyboard(
        [[button("Download", f"x:{nonce}:y"), button("Cancel", f"x:{nonce}:n")]]
    )


def start_project_menu(wizard_id: str, projects: Sequence[object]) -> dict:
    rows: list[list[dict]] = []
    for index, project in enumerate(projects):
        rows.append(
            [button(f"{project.project_id} [{project.project.platform}]", f"w:{wizard_id}:p:{index}")]
        )
    rows.append([button("Cancel", f"w:{wizard_id}:cancel")])
    return keyboard(rows)


def start_runtime_menu(wizard_id: str) -> dict:
    rows = [
        [
            button("1h", f"w:{wizard_id}:t:3600"),
            button("2h", f"w:{wizard_id}:t:7200"),
        ],
        [
            button("4h", f"w:{wizard_id}:t:14400"),
            button("8h", f"w:{wizard_id}:t:28800"),
        ],
        [button("Advanced options", f"w:{wizard_id}:a")],
        [button("Cancel", f"w:{wizard_id}:cancel")],
    ]
    return keyboard(rows)


def wizard_cancel_menu(wizard_id: str) -> dict:
    return keyboard(
        [[button("Cancel wizard", f"w:{wizard_id}:cancel"), button("Main menu", "m")]]
    )


def control_confirmation_menu(nonce: str, action_label: str) -> dict:
    return keyboard(
        [
            [button(f"Confirm: {action_label}", f"x:{nonce}:y")],
            [button("Cancel", f"x:{nonce}:n")],
        ]
    )


def resume_preview_menu(
    wizard_id: str,
    *,
    job_ref: str,
    new_session: bool,
    force: bool,
) -> dict:
    rows = [
        [button("Confirm resume", f"w:{wizard_id}:confirm")],
        [button("Add instruction", f"w:{wizard_id}:i")],
        [
            button(
                f"New session: {'on' if new_session else 'off'}",
                f"w:{wizard_id}:ns",
            ),
            button(
                f"Allow new attempt: {'on' if force else 'off'}",
                f"w:{wizard_id}:force",
            ),
        ],
        [button("Back to job", f"j:{job_ref}"), button("Cancel", f"w:{wizard_id}:cancel")],
    ]
    return keyboard(rows)


def error_menu(callback_data: str = "m", label: str = "Main menu") -> dict:
    return keyboard([[button(label, callback_data)]])
