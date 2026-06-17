"""P6-2 genre_structure_checker 单测。"""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.genre_structure_checker import (  # noqa: E402
    normalize,
    load_markers,
    scan_text,
    run_check,
)

MARKERS_PATH = REPO / "eval_set_v0" / "genre_markers.yaml"


def test_normalize_halfwidth():
    """全角→半角"""
    assert normalize("（）") == "()"
    assert normalize("ＡＢ") == "AB"


def test_normalize_whitespace():
    assert normalize("a   b\n\n c") == "a b c"


def test_load_markers_structure():
    m = load_markers(MARKERS_PATH)
    assert "pacing" in m
    assert "goals" in m
    assert "opening" in m
    assert len(m["pacing"]) == 5
    assert len(m["goals"]) == 5
    assert len(m["opening"]) == 4


def test_scan_canonical_hit():
    text = "本章是小高潮的兑现"
    hits = scan_text(text, load_markers(MARKERS_PATH))
    assert "P1" in hits


def test_scan_alias_hit():
    text = "本章开局要交代场景"
    hits = scan_text(text, load_markers(MARKERS_PATH))
    assert "P4" in hits  # alias "开局"


def test_scan_no_hit():
    text = "今天天气很好"
    hits = scan_text(text, load_markers(MARKERS_PATH))
    assert hits == set()


def test_scan_multiple_markers():
    text = "凤头要写好,主角聚光,章末要有钩子"
    hits = scan_text(text, load_markers(MARKERS_PATH))
    assert "O1" in hits  # 凤头
    assert "O2" in hits  # 主角聚光 alias
    assert "P5" in hits  # 章末 / 钩子


def test_scan_normalize_consistency():
    """全角输入应与半角等效命中。"""
    m = load_markers(MARKERS_PATH)
    h1 = scan_text("（凤头）", m)
    h2 = scan_text("(凤头)", m)
    assert h1 == h2


def test_run_check_cli_json(tmp_path):
    sample = tmp_path / "planning.md"
    sample.write_text("## 戏核\n凤头要写好,主角聚光。本章是开局。", encoding="utf-8")
    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    run_check(
        markers_path=MARKERS_PATH,
        files=[sample],
        labels=["test1"],
        output_dir=tmp_path,
    )
    assert out_json.exists()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert "results" in data
    assert len(data["results"]) == 1
    res = data["results"][0]
    assert res["label"] == "test1"
    assert "O1" in res["hits"]
    assert res["total_hits"] >= 3


def test_run_check_comparison_summary(tmp_path):
    """多文件对比:baseline 0 hits vs template 多 hits。"""
    baseline = tmp_path / "baseline.md"
    baseline.write_text("无关内容", encoding="utf-8")
    template = tmp_path / "template.md"
    template.write_text("凤头 双伏笔 短期目标 钩子", encoding="utf-8")
    run_check(
        markers_path=MARKERS_PATH,
        files=[baseline, template],
        labels=["baseline", "template"],
        output_dir=tmp_path,
    )
    data = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    by_label = {r["label"]: r["total_hits"] for r in data["results"]}
    assert by_label["baseline"] == 0
    assert by_label["template"] > 0
