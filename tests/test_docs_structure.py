import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKED_PATHS = set(
    subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
)
MODULE_READMES = (
    "docs/domains/inheritance/README.md",
    "docs/platform/document-intake/README.md",
    "docs/platform/case-workspace/README.md",
    "docs/platform/document-generation/README.md",
    "docs/platform/fast-text-audit/README.md",
    "docs/architecture/README.md",
)

def test_required_module_readmes_exist():
    missing = [path for path in MODULE_READMES if not (ROOT / path).is_file()]
    assert missing == []

def test_module_readmes_declare_routing_metadata():
    for path in MODULE_READMES:
        text = (ROOT / path).read_text(encoding="utf-8")
        for field in ("Status", "Source of truth", "Read when"):
            assert re.search(rf"^{field}:\s*\S", text, re.MULTILINE), f"{path}: {field}"

def test_module_readme_markdown_targets_exist():
    for path in MODULE_READMES:
        readme = ROOT / path
        text = readme.read_text(encoding="utf-8")
        targets = set(re.findall(r"`([^`\n]+(?:\.md|/))`", text))
        targets.update(re.findall(r"\[[^\]]*\]\(([^)\s]+\.md)\)", text))
        for target in targets:
            resolved = (ROOT / target if target.startswith(("docs/", "word_templates/")) else readme.parent / target).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
            relative = resolved.relative_to(ROOT).as_posix()
            tracked = relative in TRACKED_PATHS or resolved.is_dir() and any(
                path.startswith(f"{relative}/") for path in TRACKED_PATHS
            )
            assert tracked, f"{path}: untracked {target}"

def test_agents_routed_markdown_exists():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    section = re.search(
        r"^## 5\. Read routing[ \t]*\n(?P<body>.*?)(?=^## 6\.)",
        agents,
        re.MULTILINE | re.DOTALL,
    )
    assert section is not None, "AGENTS.md must contain Section 5 followed by Section 6"
    routed = set(re.findall(r"`(docs/[^ `]+\.md)`", section.group("body")))
    missing = sorted(path for path in routed if not (ROOT / path).is_file())
    assert missing == []
    untracked = sorted(path for path in routed if path not in TRACKED_PATHS)
    assert untracked == []
