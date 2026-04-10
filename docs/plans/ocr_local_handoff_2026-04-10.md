# OCR Local Handoff 2026-04-10

## Scope

- Date: `2026-04-10`
- Branch: `feature/ai-ocr-qr-mrz-first`
- Active context: `ocr`
- Status: working tree is dirty, no commit was created in this session

## Files Changed In Working Tree

- `docs/plans/ocr_local.md`
- `frontend/templates/cases/form.html`
- `routers/ocr_local.py`
- `tasks.py`
- `tests/test_ocr_local_v4.py`

## What Is Already Implemented

- Docs taxonomy was aligned to runtime contract:
  - `face + QR -> front_old`
  - `face + no QR -> front_new`
- Blob-first triage was added, with legacy 4-angle rescue kept in place.
- QR rescue now retries multiple image variants and rotations.
- Session image retention and review endpoints/UI were added.
- Row-level profile/side metadata is preserved after detail-phase correction.
- Latest fix in this handoff:
  - back-side detail OCR can retry alternate rotations when the current detail result is weak
  - this was added to fix cards where triage angle is acceptable for side detection but wrong for MRZ/detail extraction

## Latest Validated Result

Replay artifact:
- `tmp/ocr_test_replay_after_rotation_fix.json`

Validated command result:
- `total_images = 10`
- `persons = 5`
- `paired_count = 5`
- `unpaired_count = 0`
- `qr_hits = 2`
- `ocr_runs = 8`

Per-file status on `ocr test/`:

| File | Side | Profile | ID | Pair |
|---|---|---|---|---|
| `1.jpg` | front | `cccd_front_new` | `036084011825` | paired with `2.jpg` |
| `2.jpg` | back | `cccd_back_new` | `036084011825` | paired with `1.jpg` |
| `3.jpg` | front | `cccd_front_old` | `036082000989` | paired with `4.jpg` |
| `4.jpg` | back | `cccd_back_old` | `036082000989` | paired with `3.jpg` |
| `5.jpg` | front | `cccd_front_old` | `036185021354` | paired with `6.jpg` |
| `6.jpg` | back | `cccd_back_old` | `036185021354` | paired with `5.jpg` |
| `7.jpg` | front | `cccd_front_new` | `036065001407` | paired with `8.jpg` |
| `8.jpg` | back | `cccd_back_new` | `036065001407` | paired with `7.jpg` |
| `9.jpg` | front | `cccd_front_old` | `036168006276` | paired with `10.jpg` |
| `10.jpg` | back | `cccd_back_old` | `036168006276` | paired with `9.jpg` |

Important detail:
- `4.jpg` used to fail pairing because detail OCR stayed on angle `270` and produced a garbage ID.
- After the latest fix, detail rotation rescue selects angle `90` and extracts `036082000989`, so `3.jpg` + `4.jpg` now merge correctly.

## Latest Code Areas Touched

- `routers/ocr_local.py`
  - detail-phase scoring and back-rotation retry
  - sync updated `orientation_angle` back into `image_results`
- `tests/test_ocr_local_v4.py`
  - regression test for weak current angle + strong alternate angle on back-side detail OCR

Useful function anchors:
- `_run_detail_phase_once`
- `_run_detail_phase`
- `_detail_candidate_score`
- `_should_retry_detail_rotation`

## Tests Already Run

Commands:

```powershell
venv\Scripts\python.exe -m py_compile routers\ocr_local.py tests\test_ocr_local_v4.py
venv\Scripts\python.exe -m pytest tests\test_ocr_local_v4.py -q
```

Latest result:

```text
22 passed, 8 subtests passed
```

## How To Replay On A New Machine

1. Checkout branch `feature/ai-ocr-qr-mrz-first`.
2. Restore/install the project venv and OCR dependencies.
3. Run:

```powershell
venv\Scripts\python.exe -m py_compile routers\ocr_local.py tests\test_ocr_local_v4.py
venv\Scripts\python.exe -m pytest tests\test_ocr_local_v4.py -q
```

4. Replay the local OCR test set:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
import json
from pathlib import Path
from routers.ocr_local import local_ocr_batch_from_inputs

root = Path(r'd:/notary_app/notary_v2')
folder = root / 'ocr test'
items = []
for idx, path in enumerate(sorted(folder.glob('*.jpg'), key=lambda p: p.name)):
    items.append({'index': idx, 'filename': path.name, 'bytes': path.read_bytes()})
result = local_ocr_batch_from_inputs(items, trace_id='ocr-test-replay-after-rotation-fix')
out = root / 'tmp' / 'ocr_test_replay_after_rotation_fix.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result.get('summary', {}), ensure_ascii=False, indent=2))
'@ | venv\Scripts\python.exe -
```

Expected replay summary:
- `paired_count = 5`
- `unpaired_count = 0`

## Known Residual Issues

- Some OCR fields are still weak on old-card examples:
  - `9.jpg` / `10.jpg` still have missing `ho_ten` or `ngay_cap`
  - `4.jpg` pairs correctly now, but `ngay_cap` is still missing
- `qr_decode_ms` is still expensive on some back-side images
- `LOCAL_OCR_TRIAGE_EARLY_EXIT` remains gated and not benchmarked for rollout

## Suggested Next Steps

- Improve field extraction quality for old-card back/front pairs after pairing is stable.
- Reduce QR decode time on back-side rescue paths.
- Run benchmark set before enabling any early-exit rollout.
- Commit this working tree before moving machines, otherwise the current OCR local state will not transfer.
