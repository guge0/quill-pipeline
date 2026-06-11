"""Test _parse_present_characters fallback name extraction."""
import pytest
from pathlib import Path
from biyu.pipeline import _parse_present_characters


class TestParsePresentCharacters:
    """Tests for _parse_present_characters: frontmatter parsing + fallback."""

    def test_frontmatter_present(self, tmp_path: Path):
        """YAML frontmatter with present_characters should be returned directly."""
        outline = """---
present_characters:
  - EXAMPLE_PROTAGONIST
  - EXAMPLE_SIDEKICK
  - EXAMPLE_SUPPORTING
---

# 第1章
"""
        result = _parse_present_characters(outline, tmp_path)
        assert result == ["EXAMPLE_PROTAGONIST", "EXAMPLE_SIDEKICK", "EXAMPLE_SUPPORTING"]

    def test_no_frontmatter_no_truth_file(self, tmp_path: Path):
        """No frontmatter and no truth file → empty list."""
        outline = "# 第1章\n正文"
        result = _parse_present_characters(outline, tmp_path)
        assert result == []

    def test_fallback_strips_parentheses(self, tmp_path: Path):
        """Fallback should strip content after parentheses."""
        outline = "# 第1章\n正文"
        truth_dir = tmp_path / "truth_files"
        truth_dir.mkdir()
        (truth_dir / "current_state.md").write_text(
            "在场：EXAMPLE_VILLAIN（疑似杀母凶手）、EXAMPLE_PROTAGONIST\n", encoding="utf-8"
        )
        result = _parse_present_characters(outline, tmp_path)
        assert result == ["EXAMPLE_VILLAIN", "EXAMPLE_PROTAGONIST"]

    def test_fallback_strips_dash(self, tmp_path: Path):
        """Fallback should strip content after em-dash."""
        outline = "# 第1章\n正文"
        truth_dir = tmp_path / "truth_files"
        truth_dir.mkdir()
        (truth_dir / "current_state.md").write_text(
            "在场：EXAMPLE_SUPPORTING——成绩优异、EXAMPLE_SIDEKICK\n", encoding="utf-8"
        )
        result = _parse_present_characters(outline, tmp_path)
        assert result == ["EXAMPLE_SUPPORTING", "EXAMPLE_SIDEKICK"]

    def test_fallback_strips_period_annotation(self, tmp_path: Path):
        """Fallback should strip annotation after period within a name entry."""
        outline = "# 第1章\n正文"
        truth_dir = tmp_path / "truth_files"
        truth_dir.mkdir()
        (truth_dir / "current_state.md").write_text(
            "在场：EXAMPLE_PROTAGONIST。、EXAMPLE_CLASSMATE。\n", encoding="utf-8"
        )
        result = _parse_present_characters(outline, tmp_path)
        assert result == ["EXAMPLE_PROTAGONIST", "EXAMPLE_CLASSMATE"]

    def test_fallback_pure_name(self, tmp_path: Path):
        """Pure name without annotations passes through unchanged."""
        outline = "# 第1章\n正文"
        truth_dir = tmp_path / "truth_files"
        truth_dir.mkdir()
        (truth_dir / "current_state.md").write_text(
            "在场：EXAMPLE_PROTAGONIST、EXAMPLE_SIDEKICK、EXAMPLE_SUPPORTING\n", encoding="utf-8"
        )
        result = _parse_present_characters(outline, tmp_path)
        assert result == ["EXAMPLE_PROTAGONIST", "EXAMPLE_SIDEKICK", "EXAMPLE_SUPPORTING"]

    def test_fallback_mixed_annotations(self, tmp_path: Path):
        """Mixed annotations should all be stripped to just names."""
        outline = "# 第1章\n正文"
        truth_dir = tmp_path / "truth_files"
        truth_dir.mkdir()
        (truth_dir / "current_state.md").write_text(
            "在场：EXAMPLE_VILLAIN（疑似杀母凶手，左手有暗红色疤痕）,"
            "EXAMPLE_SUPPORTING——成绩优异，本书女主候选,EXAMPLE_PROTAGONIST\n",
            encoding="utf-8",
        )
        result = _parse_present_characters(outline, tmp_path)
        assert result == ["EXAMPLE_VILLAIN", "EXAMPLE_SUPPORTING", "EXAMPLE_PROTAGONIST"]
