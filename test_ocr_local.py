import sys
import asyncio
from pathlib import Path
from routers.ocr_local import _local_ocr_batch_from_inputs_triage_v2
from routers.ocr_local import warmup_local_ocr
import logging

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)

async def test():
    print("Warming up OCR engines...")
    success, err = warmup_local_ocr()
    if not success:
        print(f"Warmup failed: {err}")
        return

    test_dir = Path(__file__).parent / "tests" / "fixtures" / "cccd"
    files = list(test_dir.glob("*.jpg"))
    if not files:
        print("No images found in tests/fixtures/cccd")
        return
    
    inputs = []
    for f in sorted(files):
        inputs.append({"bytes": f.read_bytes(), "filename": f.name})
    
    print(f"Testing {len(files)} images...")
    results = _local_ocr_batch_from_inputs_triage_v2(inputs, qr_texts={}, client_qr_failed={})
    
    print("\n" + "="*50)
    print("               RESULTS                 ")
    print("="*50)
    for idx, person in enumerate(results.get("persons", [])):
        print(f"\n[Person {idx+1}]")
        for k, v in person.items():
            if not k.startswith("_"):
                print(f"  {k}: {v}")
    
    print("\n" + "="*50)
    print("            TIMING SUMMARY             ")
    print("="*50)
    summary = results.get("summary", {})
    from pprint import pprint
    pprint(summary, indent=2)

if __name__ == "__main__":
    asyncio.run(test())
