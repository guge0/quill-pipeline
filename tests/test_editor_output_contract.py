"""D-54: Unit tests for submit_review tool-bearing output contract.

Tests the new submit_review-based output flow:

1. submit_review tool definition schemas (single + agent)
2. Final round only has submit_review in tools array
3. execute_tool defensive error handling
4. Arguments parse fail → RUN_FAIL
5. No submit_review in final round → RUN_FAIL
6. Token budget: config-driven max_tokens flows through to adapter.generate()
7. Character card wiring (fixture check)

Zero LLM cost: uses stub adapter.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from biyu.editor.parser import (
    parse_editor_response,
    _extract_json,
)
from biyu.editor.tools import (
    SUBMIT_REVIEW_SINGLE,
    SUBMIT_REVIEW_AGENT,
    EditorFailure,
    execute_tool,
    get_submit_review_tool,
)


# ---------------------------------------------------------------------------
# Stub adapter for tool-loop / token-budget tests
# ---------------------------------------------------------------------------

class StubResponse:
    def __init__(self, text="", cost=0.0, reasoning="", raw=None,
                 tool_calls=None, finish_reason="stop"):
        self.text = text
        self.cost = cost
        self.reasoning_content = reasoning
        self.raw = raw or {"choices": [{"message": {"content": text}}]}
        self.finish_reason = finish_reason
        if tool_calls:
            self.raw["choices"][0]["message"]["tool_calls"] = tool_calls


class StubAdapter:
    """Records calls and returns scripted responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def generate(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if self._responses:
            return self._responses.pop(0)
        return StubResponse(text='{"issues": []}')


def _make_tool_call(name="look_up_character", args='{"char_name": "x"}'):
    return [{
        "id": "call_0",
        "type": "function",
        "function": {"name": name, "arguments": args},
    }]


def _make_submit_review_call(issues, confidence="high"):
    """构造一个 submit_review tool call。"""
    args = json.dumps({"issues": issues, "confidence": confidence}, ensure_ascii=False)
    return [{
        "id": "call_submit",
        "type": "function",
        "function": {"name": "submit_review", "arguments": args},
    }]


# ---------------------------------------------------------------------------
# A6-1: submit_review single schema
# ---------------------------------------------------------------------------

class TestSubmitReviewSingleSchema:
    def test_submit_review_single_structure(self):
        """SUBMIT_REVIEW_SINGLE has correct structure."""
        tool = SUBMIT_REVIEW_SINGLE
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "submit_review"
        params = tool["function"]["parameters"]
        assert "issues" in params["properties"]
        assert "issues" in params["required"]
        # issues is array
        assert params["properties"]["issues"]["type"] == "array"
        # items has EditorIssue fields
        item_props = params["properties"]["issues"]["items"]["properties"]
        for field in ("line", "quote", "type", "explanation", "fix_suggestion",
                      "auto_fixable", "severity"):
            assert field in item_props, f"Missing field: {field}"

    def test_get_submit_review_tool_single(self):
        """get_submit_review_tool('single') returns SUBMIT_REVIEW_SINGLE."""
        tool = get_submit_review_tool("single")
        assert tool["function"]["name"] == "submit_review"


# ---------------------------------------------------------------------------
# A6-2: submit_review agent schema
# ---------------------------------------------------------------------------

class TestSubmitReviewAgentSchema:
    def test_submit_review_agent_structure(self):
        """SUBMIT_REVIEW_AGENT has correct structure."""
        tool = SUBMIT_REVIEW_AGENT
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "submit_review"
        params = tool["function"]["parameters"]
        assert "issues" in params["properties"]
        assert "issues" in params["required"]
        item_props = params["properties"]["issues"]["items"]["properties"]
        for field in ("id", "type", "paragraph", "severity", "keyword",
                      "description", "suggestion"):
            assert field in item_props, f"Missing field: {field}"
        # suggestion has sub-properties
        sug_props = item_props["suggestion"]["properties"]
        assert "content" in sug_props
        assert "rationale" in sug_props

    def test_get_submit_review_tool_agent(self):
        """get_submit_review_tool('agent') returns SUBMIT_REVIEW_AGENT."""
        tool = get_submit_review_tool("agent")
        assert tool["function"]["name"] == "submit_review"

    def test_get_submit_review_tool_invalid(self):
        """get_submit_review_tool with invalid mode raises ValueError."""
        with pytest.raises(ValueError):
            get_submit_review_tool("invalid")


# ---------------------------------------------------------------------------
# A6-3: Final round only submit_review
# ---------------------------------------------------------------------------

class TestFinalRoundOnlySubmitReview:
    def test_single_mode_final_round_only_submit_review(self, tmp_path):
        """In final round, tools array should only contain submit_review."""
        from biyu.editor.editor import review_chapter

        # Round 0: tool call → Round 1: submit_review (with max_tool_rounds=1)
        tool_resp = StubResponse(
            text="checking",
            raw={"choices": [{"message": {
                "content": "checking",
                "tool_calls": _make_tool_call(),
            }}]},
        )
        submit_resp = StubResponse(
            text="done",
            raw={"choices": [{"message": {
                "content": "done",
                "tool_calls": _make_submit_review_call([{
                    "line": 1, "quote": "测试", "type": "字面伪影",
                    "explanation": "test", "fix_suggestion": "delete",
                    "auto_fixable": True, "severity": "high",
                }]),
            }}]},
        )
        adapter = StubAdapter([tool_resp, submit_resp])

        result = asyncio.run(review_chapter(
            chapter_num=1,
            chapter_text="测试正文包含测试",
            book_dir=tmp_path,
            adapter=adapter,
            max_tool_rounds=1,
        ))

        # Round 0 had full tools (lookup + submit_review)
        round0_tools = adapter.calls[0]["kwargs"]["tools"]
        tool_names = [t["function"]["name"] for t in round0_tools]
        assert "submit_review" in tool_names
        assert "look_up_character" in tool_names

        # Round 1 (final) had only submit_review
        round1_tools = adapter.calls[1]["kwargs"]["tools"]
        assert len(round1_tools) == 1
        assert round1_tools[0]["function"]["name"] == "submit_review"

        assert len(result.issues) == 1
        assert result.issues[0].type == "字面伪影"


# ---------------------------------------------------------------------------
# A6-4: execute_tool bad arguments
# ---------------------------------------------------------------------------

class TestExecuteToolBadArguments:
    def test_missing_char_name(self, tmp_path):
        """Missing char_name → BAD_ARGUMENTS JSON."""
        result = execute_tool("look_up_character", {}, tmp_path)
        data = json.loads(result)
        assert data["error"] == "BAD_ARGUMENTS"

    def test_missing_keyword(self, tmp_path):
        """Missing keyword → BAD_ARGUMENTS JSON."""
        result = execute_tool("look_up_setting", {}, tmp_path)
        data = json.loads(result)
        assert data["error"] == "BAD_ARGUMENTS"

    def test_missing_chapter_or_keyword(self, tmp_path):
        """Missing chapter_or_keyword → BAD_ARGUMENTS JSON."""
        result = execute_tool("look_up_history", {}, tmp_path)
        data = json.loads(result)
        assert data["error"] == "BAD_ARGUMENTS"

    def test_missing_symbol(self, tmp_path):
        """Missing symbol → BAD_ARGUMENTS JSON."""
        result = execute_tool("look_up_visual", {}, tmp_path)
        data = json.loads(result)
        assert data["error"] == "BAD_ARGUMENTS"


# ---------------------------------------------------------------------------
# A6-5: execute_tool unknown tool
# ---------------------------------------------------------------------------

class TestExecuteToolUnknownTool:
    def test_unknown_tool(self, tmp_path):
        """Unknown tool name → UNKNOWN_TOOL JSON."""
        result = execute_tool("nonexistent_tool", {"x": "y"}, tmp_path)
        data = json.loads(result)
        assert data["error"] == "UNKNOWN_TOOL"
        assert "nonexistent_tool" in data["message"]


# ---------------------------------------------------------------------------
# A6-6: execute_tool exception → TOOL_EXEC_ERROR
# ---------------------------------------------------------------------------

class TestExecuteToolException:
    def test_exception_returns_tool_exec_error(self, tmp_path):
        """Exception during tool execution → TOOL_EXEC_ERROR JSON."""
        # look_up_character with a corrupted book dir that raises
        # Create a book_dir with a bad characters.yaml
        bad_file = tmp_path / "characters.yaml"
        bad_file.write_text("not: valid\n  yaml: [", encoding="utf-8")
        result = execute_tool("look_up_character", {"char_name": "test"}, tmp_path)
        # yaml.safe_load might still work with this, but if it errors...
        # Actually, let's test with a non-existent book dir to force path error
        # We need a case where the function itself throws
        # look_up_visual with invalid book_dir structure should be fine
        # Let's use a simpler approach: patch the function
        import unittest.mock
        with unittest.mock.patch("biyu.editor.tools.look_up_character", side_effect=RuntimeError("boom")):
            result = execute_tool("look_up_character", {"char_name": "test"}, tmp_path)
            data = json.loads(result)
            assert data["error"] == "TOOL_EXEC_ERROR"
            assert "boom" in data["message"]


# ---------------------------------------------------------------------------
# A6-7: Arguments parse fail → RUN_FAIL
# ---------------------------------------------------------------------------

class TestArgumentsParseFail:
    def test_submit_review_bad_arguments_json(self, tmp_path):
        """submit_review with unparseable arguments → BAD_ARGUMENTS failure."""
        from biyu.editor.editor import review_chapter

        # Return a submit_review call with invalid JSON arguments
        bad_submit_resp = StubResponse(
            text="done",
            raw={"choices": [{"message": {
                "content": "done",
                "tool_calls": [{
                    "id": "call_bad",
                    "type": "function",
                    "function": {"name": "submit_review", "arguments": "not valid json {{{"},
                }],
            }}]},
        )
        adapter = StubAdapter([bad_submit_resp])

        result = asyncio.run(review_chapter(
            chapter_num=1,
            chapter_text="测试正文",
            book_dir=tmp_path,
            adapter=adapter,
            max_tool_rounds=0,
        ))

        # Should have a BAD_ARGUMENTS failure
        assert any("failure:BAD_ARGUMENTS" in e for e in result.parse_errors)


# ---------------------------------------------------------------------------
# A6-8: No submit_review in final round → RUN_FAIL
# ---------------------------------------------------------------------------

class TestNoSubmitReviewInFinalRound:
    def test_single_mode_no_submit_review_in_final_round(self, tmp_path):
        """When LLM doesn't call submit_review in final round → RUN_FAIL."""
        from biyu.editor.editor import review_chapter

        # LLM returns lookup tool calls but no submit_review
        tool_resp = StubResponse(
            text="checking",
            raw={"choices": [{"message": {
                "content": "checking",
                "tool_calls": _make_tool_call(),
            }}]},
        )
        adapter = StubAdapter([tool_resp])

        result = asyncio.run(review_chapter(
            chapter_num=1,
            chapter_text="测试正文",
            book_dir=tmp_path,
            adapter=adapter,
            max_tool_rounds=0,  # Only 1 round (final round immediately)
        ))

        # Should have a RUN_FAIL failure
        assert any("failure:RUN_FAIL" in e for e in result.parse_errors)

    def test_single_mode_submit_review_in_early_round(self, tmp_path):
        """LLM calls submit_review early → success, no more rounds."""
        from biyu.editor.editor import review_chapter

        submit_resp = StubResponse(
            text="done",
            raw={"choices": [{"message": {
                "content": "done",
                "tool_calls": _make_submit_review_call([{
                    "line": 1, "quote": "测试", "type": "字面伪影",
                    "explanation": "test", "fix_suggestion": "delete",
                    "auto_fixable": True, "severity": "high",
                }]),
            }}]},
        )
        adapter = StubAdapter([submit_resp])

        result = asyncio.run(review_chapter(
            chapter_num=1,
            chapter_text="测试正文包含测试",
            book_dir=tmp_path,
            adapter=adapter,
            max_tool_rounds=3,
        ))

        # Should succeed with 1 issue
        assert len(result.issues) == 1
        assert result.issues[0].type == "字面伪影"
        # Only 1 call (submit_review on first round)
        assert len(adapter.calls) == 1


# ---------------------------------------------------------------------------
# Tool-loop with submit_review (replaces old force-final tests)
# ---------------------------------------------------------------------------

class TestToolLoopWithSubmitReview:
    def test_single_mode_tool_then_submit(self, tmp_path):
        """Tool call then submit_review works correctly."""
        from biyu.editor.editor import review_chapter

        tool_resp = StubResponse(
            text="checking",
            raw={"choices": [{"message": {
                "content": "checking",
                "tool_calls": _make_tool_call(),
            }}]},
        )
        submit_resp = StubResponse(
            text="done",
            raw={"choices": [{"message": {
                "content": "done",
                "tool_calls": _make_submit_review_call([{
                    "line": 1, "quote": "测试", "type": "字面伪影",
                    "explanation": "test", "fix_suggestion": "delete",
                    "auto_fixable": True, "severity": "high",
                }]),
            }}]},
        )
        adapter = StubAdapter([tool_resp, submit_resp])

        result = asyncio.run(review_chapter(
            chapter_num=1,
            chapter_text="测试正文包含测试",
            book_dir=tmp_path,
            adapter=adapter,
            max_tool_rounds=3,
        ))

        assert len(result.issues) == 1
        assert result.issues[0].type == "字面伪影"
        assert len(adapter.calls) == 2

    def test_truncation_returns_failure(self, tmp_path):
        """finish_reason=length → TRUNCATION failure."""
        from biyu.editor.editor import review_chapter

        trunc_resp = StubResponse(
            text="truncated...",
            finish_reason="length",
            raw={"choices": [{"message": {"content": "truncated..."}}]},
        )
        adapter = StubAdapter([trunc_resp])

        result = asyncio.run(review_chapter(
            chapter_num=1,
            chapter_text="测试正文",
            book_dir=tmp_path,
            adapter=adapter,
            max_tool_rounds=0,
        ))

        assert any("failure:TRUNCATION" in e for e in result.parse_errors)


# ---------------------------------------------------------------------------
# Token budget control flow
# ---------------------------------------------------------------------------

class TestTokenBudgetConfig:
    """max_tokens is config-driven, not hardcoded 4096."""

    def test_single_mode_reads_max_tokens_from_config(self, tmp_path, monkeypatch):
        """editor.py should read max_completion_tokens from config."""
        from biyu.editor.editor import _load_editor_max_tokens

        val = _load_editor_max_tokens()
        assert val == 8192

    def test_single_mode_passes_configured_max_tokens(self, tmp_path):
        """adapter.generate() receives max_tokens=8192, not 4096."""
        from biyu.editor.editor import review_chapter

        submit_resp = StubResponse(
            text="done",
            raw={"choices": [{"message": {
                "content": "done",
                "tool_calls": _make_submit_review_call([]),
            }}]},
        )
        adapter = StubAdapter([submit_resp])

        asyncio.run(review_chapter(
            chapter_num=1,
            chapter_text="测试",
            book_dir=tmp_path,
            adapter=adapter,
            max_tool_rounds=0,
        ))

        assert len(adapter.calls) == 1
        assert adapter.calls[0]["kwargs"]["max_tokens"] == 8192

    def test_multi_agent_phase1_passes_configured_max_tokens(self, tmp_path):
        """multi_agent._run_agent_phase1 reads max_completion_tokens from config."""
        from biyu.editor.multi_agent import _run_agent_phase1

        submit_resp = StubResponse(
            text="done",
            raw={"choices": [{"message": {
                "content": "done",
                "tool_calls": _make_submit_review_call([{
                    "id": "A-1", "type": "rhythm", "paragraph": 1,
                    "severity": "medium", "keyword": "k",
                    "description": "d",
                    "suggestion": {"content": "c", "rationale": "r"},
                }]),
            }}]},
        )
        adapter = StubAdapter([submit_resp])

        config = {
            "agents": {"max_tool_calls_per_agent_phase1": 3, "max_issues_per_agent": 8},
            "max_completion_tokens": 8192,
        }

        issue_list, cost = asyncio.run(_run_agent_phase1(
            agent_id="A",
            chapter_num=1,
            chapter_text="测试正文",
            book_dir=tmp_path,
            adapter=adapter,
            config=config,
            prev_chapter_tail="",
        ))

        assert len(adapter.calls) >= 1
        assert adapter.calls[0]["kwargs"]["max_tokens"] == 8192
        assert len(issue_list.issues) == 1


# ---------------------------------------------------------------------------
# Character card wiring (fixture check)
# ---------------------------------------------------------------------------

class TestCharacterCardWiring:
    """Character cards are reachable by look_up_character."""

    def test_main_characters_found(self):
        from biyu.editor.tools import look_up_character

        book_dir = Path(__file__).parents[1] / "eval_set_v0" / "test_book"
        for name in ("江叙白", "何沛", "聂守仁", "苏蔓", "老覃"):
            result = look_up_character(name, book_dir)
            assert "未找到" not in result, f"Character {name} should be found"

    def test_unknown_character_not_found(self):
        from biyu.editor.tools import look_up_character

        book_dir = Path(__file__).parents[1] / "eval_set_v0" / "test_book"
        result = look_up_character("不存在的人", book_dir)
        assert "未找到" in result


# ---------------------------------------------------------------------------
# EditorFailure enum
# ---------------------------------------------------------------------------

class TestEditorFailure:
    def test_all_failure_values(self):
        assert EditorFailure.TRUNCATION.value == "TRUNCATION"
        assert EditorFailure.BAD_ARGUMENTS.value == "BAD_ARGUMENTS"
        assert EditorFailure.UNKNOWN_TOOL.value == "UNKNOWN_TOOL"
        assert EditorFailure.TOOL_EXEC_ERROR.value == "TOOL_EXEC_ERROR"
        assert EditorFailure.RUN_FAIL.value == "RUN_FAIL"
