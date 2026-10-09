"""Cross-language provenance and distributable-artifact invariants."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from truth_backend.models import Report
from truth_backend.reports import validate_references

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {"zh-CN": "demo-report.json", "en": "demo-report.en.json", "ja": "demo-report.ja.json"}


def load(language):
    return json.loads((ROOT / "examples" / FIXTURES[language]).read_text(encoding="utf-8"))


@pytest.mark.parametrize("language", FIXTURES)
def test_translated_demos_preserve_evidence_and_numbers(language):
    original, translated = load("zh-CN"), load(language)
    assert translated["language"] == language
    validate_references(Report.model_validate(translated))
    assert [c["id"] for c in translated["claims"]] == [c["id"] for c in original["claims"]]
    assert len(translated["evidence"]) == len(original["evidence"])
    for base, item in zip(original["evidence"], translated["evidence"]):
        for key in ("id", "url", "title", "excerpt", "published_at", "retrieved_at", "source_family", "screenshots"):
            assert item.get(key) == base.get(key), f"{language}: evidence {key} changed"
    for base_chart, chart in zip(original["charts"], translated["charts"]):
        assert len(chart["points"]) == len(base_chart["points"])
        for base, item in zip(base_chart["points"], chart["points"]):
            assert item["value"] == base["value"]
            assert item["evidence_ids"] == base["evidence_ids"]
            assert item.get("calculation", {}).get("source_quotes") == base.get("calculation", {}).get("source_quotes")
    assert [t["date"] for t in translated["timeline"]] == [t["date"] for t in original["timeline"]]


def test_original_capture_matches_declared_hash():
    for source in load("zh-CN")["evidence"]:
        for screenshot in source.get("screenshots", []):
            data = (ROOT / "examples" / screenshot["url"].lstrip("/")).read_bytes()
            assert hashlib.sha256(data).hexdigest() == screenshot["sha256"]
            assert data.startswith(b"\xff\xd8\xff")


@pytest.mark.parametrize("name", ["README.md", "README.zh-CN.md", "README.ja.md"])
def test_readme_local_links_and_images_exist(name):
    content = (ROOT / name).read_text(encoding="utf-8")
    assert not re.search(r"[A-Z]:[\\/]", content)
    targets = re.findall(r"\]\(([^\s)]+)\)", content) + re.findall(r'(?:src|href)="([^"#]+)"', content)
    for target in targets:
        if "://" in target or target.startswith("#"):
            continue
        assert (ROOT / target.split("#")[0]).exists(), f"{name}: missing {target}"


@pytest.mark.parametrize("language", FIXTURES)
def test_installer_is_localized_and_preserves_existing_skill(tmp_path, language):
    env = {**os.environ, "CODEX_HOME": str(tmp_path), "PYTHONUTF8": "1"}
    command = [sys.executable, "-X", "utf8", str(ROOT / "install_skill.py"), "--language", language]
    first = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", check=True)
    target = tmp_path / "skills" / "tell-me-truth"
    sentinel = target / "local-note.txt"
    sentinel.write_text("KEEP", encoding="utf-8")
    second = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", check=True)
    assert sentinel.read_text(encoding="utf-8") == "KEEP"
    assert first.stdout != second.stdout
    assert {"zh-CN": "已安装", "en": "Installed", "ja": "インストール"}[language] in first.stdout
