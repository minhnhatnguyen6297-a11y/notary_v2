"""
Debug helper — chạy: python debug_browser.py [url] [output.png]
Mặc định chụp trang chủ.

Dùng trong Claude: tôi gọi script này để xem web và fix bug.
"""
import sys, os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT_DIR = "static"

def screenshot(url, outfile, console_errors=True):
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        if console_errors:
            page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error","warning") else None)
            page.on("pageerror", lambda err: errors.append(f"[pageerror] {err}"))
        page.goto(url)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=outfile, full_page=True)
        browser.close()
    return errors

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else BASE + "/"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(OUT_DIR, "debug_shot.png")
    errs = screenshot(url, out)
    print(f"Screenshot saved: {out}")
    if errs:
        print("\nConsole errors/warnings:")
        for e in errs:
            print(" ", e.encode("utf-8", errors="replace").decode("utf-8"))
    else:
        print("No console errors.")
