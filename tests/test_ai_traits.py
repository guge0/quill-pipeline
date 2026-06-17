"""Tests for biyu.ai_traits — AI 痕迹机械度量(确定性)。"""
from __future__ import annotations
import statistics
from biyu.ai_traits import (
    split_paragraphs, split_sentences, cjk_char_count,
    measure_paragraph_lengths, exclaim_density, dash_density,
    long_unpunct_sentence_ratio, modifier_proxy, parallelism_proxy,
    four_char_proxy, measure_all,
    LONG_PARAGRAPH_CHARS, LONG_SENTENCE_CHARS, PARALLEL_RANGE_CHARS,
)


class TestDeterminism:
    def test_measure_all_is_deterministic(self):
        text = "他推开门。风很冷。\n\n她笑了。" * 10
        a = measure_all(text)
        b = measure_all(text)
        assert a == b  # 完全一致(含浮点逐字段)


class TestSplitParagraphs:
    def test_blankline_separated(self):
        text = "第一段。\n\n第二段。"
        assert len(split_paragraphs(text)) == 2

    def test_drops_empty(self):
        text = "第一段。\n\n\n\n第二段。"
        assert len(split_paragraphs(text)) == 2

    def test_empty_text(self):
        assert split_paragraphs("") == []


class TestSplitSentences:
    def test_terminal_punct(self):
        assert len(split_sentences("他走了。她来了！谁？")) == 3

    def test_empty(self):
        assert split_sentences("") == []


class TestCjkCount:
    def test_cjk_only(self):
        assert cjk_char_count("回声巷17号") == 4  # 回声巷号 4个CJK字符

    def test_empty(self):
        assert cjk_char_count("") == 0

    def test_no_cjk(self):
        assert cjk_char_count("ABC123") == 0


class TestMeasureParagraphLengths:
    def test_basic_paragraphs(self):
        text = "第一段内容。\n\n第二段内容。"
        result = measure_paragraph_lengths(text)
        assert result["count"] == 2
        assert result["mean"] > 0
        assert result["median"] > 0
        assert result["max"] > 0
        assert result["long_para_ratio"] == 0.0  # 短段落

    def test_empty_text(self):
        result = measure_paragraph_lengths("")
        assert result["count"] == 0
        assert result["mean"] == 0.0
        assert result["median"] == 0.0
        assert result["max"] == 0
        assert result["long_para_ratio"] == 0.0

    def test_long_paragraph(self):
        text = "A" * 200 + "是" * 200  # 200 CJK chars
        result = measure_paragraph_lengths(text)
        assert result["long_para_ratio"] == 1.0  # >150 chars


class TestExclaimDensity:
    def test_basic(self):
        text = "你好！世界！"
        result = exclaim_density(text)
        assert isinstance(result, float)
        assert result > 0

    def test_no_exclaim(self):
        result = exclaim_density("你好。世界。")
        assert isinstance(result, float)
        assert result == 0.0

    def test_empty(self):
        result = exclaim_density("")
        assert isinstance(result, float)
        assert result == 0.0


class TestDashDensity:
    def test_em_dash(self):
        text = "他说——停顿了"
        result = dash_density(text)
        assert isinstance(result, float)
        assert result > 0

    def test_double_dash(self):
        result = dash_density("他说--停顿了")
        assert isinstance(result, float)
        assert result > 0

    def test_no_dash(self):
        result = dash_density("他说停顿了")
        assert isinstance(result, float)
        assert result == 0.0

    def test_empty(self):
        result = dash_density("")
        assert isinstance(result, float)
        assert result == 0.0


class TestConstants:
    def test_threshold_values(self):
        assert LONG_PARAGRAPH_CHARS == 150
        assert LONG_SENTENCE_CHARS == 60
        assert PARALLEL_RANGE_CHARS == 3


class TestStubs:
    """回归: 之前是 stub,现已是真实实现 —— 这些输入仍应得到边界值。"""

    def test_long_unpunct_sentence_ratio_stub(self):
        result = long_unpunct_sentence_ratio("任何文本")
        assert result == 0.0

    def test_modifier_proxy_stub(self):
        result = modifier_proxy("任何文本")
        assert result["count"] == 0
        assert result["density_per_1k"] == 0.0
        assert result["proxy"] is True

    def test_parallelism_proxy_stub(self):
        result = parallelism_proxy("任何文本")
        assert result["uniform_run_ratio"] == 0.0
        assert result["same_start_count"] == 0
        assert result["proxy"] is True

    def test_four_char_proxy_stub(self):
        result = four_char_proxy("任何文本")
        assert result["idiom_hits"] == 0  # "任何文本" 不是成语
        assert result["raw_four_cjk_count"] == 1  # 但有 4 个 CJK 连写
        assert result["idiom_density_per_1k"] == 0.0
        assert result["raw_density_per_1k"] > 0.0  # 1个四字格 / 4字 = 250/千字
        assert result["proxy"] is True

    def test_measure_all_stub_complete(self):
        """measure_all should return a complete dict with all required keys."""
        text = "他推开门。风很冷。\n\n她笑了。" * 10
        result = measure_all(text)

        # Check all required keys exist
        required_keys = [
            "char_count_cjk", "char_count_total", "paragraph_lengths",
            "exclaim_density_per_1k", "dash_density_per_1k",
            "long_unpunct_sentence_ratio", "modifier_proxy",
            "parallelism_proxy", "four_char_proxy", "number_rhythm",
            "degenerate", "notes"
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

        # Check basic structure
        assert result["char_count_cjk"] > 0
        assert result["char_count_total"] > 0
        assert result["paragraph_lengths"]["count"] > 0
        assert result["degenerate"] is False
        assert isinstance(result["notes"], str)


class TestLongSentenceRatio:
    def test_long_unpunct_counted(self):
        # 一句无内部标点、超 60 CJK 字 → 计入
        long_sentence = "他" + "走" * 70 + "。"   # 71 CJK,无内部标点
        text = long_sentence + "短的。"
        r = long_unpunct_sentence_ratio(text)
        assert r == 0.5  # 2 句中 1 句

    def test_with_internal_punct_not_counted(self):
        s = "他" + "走" * 40 + ",又" + "走" * 30 + "。"  # 有逗号,不计
        assert long_unpunct_sentence_ratio(s) == 0.0


class TestModifierProxy:
    def test_counts_known_modifiers(self):
        text = "冰冷的风,漆黑的夜。"
        d = modifier_proxy(text)
        assert d["count"] == 2
        assert d["proxy"] is True

    def test_per_1k(self):
        text = "冰冷" * 5
        d = modifier_proxy(text)
        assert d["density_per_1k"] > 0.0


class TestParallelismProxy:
    def test_uniform_run_detected(self):
        # 三句字数完全相同(极差0≤3)→ uniform_run_ratio 高
        s = "一二三四五六。" * 3
        p = parallelism_proxy(s)
        assert p["uniform_run_ratio"] > 0.0
        assert p["proxy"] is True

    def test_varied_not_detected(self):
        s = "一。一二三四五六七八九十一二。短。"
        p = parallelism_proxy(s)
        assert p["uniform_run_ratio"] == 0.0

    def test_same_start_counted(self):
        s = "他走了。他来了。他笑了。"
        p = parallelism_proxy(s)
        assert p["same_start_count"] >= 2


class TestFourCharProxy:
    def test_idiom_hit_and_raw(self):
        text = "他不动声色地站着。"  # 简体,IDIOMS 子串命中
        d = four_char_proxy(text)
        assert d["idiom_hits"] >= 1
        assert d["raw_four_cjk_count"] >= 1
        assert d["proxy"] is True

    def test_raw_fallback(self):
        text = "回声巷里"  # 非 idiom 但 4 CJK 连写
        d = four_char_proxy(text)
        assert d["raw_four_cjk_count"] >= 1


class TestMeasureAll:
    def test_has_all_baskets(self):
        m = measure_all("他推开门。风很冷。\n\n她笑了。")
        for k in ["char_count_cjk", "paragraph_lengths", "exclaim_density_per_1k",
                  "dash_density_per_1k", "long_unpunct_sentence_ratio",
                  "modifier_proxy", "parallelism_proxy", "four_char_proxy",
                  "number_rhythm", "degenerate", "notes"]:
            assert k in m, f"missing key {k}"

    def test_number_rhythm_placeholder(self):
        m = measure_all("测试。")
        assert m["number_rhythm"]["implemented"] is False
        assert "v1" in m["number_rhythm"]["note"]


class TestEdgeCases:
    def test_empty_text(self):
        m = measure_all("")
        assert m["degenerate"] is True
        assert m["char_count_cjk"] == 0

    def test_pure_punctuation(self):
        m = measure_all("。。。！！！？？？")
        assert m["degenerate"] is True  # CJK=0 → 退化
        assert m["exclaim_density_per_1k"] == 0.0  # 防除零

    def test_super_short(self):
        m = measure_all("他走了。")
        assert m["degenerate"] is False
        assert m["char_count_cjk"] == 3

    def test_pure_dialog(self):
        text = '"你来了。"\n\n"嗯。"\n\n"坐。"'  # NOTE: 使用 \n\n 分隔,确保 split_paragraphs 得到 3 段
        m = measure_all(text)
        assert m["paragraph_lengths"]["count"] == 3
        assert m["degenerate"] is False

    def test_empty_paragraphs_only(self):
        m = measure_all("\n\n\n")
        assert m["degenerate"] is True
