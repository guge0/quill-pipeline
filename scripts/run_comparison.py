"""P6-13-D Step 4: real LLM comparison (single vs multi_agent).

Reads seeded chapters, uses clean chapters as cross-chapter reference.
Saves all request/response pairs for D-47 proof.

Usage: cd biyu && python -m scripts.run_comparison
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────

BIYU_ROOT = Path(__file__).parents[1]
BOOK_DIR = BIYU_ROOT / "eval_set_v0" / "test_book"
SEEDED_DIR = BIYU_ROOT / "eval_set_v0" / "baseline"
CLEAN_DIR = BIYU_ROOT / "eval_set_v0" / "baseline"
OUTPUT_DIR = BIYU_ROOT / "eval_set_v0" / "comparison_results"
EDITOR_YAML = BIYU_ROOT / "config" / "editor.yaml"


def load_clean(num: int) -> str:
    return (CLEAN_DIR / f"T{num}_clean.md").read_text(encoding="utf-8")


def load_seeded(num: int) -> str:
    return (SEEDED_DIR / f"T{num}_seeded.md").read_text(encoding="utf-8")


def prev_tail_clean(num: int) -> str:
    if num <= 1:
        return ""
    return load_clean(num - 1)[-500:]


# ── Logging Adapter (captures request/response for D-47) ──────────

class LoggingAdapter:
    """Wraps a real adapter, logging every generate() call."""

    def __init__(self, real_adapter, log_dir: Path, label: str):
        self._inner = real_adapter
        self._log_dir = log_dir
        self._label = label
        self._call_idx = 0
        self.call_log: list[dict] = []

    async def generate(self, messages, **kwargs):
        self._call_idx += 1
        call_id = f"{self._label}_call{self._call_idx:03d}"

        # Capture request
        request_data = {
            "call_id": call_id,
            "label": self._label,
            "messages_count": len(messages),
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
            "has_tools": kwargs.get("tools") is not None,
            "messages": messages,
            "kwargs_keys": list(kwargs.keys()),
        }

        # Call real adapter
        t0 = time.time()
        try:
            resp = await self._inner.generate(messages, **kwargs)
        except Exception as exc:
            # Log error and re-raise
            error_data = {
                **request_data,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": time.time() - t0,
            }
            self.call_log.append(error_data)
            self._save_call(call_id, error_data)
            raise

        elapsed = time.time() - t0

        # Capture response
        response_data = {
            **request_data,
            "elapsed_s": round(elapsed, 3),
            "response_text_preview": resp.text[:500] if resp.text else "",
            "cost": resp.cost,
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
            "finish_reason": resp.finish_reason,
            "has_reasoning": bool(resp.reasoning_content),
            "has_tool_calls_in_raw": bool(
                resp.raw and resp.raw.get("choices", [{}])[0].get("message", {}).get("tool_calls")
            ),
            "raw": resp.raw,
        }
        self.call_log.append(response_data)
        self._save_call(call_id, {"request": request_data, "response": response_data})
        return resp

    def _save_call(self, call_id: str, data: dict):
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"{call_id}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # Delegate attribute access to inner adapter
    def __getattr__(self, name):
        return getattr(self._inner, name)


# ── Single mode ────────────────────────────────────────────────────

async def run_single(logging_adapter: LoggingAdapter) -> dict:
    """Run single mode on 3 seeded chapters."""
    from biyu.editor.editor import review_chapter

    results = {}
    for ch in (1, 2, 3):
        text = load_seeded(ch)
        tail = prev_tail_clean(ch)
        print(f"  [single] ch{ch}: text={len(text)} chars, tail={len(tail)} chars")

        result = await review_chapter(
            chapter_num=ch,
            chapter_text=text,
            book_dir=BOOK_DIR,
            adapter=logging_adapter,
            prev_chapter_tail=tail,
        )

        results[ch] = {
            "issues": [
                {
                    "line": iss.line,
                    "quote": iss.quote,
                    "type": iss.type,
                    "explanation": iss.explanation,
                    "fix_suggestion": iss.fix_suggestion,
                    "severity": iss.severity,
                    "auto_fixable": iss.auto_fixable,
                }
                for iss in result.issues
            ],
            "cost": result.cost,
            "queries_used": result.queries_used,
        }
        print(f"    -> {len(result.issues)} issues, CNY {result.cost:.4f}")

    return results


# ── Multi-agent mode ───────────────────────────────────────────────

async def run_multi(logging_adapter: LoggingAdapter) -> dict:
    """Run multi_agent mode on 3 seeded chapters (fallback disabled)."""
    from biyu.editor.multi_agent import review_chapter_multi_agent, clear_config_cache
    import yaml

    # Temporarily modify editor.yaml: disable fallback, set mode
    orig_config = EDITOR_YAML.read_text(encoding="utf-8")
    new_config = yaml.safe_load(orig_config)
    new_config["mode"] = "multi_agent"
    new_config["fallback_on_budget_exceed"] = False
    EDITOR_YAML.write_text(
        yaml.dump(new_config, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    clear_config_cache()

    results = {}
    try:
        for ch in (1, 2, 3):
            text = load_seeded(ch)
            tail = prev_tail_clean(ch)
            print(f"  [multi] ch{ch}: text={len(text)} chars, tail={len(tail)} chars")

            merge_result = await review_chapter_multi_agent(
                chapter_num=ch,
                chapter_text=text,
                book_dir=BOOK_DIR,
                adapter=logging_adapter,
                prev_chapter_tail=tail,
            )

            results[ch] = {
                "total_issues": merge_result.total_issues,
                "high_issues": [
                    {"type": iss.type, "merged_description": iss.merged_description, "voters": iss.voters}
                    for iss in merge_result.high_issues
                ],
                "med_issues": [
                    {"type": iss.type, "merged_description": iss.merged_description, "voters": iss.voters}
                    for iss in merge_result.med_issues
                ],
                "low_issues": [
                    {"type": iss.type, "merged_description": iss.merged_description, "voters": iss.voters}
                    for iss in merge_result.low_issues
                ],
                "cost": merge_result.total_cost,
                "fallback_used": merge_result.fallback_used,
            }
            print(
                f"    -> {merge_result.total_issues} issues "
                f"(H{len(merge_result.high_issues)}/M{len(merge_result.med_issues)}/L{len(merge_result.low_issues)}), "
                f"CNY {merge_result.total_cost:.4f}, fallback={merge_result.fallback_used}"
            )
    finally:
        # Restore original config
        EDITOR_YAML.write_text(orig_config, encoding="utf-8")
        clear_config_cache()

    return results


# ── Main ───────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("P6-13-D Step 4: real LLM comparison")
    print("=" * 60)

    # Setup output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create real adapter via registry
    from biyu.llm import ModelRegistry
    registry = ModelRegistry()
    real_adapter = registry.get_adapter("v4_pro")
    print(f"\nModel: {real_adapter.model_name}")

    # Verify wiring: clean chapters in test_book
    for ch in (1, 2, 3):
        clean = load_clean(ch)
        seeded = load_seeded(ch)
        print(f"  ch{ch}: clean={len(clean)} chars, seeded={len(seeded)} chars, diff={len(seeded)-len(clean)}")

    # ── Single mode ──
    import os
    skip_single = os.environ.get("SKIP_SINGLE") == "1"
    d47_prefix = os.environ.get("D47_PREFIX", "d47_")
    single_results = {}
    single_adapter = None
    dt_single = 0.0
    if skip_single:
        print("\n--- Single mode: SKIPPED (SKIP_SINGLE=1) ---")
    else:
        print("\n--- Single mode ---")
        single_adapter = LoggingAdapter(real_adapter, OUTPUT_DIR / f"{d47_prefix}single", "single")
        t0 = time.time()
        single_results = await run_single(single_adapter)
        dt_single = time.time() - t0
        print(f"  Total: {dt_single:.1f}s, {len(single_adapter.call_log)} LLM calls")

    # ── Multi-agent mode ──
    print("\n--- Multi-agent mode ---")
    multi_adapter = LoggingAdapter(real_adapter, OUTPUT_DIR / f"{d47_prefix}multi", "multi")
    t0 = time.time()
    multi_results = await run_multi(multi_adapter)
    dt_multi = time.time() - t0
    print(f"  Total: {dt_multi:.1f}s, {len(multi_adapter.call_log)} LLM calls")

    # ── Save combined results ──
    combined = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": real_adapter.model_name,
        "single": single_results,
        "multi": multi_results,
        "timing": {
            "single_s": round(dt_single, 1),
            "multi_s": round(dt_multi, 1),
        },
        "single_call_count": len(single_adapter.call_log) if single_adapter else 0,
        "multi_call_count": len(multi_adapter.call_log),
        "single_total_cost": sum(r["cost"] for r in single_results.values()) if single_results else 0,
        "multi_total_cost": sum(r["cost"] for r in multi_results.values()),
    }

    results_path = OUTPUT_DIR / "comparison_results.json"
    results_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to: {results_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for mode_name, results in [("single", single_results), ("multi", multi_results)]:
        total_issues = sum(
            r.get("issues", r.get("total_issues", 0)) and len(r.get("issues", [])) or r.get("total_issues", 0)
            for r in results.values()
        )
        total_cost = sum(r["cost"] for r in results.values())
        print(f"  {mode_name}: total_flags={total_issues}, cost=CNY {total_cost:.4f}")

    # D-47 proof summary
    print("\nD-47 proof:")
    if single_adapter:
        print(f"  Single: {len(single_adapter.call_log)} calls saved in {OUTPUT_DIR / f'{d47_prefix}single'}")
    else:
        print(f"  Single: SKIPPED (existing captures in {OUTPUT_DIR / f'{d47_prefix}single'})")
    print(f"  Multi:  {len(multi_adapter.call_log)} calls saved in {OUTPUT_DIR / f'{d47_prefix}multi'}")

    # Verify multi ran full 3 agents x 2 phases
    multi_calls = multi_adapter.call_log
    phase1_count = sum(1 for c in multi_calls if c.get("has_tools"))
    phase2_count = sum(1 for c in multi_calls if not c.get("has_tools"))
    print(f"  Multi breakdown: {phase1_count} with-tools (Phase 1), {phase2_count} no-tools (Phase 2)")
    expected_phase1 = 9  # 3 agents x 3 chapters
    expected_phase2 = 9  # 3 agents x 3 chapters
    if phase1_count >= expected_phase1 and phase2_count >= expected_phase2:
        print(f"  [OK] Full 3 agents x 2 phases confirmed ({phase1_count}+{phase2_count} >= {expected_phase1}+{expected_phase2})")
    else:
        print(f"  [WARNING] Expected >= {expected_phase1}+{expected_phase2}, got {phase1_count}+{phase2_count}")

    # Check for fallback
    any_fallback = any(r.get("fallback_used") for r in multi_results.values())
    print(f"  Fallback triggered: {any_fallback}")
    if any_fallback:
        print("  [WARNING] Fallback was triggered! Results may be incomplete.")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
