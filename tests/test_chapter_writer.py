"""Tests for chapter_writer.py v4 prompt."""
from biyu.prompts.chapter_writer import (
    build_layer1_hard_rules,
    build_layer2_context,
    build_layer3_constraints,
    build_writer_prompt_v4,
    LAYER1_BEGIN,
    LAYER1_END,
    LAYER2_BEGIN,
    LAYER2_END,
    LAYER3_BEGIN,
    LAYER3_END,
)


def test_layer1_hard_rules_extracts_protagonist_name():
    """Layer 1 包含从 worldbook.facts 提取的主角姓名。"""
    worldbook = {
        "facts": [
            "主角姓名:张今空",
            "秘境名称:试炼之塔",
            "等级体系:LV1-LV100",
        ]
    }
    result = build_layer1_hard_rules(chapter_num=3, worldbook=worldbook)
    assert "张今空" in result
    assert "第 3 章" in result


def test_layer1_under_300_chars():
    """Layer 1 字符数不超过 300(包含格式标记)。"""
    worldbook = {
        "facts": [
            "主角姓名:张今空",
            "秘境名称:试炼之塔",
        ]
    }
    result = build_layer1_hard_rules(chapter_num=1, worldbook=worldbook)
    assert len(result) <= 300


def test_layer2_no_constraint_keywords():
    """Layer 2 内容不出现约束词(只在各子段原文中允许)。

    检查 Layer 2 的结构标记和分隔行是否不含约束词。
    Layer 2 传入的内容本身(worldbook 原文)可能包含,所以只检查非内容行。
    """
    layer2 = build_layer2_context(
        worldbook_prompt="世界观内容",
        characters=[{"name": "张三", "background": "普通背景"}],
        truth_files_block="当前状态",
        prev_tail="上一章末段",
        context_block="历史章节",
        outline="本章大纲",
        planning="本章规划",
    )
    # 提取结构行(以 # 或 【 开头的行)
    constraint_words = ["必须", "禁止", "不得", "禁止使用"]
    for line in layer2.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("【"):
            for word in constraint_words:
                assert word not in stripped, f"Layer 2 结构行含约束词 '{word}': {stripped}"


def test_layer3_contains_punctuation_rule():
    """Layer 3 必须包含破折号约束。"""
    result = build_layer3_constraints(target_words=5000)
    assert "破折号" in result
    assert "3 次/千字" in result


def test_full_prompt_layers_in_order():
    """完整 prompt 顺序为 Layer 1 → Layer 2 → Layer 3。"""
    system_prompt, user_prompt = build_writer_prompt_v4(
        chapter_num=1,
        worldbook={"facts": ["主角姓名:张今空"]},
        worldbook_prompt="世界观",
        characters=[],
        truth_files_block="",
        prev_tail="",
        context_block="",
        outline="大纲",
        planning="规划",
        target_words=5000,
    )

    # system prompt 是独立的
    assert "中文网文作者" in system_prompt

    # user prompt 中 Layer 顺序
    l1_pos = user_prompt.find(LAYER1_BEGIN)
    l2_pos = user_prompt.find(LAYER2_BEGIN)
    l3_pos = user_prompt.find(LAYER3_BEGIN)

    assert l1_pos < l2_pos < l3_pos, (
        f"Layer 顺序错误: L1={l1_pos}, L2={l2_pos}, L3={l3_pos}"
    )

    # 收尾指令
    assert "现在开始写第 1 章正文" in user_prompt
