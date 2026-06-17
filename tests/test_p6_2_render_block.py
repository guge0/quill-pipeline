"""P6-2 render_block 单测:验证 YAML → genre_block 渲染。"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from p6_2_render_block import render_genre_block  # noqa: E402

YAML_PATH = REPO / "eval_set_v0" / "template_genre.yaml"


def test_render_returns_str():
    out = render_genre_block(YAML_PATH, chapter_num=1)
    assert isinstance(out, str)
    assert len(out) > 100


def test_render_contains_all_sections():
    out = render_genre_block(YAML_PATH, chapter_num=1)
    # 三大段标题
    assert "节奏曲线" in out
    assert "目标体系" in out
    assert "开篇结构" in out
    # 本章应用提示
    assert "本章应用提示" in out


def test_render_no_hard_constraints():
    """Layer 2 纪律:不出现 NEVER/ALWAYS/MUST 大写硬指令。"""
    out = render_genre_block(YAML_PATH, chapter_num=1)
    for forbidden in ["NEVER", "ALWAYS", "MUST"]:
        assert forbidden not in out, f"含硬约束词 {forbidden}"


def test_render_contains_typical_value_disclaimer():
    out = render_genre_block(YAML_PATH, chapter_num=1)
    assert "典型值" in out
    assert "参考" in out


def test_render_includes_chapter_context():
    """本章应用提示应含 chapter_num 和累计字数估算。"""
    out5 = render_genre_block(YAML_PATH, chapter_num=5)
    assert "第 5 章" in out5
    # chapter 5 累计 ≈ 4*3000 = 12000 字
    assert "12000" in out5


def test_render_deterministic():
    """稳定性:同输入多次跑结果一致。"""
    a = render_genre_block(YAML_PATH, chapter_num=3)
    b = render_genre_block(YAML_PATH, chapter_num=3)
    assert a == b


def test_render_edge_chapter_one():
    """边缘:第 1 章累计字数应为 0。"""
    out = render_genre_block(YAML_PATH, chapter_num=1)
    assert "累计约 0 字" in out


def test_render_why_present():
    """why-based:渲染必须含 rationale,不是裸规则。"""
    out = render_genre_block(YAML_PATH, chapter_num=1)
    # 至少 3 处 "为什么" 或等价的 rationale 标记
    assert out.count("为什么") >= 3 or out.count("理由") >= 2
