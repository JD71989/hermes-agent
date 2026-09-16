"""Tests for Guardian Media Farm skill definitions."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

SKILL_FILES = [
    SKILLS_DIR / "social-media" / "guardian-social-farm" / "SKILL.md",
    SKILLS_DIR / "social-media" / "guardian-influencer-farm" / "SKILL.md",
    SKILLS_DIR / "creative" / "guardian-creative-farm" / "SKILL.md",
    SKILLS_DIR / "media" / "guardian-video-farm" / "SKILL.md",
    SKILLS_DIR / "media" / "guardian-marketing-connection" / "SKILL.md",
]


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_file_exists(skill_file: Path):
    assert skill_file.exists(), f"Skill file not found: {skill_file}"


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_frontmatter(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert text.startswith("---"), "Skill must start with YAML frontmatter"
    parts = text.split("---", 2)
    assert len(parts) >= 3, "Skill must have opening and closing frontmatter delimiters"


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_required_fields(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = parts[1]
    for field in ("name:", "description:", "version:", "license:"):
        assert field in frontmatter, f"Missing required field: {field}"


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_description_under_60_chars(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = parts[1]
    match = re.search(r"^description:\s*\"?(.+?)\"?\s*$", frontmatter, re.MULTILINE)
    assert match, "description field not found"
    desc = match.group(1).strip('"')
    assert len(desc) <= 60, f"Description too long ({len(desc)} chars): {desc}"


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_body_content(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    body = parts[2].strip() if len(parts) >= 3 else ""
    assert len(body) > 200, "Skill body should have substantial content (>200 chars)"


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_how_to_use_section(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert "## When to Use" in text or "## How to Run" in text


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_prerequisites(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert "## Prerequisites" in text


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_procedure(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert "## Procedure" in text


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_references_media_farm_tool(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert "media_farm" in text, "Skill should reference the media_farm tool"


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_rules_section(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert "## Rules" in text, "Skill must include ethical/legal rules"


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_verification(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert "## Verification" in text, "Skill must include verification steps"
