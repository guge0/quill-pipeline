"""P6-13-D follow-up: targeted Phase 2 re-run for stale combos.

Re-runs Phase 2 for ch2-AgentA and ch3-AgentB only — the two combos that
were fed empty v1 during the original D re-run due to the _repair_json
20-iteration cap bug.

Uses the corrected Phase 1 data (re-parsed with 200-iter cap) as input.

Budget: ≤¥0.05 (2 calls × ~¥0.01 each = ~¥0.02).
Stops if estimate >¥0.10.

Usage: cd biyu && python -m scripts.run_targeted_phase2
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root on path
BIYU_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(BIYU_ROOT / "src"))

D47_MULTI = BIYU_ROOT / "eval_set_v0" / "comparison_results" / "d47_multi"
OUTPUT_DIR = BIYU_ROOT / "eval_set_v0" / "comparison_results"
TARGETED_DIR = OUTPUT_DIR / "d47_targeted_phase2"


def load_call(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def content_of(call: dict) -> str:
    return call.get("response", {}).get("raw", {}).get("choices", [{}])[0].get("message", {}).get("content", "")


def extract_chapter(call: dict) -> int | None:
    for msg in call.get("request", {}).get("messages", []):
        if msg.get("role") == "user":
            m = re.search(r'"chapter"\s*:\s*(\d+)', msg["content"])
            if m:
                return int(m.group(1))
            m = re.search(r"请审阅第\s*(\d+)\s*章", msg["content"])
            if m:
                return int(m.group(1))
    return None


def extract_agent(call: dict) -> str | None:
    for msg in call.get("request", {}).get("messages", []):
        if msg.get("role") == "system":
            c = msg["content"]
            if "Editor-A" in c:
                return "A"
            if "Editor-B" in c:
                return "B"
            if "Editor-C" in c:
                return "C"
    return None


def is_phase2(call: dict) -> bool:
    for msg in call.get("request", {}).get("messages", []):
        if msg.get("role") == "system":
            return "第二轮审稿反思" in msg["content"] or "第二轮反思" in msg["content"]
    return False


def build_v1_from_capture(ch: int, agent: str) -> Any:
    """Build AgentIssueList from Phase 1 final emit, using FIXED parser."""
    from biyu.editor.multi_agent import _parse_agent_response

    # Find Phase 1 final emit for this (ch, agent)
    entries = []
    for path in sorted(D47_MULTI.glob("multi_call*.json")):
        call = load_call(path)
        c = extract_chapter(call)
        a = extract_agent(call)
        if c != ch or a != agent:
            continue
        if is_phase2(call):
            continue
        entries.append((path, content_of(call)))

    if not entries:
        raise ValueError(f"No Phase 1 entries for ch{ch} agent{agent}")

    # Last Phase 1 call is the final emit
    _, final_content = entries[-1]
    result = _parse_agent_response(final_content, agent, 1, ch, 8)
    print(f"  v1 for ch{ch}-{agent}: {len(result.issues)} issues (from {entries[-1][0].name})")
    return result


def build_v2_from_capture(ch: int, agent: str) -> Any:
    """Build AgentIssueList from existing Phase 2 capture (for non-stale agents)."""
    from biyu.editor.multi_agent import _parse_agent_response

    entries = []
    for path in sorted(D47_MULTI.glob("multi_call*.json")):
        call = load_call(path)
        c = extract_chapter(call)
        a = extract_agent(call)
        if c != ch or a != agent:
            continue
        if not is_phase2(call):
            continue
        entries.append((path, content_of(call)))

    if not entries:
        raise ValueError(f"No Phase 2 entries for ch{ch} agent{agent}")

    _, final_content = entries[-1]
    result = _parse_agent_response(final_content, agent, 2, ch, 8)
    print(f"  existing v2 for ch{ch}-{agent}: {len(result.issues)} issues")
    return result


# ── Logging adapter (captures request/response) ───────────────

class LoggingWrapper:
    """Wraps adapter to capture targeted re-run calls."""

    def __init__(self, real_adapter, log_dir: Path):
        self._inner = real_adapter
        self._log_dir = log_dir
        self._call_count = 0
        self._total_cost = 0.0
        self.call_log: list[dict] = []

    async def generate(self, messages, **kwargs):
        self._call_count += 1
        resp = await self._inner.generate(messages, **kwargs)

        # Capture
        has_tools = "tools" in kwargs
        self._log_dir.mkdir(parents=True, exist_ok=True)
        capture = {
            "request": {
                "call_id": f"targeted_{self._call_count:03d}",
                "label": "targeted_phase2",
                "messages_count": len(messages),
                "temperature": kwargs.get("temperature"),
                "max_tokens": kwargs.get("max_tokens"),
                "has_tools": has_tools,
                "kwargs_keys": list(kwargs.keys()),
                "messages": messages,
            },
            "response": {
                "raw": resp.raw,
                "completion_tokens": resp.completion_tokens,
                "prompt_tokens": resp.prompt_tokens,
                "finish_reason": resp.finish_reason,
                "cost": resp.cost,
                "text": resp.text,
            },
        }
        name = f"targeted_call{self._call_count:03d}.json"
        (self._log_dir / name).write_text(
            json.dumps(capture, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._total_cost += resp.cost
        self.call_log.append({"name": name, "cost": resp.cost})
        print(f"    call {name}: {resp.completion_tokens} tokens, ¥{resp.cost:.4f}")
        return resp

    def __getattr__(self, name):
        return getattr(self._inner, name)


async def main():
    from biyu.editor.multi_agent import (
        _run_agent_phase2,
        merge_issues,
        load_editor_config,
    )
    from biyu.llm import ModelRegistry

    print("=" * 60)
    print("P6-13-D: Targeted Phase 2 re-run (ch2-A, ch3-B)")
    print("=" * 60)

    # Build corrected v1 lists for affected chapters
    print("\n--- Building corrected v1 lists ---")
    # ch2: AgentA stale, B and C ok
    ch2_v1 = {}
    ch2_v1["A"] = build_v1_from_capture(2, "A")  # replay-corrected
    ch2_v1["B"] = build_v1_from_capture(2, "B")  # was already ok
    ch2_v1["C"] = build_v1_from_capture(2, "C")  # was already ok

    # ch3: AgentB stale, A and C ok
    ch3_v1 = {}
    ch3_v1["A"] = build_v1_from_capture(3, "A")  # was already ok
    ch3_v1["B"] = build_v1_from_capture(3, "B")  # replay-corrected
    ch3_v1["C"] = build_v1_from_capture(3, "C")  # was already ok

    # Cost estimate
    # Previous Phase 2 avg: ¥0.5280/40 = ¥0.0132 per call (mixed P1/P2)
    # Phase 2 specifically: ~¥0.01 per call
    est_cost = 2 * 0.015  # conservative estimate
    print(f"\n  Cost estimate: 2 calls × ¥0.015 = ¥{est_cost:.4f}")
    if est_cost > 0.10:
        print("  ⚠ OVER BUDGET (¥0.10 cap) — STOP")
        return
    print("  Within budget (≤¥0.05)")

    # Create adapter
    registry = ModelRegistry()
    real_adapter = registry.get_adapter("v4_pro")
    print(f"  Adapter: {real_adapter.model_name}")

    config = load_editor_config()
    logging_adapter = LoggingWrapper(real_adapter, TARGETED_DIR)

    # ── Run targeted Phase 2 ──
    print("\n--- Running targeted Phase 2 ---")

    targeted_v2 = {}  # {(ch, agent): AgentIssueList}

    # ch2-AgentA
    print("\n  [1/2] ch2-AgentA (was stale, v1 had 0 → now has 7 issues)")
    v2_ch2_a, cost_ch2_a = await _run_agent_phase2(
        agent_id="A",
        chapter_num=2,
        adapter=logging_adapter,
        own_v1=ch2_v1["A"],
        peer_v1s=[ch2_v1["B"], ch2_v1["C"]],
        config=config,
    )
    targeted_v2[(2, "A")] = v2_ch2_a
    print(f"    Result: {len(v2_ch2_a.issues)} issues, ¥{cost_ch2_a:.4f}")

    # ch3-AgentB
    print("\n  [2/2] ch3-AgentB (was stale, v1 had 0 → now has 3 issues)")
    v2_ch3_b, cost_ch3_b = await _run_agent_phase2(
        agent_id="B",
        chapter_num=3,
        adapter=logging_adapter,
        own_v1=ch3_v1["B"],
        peer_v1s=[ch3_v1["A"], ch3_v1["C"]],
        config=config,
    )
    targeted_v2[(3, "B")] = v2_ch3_b
    print(f"    Result: {len(v2_ch3_b.issues)} issues, ¥{cost_ch3_b:.4f}")

    total_cost = logging_adapter._total_cost
    print(f"\n  Total targeted cost: ¥{total_cost:.4f} ({logging_adapter._call_count} calls)")

    # ── Build complete v2 lists and re-merge ──
    print("\n--- Re-merging with corrected data ---")

    # For non-stale agents, use existing Phase 2 captures
    # ch2: B and C existing; A from targeted re-run
    ch2_v2 = {
        "A": targeted_v2[(2, "A")],
        "B": build_v2_from_capture(2, "B"),
        "C": build_v2_from_capture(2, "C"),
    }
    ch2_merge = merge_issues(ch2_v2)

    # ch3: A and C existing; B from targeted re-run
    ch3_v2 = {
        "A": build_v2_from_capture(3, "A"),
        "B": targeted_v2[(3, "B")],
        "C": build_v2_from_capture(3, "C"),
    }
    ch3_merge = merge_issues(ch3_v2)

    # ch1: all existing (was clean)
    ch1_v2 = {
        "A": build_v2_from_capture(1, "A"),
        "B": build_v2_from_capture(1, "B"),
        "C": build_v2_from_capture(1, "C"),
    }
    ch1_merge = merge_issues(ch1_v2)

    # ── Build corrected comparison results ──
    print("\n--- Corrected results ---")
    def merge_to_dict(mr) -> dict:
        return {
            "total_issues": mr.total_issues,
            "high_issues": [
                {"type": i.type, "merged_description": i.merged_description, "voters": i.voters}
                for i in mr.high_issues
            ],
            "med_issues": [
                {"type": i.type, "merged_description": i.merged_description, "voters": i.voters}
                for i in mr.med_issues
            ],
            "low_issues": [
                {"type": i.type, "merged_description": i.merged_description, "voters": i.voters}
                for i in mr.low_issues
            ],
            "cost": mr.total_cost,
            "fallback_used": mr.fallback_used,
        }

    for ch, merge_result in [(1, ch1_merge), (2, ch2_merge), (3, ch3_merge)]:
        d = merge_to_dict(merge_result)
        h = len(d["high_issues"])
        m = len(d["med_issues"])
        l = len(d["low_issues"])
        print(f"  ch{ch}: {d['total_issues']} issues (H{h}/M{m}/L{l})")

    # Save corrected results
    corrected = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": real_adapter.model_name,
        "note": "Corrected: targeted Phase 2 re-run for ch2-A and ch3-B with fixed parser v1",
        "single": {},  # unchanged
        "multi": {
            "1": merge_to_dict(ch1_merge),
            "2": merge_to_dict(ch2_merge),
            "3": merge_to_dict(ch3_merge),
        },
        "targeted_phase2_cost": total_cost,
        "targeted_calls": [
            {"call": entry["name"], "cost": entry["cost"]}
            for entry in logging_adapter.call_log
        ],
    }
    corrected_path = OUTPUT_DIR / "comparison_results_corrected.json"
    corrected_path.write_text(
        json.dumps(corrected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  Saved: {corrected_path}")

    # Also save targeted captures manifest
    manifest = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "Targeted Phase 2 re-run for stale v1 combos",
        "stale_combos": [
            {"chapter": 2, "agent": "A", "old_v1_issues": 0, "corrected_v1_issues": len(ch2_v1["A"].issues)},
            {"chapter": 3, "agent": "B", "old_v1_issues": 0, "corrected_v1_issues": len(ch3_v1["B"].issues)},
        ],
        "total_cost": total_cost,
        "calls": [
            {"call": entry["name"], "cost": entry["cost"]}
            for entry in logging_adapter.call_log
        ],
    }
    manifest_path = TARGETED_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Captures: {TARGETED_DIR}/")
    print("  Done.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
