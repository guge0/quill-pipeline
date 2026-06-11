"""P6-13-D follow-up: replay all D re-run captures through fixed parser.

After cheap-gate B revealed the _repair_json 20-iteration limit was
insufficient (real LLM outputs have 25+ unescaped ASCII quotes), we bumped
the cap to 200 and added a regression test. This script replays every
captured Phase1 / single response through the *fixed* parser to compute
the "what would have been" issue counts.

What this CANNOT do:
  - Phase 2 of multi mode was FED the wrong v1 (empty) when Phase 1
    extraction failed. Replaying Phase 1 gives us correct v1, but Phase 2
    responses in the captures are based on the wrong input. Recovering
    multi-mode v2 / merge requires a paid Phase 2 re-run.

Usage: cd biyu && python -m scripts.replay_d47_fixed_parser
"""
from __future__ import annotations

import json
from pathlib import Path

from biyu.editor.parser import parse_editor_response, _extract_json, _repair_json
from biyu.editor.multi_agent import _parse_agent_response

BIYU_ROOT = Path(__file__).parents[1]
D47_SINGLE = BIYU_ROOT / "eval_set_v0" / "comparison_results" / "d47_single"
D47_MULTI = BIYU_ROOT / "eval_set_v0" / "comparison_results" / "d47_multi"
OUT_PATH = BIYU_ROOT / "eval_set_v0" / "comparison_results" / "d47_replay_summary.json"


def load_call(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_chapter_num(call: dict) -> int | None:
    """Detect chapter from messages.

    For Phase 1: user message starts with '请审阅第 N 章正文'.
    For Phase 2: user message contains v1 JSON with '"chapter": N'.
    """
    import re
    for msg in call.get("request", {}).get("messages", []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        # Phase 2 pattern: "chapter": N (in v1 JSON)
        m = re.search(r'"chapter"\s*:\s*(\d+)', content)
        if m:
            return int(m.group(1))
        # Phase 1 pattern: '请审阅第 N 章正文'
        m = re.search(r"请审阅第\s*(\d+)\s*章", content)
        if m:
            return int(m.group(1))
    return None


def extract_agent_id(call: dict) -> str | None:
    """Detect agent (A/B/C) from system message; 'single' for single mode."""
    for msg in call.get("request", {}).get("messages", []):
        if msg.get("role") != "system":
            continue
        content = msg.get("content", "")
        if "Editor-A" in content:
            return "A"
        if "Editor-B" in content:
            return "B"
        if "Editor-C" in content:
            return "C"
        if "责任编辑" in content:
            return "single"
    return None


def extract_chapter_text(call: dict) -> str:
    """Extract chapter text from user message.

    Single mode: text follows '请审阅第 N 章正文：' header (no marker).
    Multi mode: text follows '--- 本章正文 ---' marker.
    """
    import re
    for msg in call.get("request", {}).get("messages", []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        # Multi mode marker first
        idx = content.find("--- 本章正文 ---")
        if idx >= 0:
            return content[idx + len("--- 本章正文 ---"):].strip()
        # Single mode: strip leading '请审阅第 N 章正文：\n\n'
        m = re.match(r"^请审阅第\s*\d+\s*章正文：\s*\n\n", content)
        if m:
            # If there's a '--- 上一章末 500 字 ---' block, take only the part after
            rest = content[m.end():]
            idx2 = rest.find("--- 上一章末")
            if idx2 >= 0:
                # The chapter text is BEFORE this block? Actually for ch2/3, the structure is
                # '请审阅第 N 章正文：\n\n--- 上一章末 500 字 ---\n\n<tail>\n\n<chapter_body>'
                # So we strip the marker block.
                # Find the end of the tail block.
                end_of_tail = rest.find("\n\n", idx2 + 30)
                if end_of_tail >= 0:
                    return rest[end_of_tail + 2:].strip()
            return rest.strip()
    return ""


def content_of(call: dict) -> str:
    return call.get("response", {}).get("raw", {}).get("choices", [{}])[0].get("message", {}).get("content", "")


# ── Single mode replay ─────────────────────────────────────────────

def replay_single() -> dict:
    """For each chapter, take the LAST call's content (the JSON emit) and parse."""
    # Group calls by chapter using 第N章 marker in user message
    by_chapter: dict[int, list[Path]] = {}
    for path in sorted(D47_SINGLE.glob("single_call*.json")):
        call = load_call(path)
        ch = extract_chapter_num(call)
        if ch is None:
            continue
        by_chapter.setdefault(ch, []).append(path)

    out = {}
    for ch, paths in sorted(by_chapter.items()):
        # Take the LAST call (final emit)
        last_path = paths[-1]
        call = load_call(last_path)
        content = content_of(call)
        chapter_text = extract_chapter_text(call)

        result = parse_editor_response(content, chapter_text)
        out[ch] = {
            "calls_in_chapter": len(paths),
            "final_call": last_path.name,
            "content_chars": len(content),
            "issues_recovered": len(result.issues),
            "issues": [
                {
                    "type": iss.type,
                    "line": iss.line,
                    "severity": iss.severity,
                    "quote_preview": iss.quote[:60],
                }
                for iss in result.issues
            ],
            "parse_errors": list(result.parse_errors),
        }
        print(f"  single ch{ch}: {len(result.issues)} issues recovered (final emit: {last_path.name})")
    return out


# ── Multi mode Phase1 replay ───────────────────────────────────────

def replay_multi_phase1() -> dict:
    """Replay every multi capture. For each chapter × agent, identify the
    LAST Phase1 call (final emit) and the LAST Phase2 call (reflection emit)."""
    # Phase is detected by system prompt content:
    #   Phase 2 prompt contains "第二轮审稿反思"
    #   Phase 1 prompt is the initial editor prompt (no reflection marker)
    # has_tools varies: Phase 1 initial has tools, Phase 1 fallback has NO tools.
    classified: dict[tuple[int, str, int], list[tuple[str, str, dict]]] = {}

    for path in sorted(D47_MULTI.glob("multi_call*.json")):
        call = load_call(path)
        ch = extract_chapter_num(call)
        aid = extract_agent_id(call)
        if ch is None or aid is None or aid == "single":
            continue
        # Detect Phase 2 by system prompt
        sys_text = ""
        for msg in call.get("request", {}).get("messages", []):
            if msg.get("role") == "system":
                sys_text = msg.get("content", "")
                break
        is_phase2 = "第二轮审稿反思" in sys_text or "第二轮反思" in sys_text
        phase = 2 if is_phase2 else 1
        content = content_of(call)
        key = (ch, aid, phase)
        classified.setdefault(key, []).append((path.name, content, call))

    out = {}
    all_chapters = sorted({k[0] for k in classified})
    for ch in all_chapters:
        # Phase 1 by agent
        p1_by_agent = {}
        for aid in ("A", "B", "C"):
            entries = classified.get((ch, aid, 1), [])
            if not entries:
                continue
            # Last entry is final emit
            name, content, _ = entries[-1]
            issue_list = _parse_agent_response(content, aid, 1, ch, 8)
            p1_by_agent[aid] = {
                "call": name,
                "calls_in_phase": len(entries),
                "content_chars": len(content),
                "issues_parsed": len(issue_list.issues),
                "issues": [
                    {
                        "id": iss.id,
                        "type": iss.type,
                        "paragraph": iss.paragraph,
                        "severity": iss.severity,
                        "keyword_preview": iss.keyword[:60] if iss.keyword else "",
                    }
                    for iss in issue_list.issues
                ],
            }

        # Phase 2 by agent
        p2_by_agent = {}
        empty_v1_impact = []
        for aid in ("A", "B", "C"):
            entries = classified.get((ch, aid, 2), [])
            if not entries:
                continue
            name, content, raw_call = entries[-1]
            json_str = _extract_json(content)
            p2_issues_count = None
            if json_str:
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    repaired = _repair_json(json_str)
                    try:
                        data = json.loads(repaired)
                    except json.JSONDecodeError:
                        data = None
                if isinstance(data, dict):
                    p2_issues_count = len(data.get("issues", []))

            # Check reasoning for "v1 empty" mention
            reasoning = raw_call.get("response", {}).get("raw", {}).get("choices", [{}])[0].get("message", {}).get("reasoning_content", "") or ""
            mentions_empty_v1 = any(
                marker in reasoning
                for marker in ["v1是空", "v1 为空", "v1意见是空", "v1 是空", "没有 issue", "没有提出", "v1 empty"]
            ) or ("v1" in reasoning and "空" in reasoning)

            p2_by_agent[aid] = {
                "call": name,
                "calls_in_phase": len(entries),
                "content_chars": len(content),
                "issues_parsed": p2_issues_count if p2_issues_count is not None else -1,
                "reasoning_mentions_empty_v1": mentions_empty_v1,
            }
            # If Phase 1 had issues but Phase 2 produced 0 → suspect v1 extraction bug
            p1_count = p1_by_agent.get(aid, {}).get("issues_parsed", 0)
            if p1_count > 0 and p2_issues_count == 0:
                empty_v1_impact.append({
                    "agent": aid,
                    "phase1_issues": p1_count,
                    "phase2_issues": 0,
                    "phase2_call": name,
                    "diagnosis": "Phase1 had issues but Phase2 emitted 0 — Phase2 was fed empty v1 due to old parser cap",
                })

        out[ch] = {
            "phase1_by_agent": p1_by_agent,
            "phase2_by_agent": p2_by_agent,
            "phase2_empty_v1_impact": empty_v1_impact,
        }
        p1_counts = {a: r["issues_parsed"] for a, r in p1_by_agent.items()}
        p2_counts = {a: r["issues_parsed"] for a, r in p2_by_agent.items()}
        print(f"  multi ch{ch}: P1={p1_counts}, P2={p2_counts}, impact={[e['agent'] for e in empty_v1_impact]}")

    return out


def main():
    print("=" * 60)
    print("D re-run replay through fixed parser (zero LLM cost)")
    print("=" * 60)
    print()
    print("--- Single mode ---")
    single = replay_single()
    print()
    print("--- Multi mode Phase1 ---")
    multi = replay_multi_phase1()

    summary = {
        "single": single,
        "multi_phase1": multi,
        "note": (
            "Phase 2 of multi mode was fed the wrong v1 (empty) when Phase 1 "
            "extraction failed pre-fix. Replaying Phase 1 gives correct v1, but "
            "Phase 2 captures are based on wrong input. Recovering multi-mode "
            "v2 / merge results requires a paid Phase 2 re-run."
        ),
    }
    OUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"Summary saved to: {OUT_PATH}")


if __name__ == "__main__":
    main()
