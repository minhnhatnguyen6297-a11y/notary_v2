from __future__ import annotations

import unittest

from UPLOAD.bootstrap_ui import (
    BOOTSTRAP_VERSION,
    PLAYWRIGHT_BROWSER,
    should_install_browser,
    should_install_requirements,
)


class UploadBootstrapDecisionTests(unittest.TestCase):
    def test_requirements_install_needed_when_state_missing(self):
        runtime = {"modules": {"docx": True, "win32com": True, "dotenv": True, "playwright": True}}
        self.assertTrue(should_install_requirements({}, runtime, 123))

    def test_requirements_install_skipped_when_state_and_modules_are_ready(self):
        state = {
            "bootstrap_version": BOOTSTRAP_VERSION,
            "requirements_mtime_ns": 123,
        }
        runtime = {"modules": {"docx": True, "win32com": True, "dotenv": True, "playwright": True}}
        self.assertFalse(should_install_requirements(state, runtime, 123))

    def test_requirements_install_needed_when_any_module_missing(self):
        state = {
            "bootstrap_version": BOOTSTRAP_VERSION,
            "requirements_mtime_ns": 123,
        }
        runtime = {"modules": {"docx": True, "win32com": False, "dotenv": True, "playwright": True}}
        self.assertTrue(should_install_requirements(state, runtime, 123))

    def test_browser_install_needed_when_browser_missing(self):
        state = {"playwright_browser": PLAYWRIGHT_BROWSER}
        runtime = {"chromium_ready": False}
        self.assertTrue(should_install_browser(state, runtime))

    def test_browser_install_skipped_when_browser_ready(self):
        state = {"playwright_browser": PLAYWRIGHT_BROWSER}
        runtime = {"chromium_ready": True}
        self.assertFalse(should_install_browser(state, runtime))


if __name__ == "__main__":
    unittest.main()
