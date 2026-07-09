"""Playwright script để debug Stage UI.

Chạy:
  .\venv\Scripts\python.exe tests/playwright/stage_debug.py

Yêu cầu:
  - Server đang chạy ở http://127.0.0.1:8000
  - Đã cài Playwright: pip install playwright && playwright install chromium

Các hành động hỗ trợ:
  - Mở form cases/create
  - Thêm người vào stage (OCR hoặc thủ công)
  - Bấm Cap nhat
  - Xóa dòng
  - Chụp console log, network requests
  - Screenshot các trạng thái
"""
import asyncio
import sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Chua cai Playwright. Chay: pip install playwright && playwright install chromium")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = "runtime/playwright_screenshots"


async def main():
    import os
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context()
        page = await context.new_page()

        # Collect console logs
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type.upper()}] {msg.text}"))
        page.on("pageerror", lambda err: logs.append(f"[PAGE_ERROR] {err}"))

        # 1. Navigate to create case
        print("=== Buoc 1: Mo trang tao ho so ===")
        await page.goto(f"{BASE_URL}/cases/create")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=f"{SCREENSHOT_DIR}/01_create_page.png", full_page=True)

        # 2. Find stage area
        print("=== Buoc 2: Kiem tra vung stage ===")
        staging_area = await page.query_selector("#ocr-staging-area")
        if staging_area:
            print("  + Vung stage da render")
        else:
            print("  - KHONG tim thay vung stage (#ocr-staging-area)")

        # 3. Count stage rows
        rows = await page.query_selector_all("#ocr-staging-area .ocr-staged-row")
        print(f"  + So dong stage: {len(rows)}")

        # 4. Check delete buttons
        for i, row in enumerate(rows):
            del_btn = await row.query_selector(".stage-remove-btn")
            cid = await row.get_attribute("data-cid") or ""
            print(f"  + Dong {i+1}: cid={cid}, co nut xoa={del_btn is not None}")

        # 5. Find Cap nhat button
        update_btn = await page.query_selector("#btn-save-participants")
        if update_btn:
            is_disabled = await update_btn.is_disabled()
            text = await update_btn.inner_text()
            print("\n=== Buoc 3: Nut Cap nhat ===")
            print(f"  + Text: '{text}'")
            print(f"  + Disabled: {is_disabled}")
        else:
            print("  - KHONG tim thay nut #btn-save-participants")

        # 6. Try adding a manual row via Nhap tay button if exists
        # Check for Thêm button
        add_btn = await page.query_selector("#btn-add-person")
        if add_btn:
            print("\n=== Buoc 4: Them nguoi thu cong ===")
            await add_btn.click()
            await page.wait_for_timeout(500)
            rows = await page.query_selector_all("#ocr-staging-area .ocr-staged-row")
            print(f"  + Sau khi bam Them: {len(rows)} dong")
            if rows:
                new_row = rows[-1]
                del_btn = await new_row.query_selector(".stage-remove-btn")
                print(f"  + Dong moi co nut xoa: {del_btn is not None}")
                # Fill name
                name_input = await new_row.query_selector('[data-key="ho_ten"]')
                if name_input:
                    await name_input.fill("Nguyen Van Test")
                    print("  + Da dien ten: Nguyen Van Test")
                await page.screenshot(path=f"{SCREENSHOT_DIR}/02_after_add.png", full_page=True)

        # 7. Check if there are rows with red border (errors)
        red_rows = await page.query_selector_all('#ocr-staging-area .ocr-staged-row[style*="f87171"]')
        if red_rows:
            print("\n=== Loi: Dong bi bao do ===")
        for i, r in enumerate(red_rows):
            title = await r.get_attribute("title") or "(khong co tooltip)"
            print(f"  + Dong {i+1}: title={title}")

        # 8. Try clicking Cap nhat
        if update_btn and not await update_btn.is_disabled():
            print("\n=== Buoc 5: Bam Cap nhat ===")
            logs.clear()
            await update_btn.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/03_after_update.png", full_page=True)

            # Check console errors
            errors = [line for line in logs if "ERROR" in line or "FAIL" in line or "exception" in line.lower()]
            if errors:
                print(f"  + Loi console: {len(errors)}")
                for e in errors:
                    print(f"    {e}")
            else:
                print("  + Khong loi console")

            # Check for toast
            toast = await page.query_selector(".toast")
            if toast:
                toast_text = await toast.inner_text()
                print(f"  + Toast: {toast_text}")

        # 9. Print all console logs
        print("\n=== Toan bo console log ===")
        for line in logs[-30:]:
            print(f"  {line}")

        # 10. Final screenshot
        await page.screenshot(path=f"{SCREENSHOT_DIR}/99_final.png", full_page=True)

        print(f"\nScreenshots: {SCREENSHOT_DIR}/")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
