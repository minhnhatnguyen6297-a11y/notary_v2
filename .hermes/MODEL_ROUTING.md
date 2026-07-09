# Model routing for notary_v2

Use this as a cost-control guide. The repo already has `.agents/model-budget.json`; this file summarizes when to use each tier.

## Recommended default
- Default for routine work: Tier A / balanced coder model.
- Escalate only when the task crosses module boundaries, touches OCR logic, or requires architecture/debug reasoning.

## Tier B - cheapest / token-saving
Use for:
- Reading/summarizing docs and plans.
- Search/replace.
- Comments/log messages.
- Small config edits.
- Explaining one file without changing code.

Repo-local examples from `.agents/model-budget.json`:
- `mimo-v2.5`
- `deepseek-v4-flash`
- `minimax-m3`

## Tier A - balanced coding
Use for:
- CRUD changes.
- Small/normal features under AGENTS.md limits.
- Tests for existing behavior.
- Frontend/backend sync where scope is clear.

Repo-local examples:
- `qwen3.7-plus`
- `deepseek-v4-pro`
- `mimo-v2.5-pro`

## Tier S - strongest reasoning
Use for:
- OCR pipeline changes.
- Architecture planning.
- Complex debug across UI/API/DB/OCR.
- Major refactor or schema/API/Celery contract changes.

Repo-local examples:
- `glm-5.2`
- `kimi-k2.7-code`
- `qwen3.7-max`

## Hermes token-saving commands
From repo root:

```bash
hermes chat -q "Quet nhanh task nay theo AGENTS.md, dung search truoc, chi doc file lien quan, de xuat scope/test/model tier." --toolsets file,terminal
```

For local code-only tasks, prefer:

```bash
hermes chat --toolsets file,terminal
```

Avoid loading web/browser/vision unless the task needs them.

## Prompt template

```text
Lam viec trong D:/notary_v2.
Doc AGENTS.md truoc. Tiet kiem token: search/list truoc, khong doc venv/.git/runtime/logs/db/image fixtures neu khong can.
Task: <mo ta>
Hay tra ve: tier, scope lock, file se doc/sua, test can chay, model tier de xuat.
Chua sua code cho den khi scope ro.
```
