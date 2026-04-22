# Codex Relay

## Goal

Provide a minimal local workflow for:

1. task intake
2. planner draft
3. critic response
4. final plan for approval
5. execution only after approval
6. optional review pass after execution

This is intentionally smaller than a full multi-agent framework. The main requirement is low setup overhead while keeping a clear approval gate.

## Runtime Shape

- Entry point: `tools/codex_relay.py`
- Thin local web UI: `tools/codex_relay_web.py`
- Runtime data: `runtime/codex_relay/<timestamp>-<slug>/`
- Agent roles:
  - `Planner`
  - `Critic`
  - `PlannerFinalizer`
  - `Executor`
  - `Reviewer`

All roles currently run on the same Codex model. The separation is prompt-based rather than provider-based.

## Input Contract

Task input must contain four fields:

```text
Lam gi: ...
Sua phan nao: ...
Pham vi: ...
Muc tieu: ...
```

The CLI supports both file-based input and interactive terminal prompts.
You can start from `tools/codex_relay_task_template.md`.

## Commands

Create draft artifacts:

```powershell
python tools/codex_relay.py draft --task tasks\my_task.md
```

Or use terminal prompts:

```powershell
python tools/codex_relay.py draft --interactive
```

Create artifacts and print the final plan immediately:

```powershell
python tools/codex_relay.py draft-and-open --interactive
```

Approve a run:

```powershell
python tools/codex_relay.py approve --run-dir runtime\codex_relay\20260421-120000-my-task
```

Execute an approved run:

```powershell
python tools/codex_relay.py execute --run-dir runtime\codex_relay\20260421-120000-my-task
```

Execute and review in one step:

```powershell
python tools/codex_relay.py execute --run-dir runtime\codex_relay\20260421-120000-my-task --with-review
```

Run a reviewer pass again after execution:

```powershell
python tools/codex_relay.py review --run-dir runtime\codex_relay\20260421-120000-my-task
```

Inspect status:

```powershell
python tools/codex_relay.py status --run-dir runtime\codex_relay\20260421-120000-my-task
```

Start the local web UI:

```powershell
python tools/codex_relay_web.py
```

Then open `http://127.0.0.1:8765`.

## Artifacts

Each run stores:

- `task.md`
- `planner.md`
- `critic.md`
- `final_plan.md`
- `execution_summary.md` after execution
- `review.md` after review
- `*.jsonl` raw Codex event streams
- `status.json`

## Notes

- Windows execution uses `cmd /c codex.cmd ...` to avoid PowerShell execution-policy failures on `codex.ps1`.
- Approval is explicit. `execute` fails unless the run was marked approved first.
- The web UI is dependency-light and uses only the Python standard library.
- This workflow still relies on the local Codex CLI login/profile already present on the machine.
