"""¥0 自检: 反机械 patch 正确追加到 Layer3,不破坏原结构。不调 LLM。"""
from __future__ import annotations
import sys
from pathlib import Path

# 让 tests 能 import scripts.* (pytest pythonpath 只含 src/)
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.p6_humanity_generate_variant import (  # noqa: E402
    install_anti_mechanical_patch, ANTI_MECHANICAL_BLOCK)
from biyu.prompts.chapter_writer import LAYER3_END, build_layer3_constraints  # noqa: E402


def test_patch_appends_before_layer3_end():
    """验证 patch 正确插入反机械块且不破坏 LAYER3_END 标记。"""
    # 保存原始函数
    import biyu.prompts.chapter_writer as cw
    original_func = cw.build_layer3_constraints

    # 获取原始输出
    original = original_func(5000)

    # 安装 patch
    install_anti_mechanical_patch()
    patched = cw.build_layer3_constraints(5000)

    try:
        # 核心断言
        assert "反机械痕迹" in patched, "反机械块应被注入"
        assert patched.count(LAYER3_END) == original.count(LAYER3_END), \
            "LAYER3_END 标记数不应改变"
        assert len(patched) > len(original), "patched 版本应更长"
        assert patched.index("反机械痕迹") < patched.rindex(LAYER3_END), \
            "反机械块应在 LAYER3_END 之前"
    finally:
        # 恢复原始函数,避免污染其他测试
        cw.build_layer3_constraints = original_func


def test_patch_multiple_calls():
    """验证 patch 可多次调用且输出稳定。"""
    import biyu.prompts.chapter_writer as cw
    original_func = cw.build_layer3_constraints

    try:
        install_anti_mechanical_patch()
        result1 = cw.build_layer3_constraints(5000)
        result2 = cw.build_layer3_constraints(5000)

        # 两次调用应产生相同输出
        assert result1 == result2, "patched 函数多次调用应产生相同输出"
        assert result1.count("反机械痕迹") == 1, "反机械块应只出现一次"
    finally:
        cw.build_layer3_constraints = original_func


def test_patch_preserves_target_words():
    """验证 patch 不破坏 target_words 参数传递。"""
    import biyu.prompts.chapter_writer as cw
    original_func = cw.build_layer3_constraints

    try:
        install_anti_mechanical_patch()

        # 测试不同 target_words 值
        for words in [3000, 5000, 7000]:
            result = cw.build_layer3_constraints(words)
            assert f"≥ {words} 中文字符" in result, \
                f"target_words={words} 应被正确注入"
            assert f"≤ {words + 1500} 字符" in result, \
                f"上限 = {words} + 1500 应被正确计算"
    finally:
        cw.build_layer3_constraints = original_func


def test_patch_does_not_duplicate_layer3_end():
    """验证 patch 不会在 LAYER3_END 位置产生重复。"""
    import biyu.prompts.chapter_writer as cw
    original_func = cw.build_layer3_constraints

    try:
        install_anti_mechanical_patch()
        result = cw.build_layer3_constraints(5000)

        # LAYER3_END 应只出现一次
        assert result.count(LAYER3_END) == 1, "LAYER3_END 应只出现一次"

        # 反机械块应在最后一次 LAYER3_END 之前
        last_end_pos = result.rindex(LAYER3_END)
        anti_mech_pos = result.index("反机械痕迹")
        assert anti_mech_pos < last_end_pos, "反机械块应在 LAYER3_END 之前"
    finally:
        cw.build_layer3_constraints = original_func
