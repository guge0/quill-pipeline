"""P6-1A Step 3: Run new Architect for CH28, capture request body.

Outputs:
  outputs/P6-1A/ch28_creative_outline.md        — Architect 细纲产出
  outputs/P6-1A/llm_request_body_architect_first_call.json — D-47 取证
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

BOOK_DIR = REPO_ROOT / "data" / "EXAMPLE_PROTAGONIST_T-P3-A验证"
OUTPUT_DIR = REPO_ROOT / "outputs" / "P6-1A"

_original_post = httpx.AsyncClient.post


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Load data ----
    from biyu.worldbook import load_worldbook, build_worldbook_prompt
    from biyu.config import load_characters_yaml
    from biyu.truth_files import read_all_truth_files
    from biyu.prompts.v3_opening import build_planning_prompt

    # sub-md (outline)
    outline_path = REPO_ROOT / "data" / "sub_md" / "ch28.md"
    outline = outline_path.read_text(encoding="utf-8")
    print(f"sub-md: {len(outline)} chars")

    # worldbook
    wb = load_worldbook(BOOK_DIR)
    worldbook_prompt = build_worldbook_prompt(wb)
    print(f"worldbook: {len(worldbook_prompt)} chars")

    # characters
    characters = load_characters_yaml(BOOK_DIR)
    print(f"characters: {len(characters)} loaded")

    # truth_files
    truth_files_block = ""
    truth_data = read_all_truth_files(BOOK_DIR)
    for name, content in truth_data.items():
        if content.strip():
            truth_files_block += f"=== {name} ===\n{content}\n\n"
    print(f"truth_files: {len(truth_files_block)} chars")

    # ---- Build prompt ----
    planning_content = build_planning_prompt(
        outline=outline,
        characters=characters,
        truth_files_block=truth_files_block,
        worldbook_prompt=worldbook_prompt,
        chapter_num=28,
    )
    print(f"planning prompt: {len(planning_content)} chars")
    print()

    # ---- LLM call with capture ----
    from biyu.llm.registry import ModelRegistry

    registry = ModelRegistry()
    # Use planner model (r1 = deepseek-reasoner)
    planner_alias = registry.get_pipeline_config().get("planner", "r1")
    adapter = registry.get_adapter_for_stage("planner")
    print(f"Adapter: {adapter.model_name} (alias={planner_alias})")

    captured_bodies = []

    async def capturing_post(self, url, **kwargs):
        body = kwargs.get("json")
        if body is not None:
            captured_bodies.append({
                "url": str(url),
                "payload": body,
            })
        return await _original_post(self, url, **kwargs)

    messages = [{"role": "user", "content": planning_content}]

    print("Calling Architect LLM...")
    t0 = time.time()

    with patch.object(httpx.AsyncClient, "post", capturing_post):
        from biyu.pipeline import _call_with_retry
        resp = await _call_with_retry(adapter, messages)

    elapsed = time.time() - t0
    print(f"Architect completed in {elapsed:.1f}s, cost=¥{resp.cost:.4f}")
    print()

    planning_text = resp.text
    print(f"Output length: {len(planning_text)} chars")
    print()

    # ---- Keyword scan ----
    banned = ["风格", "文风", "调性", "笔触", "文笔风格", "风格指引", "风格强化", "声纹", "指纹"]
    hits = [(w, planning_text.index(w)) for w in banned if w in planning_text]
    if hits:
        print("!!! KEYWORD SCAN HITS !!!")
        for w, pos in hits:
            ctx_start = max(0, pos - 20)
            ctx_end = min(len(planning_text), pos + 20)
            print(f"  '{w}' at pos {pos}: ...{planning_text[ctx_start:ctx_end]}...")
    else:
        print("Keyword scan: PASSED (no banned words)")
    print()

    # ---- Save outline ----
    outline_out = OUTPUT_DIR / "ch28_creative_outline.md"
    outline_out.write_text(planning_text, encoding="utf-8")
    print(f"Outline saved: {outline_out}")

    # ---- Save D-47 evidence ----
    if not captured_bodies:
        print("ERROR: No API calls captured!")
        return False

    body = captured_bodies[0]["payload"]

    # Check characters injection in messages
    messages_have_chars = False
    for m in body.get("messages", []):
        content = str(m.get("content", ""))
        if "在场角色" in content:
            messages_have_chars = True
            break

    evidence = {
        "capture_note": "D-47 取证: P6-1A Architect 首次调用发给 LLM 的实际请求体",
        "chapter": "ch28",
        "stage": "architect",
        "capture_method": "httpx post monkey-patch",
        "total_api_calls": len(captured_bodies),
        "model": body.get("model"),
        "temperature": body.get("temperature"),
        "max_tokens": body.get("max_tokens"),
        "characters_injected_in_messages": messages_have_chars,
        "messages_summary": [
            {"role": m.get("role"), "content_length": len(str(m.get("content", "")))}
            for m in body.get("messages", [])
        ],
        "messages": body.get("messages"),
    }

    evidence_path = OUTPUT_DIR / "llm_request_body_architect_first_call.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"D-47 evidence saved: {evidence_path}")
    print(f"  characters injected: {messages_have_chars}")
    print(f"  messages count: {len(body.get('messages', []))}")
    print()

    # ---- Print outline for review ----
    print("=" * 60)
    print("ARCHITECT OUTPUT (full text):")
    print("=" * 60)
    print(planning_text)
    print("=" * 60)

    return True


if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # Force UTF-8 output on Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
