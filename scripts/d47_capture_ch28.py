"""D-47 dynamic evidence capture for CH28: re-run Editor on CH28 text only.

This script captures the actual LLM request body during an Editor call,
proving that `tools` field is present and non-empty.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

BOOK_DIR = REPO_ROOT / "data" / "张今空_T-P3-A验证"
OUTPUT_DIR = REPO_ROOT / "outputs" / "P6-0"

# Original function references
_original_post = httpx.AsyncClient.post


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from biyu.llm.registry import ModelRegistry
    from biyu.editor.editor import review_chapter

    registry = ModelRegistry()
    adapter = registry.get_adapter("v4_pro")

    # Read CH28 text
    ch28_path = BOOK_DIR / "chapters" / "ch28.md"
    if not ch28_path.exists():
        print(f"ERROR: {ch28_path} not found")
        return False
    ch28_text = ch28_path.read_text(encoding="utf-8")

    # Read prev chapter tail
    ch27_path = BOOK_DIR / "chapters" / "ch27.md"
    prev_tail = ""
    if ch27_path.exists():
        prev_text = ch27_path.read_text(encoding="utf-8")
        prev_tail = prev_text[-500:]

    print(f"CH28 text: {len(ch28_text)} chars")
    print(f"Prev tail: {len(prev_tail)} chars")
    print(f"Adapter: {adapter.model_name}")
    print()

    # Capture LLM request bodies
    captured_bodies = []

    async def capturing_post(self, url, **kwargs):
        body = kwargs.get("json")
        if body is not None:
            captured_bodies.append({
                "url": str(url),
                "payload": body,
            })
        return await _original_post(self, url, **kwargs)

    print("Running Editor with request capture...")
    t0 = time.time()

    with patch.object(httpx.AsyncClient, "post", capturing_post):
        result = await review_chapter(
            chapter_num=28,
            chapter_text=ch28_text,
            book_dir=BOOK_DIR,
            adapter=adapter,
            prev_chapter_tail=prev_tail,
            max_tool_rounds=3,
        )

    elapsed = time.time() - t0
    print(f"Editor completed in {elapsed:.1f}s")
    print(f"Captured {len(captured_bodies)} API calls")
    print(f"Tool calls used: {len(result.queries_used)}")
    print(f"Issues found: {len(result.issues)}")
    for q in result.queries_used:
        print(f"  - {q}")
    print()

    # Build D-47 evidence
    first_editor_call = None
    for cap in captured_bodies:
        body = cap["payload"]
        if "tools" in body and body["tools"]:
            first_editor_call = cap
            break

    if not first_editor_call and captured_bodies:
        first_editor_call = captured_bodies[0]

    if not first_editor_call:
        print("ERROR: No API calls captured!")
        return False

    body = first_editor_call["payload"]
    evidence = {
        "capture_note": "D-47 取证: CH28 Editor 首次调用发给 LLM 的实际请求体",
        "chapter": "ch28",
        "capture_method": "Re-run Editor on CH28 generated text with httpx post monkey-patch",
        "total_api_calls": len(captured_bodies),
        "tools_field_present": "tools" in body,
        "tools_count": len(body.get("tools", [])),
        "tools_names": [
            t.get("function", {}).get("name", "?")
            for t in body.get("tools", [])
        ],
        "model": body.get("model"),
        "temperature": body.get("temperature"),
        "max_tokens": body.get("max_tokens"),
        "messages_summary": [
            {"role": m.get("role"), "content_length": len(str(m.get("content", "")))}
            for m in body.get("messages", [])
        ],
        "tools": body.get("tools"),
    }

    path = OUTPUT_DIR / "llm_request_body_ch28_first_call.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"D-47 evidence saved: {path}")
    print()

    # Print summary
    tools_ok = evidence["tools_field_present"] and evidence["tools_count"] > 0
    print(f"tools 字段存在: {evidence['tools_field_present']}")
    print(f"tools 数量: {evidence['tools_count']}")
    print(f"tools 名称: {evidence['tools_names']}")
    print(f"D-47 判定: {'通过' if tools_ok else '失败'}")

    return tools_ok


if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
