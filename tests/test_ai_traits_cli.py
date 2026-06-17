"""Tests for tools.ai_traits CLI + 报告生成。"""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from biyu.ai_traits import measure_all
from tools.ai_traits import generate_json_report, generate_md_report, main


@pytest.fixture()
def sample_text_file(tmp_path):
    p = tmp_path / "T1.md"
    p.write_text("他推开报刊亭的玻璃门。风很冷,不动声色。\n\n她笑了。", encoding="utf-8")
    return p


def test_json_report_has_chapter(tmp_path, sample_text_file):
    out = tmp_path / "out.json"
    generate_json_report([{"chapter": "T1", "source_file": str(sample_text_file),
                           "metrics": {}}], out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["chapter"] == "T1"


def test_md_report_contains_proxy_disclaimer(tmp_path, sample_text_file):
    m = measure_all(sample_text_file.read_text(encoding="utf-8"))
    out = tmp_path / "out.md"
    generate_md_report([{"chapter": "T1", "source_file": str(sample_text_file),
                         "metrics": m}], out)
    txt = out.read_text(encoding="utf-8")
    assert "proxy" in txt.lower()
    assert "不判" in txt or "不否决" in txt


def test_cli_main_writes_both_formats(tmp_path, sample_text_file, monkeypatch):
    out_dir = tmp_path / "report"
    monkeypatch.setattr("sys.argv", [
        "ai_traits", str(sample_text_file),
        "--chapter-ids", "T1", "--output-dir", str(out_dir)])
    main()
    assert (out_dir / "ai_traits_report.json").exists()
    assert (out_dir / "ai_traits_report.md").exists()
