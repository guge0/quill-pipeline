"""Tests for tools.anchor_checker."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

from tools.anchor_checker import (
    check_atomic,
    check_composite,
    compute_stats,
    generate_json_report,
    generate_md_report,
    normalize,
    run_check,
)


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------
class TestNormalize:
    def test_halfwidth_unchanged(self):
        assert normalize("A-113") == "A-113"

    def test_fullwidth_to_halfwidth(self):
        assert normalize("Ａ－１１３") == "A-113"

    def test_fullwidth_alpha(self):
        assert normalize("ＡＢＣ") == "ABC"

    def test_whitespace_collapse(self):
        assert normalize("回声  巷　17号") == "回声 巷 17号"

    def test_strip(self):
        assert normalize("  hello  ") == "hello"

    def test_fullwidth_number(self):
        assert normalize("０７号") == "07号"

    def test_mixed_full_half(self):
        """全半角混写场景"""
        assert normalize("Ａ-113") == "A-113"


# ---------------------------------------------------------------------------
# Atomic 命中
# ---------------------------------------------------------------------------
class TestCheckAtomic:
    @pytest.fixture()
    def sample_anchors(self):
        return [
            {"id": "T1-H01", "type": "时间", "canonical": "十一点二十", "aliases": ["23:20"]},
            {"id": "T1-H02", "type": "地点", "canonical": "回声巷17号", "aliases": ["回声巷十七号"]},
            {"id": "T1-H03", "type": "地点", "canonical": "守拙斋", "aliases": []},
        ]

    def test_canonical_hit(self, sample_anchors):
        text = "他十一点二十抵达回声巷巷口"
        results = check_atomic(sample_anchors, text)
        assert results[0]["hit"] is True
        assert results[0]["hit_by"] == "十一点二十"

    def test_alias_hit(self, sample_anchors):
        text = "他23:20抵达回声巷巷口"
        results = check_atomic(sample_anchors, text)
        assert results[0]["hit"] is True
        assert results[0]["hit_by"] == "23:20"

    def test_miss(self, sample_anchors):
        text = "他在中午十二点到了公司"
        results = check_atomic(sample_anchors, text)
        assert results[0]["hit"] is False
        assert results[0]["hit_by"] is None

    def test_chinese_number_alias_hit(self, sample_anchors):
        text = "回声巷十七号在巷尾"
        results = check_atomic(sample_anchors, text)
        assert results[1]["hit"] is True
        assert results[1]["hit_by"] == "回声巷十七号"

    def test_fullwidth_alias_normalization(self):
        anchors = [
            {"id": "T1-H09", "type": "数字", "canonical": "07号黄铜钥匙", "aliases": ["编号07", "零七号"]},
        ]
        text = "他拿到了编号０７的钥匙"
        results = check_atomic(anchors, text)
        assert results[0]["hit"] is True

    def test_cross_chapter_field_preserved(self):
        anchors = [
            {
                "id": "T3-H01", "type": "时间", "canonical": "上午十点",
                "aliases": ["早上十点", "10点"], "cross_chapter_of": "T1-H13",
            },
        ]
        text = "上午十点到了档案馆"
        results = check_atomic(anchors, text)
        assert results[0]["hit"] is True
        assert results[0]["cross_chapter_of"] == "T1-H13"


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------
class TestCheckComposite:
    def test_all_members_hit(self):
        atomic_results = [
            {"id": "T1-H13", "hit": True},
            {"id": "T1-H14", "hit": True},
            {"id": "T1-H12", "hit": True},
            {"id": "T1-H15", "hit": True},
        ]
        composite = [{"id": "T1-C01", "name": "约定·档案馆碰头", "members": ["T1-H13", "T1-H14", "T1-H12", "T1-H15"]}]
        results = check_composite(composite, atomic_results)
        assert results[0]["all_hit"] is True

    def test_one_member_miss(self):
        atomic_results = [
            {"id": "T1-H13", "hit": True},
            {"id": "T1-H14", "hit": False},
            {"id": "T1-H12", "hit": True},
            {"id": "T1-H15", "hit": True},
        ]
        composite = [{"id": "T1-C01", "name": "约定·档案馆碰头", "members": ["T1-H13", "T1-H14", "T1-H12", "T1-H15"]}]
        results = check_composite(composite, atomic_results)
        assert results[0]["all_hit"] is False

    def test_single_member_composite(self):
        atomic_results = [
            {"id": "T1-H17", "hit": True},
        ]
        composite = [{"id": "T1-C02", "name": "约定·不单独进当铺", "members": ["T1-H17"]}]
        results = check_composite(composite, atomic_results)
        assert results[0]["all_hit"] is True


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
class TestComputeStats:
    def test_basic_stats(self):
        atomic = [
            {"id": "H1", "type": "时间", "hit": True, "canonical": "A", "cross_chapter_of": None},
            {"id": "H2", "type": "时间", "hit": False, "canonical": "B", "cross_chapter_of": None},
            {"id": "H3", "type": "地点", "hit": True, "canonical": "C", "cross_chapter_of": None},
        ]
        stats = compute_stats("T1", atomic)
        assert stats["atomic"]["total"] == 3
        assert stats["atomic"]["hit"] == 2
        assert stats["atomic"]["ratio"] == pytest.approx(2 / 3)

    def test_by_type(self):
        atomic = [
            {"id": "H1", "type": "时间", "hit": True, "canonical": "A", "cross_chapter_of": None},
            {"id": "H2", "type": "时间", "hit": False, "canonical": "B", "cross_chapter_of": None},
            {"id": "H3", "type": "地点", "hit": True, "canonical": "C", "cross_chapter_of": None},
        ]
        stats = compute_stats("T1", atomic)
        assert stats["by_type"]["时间"]["total"] == 2
        assert stats["by_type"]["时间"]["hit"] == 1
        assert stats["by_type"]["地点"]["total"] == 1
        assert stats["by_type"]["地点"]["hit"] == 1

    def test_cross_chapter_subset(self):
        atomic = [
            {"id": "H1", "type": "时间", "hit": True, "canonical": "A", "cross_chapter_of": None},
            {"id": "H2", "type": "地点", "hit": False, "canonical": "B", "cross_chapter_of": "T1-H14"},
        ]
        stats = compute_stats("T3", atomic)
        assert stats["cross_chapter"]["total"] == 1
        assert stats["cross_chapter"]["hit"] == 0

    def test_empty_cross_chapter(self):
        atomic = [
            {"id": "H1", "type": "时间", "hit": True, "canonical": "A", "cross_chapter_of": None},
        ]
        stats = compute_stats("T1", atomic)
        assert stats["cross_chapter"]["total"] == 0


# ---------------------------------------------------------------------------
# 端到端: run_check 用临时文件
# ---------------------------------------------------------------------------
class TestRunCheck:
    @pytest.fixture()
    def tmp_yaml(self, tmp_path):
        data = {
            "T1": {
                "atomic": [
                    {"id": "T1-H01", "type": "时间", "canonical": "十一点二十", "aliases": ["23:20"]},
                    {"id": "T1-H02", "type": "地点", "canonical": "回声巷17号", "aliases": ["回声巷十七号"]},
                    {"id": "T1-H03", "type": "地点", "canonical": "守拙斋", "aliases": []},
                ],
                "composite": [
                    {"id": "T1-C01", "name": "测试组合", "members": ["T1-H01", "T1-H02"]},
                ],
            }
        }
        p = tmp_path / "anchors.yaml"
        p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return p

    def test_full_run(self, tmp_yaml, tmp_path):
        text = "他十一点二十到了回声巷17号，走进守拙斋。"
        text_file = tmp_path / "T1_test.md"
        text_file.write_text(text, encoding="utf-8")

        report = run_check(str(tmp_yaml), str(text_file), "T1")
        assert report["chapter"] == "T1"
        assert report["stats"]["atomic"]["total"] == 3
        assert report["stats"]["atomic"]["hit"] == 3
        assert report["stats"]["atomic"]["ratio"] == 1.0
        assert report["stats"]["composite"]["hit"] == 1

    def test_partial_hit(self, tmp_yaml, tmp_path):
        text = "他去了回声巷17号，但没进守拙斋。"  # 缺十一点二十
        text_file = tmp_path / "T1_test2.md"
        text_file.write_text(text, encoding="utf-8")

        report = run_check(str(tmp_yaml), str(text_file), "T1")
        # 回声巷17号命中, 守拙斋也命中(子串), 十一点二十未命中
        assert report["stats"]["atomic"]["hit"] == 2
        assert report["stats"]["composite"]["hit"] == 0  # T1-H01缺失导致composite失败

    def test_chapter_id_inference(self, tmp_yaml, tmp_path):
        text = "十一点二十，回声巷17号，守拙斋。"
        text_file = tmp_path / "T1_clean.md"
        text_file.write_text(text, encoding="utf-8")

        report = run_check(str(tmp_yaml), str(text_file))
        assert report["chapter"] == "T1"


# ---------------------------------------------------------------------------
# 报告格式
# ---------------------------------------------------------------------------
class TestReportGeneration:
    @pytest.fixture()
    def sample_results(self):
        return [{
            "chapter": "T1",
            "source_file": "baseline/T1_clean.md",
            "atomic_results": [
                {"id": "T1-H01", "type": "时间", "canonical": "十一点二十", "hit": True, "hit_by": "十一点二十", "cross_chapter_of": None},
                {"id": "T1-H02", "type": "地点", "canonical": "回声巷17号", "hit": False, "hit_by": None, "cross_chapter_of": None},
            ],
            "composite_results": [],
            "stats": {
                "atomic": {"total": 2, "hit": 1, "miss": 1, "ratio": 0.5},
                "by_type": {
                    "时间": {"total": 1, "hit": 1, "miss": 0, "ratio": 1.0},
                    "地点": {"total": 1, "hit": 0, "miss": 1, "ratio": 0.0},
                },
                "cross_chapter": {"total": 0, "hit": 0, "ratio": None},
            },
        }]

    def test_json_report(self, sample_results, tmp_path):
        out = tmp_path / "report.json"
        generate_json_report(sample_results, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["chapter"] == "T1"

    def test_md_report(self, sample_results, tmp_path):
        out = tmp_path / "report.md"
        generate_md_report(sample_results, out)
        content = out.read_text(encoding="utf-8")
        assert "# Anchor Check Report" in content
        assert "T1" in content
        assert "50.0%" in content
