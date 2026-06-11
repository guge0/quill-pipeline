"""P6-0-PRE 最小验证脚本: D-47 取证 + Editor 工具调用验证。

构造一段与角色卡(陈风)冲突的文本，验证:
1. Editor 实际收到 LLM 请求体中的 tools 字段非空(D-47)
2. Editor 真的调出了工具 (tool_calls_count >= 1)
3. Editor 真的报出了预期 issue
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

import httpx

# 把 src 加到 path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from biyu.llm.registry import ModelRegistry
from biyu.editor.editor import review_chapter

BOOK_DIR = REPO_ROOT / "data" / "P1C日更验证"
OUTPUT_DIR = REPO_ROOT / "outputs" / "P6-0-PRE"

# 已知有 issue 的测试文本: 陈风在角色卡里 16 岁、修炼混沌诀、持断剑"无咎"
# 这里写成 25 岁、修炼烈火诀——Editor 需查角色卡才能发现冲突
TEST_TEXT = """陈风今年二十五岁，修炼的是烈火诀。他站在青石镇的街头，望着远处的矿脉。
手中的长剑泛着火红色的光芒。EXAMPLE_VILLAIN走过来拍了拍他的肩膀："陈兄，你的烈火诀又有突破了。"
陈风微微一笑："运气好而已。"他收起长剑，转身往矿场走去。"""

KNOWN_ISSUE_DESC = (
    "陈风在角色卡中为 16 岁、修炼混沌诀、持断剑'无咎'。"
    "测试文本写成 25 岁、修炼烈火诀、长剑泛红光——三项与角色卡冲突，"
    "Editor 需调用 look_up_character 才能发现。"
)


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 捕获 LLM 请求体 ----
    captured_bodies: list[dict] = []

    original_post = httpx.AsyncClient.post

    async def capturing_post(self, url, **kwargs):
        """Wrapper: 在发送前把 json payload 存下来。"""
        body = kwargs.get("json")
        if body is not None:
            captured_bodies.append({
                "url": str(url),
                "payload": body,
            })
        return await original_post(self, url, **kwargs)

    # ---- 运行 Editor ----
    registry = ModelRegistry()
    # Editor 用 v4_pro (pipeline 中 editor 通常用 writer 同模型)
    adapter = registry.get_adapter("v4_pro")

    print("=" * 60)
    print("P6-0-PRE 最小验证开始")
    print("=" * 60)
    print(f"测试文本长度: {len(TEST_TEXT)} 字")
    print(f"已知 issue: {KNOWN_ISSUE_DESC}")
    print(f"book_dir: {BOOK_DIR}")
    print(f"adapter model: {adapter.model_name}")
    print()

    with patch.object(httpx.AsyncClient, "post", capturing_post):
        result = await review_chapter(
            chapter_num=999,
            chapter_text=TEST_TEXT,
            book_dir=BOOK_DIR,
            adapter=adapter,
            max_tool_rounds=3,
        )

    # ---- 保存 LLM 请求体取证 ----
    llm_request_body_path = OUTPUT_DIR / "llm_request_body.json"
    request_body_data = {
        "capture_note": "D-47 取证: Editor 发给 LLM 的实际请求体",
        "capture_count": len(captured_bodies),
        "rounds": [],
    }

    for i, cap in enumerate(captured_bodies):
        round_data = {
            "round_index": i,
            "url": cap["url"],
            "payload_keys": list(cap["payload"].keys()),
            "tools_field_present": "tools" in cap["payload"],
            "tools_count": len(cap["payload"].get("tools", [])),
            "tools_names": [
                t.get("function", {}).get("name", "?")
                for t in cap["payload"].get("tools", [])
            ],
            "model": cap["payload"].get("model"),
            "temperature": cap["payload"].get("temperature"),
            "max_tokens": cap["payload"].get("max_tokens"),
            # messages 只给结构摘要,控制体积
            "messages_summary": [
                {"role": m.get("role"), "content_length": len(str(m.get("content", "")))}
                for m in cap["payload"].get("messages", [])
            ],
            # 完整 tools 字段 (D-47 核心证据)
            "tools": cap["payload"].get("tools"),
        }
        request_body_data["rounds"].append(round_data)

    with open(llm_request_body_path, "w", encoding="utf-8") as f:
        json.dump(request_body_data, f, ensure_ascii=False, indent=2)
    print(f"D-47 取证已保存: {llm_request_body_path}")

    # ---- 保存最小验证日志 ----
    val_log = {
        "test_text": TEST_TEXT,
        "known_issue": KNOWN_ISSUE_DESC,
        "editor_result": {
            "tool_calls_count": len(result.queries_used),
            "queries_used": result.queries_used,
            "issues_count": len(result.issues),
            "issues": [
                {
                    "type": issue.type,
                    "severity": issue.severity,
                    "quoted_text": issue.quoted_text,
                    "explanation": issue.explanation,
                    "fix_suggestion": issue.fix_suggestion,
                }
                for issue in result.issues
            ],
            "parse_errors": result.parse_errors,
            "confidence": result.confidence,
            "raw_response_last_2000": result.raw_response[-2000:] if result.raw_response else "",
        },
        "d47_evidence": {
            "tools_field_present": request_body_data["rounds"][0]["tools_field_present"] if request_body_data["rounds"] else False,
            "tools_count_first_round": request_body_data["rounds"][0]["tools_count"] if request_body_data["rounds"] else 0,
            "tools_names_first_round": request_body_data["rounds"][0]["tools_names"] if request_body_data["rounds"] else [],
        },
        "token_usage": "EditorResult 不携带 token 信息，详见 llm_request_body.json 中的 capture_count",
    }

    val_log_path = OUTPUT_DIR / "min_validation_log.json"
    with open(val_log_path, "w", encoding="utf-8") as f:
        json.dump(val_log, f, ensure_ascii=False, indent=2)
    print(f"验证日志已保存: {val_log_path}")

    # ---- 判定 ----
    print()
    print("=" * 60)
    print("验证判定")
    print("=" * 60)

    evidence_a = (
        request_body_data["rounds"]
        and request_body_data["rounds"][0]["tools_field_present"]
        and request_body_data["rounds"][0]["tools_count"] > 0
    )
    evidence_b_tool = len(result.queries_used) >= 1
    evidence_b_issue = len(result.issues) >= 1

    print(f"证据 A (D-47 tools 字段非空): {'PASS' if evidence_a else 'FAIL'}")
    if request_body_data["rounds"]:
        r = request_body_data["rounds"][0]
        print(f"  -> tools_field_present={r['tools_field_present']}, tools_count={r['tools_count']}, names={r['tools_names']}")
    print(f"证据 B-1 (工具实际调用 >= 1):  {'PASS' if evidence_b_tool else 'FAIL'}")
    print(f"  -> tool_calls_count={len(result.queries_used)}, queries={result.queries_used}")
    print(f"证据 B-2 (Editor 报出 issue):    {'PASS' if evidence_b_issue else 'FAIL'}")
    print(f"  -> issues_count={len(result.issues)}")
    for iss in result.issues:
        print(f"     - [{iss.get('type')}] {iss.get('quoted_text', '')[:60]}...")

    all_pass = evidence_a and evidence_b_tool and evidence_b_issue
    print()
    if all_pass:
        print(">>> 全部通过,修复有效 <<<")
    else:
        print(">>> 有证据缺失,修复不算完成 <<<")

    return all_pass


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
