"""
Codex Relay — minimal local workflow for Planner/Critic/Finalizer/Executor/Reviewer.

Usage:
  python tools/codex_relay.py draft --task <task_file>
  python tools/codex_relay.py approve --run-dir <run_dir>
  python tools/codex_relay.py execute --run-dir <run_dir> [--with-review]
  python tools/codex_relay.py review --run-dir <run_dir>
  python tools/codex_relay.py status --run-dir <run_dir>
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows cp1252 console fix
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

RUNTIME_BASE = Path("runtime/codex_relay")

CODEX_CMD = ["cmd", "/c", "codex.cmd", "exec", "--json"]

# ─── Role prompts ────────────────────────────────────────────────────────────

PLANNER_PROMPT = """\
Bạn là Planner. Nhiệm vụ của bạn là đọc task dưới đây và tạo một bản plan chi tiết.

Yêu cầu output:
- Bắt đầu bằng `# Plan`
- `## Goal`: Mô tả mục tiêu tổng thể
- `## Proposed Changes`: Liệt kê từng thay đổi cụ thể (file, dòng, logic)
- `## Risks`: Các rủi ro có thể xảy ra và cách giảm thiểu
- `## Out of Scope`: Những gì KHÔNG được làm
- `## Acceptance Criteria`: Điều kiện để coi task là hoàn thành

Không được implement bất kỳ code nào. Chỉ lên plan.

Task:
{task}
"""

CRITIC_PROMPT = """\
Bạn là Critic. Nhiệm vụ của bạn là đánh giá plan sau đây và tìm ra các vấn đề.

Yêu cầu output:
- Bắt đầu bằng `# Critique`
- Phần tốt của plan (ngắn gọn)
- `## Findings`: Liệt kê từng vấn đề theo mức độ: `High`, `Medium`, `Low`
  - Mỗi finding phải có: file/line nếu liên quan, mô tả vấn đề, tại sao là rủi ro
- `## Missing`: Những gì plan chưa đề cập mà cần thiết
- `## Questions`: Câu hỏi cần làm rõ trước khi implement

Plan cần đánh giá:
{planner}

Task gốc:
{task}
"""

FINALIZER_PROMPT = """\
Bạn là PlannerFinalizer. Nhiệm vụ là tổng hợp plan từ Planner và phản hồi từ Critic thành một Final Plan hoàn chỉnh.

Yêu cầu output:
- Bắt đầu bằng `# Final Plan`
- `## Goal`: Mục tiêu (giữ nguyên hoặc làm rõ hơn từ plan gốc)
- `## Final Steps`: Các bước thực hiện cụ thể, đã tích hợp phản hồi từ Critic
  - Mỗi bước phải rõ file, logic, test nếu cần
- `## Constraints`: Ràng buộc bắt buộc (không được vi phạm)
- `## Acceptance`: Điều kiện hoàn thành cuối cùng

Đảm bảo Final Plan đã giải quyết các `High` và `Medium` findings từ Critic.

Plan gốc:
{planner}

Phê bình từ Critic:
{critic}

Task gốc:
{task}
"""

EXECUTOR_PROMPT = """\
Bạn là Executor. Nhiệm vụ là implement đúng theo Final Plan đã được duyệt.

Ràng buộc bắt buộc:
- Chỉ sửa đúng các file trong plan. Không mở rộng sang file khác.
- Không đổi API contract, endpoint name, DB schema trừ khi plan nêu rõ.
- Sau khi implement, báo cáo kết quả theo format sau:

`Da sua dung [N] thay doi trong scope duyet.`

Sau đó liệt kê từng thay đổi:
- `Bug/Task #N:` mô tả đã làm gì, file:line cụ thể
- Nếu có test: kết quả chạy test

Final Plan cần implement:
{final_plan}

Task gốc:
{task}
"""

REVIEWER_PROMPT = """\
Bạn là Reviewer. Nhiệm vụ là review implementation vừa xong và tìm bug, scope violation, contract violation.

Yêu cầu output:
- Bắt đầu bằng `# Review`
- `## Findings`: Liệt kê từng vấn đề theo `High`, `Medium`, `Low`
  - Mỗi finding phải có file:line, mô tả vấn đề cụ thể
- `## Residual Risks`: Rủi ro còn lại chưa được fix
- `## Suggested Follow-up`: Đề xuất bước tiếp theo nếu cần

So sánh kỹ execution_summary với Final Plan đã duyệt. Bất kỳ thay đổi nào ngoài scope plan đều phải bị flag.

Final Plan đã duyệt:
{final_plan}

Execution Summary:
{execution_summary}

Task gốc:
{task}
"""


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _slug(text: str, max_len: int = 40) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:max_len]


def _make_run_dir(task: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slug(task.get("lam_gi", "task"))
    run_dir = RUNTIME_BASE / f"{ts}-{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _read_task(path: str) -> dict:
    content = Path(path).read_text(encoding="utf-8")
    task = {}
    for line in content.splitlines():
        for key in ("Lam gi", "Sua phan nao", "Pham vi", "Muc tieu",
                    "Batch anh", "Expected", "Direct output",
                    "Project/UI output", "Tang nghi ngo sai",
                    "Muc tieu fix vong nay"):
            pattern = rf"^{re.escape(key)}\s*:\s*(.+)"
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                norm_key = key.lower().replace(" ", "_")
                task[norm_key] = m.group(1).strip()
    if not task:
        task["lam_gi"] = content.strip()
    return task


def _format_task(task: dict) -> str:
    lines = []
    mapping = [
        ("lam_gi", "Lam gi"),
        ("sua_phan_nao", "Sua phan nao"),
        ("pham_vi", "Pham vi"),
        ("muc_tieu", "Muc tieu"),
        ("batch_anh", "Batch anh"),
        ("expected", "Expected"),
        ("direct_output", "Direct output"),
        ("project/ui_output", "Project/UI output"),
        ("tang_nghi_ngo_sai", "Tang nghi ngo sai"),
        ("muc_tieu_fix_vong_nay", "Muc tieu fix vong nay"),
    ]
    for key, label in mapping:
        if task.get(key):
            lines.append(f"{label}: {task[key]}")
    return "\n".join(lines) if lines else str(task)


def _run_codex(prompt: str, out_md: Path, jsonl_path: Path) -> bool:
    cmd = CODEX_CMD + ["-o", str(out_md), prompt]
    print(f"  -> codex exec [{out_md.name}] ...", flush=True)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(Path.cwd()),
        )
        if result.stdout:
            jsonl_path.write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0:
            print(f"  [ERROR] codex exited {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr[:500], file=sys.stderr)
            return False
        if not out_md.exists():
            print(f"  [ERROR] {out_md.name} không được tạo ra", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"  [ERROR] {e}", file=sys.stderr)
        return False


def _load_status(run_dir: Path) -> dict:
    p = run_dir / "status.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_status(run_dir: Path, status: dict) -> None:
    (run_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_draft(args):
    task = _read_task(args.task)
    if not task.get("lam_gi"):
        print("[ERROR] Task file phải có trường 'Lam gi:'", file=sys.stderr)
        sys.exit(1)

    run_dir = _make_run_dir(task)
    print(f"Draft created at: {run_dir}")

    task_text = _format_task(task)
    (run_dir / "task.md").write_text(task_text, encoding="utf-8")

    status = {
        "status": "awaiting_approval",
        "model": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "approved_at": None,
        "executed_at": None,
        "task": task,
        "artifacts": {
            "task": str(run_dir / "task.md"),
            "planner": str(run_dir / "planner.md"),
            "critic": str(run_dir / "critic.md"),
            "final_plan": str(run_dir / "final_plan.md"),
        },
        "final_plan_summary": "",
    }
    _save_status(run_dir, status)

    # Planner
    print("\n[1/3] Planner ...", flush=True)
    planner_prompt = PLANNER_PROMPT.format(task=task_text)
    if not _run_codex(planner_prompt, run_dir / "planner.md", run_dir / "planner.jsonl"):
        print("[ERROR] Planner thất bại. Dừng.", file=sys.stderr)
        sys.exit(1)

    planner_text = (run_dir / "planner.md").read_text(encoding="utf-8")

    # Critic
    print("\n[2/3] Critic ...", flush=True)
    critic_prompt = CRITIC_PROMPT.format(task=task_text, planner=planner_text)
    if not _run_codex(critic_prompt, run_dir / "critic.md", run_dir / "critic.jsonl"):
        print("[ERROR] Critic thất bại. Dừng.", file=sys.stderr)
        sys.exit(1)

    critic_text = (run_dir / "critic.md").read_text(encoding="utf-8")

    # Finalizer
    print("\n[3/3] PlannerFinalizer ...", flush=True)
    finalizer_prompt = FINALIZER_PROMPT.format(
        task=task_text, planner=planner_text, critic=critic_text
    )
    if not _run_codex(finalizer_prompt, run_dir / "final_plan.md", run_dir / "finalizer.jsonl"):
        print("[ERROR] Finalizer thất bại. Dừng.", file=sys.stderr)
        sys.exit(1)

    final_text = (run_dir / "final_plan.md").read_text(encoding="utf-8")
    status["final_plan_summary"] = final_text.splitlines()[0] if final_text else ""
    _save_status(run_dir, status)

    print(f"\nDraft OK. Run dir: {run_dir.resolve()}")
    print(f"  -> Doc final_plan.md, sau do chay: python tools/codex_relay.py approve --run-dir {run_dir}")


def cmd_approve(args):
    run_dir = Path(args.run_dir)
    status = _load_status(run_dir)
    if not status:
        print(f"[ERROR] Không tìm thấy status.json trong {run_dir}", file=sys.stderr)
        sys.exit(1)
    if status.get("status") == "completed":
        print("[WARN] Run này đã completed rồi.")
    status["status"] = "approved"
    status["approved_at"] = datetime.now().isoformat(timespec="seconds")
    _save_status(run_dir, status)
    print(f"Approved: {run_dir}")


def cmd_execute(args):
    run_dir = Path(args.run_dir)
    status = _load_status(run_dir)
    if not status:
        print(f"[ERROR] Không tìm thấy status.json trong {run_dir}", file=sys.stderr)
        sys.exit(1)
    if status.get("status") not in ("approved", "completed"):
        print(f"[ERROR] Run chưa được approve (status={status.get('status')}). Chạy approve trước.", file=sys.stderr)
        sys.exit(1)

    task = status.get("task", {})
    task_text = _format_task(task)
    final_plan_path = run_dir / "final_plan.md"
    if not final_plan_path.exists():
        print(f"[ERROR] Không tìm thấy final_plan.md trong {run_dir}", file=sys.stderr)
        sys.exit(1)
    final_plan_text = final_plan_path.read_text(encoding="utf-8")

    print("\n[1/1] Executor ...", flush=True)
    exec_prompt = EXECUTOR_PROMPT.format(task=task_text, final_plan=final_plan_text)
    if not _run_codex(exec_prompt, run_dir / "execution_summary.md", run_dir / "executor.jsonl"):
        print("[ERROR] Executor thất bại. Run dir vẫn ở state approved — chạy lại execute.", file=sys.stderr)
        sys.exit(1)

    status["executed_at"] = datetime.now().isoformat(timespec="seconds")
    status["artifacts"]["execution_summary"] = str(run_dir / "execution_summary.md")

    if args.with_review:
        print("\n[Review pass] Reviewer ...", flush=True)
        exec_text = (run_dir / "execution_summary.md").read_text(encoding="utf-8")
        review_prompt = REVIEWER_PROMPT.format(
            task=task_text, final_plan=final_plan_text, execution_summary=exec_text
        )
        if _run_codex(review_prompt, run_dir / "review.md", run_dir / "reviewer.jsonl"):
            status["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
            status["artifacts"]["review"] = str(run_dir / "review.md")
        else:
            print("[WARN] Reviewer thất bại, bỏ qua. Có thể chạy lại bằng review command.", file=sys.stderr)

    status["status"] = "completed"
    _save_status(run_dir, status)
    print(f"\nExecute OK. Xem: {run_dir / 'execution_summary.md'}")


def cmd_review(args):
    run_dir = Path(args.run_dir)
    status = _load_status(run_dir)
    if not status:
        print(f"[ERROR] Không tìm thấy status.json trong {run_dir}", file=sys.stderr)
        sys.exit(1)

    task = status.get("task", {})
    task_text = _format_task(task)
    final_plan_text = (run_dir / "final_plan.md").read_text(encoding="utf-8")
    exec_text = (run_dir / "execution_summary.md").read_text(encoding="utf-8")

    print("\n[Review] Reviewer ...", flush=True)
    review_prompt = REVIEWER_PROMPT.format(
        task=task_text, final_plan=final_plan_text, execution_summary=exec_text
    )
    if not _run_codex(review_prompt, run_dir / "review.md", run_dir / "reviewer.jsonl"):
        print("[ERROR] Reviewer thất bại.", file=sys.stderr)
        sys.exit(1)

    status["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
    status["artifacts"]["review"] = str(run_dir / "review.md")
    _save_status(run_dir, status)
    print(f"Review OK. Xem: {run_dir / 'review.md'}")


def cmd_status(args):
    run_dir = Path(args.run_dir)
    status = _load_status(run_dir)
    if not status:
        print(f"[ERROR] Không tìm thấy status.json trong {run_dir}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(status, ensure_ascii=False, indent=2))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Codex Relay")
    sub = parser.add_subparsers(dest="command")

    p_draft = sub.add_parser("draft")
    p_draft.add_argument("--task", required=True)
    p_draft.add_argument("--run-dir", default=None, help="(ignored, kept for compat)")

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("--run-dir", required=True)

    p_exec = sub.add_parser("execute")
    p_exec.add_argument("--run-dir", required=True)
    p_exec.add_argument("--with-review", action="store_true")

    p_review = sub.add_parser("review")
    p_review.add_argument("--run-dir", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--run-dir", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "draft": cmd_draft,
        "approve": cmd_approve,
        "execute": cmd_execute,
        "review": cmd_review,
        "status": cmd_status,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
