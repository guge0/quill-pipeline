"""test_auditor_character_presence — CharacterPresenceAuditor 单元测试。"""
import pytest

from biyu.auditor.character_presence import CharacterPresenceAuditor, _extract_named_characters
from biyu.auditor.base import Severity


class TestExtractNamedCharacters:
    def test_basic(self):
        text = "EXAMPLE_PROTAGONIST和EXAMPLE_FEMALE_LEAD一起走进了秘境。"
        names = ["EXAMPLE_PROTAGONIST", "EXAMPLE_FEMALE_LEAD", "EXAMPLE_ALLY"]
        found = _extract_named_characters(text, names)
        assert "EXAMPLE_PROTAGONIST" in found
        assert "EXAMPLE_FEMALE_LEAD" in found
        assert "EXAMPLE_ALLY" not in found


class TestCharacterPresenceAuditor:
    def test_no_present_list(self):
        auditor = CharacterPresenceAuditor()
        ctx = {
            "characters": [{"name": "EXAMPLE_PROTAGONIST"}, {"name": "EXAMPLE_FEMALE_LEAD"}],
        }
        result = auditor.run("EXAMPLE_PROTAGONIST站在那里。", ctx)
        assert result.checker == "character_presence"
        assert "EXAMPLE_PROTAGONIST" in result.message

    def test_unexpected_character(self):
        auditor = CharacterPresenceAuditor()
        ctx = {
            "characters": [{"name": "EXAMPLE_PROTAGONIST"}, {"name": "EXAMPLE_FEMALE_LEAD"}, {"name": "EXAMPLE_ALLY"}],
            "present_characters": ["EXAMPLE_PROTAGONIST"],
        }
        result = auditor.run("EXAMPLE_PROTAGONIST和EXAMPLE_FEMALE_LEAD一起走进了秘境。", ctx)
        assert "非在场角色出现" in result.message
        assert "EXAMPLE_FEMALE_LEAD" in result.message

    def test_all_present(self):
        auditor = CharacterPresenceAuditor()
        ctx = {
            "characters": [{"name": "EXAMPLE_PROTAGONIST"}, {"name": "EXAMPLE_FEMALE_LEAD"}],
            "present_characters": ["EXAMPLE_PROTAGONIST", "EXAMPLE_FEMALE_LEAD"],
        }
        result = auditor.run("EXAMPLE_PROTAGONIST和EXAMPLE_FEMALE_LEAD一起走进了秘境。", ctx)
        assert "一致" in result.message

    def test_name_property(self):
        auditor = CharacterPresenceAuditor()
        assert auditor.name == "character_presence"
