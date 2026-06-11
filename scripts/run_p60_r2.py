"""P6-0 runner (round 2): CH29→CH30 only. CH28 already done.

Budget adjusted: target ¥0.50 / alarm ¥0.60 / hard-stop ¥0.80 (per actual ~¥0.25/chapter).
Outputs saved BEFORE budget check (bug fix from round 1).
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

BOOK_DIR = REPO_ROOT / "data" / "EXAMPLE_PROTAGONIST_T-P3-A验证"
OUTPUT_DIR = REPO_ROOT / "outputs" / "P6-0"

# Adjusted budget (CH28 already cost ¥0.2533, running CH29+CH30)
BUDGET_TARGET = 0.50
BUDGET_ALARM = 0.60
BUDGET_HARD_STOP = 0.80

CHAPTERS = [29, 30]

# ---------------------------------------------------------------------------
from biyu.pipeline import generate_chapter          # noqa: E402
from biyu.editor.editor import review_chapter as _original_review_chapter  # noqa: E402

# ---------------------------------------------------------------------------
captured_api_calls: list[dict] = []
captured_editor_results: dict[int, dict] = {}

# ---------------------------------------------------------------------------
_original_post = httpx.AsyncClient.post


async def _capturing_post(self, url, **kwargs):
    body = kwargs.get("json")
    if body is not None:
        captured_api_calls.append({
            "url": str(url),
            "payload_keys": list(body.keys()),
            "model": body.get("model"),
            "tools_field_present": "tools" in body,
            "tools_count": len(body.get("tools", [])),
            "tools_names": [
                t.get("function", {}).get("name", "?")
                for t in body.get("tools", [])
            ],
            "messages_count": len(body.get("messages", [])),
            "timestamp": time.time(),
            "payload_snapshot": {
                k: v for k, v in body.items()
                if k != "messages"
            },
        })
    return await _original_post(self, url, **kwargs)


async def _capturing_review_chapter(chapter_num, chapter_text, book_dir, adapter, **kwargs):
    result = await _original_review_chapter(
        chapter_num, chapter_text, book_dir, adapter, **kwargs
    )
    captured_editor_results[chapter_num] = {
        "tool_calls_count": len(result.queries_used),
        "queries_used": result.queries_used,
        "issues": [
            {
                "type": issue.type,
                "suggestion": issue.fix_suggestion,
                "quoted_text": issue.quoted_text or issue.quote,
                "explanation": issue.explanation,
                "severity": issue.severity,
                "auto_fixable": issue.auto_fixable,
                "line": issue.line,
                "subtype": issue.subtype,
            }
            for issue in result.issues
        ],
        "parse_errors": result.parse_errors,
        "confidence": result.confidence,
        "raw_response_length": len(result.raw_response) if result.raw_response else 0,
    }
    return result


# ---------------------------------------------------------------------------
def write_editor_issues_json(chapter_num: int, ed_data: dict, boundary_events: list[dict]):
    output = {
        "chapter": f"ch{chapter_num}",
        "editor_mode": "single",
        "tool_calls_count": ed_data.get("tool_calls_count", 0),
        "issues": ed_data.get("issues", []),
        "boundary_events": boundary_events,
    }
    path = OUTPUT_DIR / f"editor_issues_ch{chapter_num}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  [output] {path.name}")


def write_run_log(chapter_num: int, result, wall_clock: float):
    stage_names = list(result.stage_latencies.keys())
    log = {
        "chapter": chapter_num,
        "wall_clock_seconds": round(wall_clock, 1),
        "cost_cny": round(result.cost_cny, 4),
        "word_count": result.word_count,
        "stage_latencies": result.stage_latencies,
        "warnings": result.warnings,
        "stages_completed": stage_names,
        "pending": any(
            "BLOCK" in w or "Editor 标记需审查" in w
            for w in result.warnings
        ),
    }
    path = OUTPUT_DIR / f"run_log_ch{chapter_num}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"  [output] {path.name}")


def copy_chapter_output(chapter_num: int):
    src = BOOK_DIR / "chapters" / f"ch{chapter_num}.md"
    if not src.exists():
        src = BOOK_DIR / "chapters" / "_pending" / f"ch{chapter_num}.md"
    if src.exists():
        dst = OUTPUT_DIR / f"ch{chapter_num}.md"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  [output] ch{chapter_num}.md ({src.parent.name}/)")
    else:
        print(f"  [WARN] ch{chapter_num}.md not found in chapters/")


def detect_boundary_events(result, ed_data: dict) -> list[dict]:
    events = []
    for w in result.warnings:
        evt_type = "OTHER"
        w_upper = w.upper()
        if "TIMEOUT" in w_upper:
            evt_type = "TIMEOUT"
        elif "PARSE_ERROR" in w_upper or "解析" in w:
            evt_type = "PARSE_ERROR"
        elif "空" in w and "返回" in w:
            evt_type = "EMPTY_RESPONSE"
        elif "失败" in w or "FAIL" in w_upper:
            evt_type = "TOOL_CALL_FAILED"
        events.append({"stage": "unknown", "event_type": evt_type, "detail": w})
    for pe in ed_data.get("parse_errors", []):
        events.append({
            "stage": "editor",
            "event_type": "PARSE_ERROR" if "JSON" in pe else "OTHER",
            "detail": pe,
        })
    return events


# ---------------------------------------------------------------------------
async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("P6-0 round 2: CH29->CH30 (CH28 already done)")
    print("=" * 60)
    print(f"Budget: target {BUDGET_TARGET} / alarm {BUDGET_ALARM} / hard-stop {BUDGET_HARD_STOP}")
    print()

    cumulative_cost = 0.0
    chapter_results = {}
    all_boundary_events = {}

    with patch.object(httpx.AsyncClient, "post", _capturing_post), \
         patch("biyu.editor.editor.review_chapter", _capturing_review_chapter):
        for ch_num in CHAPTERS:
            print()
            print("=" * 60)
            print(f"CH{ch_num} start")
            print("=" * 60)

            t_start = time.time()

            try:
                result = await generate_chapter(
                    book_dir=BOOK_DIR,
                    chapter_num=ch_num,
                )
            except Exception as e:
                print(f"  [ERROR] CH{ch_num} pipeline error: {e}")
                import traceback
                traceback.print_exc()
                all_boundary_events[ch_num] = [{
                    "stage": "pipeline",
                    "event_type": "OTHER",
                    "detail": f"pipeline crash: {e}",
                }]
                break

            wall_clock = time.time() - t_start
            cumulative_cost += result.cost_cny

            chapter_results[ch_num] = {
                "result": result,
                "wall_clock": wall_clock,
            }

            stage_names = list(result.stage_latencies.keys())
            print(f"\n  CH{ch_num} done: {wall_clock:.1f}s, {result.cost_cny:.4f} CNY, "
                  f"{result.word_count} chars, cumulative {cumulative_cost:.4f}")
            print(f"  Stages: {stage_names}")
            print(f"  Warnings: {len(result.warnings)}")

            # ---- SAVE OUTPUTS FIRST (bug fix from round 1) ----
            ed_data = captured_editor_results.get(ch_num, {
                "tool_calls_count": 0,
                "issues": [],
                "parse_errors": ["Editor not called or result not captured"],
            })

            boundary_events = detect_boundary_events(result, ed_data)
            all_boundary_events[ch_num] = boundary_events

            write_editor_issues_json(ch_num, ed_data, boundary_events)
            write_run_log(ch_num, result, wall_clock)
            copy_chapter_output(ch_num)
            print(f"  CH{ch_num} outputs saved")

            # Budget check AFTER saving
            if cumulative_cost >= BUDGET_HARD_STOP:
                print(f"\n  *** HARD STOP: cumulative {cumulative_cost:.4f} >= {BUDGET_HARD_STOP} ***")
                break
            elif cumulative_cost >= BUDGET_ALARM:
                print(f"\n  !!! ALARM: cumulative {cumulative_cost:.4f} >= {BUDGET_ALARM} !!!")

    # ---- Summary ----
    print()
    print("=" * 60)
    print("P6-0 round 2 done")
    print("=" * 60)
    print(f"Chapters completed: {len(chapter_results)}")
    print(f"Cumulative cost (CH29+CH30): {cumulative_cost:.4f} CNY")

    for ch_num in chapter_results:
        cr = chapter_results[ch_num]
        r = cr["result"]
        ed = captured_editor_results.get(ch_num, {})
        be_count = len(all_boundary_events.get(ch_num, []))
        print(f"  CH{ch_num}: {cr['wall_clock']:.1f}s, {r.cost_cny:.4f} CNY, "
              f"{r.word_count} chars, issues={len(ed.get('issues', []))}, "
              f"tool_calls={ed.get('tool_calls_count', 0)}, boundary_events={be_count}")

    # Write round 2 summary (final report will be assembled separately)
    summary = {
        "round": 2,
        "chapters": CHAPTERS,
        "completed": list(chapter_results.keys()),
        "cumulative_cost_ch29_ch30": cumulative_cost,
        "per_chapter": {
            str(ch_num): {
                "wall_clock": chapter_results[ch_num]["wall_clock"],
                "cost_cny": chapter_results[ch_num]["result"].cost_cny,
                "word_count": chapter_results[ch_num]["result"].word_count,
                "stages": list(chapter_results[ch_num]["result"].stage_latencies.keys()),
                "warnings": chapter_results[ch_num]["result"].warnings,
                "editor_tool_calls": captured_editor_results.get(ch_num, {}).get("tool_calls_count", 0),
                "editor_issues_count": len(captured_editor_results.get(ch_num, {}).get("issues", [])),
                "boundary_events_count": len(all_boundary_events.get(ch_num, [])),
            }
            for ch_num in chapter_results
        },
        "editor_results": {str(k): v for k, v in captured_editor_results.items()},
        "boundary_events": {str(k): v for k, v in all_boundary_events.items()},
    }

    summary_path = OUTPUT_DIR / "round2_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nRound 2 summary saved: {summary_path}")

    return len(chapter_results) == len(CHAPTERS)


if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
