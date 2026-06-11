"""P6-0-PRE-2 验证脚本: DSML 兼容修复 + D-47 双证据验证。

复用 P6-0-PRE 同一段 110 字测试文本，验证:
1. D-47 请求体: tools 字段非空
2. raw_response: 落盘（含 DSML 样本如再现）
3. B-2: Editor 报出预期 issue
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from biyu.llm.registry import ModelRegistry
from biyu.editor.editor import review_chapter

BOOK_DIR = REPO_ROOT / "data" / "P1C日更验证"
OUTPUT_DIR = REPO_ROOT / "outputs" / "P6-0-PRE-2"

TEST_TEXT = """陈风今年二十五岁，修炼的是烈火诀。他站在青石镇的街头，望着远处的矿脉。
手中的长剑泛着火红色的光芒。EXAMPLE_VILLAIN走过来拍了拍他的肩膀："陈兄，你的烈火诀又有突破了。"
陈风微微一笑："运气好而已。"他收起长剑，转身往矿场走去。"""

KNOWN_ISSUE_DESC = (
    "陈风角色卡为 16 岁、修炼混沌诀、持断剑'无咎'。"
    "测试文本写成 25 岁、修炼烈火诀、长剑泛红光——三项冲突。"
)


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    captured_bodies: list[dict] = []

    original_post = httpx.AsyncClient.post

    async def capturing_post(self, url, **kwargs):
        body = kwargs.get("json")
        if body is not None:
            captured_bodies.append({"url": str(url), "payload": body})
        return await original_post(self, url, **kwargs)

    registry = ModelRegistry()
    adapter = registry.get_adapter("v4_pro")

    print("=" * 60)
    print("P6-0-PRE-2 验证开始")
    print("=" * 60)

    with patch.object(httpx.AsyncClient, "post", capturing_post):
        result = await review_chapter(
            chapter_num=999,
            chapter_text=TEST_TEXT,
            book_dir=BOOK_DIR,
            adapter=adapter,
            max_tool_rounds=3,
        )

    # ---- D-47: 请求体取证 ----
    llm_body = {"capture_count": len(captured_bodies), "rounds": []}
    for i, cap in enumerate(captured_bodies):
        p = cap["payload"]
        llm_body["rounds"].append({
            "round_index": i,
            "tools_field_present": "tools" in p,
            "tools_count": len(p.get("tools", [])),
            "tools_names": [t["function"]["name"] for t in p.get("tools", [])],
            "model": p.get("model"),
            "messages_count": len(p.get("messages", [])),
        })
    with open(OUTPUT_DIR / "llm_request_body.json", "w", encoding="utf-8") as f:
        json.dump(llm_body, f, ensure_ascii=False, indent=2)

    # ---- raw_response 落盘 ----
    raw_resp_data = {
        "raw_response": result.raw_response,
        "parse_errors": result.parse_errors,
    }
    with open(OUTPUT_DIR / "raw_response.json", "w", encoding="utf-8") as f:
        json.dump(raw_resp_data, f, ensure_ascii=False, indent=2)

    # ---- 验证日志 ----
    val_log = {
        "test_text": TEST_TEXT,
        "known_issue": KNOWN_ISSUE_DESC,
        "editor_result": {
            "tool_calls_count": len(result.queries_used),
            "queries_used": result.queries_used,
            "issues_count": len(result.issues),
            "issues": [
                {
                    "type": iss.type,
                    "severity": iss.severity,
                    "quoted_text": iss.quoted_text,
                    "explanation": iss.explanation,
                    "fix_suggestion": iss.fix_suggestion,
                }
                for iss in result.issues
            ],
            "parse_errors": result.parse_errors,
            "confidence": result.confidence,
        },
    }
    with open(OUTPUT_DIR / "min_validation_log.json", "w", encoding="utf-8") as f:
        json.dump(val_log, f, ensure_ascii=False, indent=2)

    # ---- 判定 ----
    print()
    print("=" * 60)
    print("验证判定")
    print("=" * 60)

    evidence_a = llm_body["rounds"] and llm_body["rounds"][0]["tools_field_present"] and llm_body["rounds"][0]["tools_count"] > 0
    dsml_in_raw = "<｜｜DSML｜｜tool_calls>" in result.raw_response
    evidence_b2 = len(result.issues) >= 1

    print(f"证据 A (D-47 tools 非空):    {'PASS' if evidence_a else 'FAIL'}")
    print(f"证据 B-1 (raw_response 落盘): PASS (DSML={'YES' if dsml_in_raw else 'NO'})")
    print(f"证据 B-2 (issue 报出 >= 1):   {'PASS' if evidence_b2 else 'FAIL'} (count={len(result.issues)})")

    if result.issues:
        for iss in result.issues:
            print(f"  - [{iss.type}/{iss.severity}] {iss.quoted_text[:60]}...")

    print(f"tool_calls_count: {len(result.queries_used)}")
    for q in result.queries_used:
        print(f"  -> {q}")

    all_pass = evidence_a and evidence_b2
    print()
    print(f">>> {'全部通过' if all_pass else '有证据缺失'} <<<")
    return all_pass


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
