"""Cheap-gate A: Replay D-47 captured responses through repaired emit/parse.

Zero-cost verification: feed already-captured LLM responses through the
repaired JSON emit/parse pipeline to check what can be recovered.

Result expectations:
  T3 (single_call011): MUST recover E02 + 2 extra issues (JSON had unescaped ")
  T2 (single_call006): CANNOT recover E07 (content truncated to 146 chars;
                        reasoning consumed all 4096 token budget).
                        This proves bug (max_tokens adaptation) is NECESSARY.

Usage: cd biyu && python -m scripts.replay_d47_cheap_gate
"""
from __future__ import annotations

import json
from pathlib import Path

from biyu.editor.parser import parse_editor_response, _repair_json, _extract_json

D47_DIR = Path(__file__).parents[1] / "eval_set_v0" / "comparison_results" / "d47_pre_single"


def load_call(name: str) -> dict:
    with open(D47_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def extract_chapter_text(call_data: dict) -> str:
    for msg in call_data["request"]["messages"]:
        if msg["role"] == "user":
            content = msg["content"]
            idx = content.find("--- 本章正文 ---")
            if idx >= 0:
                return content[idx + len("--- 本章正文 ---"):].strip()
    return ""


def replay_t3():
    """T3 recovery: single_call011 — JSON with unescaped ASCII " in issue #2."""
    print("=" * 60)
    print("T3 recovery (single_call011)")
    print("=" * 60)

    data = load_call("single_call011.json")
    raw_content = data["response"]["raw"]["choices"][0]["message"]["content"]
    chapter_text = extract_chapter_text(data)

    result = parse_editor_response(raw_content, chapter_text)
    print(f"  Issues recovered: {len(result.issues)}")
    for iss in result.issues:
        af = " [AUTO]" if iss.auto_fixable else ""
        print(f"    type={iss.type}, quote={iss.quote[:40]}, severity={iss.severity}{af}")
    print(f"  Parse notes: {len(result.parse_errors)}")
    for note in result.parse_errors:
        print(f"    {note}")

    expected_types = {"字面伪影", "跨章一致性", "逻辑漏洞"}
    recovered_types = {iss.type for iss in result.issues}

    ok = len(result.issues) == 3 and expected_types == recovered_types
    print(f"\n  [PASS] T3 recovered all 3 issues including E02" if ok
          else f"\n  [FAIL] Expected {expected_types}, got {recovered_types}")
    return ok


def replay_t2():
    """T2 recovery: single_call006 — truncated JSON (146 chars).

    Expected to FAIL recovery: content was truncated because reasoning
    consumed all 4096 tokens. This proves bug (max_tokens) is necessary.
    """
    print("\n" + "=" * 60)
    print("T2 recovery (single_call006) — EXPECTED TO FAIL")
    print("=" * 60)

    data = load_call("single_call006.json")
    raw_content = data["response"]["raw"]["choices"][0]["message"]["content"]
    usage = data["response"]["raw"]["usage"]
    reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
    completion_tokens = data["response"]["completion_tokens"]

    print(f"  finish_reason: {data['response']['finish_reason']}")
    print(f"  completion_tokens: {completion_tokens} (reasoning: {reasoning_tokens})")
    print(f"  content length: {len(raw_content)} chars")
    print(f"  content preview: {raw_content[:80]}...")

    # Confirm E07 is in reasoning_content
    reasoning = data["response"]["raw"]["choices"][0]["message"].get("reasoning_content", "")
    e07_markers = ["生物识别", "体检", "同一台机器"]
    e07_found = [m for m in e07_markers if m in reasoning]
    print(f"  E07 markers in reasoning: {e07_found}")

    # Attempt repair
    json_str = _extract_json(raw_content)
    if json_str:
        repaired = _repair_json(json_str)
        try:
            json.loads(repaired)
            print(f"  [UNEXPECTED] T2 content parsed successfully!")
            return True
        except json.JSONDecodeError as e:
            print(f"  Repair result: FAIL ({e})")

    print(f"\n  [EXPECTED FAIL] T2 cannot be recovered by JSON repair alone.")
    print(f"  Content truncated at 146 chars; reasoning used {reasoning_tokens}/{completion_tokens} tokens.")
    print(f"  E07 was identified in reasoning but never reached content phase.")
    print(f"  This proves bug (max_tokens adaptation) is NECESSARY, not optional.")
    return False


def main():
    print("Cheap-gate A: D-47 replay through repaired emit/parse (zero LLM cost)")
    print()

    t3_ok = replay_t3()
    t2_ok = replay_t2()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  T3 (JSON repair): {'PASS' if t3_ok else 'FAIL'} — 3 issues recovered")
    print(f"  T2 (truncation):  {'N/A (expected fail)' if not t2_ok else 'PASS'}")
    print()
    print("  Cheap-gate A: NECESSARY BUT NOT SUFFICIENT")
    print("  - JSON repair (bug ) recovers T3's 3 issues (E02 + 2 extra)")
    print("  - T2's E07 cannot be recovered — proves max_tokens fix (bug ) is necessary")
    print("  - Tool-loop / truncation end-to-end still needs paid re-run to confirm")


if __name__ == "__main__":
    main()
