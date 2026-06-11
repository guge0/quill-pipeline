"""P6-1A Step 4b: Run multi_agent Editor on the already-saved CH28 text.

Writer already completed (CNY0.2214, 6775 chars).
This only runs the Editor stage.

Output:
  outputs/P6-1A/editor_issues_ch28_new.json
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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    from biyu.config import get_registry
    from biyu.editor.multi_agent import review_chapter_multi_agent

    # Load Writer output
    ch28_path = OUTPUT_DIR / "ch28_new.md"
    ch28_text = ch28_path.read_text(encoding="utf-8")
    print(f"CH28 text: {len(ch28_text)} chars")

    # Prev tail for editor
    prev_tail = ""
    prev_ch = BOOK_DIR / "chapters" / "ch27.md"
    if prev_ch.exists():
        prev_tail = prev_ch.read_text(encoding="utf-8")[-500:]
    print(f"Prev tail: {len(prev_tail)} chars")

    registry = get_registry()
    editor_adapter = registry.get_adapter_for_stage("writer")
    print(f"Editor adapter: {editor_adapter.model_name}")
    print()

    captured_bodies = []
    async def capturing_post(self, url, **kwargs):
        body = kwargs.get("json")
        if body is not None:
            captured_bodies.append({"url": str(url), "payload": body})
        return await _original_post(self, url, **kwargs)

    print("[Editor] Running multi_agent (A/B/C)...")
    t0 = time.time()

    with patch.object(httpx.AsyncClient, "post", capturing_post):
        merge_result = await review_chapter_multi_agent(
            chapter_num=28,
            chapter_text=ch28_text,
            book_dir=BOOK_DIR,
            adapter=editor_adapter,
            prev_chapter_tail=prev_tail,
        )

    elapsed = time.time() - t0
    print(f"[Editor] Done: {elapsed:.1f}s, CNY{merge_result.total_cost:.4f}")
    print(f"[Editor] Issues: {merge_result.total_issues} total, "
          f"{len(merge_result.high_issues)} high severity")
    if merge_result.fallback_used:
        print(f"[Editor] Fallback used")

    # Budget
    architect_total = 0.32
    writer_cost = 0.2214
    editor_cost = merge_result.total_cost
    grand_total = architect_total + writer_cost + editor_cost
    print(f"\n[Budget] Architect: CNY{architect_total:.4f}")
    print(f"[Budget] Writer:    CNY{writer_cost:.4f}")
    print(f"[Budget] Editor:    CNY{editor_cost:.4f}")
    print(f"[Budget] TOTAL:     CNY{grand_total:.4f} (alarm=0.65, hard_stop=0.90)")

    # Save editor issues
    editor_issues = {
        "chapter": "ch28",
        "mode": "multi_agent",
        "total_issues": merge_result.total_issues,
        "high_severity_count": len(merge_result.high_issues),
        "fallback_used": merge_result.fallback_used,
        "editor_cost_cny": round(editor_cost, 4),
        "issues": [],
    }
    for issue in merge_result.all_issues:
        editor_issues["issues"].append({
            "agent": getattr(issue, "agent", "unknown"),
            "type": issue.type,
            "severity": issue.severity,
            "description": issue.description,
            "suggestion": issue.suggestion,
        })

    ed_path = OUTPUT_DIR / "editor_issues_ch28_new.json"
    with open(ed_path, "w", encoding="utf-8") as f:
        json.dump(editor_issues, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {ed_path}")

    # Print issues summary
    print(f"\n{'=' * 50}")
    print("EDITOR ISSUES SUMMARY:")
    for issue in editor_issues["issues"]:
        print(f"  [{issue['agent']}] [{issue['severity']}] {issue['type']}: {issue['description'][:80]}")

    # Update run log
    import json as _json
    log_path = OUTPUT_DIR / "run_log_ch28_new.json"
    if log_path.exists():
        run_log = _json.loads(log_path.read_text(encoding="utf-8"))
    else:
        run_log = {"stages": [], "boundary_events": []}

    run_log["stages"].append({
        "stage": "editor_multi_agent",
        "elapsed_s": round(elapsed, 1),
        "cost_cny": round(editor_cost, 4),
        "total_issues": merge_result.total_issues,
        "high_severity_issues": len(merge_result.high_issues),
        "fallback_used": merge_result.fallback_used,
    })
    run_log["total_cost"] = round(grand_total, 4)
    if merge_result.fallback_used:
        run_log["boundary_events"].append("editor_fallback_used")

    log_path.write_text(_json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated: {log_path}")

    return True


if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
