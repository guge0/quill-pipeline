"""P6-2 monkey-patch 单测:验证双绑定注入正确。"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import biyu.pipeline as pipe  # noqa: E402
import biyu.prompts.v3_opening as vo  # noqa: E402

from p6_2_generate_template_variant import install_genre_patch, _patched_factory  # noqa: E402

YAML_PATH = REPO / "eval_set_v0" / "template_genre.yaml"


def test_install_patches_both_bindings():
    """双绑定:vo 和 pipe 都应是 patched,且是同一个函数。"""
    original_vo = vo.build_planning_prompt
    original_pipe = pipe.build_planning_prompt
    try:
        install_genre_patch(YAML_PATH)
        assert vo.build_planning_prompt is pipe.build_planning_prompt
        assert vo.build_planning_prompt is not original_vo
    finally:
        vo.build_planning_prompt = original_vo
        pipe.build_planning_prompt = original_pipe


def test_patched_output_contains_genre_block():
    """patched 调用应在输出含 genre_block 标题。"""
    original_vo = vo.build_planning_prompt
    original_pipe = pipe.build_planning_prompt
    try:
        install_genre_patch(YAML_PATH)
        out = vo.build_planning_prompt(
            outline="测试 sub-md",
            chapter_num=3,
        )
        assert "题材结构骨架" in out
        assert "节奏曲线" in out
        assert "目标体系" in out
        assert "开篇结构" in out
    finally:
        vo.build_planning_prompt = original_vo
        pipe.build_planning_prompt = original_pipe


def test_patched_output_anchor_block_passthrough():
    """anchor_block 参数应透传给原函数。"""
    original_vo = vo.build_planning_prompt
    original_pipe = pipe.build_planning_prompt
    try:
        install_genre_patch(YAML_PATH)
        out = vo.build_planning_prompt(
            outline="测试",
            chapter_num=1,
            anchor_block="- 时间:十一点二十",
        )
        assert "时间:十一点二十" in out  # anchor_block 透传
        assert "题材结构骨架" in out  # genre_block 也注入
    finally:
        vo.build_planning_prompt = original_vo
        pipe.build_planning_prompt = original_pipe


def test_patched_deterministic():
    """稳定性:多次调用一致。"""
    original_vo = vo.build_planning_prompt
    original_pipe = pipe.build_planning_prompt
    try:
        install_genre_patch(YAML_PATH)
        out1 = vo.build_planning_prompt(outline="x", chapter_num=2)
        out2 = vo.build_planning_prompt(outline="x", chapter_num=2)
        assert out1 == out2
    finally:
        vo.build_planning_prompt = original_vo
        pipe.build_planning_prompt = original_pipe


def test_patched_fallback_when_marker_missing():
    """marker "## 输出格式" 缺失时走 append fallback。"""
    # 用 _patched_factory 直接构造,绕过真实 original(模拟 marker 缺失场景)
    def fake_original(**kwargs):
        return "no marker here"

    patched = _patched_factory(fake_original, YAML_PATH)
    out = patched(outline="x", chapter_num=1)
    assert "题材结构骨架" in out
    assert "no marker here" in out
    # fallback:genre_block 应在末尾(不在中间)
    assert out.index("题材结构骨架") > out.index("no marker here")


def test_patched_marker_present_inserts_before_marker():
    """marker 存在时:genre_block 插在 "## 输出格式" 之前。"""
    def fake_original(**kwargs):
        return "开头内容\n\n## 输出格式\n\n格式要求"

    patched = _patched_factory(fake_original, YAML_PATH)
    out = patched(outline="x", chapter_num=1)
    # genre_block 应在 "## 输出格式" 之前
    assert out.index("题材结构骨架") < out.index("## 输出格式")
