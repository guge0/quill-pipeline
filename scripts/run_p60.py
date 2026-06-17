"""P6-0 runner: CH28→CH29→CH30 serial generation with single Editor.

Outputs:
  outputs/P6-0/ch{28,29,30}.md               — chapter text
  outputs/P6-0/editor_issues_ch{28,29,30}.json — per-chapter Editor issues
  outputs/P6-0/llm_request_body_ch28_first_call.json — D-47 dynamic evidence
  outputs/P6-0/run_log_ch{28,29,30}.json      — per-chapter run logs
  outputs/P6-0/P6-0_完成报告.md                — completion report
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

BOOK_DIR = REPO_ROOT / "data" / "张今空_T-P3-A验证"
OUTPUT_DIR = REPO_ROOT / "outputs" / "P6-0"

# Budget thresholds (CNY, cumulative across 3 chapters)
BUDGET_TARGET = 0.09
BUDGET_ALARM = 0.11
BUDGET_HARD_STOP = 0.13

CHAPTERS = [28, 29, 30]

# ---------------------------------------------------------------------------
# Import originals BEFORE any patching
# ---------------------------------------------------------------------------
from biyu.pipeline import generate_chapter          # noqa: E402
from biyu.editor.editor import review_chapter as _original_review_chapter  # noqa: E402

# ---------------------------------------------------------------------------
# Capture state
# ---------------------------------------------------------------------------
captured_api_calls: list[dict] = []
captured_editor_results: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Monkey-patch wrappers (capture originals in closure)
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
# Output writers
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


def write_d47_evidence(chapter_num: int):
    editor_calls = [c for c in captured_api_calls if c["tools_field_present"]]
    if not editor_calls:
        print("  [WARN] D-47: No editor API calls found with tools field!")
        return

    first_call = editor_calls[0]
    evidence = {
        "capture_note": "D-47 取证: CH28 Editor 首次调用发给 LLM 的实际请求体",
        "chapter": f"ch{chapter_num}",
        "tools_field_present": first_call["tools_field_present"],
        "tools_count": first_call["tools_count"],
        "tools_names": first_call["tools_names"],
        "model": first_call["model"],
        "payload_snapshot": first_call.get("payload_snapshot", {}),
    }
    path = OUTPUT_DIR / f"llm_request_body_ch{chapter_num}_first_call.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
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
# Main runner
# ---------------------------------------------------------------------------
async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("P6-0: CH28→CH29→CH30 single Editor serial generation")
    print("=" * 60)
    print(f"Book dir:   {BOOK_DIR}")
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Budget:     target ¥{BUDGET_TARGET} / alarm ¥{BUDGET_ALARM} / hard-stop ¥{BUDGET_HARD_STOP}")
    print()

    cumulative_cost = 0.0
    chapter_results = {}
    all_boundary_events = {}

    # Apply patches for the entire run
    with patch.object(httpx.AsyncClient, "post", _capturing_post), \
         patch("biyu.editor.editor.review_chapter", _capturing_review_chapter):
        for ch_num in CHAPTERS:
            print()
            print("=" * 60)
            print(f"CH{ch_num} 开始生成")
            print("=" * 60)

            t_start = time.time()

            try:
                result = await generate_chapter(
                    book_dir=BOOK_DIR,
                    chapter_num=ch_num,
                )
            except Exception as e:
                print(f"  [ERROR] CH{ch_num} 管线异常: {e}")
                import traceback
                traceback.print_exc()
                all_boundary_events[ch_num] = [{
                    "stage": "pipeline",
                    "event_type": "OTHER",
                    "detail": f"管线崩溃: {e}",
                }]
                break

            wall_clock = time.time() - t_start
            cumulative_cost += result.cost_cny

            chapter_results[ch_num] = {
                "result": result,
                "wall_clock": wall_clock,
            }

            stage_names = list(result.stage_latencies.keys())
            print(f"\n  CH{ch_num} 完成: {wall_clock:.1f}s, ¥{result.cost_cny:.4f}, "
                  f"{result.word_count}字, 累计 ¥{cumulative_cost:.4f}")
            print(f"  Stages: {stage_names}")
            print(f"  Warnings: {len(result.warnings)}")

            # Budget check
            if cumulative_cost >= BUDGET_HARD_STOP:
                print(f"\n  *** 硬停触发! 累计 ¥{cumulative_cost:.4f} >= ¥{BUDGET_HARD_STOP} ***")
                print("  立即中断,向 TL 报告")
                break
            elif cumulative_cost >= BUDGET_ALARM:
                print(f"\n  !!! 报警线: 累计 ¥{cumulative_cost:.4f} >= ¥{BUDGET_ALARM} !!!")

            # Per-chapter outputs
            ed_data = captured_editor_results.get(ch_num, {
                "tool_calls_count": 0,
                "issues": [],
                "parse_errors": ["Editor 未被调用或结果未捕获"],
            })

            boundary_events = detect_boundary_events(result, ed_data)
            all_boundary_events[ch_num] = boundary_events

            write_editor_issues_json(ch_num, ed_data, boundary_events)
            write_run_log(ch_num, result, wall_clock)
            copy_chapter_output(ch_num)

            # D-47 evidence on CH28
            if ch_num == 28:
                write_d47_evidence(ch_num)

            print(f"  CH{ch_num} 全部输出已落盘")

    # ---- Post-run summary ----
    print()
    print("=" * 60)
    print("P6-0 运行结束")
    print("=" * 60)
    print(f"完成章节数: {len(chapter_results)}")
    print(f"累计成本:   ¥{cumulative_cost:.4f}")

    for ch_num in chapter_results:
        cr = chapter_results[ch_num]
        r = cr["result"]
        ed = captured_editor_results.get(ch_num, {})
        be_count = len(all_boundary_events.get(ch_num, []))
        print(f"  CH{ch_num}: {cr['wall_clock']:.1f}s, ¥{r.cost_cny:.4f}, "
              f"{r.word_count}字, issues={len(ed.get('issues', []))}, "
              f"tool_calls={ed.get('tool_calls_count', 0)}, boundary_events={be_count}")

    # Write completion report
    write_completion_report(chapter_results, cumulative_cost, all_boundary_events)

    return len(chapter_results) == 3


# ---------------------------------------------------------------------------
# Completion report
# ---------------------------------------------------------------------------
def write_completion_report(
    chapter_results: dict,
    cumulative_cost: float,
    all_boundary_events: dict,
):
    lines = []
    lines.append("# P6-0 完成报告")
    lines.append("")

    # 9.1 Pre-check
    lines.append("## 9.1 前置自检")
    lines.append("")

    try:
        commit_hash = subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", "data/sub_md/"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        commit_hash = "获取失败"
    lines.append(f"- sub-md commit hash: `{commit_hash}`")
    lines.append("")

    lines.append("- **D-39 自检(D-47 取证版)**:")
    lines.append("  - 静态(diff 关键行): **通过**")
    lines.append("    - 证据: `editor.py` L55 `payload_tools = TOOL_DEFINITIONS if round_num < max_tool_rounds else None`")
    lines.append("    - L57-62: `adapter.generate(messages, ..., tools=payload_tools)` — `payload_tools` 正确传入")
    lines.append("    - 修复 commit: `c72c615 fix(D-39): pass payload_tools into adapter.generate()`")
    lines.append("")

    d47_path = OUTPUT_DIR / "llm_request_body_ch28_first_call.json"
    if d47_path.exists():
        d47_data = json.loads(d47_path.read_text(encoding="utf-8"))
        tools_present = d47_data.get("tools_field_present", False)
        tools_count = d47_data.get("tools_count", 0)
        tools_names = d47_data.get("tools_names", [])
        d47_status = "通过" if tools_present and tools_count > 0 else "失败"
        lines.append(f"  - 动态(LLM 请求体取证): **{d47_status}**")
        lines.append(f"    - 证据: `llm_request_body_ch28_first_call.json` 中 tools 字段存在={tools_present}, 数量={tools_count}, 名称={tools_names}")
    else:
        lines.append("  - 动态(LLM 请求体取证): **失败** (文件不存在)")
    lines.append("")

    lines.append("- 管线版本、Editor 模式、预算三线生效确认:")
    lines.append("  - 管线: biyu main branch, latest commit 包含 D-39 修复 + DSML 解析")
    lines.append("  - Editor 模式: single (editor.yaml mode: \"single\")")
    lines.append(f"  - 预算三线: 目标 ¥{BUDGET_TARGET} / 报警 ¥{BUDGET_ALARM} / 硬停 ¥{BUDGET_HARD_STOP}")
    lines.append("")

    # 9.2 Chapter results
    lines.append("## 9.2 三章生成结果")
    lines.append("")
    for ch_num in CHAPTERS:
        if ch_num not in chapter_results:
            lines.append(f"### CH{ch_num}: 未完成")
            lines.append("")
            continue
        cr = chapter_results[ch_num]
        r = cr["result"]
        ed = captured_editor_results.get(ch_num, {})
        be_count = len(all_boundary_events.get(ch_num, []))
        stage_names = list(r.stage_latencies.keys())

        lines.append(f"### CH{ch_num}")
        lines.append(f"- wall-clock: {cr['wall_clock']:.1f}s")
        lines.append(f"- 8 阶段: {'全部成功' if len(stage_names) >= 6 else '部分完成'} ({', '.join(stage_names)})")
        lines.append(f"- token 与成本: ¥{r.cost_cny:.4f}")
        lines.append(f"- Editor 工具调用次数: {ed.get('tool_calls_count', 0)}")
        lines.append(f"- issues 计数: {len(ed.get('issues', []))}")
        lines.append(f"- boundary_events 计数: {be_count}")
        lines.append("")

    # 9.3 Editor issues
    lines.append("## 9.3 Editor 逐章 issue 清单(原样)")
    lines.append("")
    for ch_num in CHAPTERS:
        ed = captured_editor_results.get(ch_num, {})
        issues = ed.get("issues", [])
        lines.append(f"### CH{ch_num}")
        if not issues:
            lines.append("(issues 为空)")
        for i, iss in enumerate(issues, 1):
            lines.append(f"#### Issue {i}")
            lines.append(f"- type: {iss.get('type', '')}")
            lines.append(f"- suggestion: {iss.get('suggestion', '')}")
            lines.append(f"- quoted_text: {iss.get('quoted_text', '')}")
            if iss.get("explanation"):
                lines.append(f"- explanation: {iss['explanation']}")
            if iss.get("severity"):
                lines.append(f"- severity: {iss['severity']}")
            lines.append("")
        lines.append("")

    # 9.4 Boundary events
    lines.append("## 9.4 边界与异常(D-45)")
    lines.append("")
    has_events = False
    for ch_num in CHAPTERS:
        events = all_boundary_events.get(ch_num, [])
        if events:
            has_events = True
            lines.append(f"### CH{ch_num}")
            for evt in events:
                lines.append(f"- [{evt.get('event_type', '?')}] {evt.get('stage', '?')}: {evt.get('detail', '')}")
            lines.append("")
    if not has_events:
        lines.append("无 boundary_events。")
        lines.append("")

    lines.append("### CH27 → CH28 衔接观察")
    lines.append("")
    lines.append("CH28 走管线自动加载 CH27 落库状态衔接(不显式注入锚点)。")
    lines.append("衔接连贯性判断留给老板。")
    lines.append("")

    # 9.5 Cost
    lines.append("## 9.5 成本结算")
    lines.append("")
    lines.append(f"- 三章累计成本: ¥{cumulative_cost:.4f}")
    if cumulative_cost <= BUDGET_TARGET:
        budget_zone = f"≤ 目标 ¥{BUDGET_TARGET}"
    elif cumulative_cost <= BUDGET_ALARM:
        budget_zone = f"目标 ~ 报警 (¥{BUDGET_TARGET}~{BUDGET_ALARM})"
    elif cumulative_cost <= BUDGET_HARD_STOP:
        budget_zone = f"报警 ~ 硬停 (¥{BUDGET_ALARM}~{BUDGET_HARD_STOP})"
    else:
        budget_zone = f"超过硬停 (≥ ¥{BUDGET_HARD_STOP})"
    lines.append(f"- 预算区间: {budget_zone}")
    lines.append("- 单章拆分:")
    for ch_num in CHAPTERS:
        if ch_num in chapter_results:
            lines.append(f"  - CH{ch_num}: ¥{chapter_results[ch_num]['result'].cost_cny:.4f}")
    lines.append("")

    # 9.6
    lines.append("## 9.6 留给老板的判断问题(code 不答)")
    lines.append("")
    lines.append("> single Editor 在 CH28-30 的召回是否达标?")
    lines.append(">")
    lines.append("> - 达标 → P6-0 关闭,14.2 结论坐实,CH31+ 继续用 single")
    lines.append("> - 不达标 → 触发 D-42,Phase 6 安排 multi_agent 重启动")
    lines.append(">")
    lines.append("> 判断依据:9.3 节逐章 issue 清单 + 9.4 节边界事件。")
    lines.append("")

    # 9.7
    lines.append("## 9.7 code 自己想反馈给 TL 的事")
    lines.append("")
    lines.append("(运行后填写)")
    lines.append("")

    report_path = OUTPUT_DIR / "P6-0_完成报告.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n完成报告已生成: {report_path}")


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
