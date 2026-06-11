"""Editor 主逻辑 — 调用 LLM 审稿 + function calling 工具查询。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from .parser import EditorResult, parse_editor_response, _extract_json
from .prompts import EDITOR_SYSTEM_PROMPT, build_editor_user_prompt
from .tools import (
    TOOL_DEFINITIONS,
    SUBMIT_REVIEW_SINGLE,
    EditorFailure,
    execute_tool,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config: max_completion_tokens（reasoning + content 共享预算）
# ---------------------------------------------------------------------------

def _load_editor_max_tokens() -> int:
    """从 config/editor.yaml 读取 max_completion_tokens，默认 8192。"""
    config_path = Path(__file__).parents[2] / "config" / "editor.yaml"
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("max_completion_tokens", 8192)
    except Exception:
        return 8192


def _make_failure_result(failure: EditorFailure, chapter_text: str,
                         total_cost: float = 0.0,
                         queries_used: list[str] | None = None) -> EditorResult:
    """构造一个带 failure 标记的 EditorResult。"""
    result = EditorResult(raw_response="", parse_errors=[f"failure:{failure.value}"])
    result.queries_used = queries_used or []
    result.cost = total_cost
    return result


def _parse_submit_review_call(submit_call: dict, chapter_text: str,
                               total_cost: float,
                               queries_used: list[str]) -> EditorResult:
    """解析 submit_review 工具调用的 arguments，返回 EditorResult。

    如果 arguments JSON 解析失败，返回 RUN_FAIL failure result。
    """
    args_str = submit_call["function"]["arguments"]
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError:
        logger.error("submit_review arguments JSON parse failed: %s", args_str[:200])
        return _make_failure_result(EditorFailure.BAD_ARGUMENTS, chapter_text, total_cost, queries_used)

    # 将 submit_review 的 issues + confidence 包装成 parse_editor_response 期望的 JSON
    data = {
        "issues": args.get("issues", []),
        "queries_used": queries_used,
        "confidence": args.get("confidence", "medium"),
    }
    fake_json = json.dumps(data, ensure_ascii=False)
    result = parse_editor_response(fake_json, chapter_text)
    result.queries_used = queries_used
    result.cost = total_cost
    return result


async def review_chapter(
    chapter_num: int,
    chapter_text: str,
    book_dir: Path,
    adapter,  # LLMAdapter
    *,
    characters_summary: str = "",
    prev_chapter_tail: str = "",
    max_tool_rounds: int = 3,
) -> EditorResult:
    """Editor 审稿：调用 LLM + function calling 工具查询。

    Args:
        chapter_num: 章节号。
        chapter_text: 章节正文。
        book_dir: 书目录。
        adapter: LLMAdapter 实例（DeepSeek V4-Pro）。
        characters_summary: 角色速查文本。
        prev_chapter_tail: 上一章末 500 字。
        max_tool_rounds: 最大工具调用轮数。

    Returns:
        EditorResult
    """
    user_prompt = build_editor_user_prompt(
        chapter_num=chapter_num,
        chapter_text=chapter_text,
        characters_summary=characters_summary,
        prev_chapter_tail=prev_chapter_tail,
    )

    messages = [
        {"role": "system", "content": EDITOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # 多轮对话：LLM 调用 → 检查 tool_calls → 执行工具 → 继续对话
    queries_used: list[str] = []
    total_cost = 0.0
    max_completion_tokens = _load_editor_max_tokens()

    for round_num in range(max_tool_rounds + 1):
        # 前 N 轮给 lookup tools + submit_review；收尾轮只给 submit_review
        if round_num < max_tool_rounds:
            payload_tools = TOOL_DEFINITIONS + [SUBMIT_REVIEW_SINGLE]
        else:
            payload_tools = [SUBMIT_REVIEW_SINGLE]

        resp = await adapter.generate(
            messages,
            temperature=0.1,
            max_tokens=max_completion_tokens,
            tools=payload_tools,
        )
        total_cost += resp.cost
        resp_text = resp.text

        # 检查 finish_reason=length → TRUNCATION
        if getattr(resp, "finish_reason", None) == "length":
            logger.warning("Response truncated (finish_reason=length)")
            return _make_failure_result(EditorFailure.TRUNCATION, chapter_text, total_cost, queries_used)

        # 从标准 OpenAI 格式提取 tool_calls
        tool_calls = []
        if resp.raw is not None:
            choices = resp.raw.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                tool_calls = message.get("tool_calls") or []

        # 检查是否含 submit_review 调用
        submit_call = next(
            (tc for tc in tool_calls if tc["function"]["name"] == "submit_review"),
            None,
        )
        if submit_call:
            return _parse_submit_review_call(submit_call, chapter_text, total_cost, queries_used)

        # 非 submit_review 的工具调用，照常执行
        if not tool_calls:
            # 无工具调用也无 submit_review → 收尾轮是 RUN_FAIL，非收尾轮继续
            if round_num == max_tool_rounds:
                return _make_failure_result(EditorFailure.RUN_FAIL, chapter_text, total_cost, queries_used)
            # 非收尾轮但无工具调用：LLM 给了纯文本，视为提前结束但没调 submit_review
            return _make_failure_result(EditorFailure.RUN_FAIL, chapter_text, total_cost, queries_used)

        # 执行 lookup 工具调用
        assistant_msg = {"role": "assistant", "content": resp_text, "tool_calls": tool_calls}
        if resp.reasoning_content:
            assistant_msg["reasoning_content"] = resp.reasoning_content
        messages.append(assistant_msg)

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            tc_id = tc.get("id", "")
            try:
                tool_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            tool_result = execute_tool(tool_name, tool_args, book_dir)
            queries_used.append(f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": tool_name,
                "content": tool_result,
            })

    # 循环结束但未返回 → 收尾轮未调 submit_review
    return _make_failure_result(EditorFailure.RUN_FAIL, chapter_text, total_cost, queries_used)
